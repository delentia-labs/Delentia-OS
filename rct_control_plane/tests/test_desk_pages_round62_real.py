"""
Round 62: the owner's Desk pages for hooks, the skill curator, memory suggestions and trajectories - and the weekly curator report in the daemon.

Real FastAPI app with the Desk's kernel swapped for a temp store, real approvals and signatures, real SQLite skill library, real files on disk.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from rct_control_plane import approvals, desk_api, memory_nudge, trajectories
from rct_control_plane.api import create_app
from rct_control_plane.autonomous_scheduler import AutonomousScheduler
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary

GUARD = '''def pre_tool_call(tool_name, args):
    if "secret" in str(args):
        return {"action": "block", "reason": "names a secret"}
    return None
'''


class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def desk(tmp_path, monkeypatch):
    for name in ("DELENTIA_API_TOKEN", approvals.APPROVERS_ENV, memory_nudge.ENV, trajectories.ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    path = tmp_path / "keys" / "owner.pem"
    public = approvals.generate_approver_key(str(path))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    with TestClient(create_app()) as client:
        yield client, persistence, str(path), tmp_path


def sign(persistence, approval_id, key_path):
    store = approvals.PendingActionStore(persistence)
    record = store.get(approval_id)
    signed = approvals.sign_decision(key_path, approval_id, record.action_sha256, "APPROVED")
    store.decide(approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])


class TestHooksPage:
    def test_propose_request_sign_activate_disable(self, desk):
        client, persistence, key, _ = desk
        assert client.get("/v1/desk/hooks").json()["hooks"] == []
        proposed = client.post("/v1/desk/hooks/propose", json={"name": "no_secrets", "code": GUARD, "description": "refuse anything naming a secret"})
        assert proposed.status_code == 200 and proposed.json()["status"] == "PROPOSED"
        detail = client.get("/v1/desk/hooks/no_secrets").json()
        assert "names a secret" in detail["code"] and detail["status"] == "PROPOSED"
        requested = client.post("/v1/desk/hooks/no_secrets/request")
        assert requested.status_code == 200 and "delentia approvals approve" in requested.json()["how"]
        approval_id = requested.json()["approval_id"]
        assert client.post("/v1/desk/hooks/activate", json={"approval_id": approval_id}).status_code == 403          # nothing runs before a signature
        sign(persistence, approval_id, key)
        activated = client.post("/v1/desk/hooks/activate", json={"approval_id": approval_id})
        assert activated.status_code == 200
        listed = client.get("/v1/desk/hooks").json()
        assert listed["hooks"][0]["status"] == "ACTIVE" and listed["hooks"][0]["approval"]["status"] == "EXECUTED" and "pre_tool_call" in listed["limits"]["points"]
        assert client.post("/v1/desk/hooks/no_secrets/disable").status_code == 200
        assert client.get("/v1/desk/hooks").json()["hooks"][0]["status"] == "DISABLED"
        assert client.post("/v1/desk/hooks/no_secrets/disable").status_code == 404

    def test_code_that_breaks_the_rules_is_rejected_and_cannot_be_requested(self, desk):
        client, *_ = desk
        out = client.post("/v1/desk/hooks/propose", json={"name": "sneaky", "code": "import os\n\ndef pre_tool_call(t, a):\n    return None\n"})
        assert out.status_code == 200 and out.json()["status"] == "REJECTED"
        assert client.post("/v1/desk/hooks/sneaky/request").status_code == 400
        assert client.post("/v1/desk/hooks/propose", json={"name": "Bad Name", "code": GUARD}).status_code == 400
        assert client.get("/v1/desk/hooks/ghost").status_code == 404


def add_skill(library, problem, uses=0, successes=0, solution=("step one", "step two")):
    import uuid
    from datetime import datetime, timezone
    from rct_control_plane.skill_library import _tokenize
    sid = "sk-" + uuid.uuid4().hex[:6]
    with sqlite3.connect(library.db_path) as conn:
        conn.execute("INSERT INTO skills (id, problem_statement, solution, keywords, delta, resilience, g_before, g_after, growth_ratio, governance_violation, created_at, session_id, "
                     "uses, successes, failures, reinforced, archived) VALUES (?, ?, ?, ?, 0.1, 0.5, 1.0, 1.1, 1.1, 0, ?, NULL, ?, ?, ?, 1, 0)",
                     (sid, problem, json.dumps(list(solution)), json.dumps(sorted(set(_tokenize(problem)))), datetime.now(timezone.utc).isoformat(), uses, successes, uses - successes))
    return sid


class TestCuratorPage:
    def test_review_apply_and_unarchive(self, desk):
        client, *_ = desk
        library = SkillLibrary()
        weak = add_skill(library, "deploy the staging service", uses=4, successes=0)
        add_skill(library, "summarise the weekly report", uses=4, successes=4)
        state = client.get("/v1/desk/curator").json()
        assert [p["id"] for p in state["proposals"]] == [weak] and state["archived"] == []
        applied = client.post("/v1/desk/curator/apply", json={}).json()
        assert [p["id"] for p in applied["archived"]] == [weak]
        after = client.get("/v1/desk/curator").json()
        assert [a["id"] for a in after["archived"]] == [weak] and after["archived"][0]["solution"] is None and after["proposals"] == []
        assert client.post(f"/v1/desk/curator/skills/{weak}/unarchive").status_code == 200
        assert client.post(f"/v1/desk/curator/skills/{weak}/unarchive").status_code == 404
        assert client.get("/v1/desk/curator").json()["archived"] == []


class TestSuggestionsPage:
    def test_the_owner_sees_and_can_dismiss_but_cannot_keep_for_someone(self, desk, monkeypatch):
        client, persistence, *_ = desk
        monkeypatch.setenv(memory_nudge.ENV, "1")
        made = memory_nudge.MemoryCandidates(persistence).propose_from_goal("telegram-42", "I live in Oslo")
        state = client.get("/v1/desk/suggestions").json()
        assert state["enabled"] is True and state["suggestions"][0]["id"] == made[0]["id"] and state["suggestions"][0]["namespace"] == "telegram-42"
        assert client.post(f"/v1/desk/suggestions/{made[0]['id']}/dismiss").status_code == 200
        assert client.get("/v1/desk/suggestions").json()["suggestions"] == [] and persistence.list_memories("telegram-42") == []
        assert client.post(f"/v1/desk/suggestions/{made[0]['id']}/dismiss").status_code == 404
        assert client.get("/v1/desk/suggestions", params={"status": "bogus"}).status_code == 400
        assert client.get("/v1/desk/suggestions", params={"status": "dismissed"}).json()["suggestions"][0]["status"] == "dismissed"


class TestTrajectoriesPage:
    def test_off_by_default_and_shows_what_was_recorded(self, desk, monkeypatch):
        client, *_ = desk
        off = client.get("/v1/desk/trajectories").json()
        assert off["recording"] is False and off["stats"]["episodes"] == 0 and "DELENTIA_RECORD_TRAJECTORIES" in off["how"]
        monkeypatch.setenv(trajectories.ENV, "1")
        trajectories.record({"goal": "Read notes.txt", "final_answer": "ok", "stopped_reason": "llm_finished", "iterations": 1,
                             "steps": [{"tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "notes.txt"}, "tool_result": {"content": "key api_key=abcDEF1234567"}}],
                             "intent_verification": {"aligned_with_intent": True}, "taint": {"tainted": False}}, "telegram-42", "m")
        on = client.get("/v1/desk/trajectories").json()
        assert on["recording"] is True and on["stats"]["episodes"] == 1
        row = on["recent"][0]
        assert row["tools"] == ["delentia_read_repo_file"] and row["verified"] is True and row["person"].startswith("p-") and "abcDEF1234567" not in json.dumps(on)


class TestWeeklyCuratorReport:
    def test_it_reports_and_archives_nothing(self, desk):
        client, persistence, *_ = desk
        library = SkillLibrary()
        weak = add_skill(library, "deploy the staging service", uses=4, successes=0)
        scheduler = AutonomousScheduler(kernel=_Kernel(persistence))
        task = next(t for t in scheduler.list_tasks() if t["name"] == "skill_curator_report")
        assert task["interval_seconds"] == 604800 and task["is_enabled"] is True
        result = scheduler.trigger_task("task_skill_curator_report")
        assert result["status"] == "SUCCESS" and "nothing archived" in result["output"]
        assert library.get_skill(weak).archived is False
        with persistence._connect() as conn:
            row = conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'skill_curator' AND action = 'report'").fetchone()
        report = json.loads(row[0])
        assert report["counts"] == {"weak": 1} and "deploy" not in row[0]

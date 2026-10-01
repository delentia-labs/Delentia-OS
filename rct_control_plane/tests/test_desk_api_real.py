"""
Round 50: /v1/desk/* - the endpoints behind the redesigned Desk GUI. Real
FastAPI app, real SQLite (a temporary persistence swapped in for the shared
kernel's), real governed episodes (scripted model, faked MCP) so the Sessions
page is reconstructed from genuine audit rows. Nothing here is mocked data.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio

import pytest
from fastapi.testclient import TestClient

import rct_control_plane.autonomous_loop as autonomous_loop_module
import rct_control_plane.desk_api as desk_api
from rct_control_plane.api import create_app
from rct_control_plane.desk_agent_stream import agent_events
from rct_control_plane.persistence import ControlPlanePersistence
from test_governed_autonomous_loop_real import _FakeMCP, _loop

RECALL = {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "notes"}, "reasoning": "look it up"}
WRITE = {"action": "call_tool", "tool_name": "delentia_write_repo_file",
         "tool_args": {"relative_path": "docs/x.md", "content_text": "hi"}, "reasoning": "write it"}


def _script(monkeypatch, decisions):
    calls = {"n": 0}

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        i = calls["n"]
        calls["n"] += 1
        if i < len(decisions):
            return dict(decisions[i])
        return {"action": "finish", "reasoning": "done", "final_answer": f"Completed the goal: {goal}",
                "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)


class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def desk(tmp_path, monkeypatch):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
    from rct_control_plane.skill_library import SkillLibrary
    skills = SkillLibrary(db_path=str(tmp_path / "skills.db"))
    monkeypatch.setattr(desk_api, "_skills", lambda: skills)
    with TestClient(create_app()) as client:
        yield client, persistence, tmp_path


def _run_episode(tmp_path, persistence, monkeypatch, goal, decisions, name):
    _script(monkeypatch, decisions)
    loop = _loop(tmp_path, name, mcp=_FakeMCP())
    loop._persistence = persistence  # write into the persistence the Desk reads
    return asyncio.run(loop.run(goal))


def test_sessions_are_rebuilt_from_real_audit_rows(desk, monkeypatch):
    client, persistence, tmp_path = desk
    _run_episode(tmp_path, persistence, monkeypatch, "find my release notes", [RECALL], "desk-a")
    _run_episode(tmp_path, persistence, monkeypatch, "write a note", [WRITE], "desk-b")
    listed = client.get("/v1/desk/sessions").json()["sessions"]
    assert [s["namespace"] for s in listed] == ["desk-b", "desk-a"]
    a = listed[1]
    assert a["goal"] == "find my release notes" and a["stopped_reason"] == "llm_finished"
    assert a["route"] in ("fast", "slow") and a["guard"] == "clean" and 0 <= a["goal_F"] <= 1
    assert listed[0]["stopped_reason"] == "pending_approval" and listed[0]["approval_id"]

    detail = client.get(f"/v1/desk/sessions/{a['id']}").json()
    kinds = [e["type"] for e in detail["events"]]
    assert "autonomous_loop_step" in kinds
    assert detail["rct7_steps"] and detail["jitna"]["content_hash"]
    assert client.get("/v1/desk/sessions/999999").status_code == 404


def test_tools_are_classified_by_gate(desk):
    client, _, _ = desk
    data = client.get("/v1/desk/tools").json()
    by_name = {t["name"]: t["gate"] for t in data["tools"]}
    assert data["count"] >= 30
    assert by_name["delentia_write_repo_file"] == "approval"
    assert by_name["delentia_run_sandboxed_command"] == "fdia"
    assert by_name["delentia_recall"] == "open"


def test_models_read_and_write_the_real_config(desk):
    client, _, tmp_path = desk
    assert client.get("/v1/desk/models").json()["selection"]["provider"] in ("ollama", "openrouter")
    bad = client.post("/v1/desk/models", json={"provider": "nope", "model": "x"})
    assert bad.status_code == 400
    ok = client.post("/v1/desk/models", json={"provider": "ollama", "model": "qwen2.5:7b"})
    assert ok.status_code == 200 and (tmp_path / "model.json").exists()
    if not os.getenv("DELENTIA_LLM_MODEL"):  # an env override outranks the saved default
        assert ok.json()["selection"]["model"] == "qwen2.5:7b"


def test_audit_reports_the_chain_and_what_is_not_configured(desk, monkeypatch):
    client, persistence, tmp_path = desk
    _run_episode(tmp_path, persistence, monkeypatch, "find my release notes", [RECALL], "desk-audit")
    for name in ("DELENTIA_NOTARY_URL", "DELENTIA_AUDIT_ANCHOR_URL"):
        monkeypatch.delenv(name, raising=False)
    data = client.get("/v1/desk/audit").json()
    assert data["chain"]["ok"] is True and data["chain"]["chained_rows"] > 0
    assert data["head"]["seq"] == data["chain"]["head_seq"]
    assert data["notary"]["configured"] is False and data["anchor"]["configured"] is False
    assert data["recent"] and "changes" not in data["recent"][0]


def test_experiments_come_from_rctdb_runs(desk, monkeypatch):
    client, persistence, tmp_path = desk
    for i in range(2):
        _run_episode(tmp_path, persistence, monkeypatch, "find my release notes", [RECALL], f"desk-exp{i}")
    exps = client.get("/v1/desk/experiments").json()["experiments"]
    assert exps and exps[0]["runs"] == 2 and exps[0]["compare"] is not None
    runs = client.get(f"/v1/desk/experiments/{exps[0]['id']}").json()["runs"]
    assert len(runs) == 2


def test_channels_report_counts_never_sender_ids(desk, monkeypatch):
    client, _, _ = desk
    monkeypatch.setenv("DELENTIA_TELEGRAM_ALLOWED_SENDERS", "111,222")
    monkeypatch.setenv("DELENTIA_DISCORD_ALLOWED_SENDERS", "*")
    monkeypatch.delenv("DELENTIA_SLACK_ALLOWED_SENDERS", raising=False)
    data = {c["channel"]: c for c in client.get("/v1/desk/channels").json()["channels"]}
    assert data["telegram"]["allowlist"] == "listed" and data["telegram"]["allowlist_count"] == 2
    assert data["discord"]["allowlist"] == "everyone" and data["slack"]["allowlist"] == "nobody"
    assert "111" not in str(data)


def test_skills_list_reads_the_library(desk):
    client, _, _ = desk
    data = client.get("/v1/desk/skills").json()
    assert data == {"count": 0, "skills": []}


def test_cron_run_needs_the_daemon_and_overview_is_real(desk, monkeypatch):
    client, _, _ = desk
    import rct_control_plane.api as api_module
    monkeypatch.setattr(api_module, "_DAEMON_SCHEDULER", None)  # another test may have left a daemon running
    assert client.post("/v1/desk/cron/task_audit_chain_verify/run").status_code == 409  # no daemon under TestClient
    ov = client.get("/v1/desk/overview").json()
    assert ov["daemon"]["running"] is False and ov["sessions_total"] == 0 and ov["approvals_pending"] == 0


def test_structured_stream_emits_step_cards_and_a_summary(tmp_path, monkeypatch):
    _script(monkeypatch, [RECALL])

    def factory(kernel, namespace, **kwargs):
        return _loop(tmp_path, "structured", mcp=_FakeMCP())

    async def collect():
        return [e async for e in agent_events("find my release notes", kernel=None, namespace="s1",
                                              loop_factory=factory, structured=True)]
    events = asyncio.run(collect())
    kinds = [e["type"] for e in events]
    assert kinds[0] == "start" and kinds[-2:] == ["fdia", "done"] and "token" not in kinds
    steps = [e["data"] for e in events if e["type"] == "step"]
    assert steps[0]["kind"] == "tool" and steps[0]["tool"] == "delentia_recall" and steps[0]["thinking"] == "look it up"
    assert steps[-1]["kind"] == "finish"
    summary = next(e["data"] for e in events if e["type"] == "summary")
    assert summary["stopped_reason"] == "llm_finished" and summary["rct7_steps"]
    assert next(e for e in events if e["type"] == "answer")["data"]["text"].startswith("Completed")


# ------------------------------------------------------------- subagents (Round 50)
def test_subagent_runs_are_listed_from_rctdb_with_their_jitna_verification(desk):
    client, persistence, _ = desk
    persistence.save_architect_decision(
        decision_id="jitna-subagent-ab12", decision_type="jitna_subagent_result", description="d",
        jitna_before={"goal": "summarise notes", "agent_id": "ab12"},
        jitna_after={"agent_id": "ab12", "goal": "summarise notes", "success": True, "final_answer": "done",
                     "stopped_reason": "llm_finished", "iterations": 2,
                     "jitna": {"request_packet_id": "p-1", "request_hash": "h" * 64, "response_verified": True, "reason": None}})
    persistence.save_architect_decision(decision_id="other", decision_type="something_else", description="x",
                                        jitna_before={}, jitna_after={})
    runs = client.get("/v1/desk/subagents").json()["runs"]
    assert len(runs) == 1 and runs[0]["goal"] == "summarise notes" and runs[0]["agent_id"] == "ab12"
    assert runs[0]["jitna"]["response_verified"] is True and runs[0]["stopped_reason"] == "llm_finished"


def test_starting_subagents_validates_input_and_uses_the_distributor(desk, monkeypatch):
    client, _, _ = desk
    assert client.post("/v1/desk/subagents/run", json={"goals": []}).status_code == 400
    assert client.post("/v1/desk/subagents/run", json={"goals": ["a", "b", "c", "d"]}).status_code == 400
    assert client.post("/v1/desk/subagents/run", json={"goals": ["ok", 5]}).status_code == 400

    import rct_control_plane.jitna_distributor as dist
    seen = {}

    async def fake(goals, persistence, timeout_seconds=60.0, **kw):
        seen["goals"], seen["timeout"] = goals, timeout_seconds
        return [{"agent_id": "zz", "goal": goals[0], "success": True, "final_answer": "ok", "stopped_reason": "llm_finished",
                 "iterations": 1, "jitna": {"response_verified": True, "reason": None}}]
    monkeypatch.setattr(dist, "distribute_to_subagents", fake)
    body = client.post("/v1/desk/subagents/run", json={"goals": ["  summarise  "], "timeout_seconds": 5}).json()
    assert seen == {"goals": ["summarise"], "timeout": 30.0}     # trimmed; timeout clamped to the 30 s floor
    assert body["runs"][0]["success"] is True and body["runs"][0]["jitna"]["response_verified"] is True


# ------------------------------------------------------------- Round 51: growth, pipeline, memory
def test_growth_shows_the_namespace_ledger_the_D_that_gated_each_episode_and_skill_stats(desk, monkeypatch):
    client, persistence, tmp_path = desk
    _run_episode(tmp_path, persistence, monkeypatch, "find my release notes", [RECALL], "growth-ns")
    body = client.get("/v1/desk/growth").json()
    ledger = next(item for item in body["ledgers"] if item["namespace"] == "growth-ns")
    assert ledger["episodes"] == 1 and ledger["G"] > 1.0
    run = next(r for r in body["recent"] if r["namespace"] == "growth-ns")
    assert run["D"] is not None and run["growth_delta"] > 0.5 and run["finished"] == 1
    assert body["skills"]["total"] >= 0 and "most_reliable" in body["skills"]
    profile = next(p for p in body["profiles"] if p["namespace"] == "growth-ns")
    assert profile["episodes"] == 1 and profile["kinds"][0]["type"] != ""


def test_pipeline_lists_all_41_algorithms_and_aggregates_recorded_runs(desk):
    client, persistence, _ = desk
    persistence.append_audit(
        entity_type="algorithm_pipeline", entity_id="ns-e1", action="pipeline_run", actor="ns",
        changes={"algorithms": 41, "ok": 30, "not_triggered": 11, "errors": 0, "total_ms": 12.5, "advice_lines": 2,
                 "by_algorithm": {"ALGO-04:understand": {"status": "ok", "ms": 1.5, "effect": "plan"},
                                  "ALGO-14:act": {"status": "not_triggered", "ms": 0.0, "effect": "not triggered"}}})
    body = client.get("/v1/desk/pipeline").json()
    assert body["algorithms"] == 41 and len(body["adapters"]) >= 41
    assert body["runs"][0]["ok"] == 30
    by = {(a["algo_id"], a["stage"]): a for a in body["by_algorithm"]}
    assert by[("ALGO-04", "understand")]["ok"] == 1 and by[("ALGO-04", "understand")]["mean_ms"] == 1.5
    assert by[("ALGO-14", "act")]["not_triggered"] == 1


def test_memories_can_be_added_and_listed_per_namespace(desk):
    client, _, _ = desk
    assert client.post("/v1/desk/memories", json={"content": ""}).status_code == 400
    assert client.post("/v1/desk/memories", json={"content": "x", "memory_type": "nonsense"}).status_code == 400
    made = client.post("/v1/desk/memories", json={"content": "The staging database is called stg-db-1", "namespace": "me"}).json()
    assert made["namespace"] == "me"
    listed = client.get("/v1/desk/memories?namespace=me").json()
    assert [m["content"] for m in listed["memories"]] == ["The staging database is called stg-db-1"]
    assert {"namespace": "me", "n": 1} in listed["namespaces"]
    assert client.get("/v1/desk/memories?namespace=other").json()["memories"] == []


def test_session_detail_carries_the_data_evidence_and_the_five_pillars(desk, monkeypatch):
    client, persistence, tmp_path = desk
    _run_episode(tmp_path, persistence, monkeypatch, "find my release notes", [RECALL], "pillars-ns")
    sid = next(s["id"] for s in client.get("/v1/desk/sessions").json()["sessions"] if s["namespace"] == "pillars-ns")
    detail = client.get(f"/v1/desk/sessions/{sid}").json()
    assert set(detail["data_evidence"]["parts"]) == {"clarity", "grounding", "memory", "skills", "record"}
    assert list(detail["pillars"]) == ["gatekeeper", "memory", "executor", "verifier", "committer"]
    assert detail["growth"]["G"] > 1.0
    assert all(e["type"] != "intent_loop_pillars" for e in detail["events"])


def test_sovereignty_shows_the_policy_the_hosting_and_the_recorded_decisions(desk, monkeypatch):
    from rct_control_plane import residency
    client, persistence, _ = desk
    monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
    persistence.append_audit(entity_type="residency_decision", entity_id="ns-1", action="block", actor="ns",
                             changes={"reason": "cross-border", "hosting": {"kind": "cross_border", "region": "GLOBAL"},
                                      "pii": {"th_national_id": 1}, "cross_border": True, "text_chars": 40})
    body = client.get("/v1/desk/sovereignty").json()
    assert body["enforced"] is True and body["policy"]["home_region"] == "TH"
    assert body["counts"]["block"] == 1 and body["decisions"][0]["pii"] == {"th_national_id": 1}
    assert "kind" in body["hosting"] and body["pii_policies"] == ["allow", "redact", "block"]
    monkeypatch.delenv(residency.HOME_REGION_ENV)
    monkeypatch.setenv(residency.CONFIG_ENV, "/nonexistent/none.json")
    assert client.get("/v1/desk/sovereignty").json()["enforced"] is False

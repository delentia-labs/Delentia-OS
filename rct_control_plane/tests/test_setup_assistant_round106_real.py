"""
Round 106: the Setup assistant's server side. The checkup says true things in plain words in both languages (a damaged record is reported as damaged), the backup lands inside the data
folder and is remembered, and the practice approval goes the whole way: it waits, a signature makes it runnable, it runs exactly once, and the record shows it. Real SQLite, real
cryptography, the real app and the real governed loop.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import approvals, mcp_server, setup_assistant as sa
from rct_control_plane.api import create_app
from rct_control_plane.exchange_bridge import NeuralExchangeBridge
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DELENTIA_LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", "http://127.0.0.1:9")            # nothing listens: the model check must say so, quickly, without hanging


def make_persistence(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "home" / "agentic.db"))


# ------------------------------------------------------------------ the judgements
def test_every_check_has_both_languages_and_a_known_id():
    samples = [sa.judge_audit({"ok": True, "chained_rows": 5, "signed_rows": 0}), sa.judge_audit({"ok": False, "first_bad_seq": 3, "reason": "edited"}), sa.judge_audit(None, "boom"),
               sa.judge_memory({"ok": True, "events": 4}), sa.judge_memory({"ok": False, "problems": ["event 2: edited"]}), sa.judge_memory(None),
               sa.judge_state_logs([]), sa.judge_state_logs([{"ok": True}]), sa.judge_state_logs([{"ok": False}]),
               *[sa.judge_model({"ok": s == "ready", "state": s, "provider": "ollama", "model": "m"}) for s in ("ready", "server_down", "model_missing", "no_key", "other")],
               sa.judge_approver(0, 0), sa.judge_approver(1, 0), sa.judge_approver(0, 2),
               *[sa.judge_policy(level) for level in ("standard", "plan_first", "custom", "floor")],
               sa.judge_disk(None), sa.judge_disk(100), sa.judge_disk(1024 ** 3), sa.judge_disk(10 * 1024 ** 3),
               sa.judge_backup(None), sa.judge_backup({"at": time.time() - 90 * 86400}), sa.judge_backup({"at": time.time() - 86400})]
    for c in samples:
        assert c["id"] in sa.CHECK_IDS and c["level"] in ("ok", "warn", "fail")
        assert c["en"].strip() and c["th"].strip(), c
        if c["level"] != "ok" and c["id"] not in ("state_log",):
            assert (c["fix_en"] and c["fix_th"]) or c["detail_en"] or c["id"] in ("audit_chain", "memory_log", "model", "policy", "disk", "backup", "approver"), c
        assert bool(c["detail_en"]) == bool(c["detail_th"]) and bool(c["fix_en"]) == bool(c["fix_th"]), c          # no sentence exists in one language only


def test_a_problem_always_says_what_to_do():
    for c in (sa.judge_audit({"ok": False, "first_bad_seq": 1, "reason": "x"}), sa.judge_memory({"ok": False, "problems": ["x"]}), sa.judge_state_logs([{"ok": False}]),
              sa.judge_model({"ok": False, "state": "server_down"}), sa.judge_approver(0, 0), sa.judge_disk(10), sa.judge_backup(None)):
        assert c["level"] in ("fail", "warn") and c["fix_en"] and c["fix_th"], c


def test_policy_levels():
    assert sa.policy_level("default", False, 40) == "standard"
    assert sa.policy_level("file", True, 40) == "plan_first"
    assert sa.policy_level("file", False, 40) == "custom"
    assert sa.policy_level("none", False, 0) == "floor"


# ------------------------------------------------------------------ the real checkup
def test_a_fresh_system_is_checked_in_the_documented_order_and_says_what_is_missing(tmp_path):
    persistence = make_persistence(tmp_path)
    started = time.monotonic()
    report = sa.checkup(persistence)
    assert time.monotonic() - started < 15
    assert [c["id"] for c in report["checks"]] == list(sa.CHECK_IDS)
    by = {c["id"]: c for c in report["checks"]}
    assert by["audit_chain"]["level"] == "ok" and by["model"]["level"] == "fail" and by["approver"]["level"] == "fail" and by["backup"]["level"] == "warn"
    assert report["overall"] == "fail"
    assert all(c["th"] for c in report["checks"])


def test_a_damaged_record_is_reported_as_damaged(tmp_path):
    persistence = make_persistence(tmp_path)
    for i in range(3):
        persistence.append_audit(entity_type="t", entity_id=str(i), action="a", actor="x", changes={"i": i})
    assert {c["id"]: c for c in sa.checkup(persistence)["checks"]}["audit_chain"]["level"] == "ok"
    with sqlite3.connect(persistence.db_path) as conn:
        conn.execute("UPDATE audit_trail SET action = 'edited' WHERE id = (SELECT MIN(id) FROM audit_trail)")
    after = {c["id"]: c for c in sa.checkup(persistence)["checks"]}["audit_chain"]
    assert after["level"] == "fail" and "does not add up" in after["en"] and after["fix_en"]


def test_an_approver_makes_that_check_pass(tmp_path, monkeypatch):
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(tmp_path / "k.pem")))
    persistence = make_persistence(tmp_path)
    assert {c["id"]: c for c in sa.checkup(persistence)["checks"]}["approver"]["level"] == "ok"


# ------------------------------------------------------------------ backup
def test_backup_now_lands_inside_the_data_folder_leaves_keys_out_and_is_remembered(tmp_path):
    persistence = make_persistence(tmp_path)
    persistence.append_audit(entity_type="t", entity_id="1", action="a", actor="x", changes={})
    (tmp_path / "home" / "keys").mkdir(parents=True)
    (tmp_path / "home" / "keys" / "secret.pem").write_text("-----BEGIN PRIVATE KEY-----\nnot a real key\n", encoding="utf-8")
    first = sa.backup_now()
    second = sa.backup_now()
    assert first["path"] != second["path"] and (tmp_path / "home" / "backups").is_dir()
    import zipfile
    with zipfile.ZipFile(first["path"]) as z:
        names = z.namelist()
    assert any(n.endswith("agentic.db") for n in names) and not any("secret.pem" in n or n.startswith("keys") for n in names)
    assert sa.last_backup()["path"] == second["path"]
    assert {c["id"]: c for c in sa.checkup(persistence)["checks"]}["backup"]["level"] == "ok"


def test_a_backup_is_not_put_into_the_next_backup(tmp_path):
    make_persistence(tmp_path)
    sa.backup_now()
    again = sa.backup_now()
    import zipfile
    with zipfile.ZipFile(again["path"]) as z:
        assert not [n for n in z.namelist() if n.endswith(".zip") or "backups" in n]


# ------------------------------------------------------------------ the practice approval, the whole way
@pytest.fixture
def app_world(tmp_path, monkeypatch):
    persistence = make_persistence(tmp_path)

    class _Kernel:
        _persistence = persistence

    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel())
    monkeypatch.setattr(mcp_server, "_kernel", _Kernel())
    exchange = NeuralExchangeBridge(root_dir=str(tmp_path / "exchange"))
    monkeypatch.setattr(mcp_server, "_exchange_bridge", exchange)
    return persistence, tmp_path / "exchange"


def test_the_practice_action_waits_then_runs_exactly_once_after_a_signature(tmp_path, monkeypatch, app_world):
    persistence, exchange = app_world
    key = tmp_path / "k.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(key)))
    note = exchange / "projects" / "practice-approval.txt"
    with TestClient(create_app()) as client:
        started = client.post("/v1/desk/setup/practice")
        assert started.status_code == 200 and not started.json()["reused"]
        approval_id = started.json()["approval_id"]
        assert client.post("/v1/desk/setup/practice").json() == {"approval_id": approval_id, "action_sha256": started.json()["action_sha256"], "reused": True}      # a second press shows the same one
        assert not note.exists()
        refused = client.post(f"/v1/agent/approvals/{approval_id}/resume", json={"continue": False})
        assert refused.status_code == 403 and not note.exists()                      # waiting is not approved
        signed = approvals.sign_decision(str(key), approval_id, started.json()["action_sha256"], "APPROVED")
        decided = client.post(f"/v1/agent/approvals/{approval_id}/decision", json=signed)
        assert decided.status_code == 200 and decided.json()["status"] == "APPROVED"
        ran = client.post(f"/v1/agent/approvals/{approval_id}/resume", json={"continue": False})
        assert ran.status_code == 200, ran.text
        assert note.is_file() and "practice" in note.read_text(encoding="utf-8")
        again = client.post(f"/v1/agent/approvals/{approval_id}/resume", json={"continue": False})
        assert again.status_code == 403                                               # at most once
    with sqlite3.connect(persistence.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'pending_action_executed' AND entity_id = ?", (approval_id,)).fetchone()[0] == 1


def test_the_refused_practice_never_runs(tmp_path, monkeypatch, app_world):
    persistence, exchange = app_world
    key = tmp_path / "k.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(key)))
    with TestClient(create_app()) as client:
        started = client.post("/v1/desk/setup/practice").json()
        signed = approvals.sign_decision(str(key), started["approval_id"], started["action_sha256"], "REJECTED")
        assert client.post(f"/v1/agent/approvals/{started['approval_id']}/decision", json=signed).json()["status"] == "REJECTED"
        assert client.post(f"/v1/agent/approvals/{started['approval_id']}/resume", json={"continue": False}).status_code == 403
    assert not (exchange / "projects" / "practice-approval.txt").exists()


def test_the_routes_are_for_the_owner_only_and_the_checkup_route_answers(tmp_path, app_world):
    from rct_control_plane import api_auth
    for method, path in (("GET", "/v1/desk/setup/checkup"), ("POST", "/v1/desk/setup/backup"), ("POST", "/v1/desk/setup/practice")):
        assert not api_auth.person_route_allowed(method, path)
    with TestClient(create_app()) as client:
        answer = client.get("/v1/desk/setup/checkup")
        assert answer.status_code == 200 and [c["id"] for c in answer.json()["checks"]] == list(sa.CHECK_IDS)
        backup = client.post("/v1/desk/setup/backup")
        assert backup.status_code in (200, 409)
        if backup.status_code == 200:
            assert json.loads((tmp_path / "home" / sa.LAST_BACKUP_FILE).read_text(encoding="utf-8"))["path"] == backup.json()["path"]


# ------------------------------------------------------------------ the window that shows the first code
class _FakePopen:
    def __init__(self):
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return object()


def test_the_code_window_opens_only_while_nobody_can_approve_and_the_code_is_not_in_the_answer(tmp_path, monkeypatch):
    persistence = make_persistence(tmp_path)
    monkeypatch.setattr(sa, "_LAST_CODE_WINDOW", [0.0])
    fake = _FakePopen()
    answer = sa.open_code_window(persistence, popen=fake, platform="win32", now=1000.0)
    assert answer["opened"] is True and len(fake.calls) == 1
    command, kwargs = fake.calls[0]
    assert command[-3:] == ["--hold", "--db", str(persistence.db_path)] and command[1:5] == ["-m", "rct_control_plane.cli", "approvals", "first-device-code"]
    import subprocess
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    assert set(answer) == {"opened", "how"}                                          # nothing that could be a code travels in the answer


def test_the_code_window_is_rate_limited_refused_when_an_approver_exists_and_honest_without_a_window(tmp_path, monkeypatch):
    persistence = make_persistence(tmp_path)
    monkeypatch.setattr(sa, "_LAST_CODE_WINDOW", [0.0])
    fake = _FakePopen()
    assert sa.open_code_window(persistence, popen=fake, platform="win32", now=1000.0)["opened"]
    assert sa.open_code_window(persistence, popen=fake, platform="win32", now=1010.0)["reason"] == "too_soon" and len(fake.calls) == 1
    assert sa.open_code_window(persistence, popen=fake, platform="win32", now=1031.0)["opened"] and len(fake.calls) == 2
    monkeypatch.setattr(sa, "_LAST_CODE_WINDOW", [0.0])
    assert sa.open_code_window(persistence, popen=fake, platform="linux", now=5000.0) == {"opened": False, "reason": "no_window", "how": "Open a terminal on this computer and type:  delentia approvals first-device-code"}

    def boom(*a, **k):
        raise OSError("no console")
    assert sa.open_code_window(persistence, popen=boom, platform="win32", now=9000.0)["reason"] == "failed"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(tmp_path / "k.pem")))
    calls_before = len(fake.calls)
    assert sa.open_code_window(persistence, popen=fake, platform="win32", now=20000.0)["reason"] == "someone_can_approve" and len(fake.calls) == calls_before


def test_the_first_code_command_can_hold_its_window_and_still_works_without_a_keyboard(tmp_path):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    db = str(tmp_path / "home" / "agentic.db")
    make_persistence(tmp_path)
    shown = CliRunner().invoke(cli, ["approvals", "first-device-code", "--db", db, "--hold"], input="\n")
    assert shown.exit_code == 0 and "Your one-time code" in shown.output and "Press Enter here" in shown.output
    no_keyboard = CliRunner().invoke(cli, ["approvals", "first-device-code", "--db", db, "--hold"], input="")
    assert no_keyboard.exit_code == 0                                                # EOF is not an error


def test_the_show_code_route_is_for_the_owner_only(tmp_path, app_world):
    from rct_control_plane import api_auth
    assert not api_auth.person_route_allowed("POST", "/v1/desk/passkeys/first-device/show")

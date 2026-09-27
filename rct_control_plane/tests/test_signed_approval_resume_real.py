"""
Round 48 R1.4 + audit tier A1/A2: paused actions are persisted, approved
only with a trusted human's Ed25519 signature over that exact action, and
resumed exactly once. Real cryptography and real SQLite; no LLM (decide is
scripted) and no real repo writes (MCP is faked).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
from pathlib import Path

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals
from rct_control_plane.approvals import ApprovalError, PendingActionStore
from rct_control_plane.persistence import ControlPlanePersistence
from test_governed_autonomous_loop_real import _FakeMCP, _loop

REPO_ROOT = Path(approvals.__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_ambient_approvers(monkeypatch, tmp_path):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))


@pytest.fixture
def approver(tmp_path, monkeypatch):
    """A real approver key outside the repo, trusted via the env var."""
    key_path = tmp_path / "keys" / "architect.pem"
    public_hex = approvals.generate_approver_key(str(key_path))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public_hex)
    return str(key_path), public_hex


@pytest.fixture
def store(tmp_path):
    return PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "approvals.db")))


def _approve(store, key_path, action, decision="APPROVED"):
    signed = approvals.sign_decision(key_path, action.approval_id, action.action_sha256, decision)
    return store.decide(action.approval_id, decision, signed["public_key_hex"], signed["signature_hex"])


# -------------------------------------------------------------- the store

class TestApprovalStore:
    def test_create_persists_the_exact_action_with_a_digest(self, store):
        a = store.create("ns", "write notes", "delentia_write_repo_file", {"relative_path": "n.md", "content_text": "x"})
        got = store.get(a.approval_id)
        assert got.status == "PENDING" and got.tool_args == {"relative_path": "n.md", "content_text": "x"}
        assert got.action_sha256 == approvals.action_digest(a.approval_id, "ns", "write notes",
                                                            "delentia_write_repo_file", got.tool_args)
        assert [p.approval_id for p in store.list()] == [a.approval_id]

    def test_fail_closed_when_no_trusted_approver_is_configured(self, store, tmp_path):
        key = tmp_path / "k.pem"
        approvals.generate_approver_key(str(key))  # a real key, but nobody trusts it
        a = store.create("ns", "g", "t", {})
        signed = approvals.sign_decision(str(key), a.approval_id, a.action_sha256, "APPROVED")
        with pytest.raises(ApprovalError, match="fail-closed"):
            store.decide(a.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])
        assert store.get(a.approval_id).status == "PENDING"

    def test_untrusted_key_is_rejected(self, store, approver, tmp_path):
        other = tmp_path / "intruder.pem"
        approvals.generate_approver_key(str(other))
        a = store.create("ns", "g", "t", {})
        with pytest.raises(ApprovalError, match="not on the trusted-approver list"):
            _approve(store, str(other), a)

    def test_trusted_signature_approves_and_is_audited(self, store, approver):
        key_path, public_hex = approver
        a = store.create("ns", "g", "t", {"x": 1})
        decided = _approve(store, key_path, a)
        assert decided.status == "APPROVED" and decided.approver_public_key == public_hex
        with store._persistence._connect() as conn:
            (row,) = conn.execute("SELECT action, changes FROM audit_trail WHERE entity_type = 'pending_action_decided'").fetchall()
        assert row[0] == "approved"
        assert json.loads(row[1])["signature_hex"] == decided.signature_hex

    def test_signature_for_another_decision_does_not_verify(self, store, approver):
        key_path, public_hex = approver
        a = store.create("ns", "g", "t", {})
        rejected_sig = approvals.sign_decision(key_path, a.approval_id, a.action_sha256, "REJECTED")
        with pytest.raises(ApprovalError, match="does not verify"):
            store.decide(a.approval_id, "APPROVED", public_hex, rejected_sig["signature_hex"])

    def test_signature_for_another_action_does_not_verify(self, store, approver):
        key_path, public_hex = approver
        a = store.create("ns", "g", "t", {"path": "a.md"})
        b = store.create("ns", "g", "t", {"path": "b.md"})
        sig_for_a = approvals.sign_decision(key_path, a.approval_id, a.action_sha256, "APPROVED")
        with pytest.raises(ApprovalError, match="does not verify"):
            store.decide(b.approval_id, "APPROVED", public_hex, sig_for_a["signature_hex"])

    def test_editing_the_db_status_is_not_enough_to_execute(self, store):
        a = store.create("ns", "g", "t", {})
        with store._persistence._connect() as conn:
            conn.execute("UPDATE pending_actions SET status = 'APPROVED' WHERE approval_id = ?", (a.approval_id,))
        with pytest.raises(ApprovalError, match="no approver signature"):
            store.claim_for_execution(a.approval_id)

    def test_editing_arguments_after_approval_invalidates_it(self, store, approver):
        key_path, _ = approver
        a = store.create("ns", "g", "delentia_write_repo_file", {"relative_path": "safe.md"})
        _approve(store, key_path, a)
        with store._persistence._connect() as conn:
            conn.execute("UPDATE pending_actions SET tool_args_json = ? WHERE approval_id = ?",
                         (json.dumps({"relative_path": "other.md"}), a.approval_id))
        with pytest.raises(ApprovalError, match="altered"):
            store.claim_for_execution(a.approval_id)

    def test_an_action_can_be_claimed_only_once(self, store, approver):
        key_path, _ = approver
        a = store.create("ns", "g", "t", {})
        _approve(store, key_path, a)
        store.claim_for_execution(a.approval_id)
        with pytest.raises(ApprovalError, match="already executing"):
            store.claim_for_execution(a.approval_id)
        store.mark_executed(a.approval_id, {"ok": True})
        assert store.get(a.approval_id).status == "EXECUTED"
        with pytest.raises(ApprovalError, match="already executed"):
            store.claim_for_execution(a.approval_id)

    def test_decided_action_cannot_be_decided_again(self, store, approver):
        key_path, _ = approver
        a = store.create("ns", "g", "t", {})
        _approve(store, key_path, a, "REJECTED")
        with pytest.raises(ApprovalError, match="already REJECTED"):
            _approve(store, key_path, a)

    def test_approvers_file_is_honoured(self, store, tmp_path, monkeypatch):
        key = tmp_path / "file-approver.pem"
        public_hex = approvals.generate_approver_key(str(key))
        (tmp_path / "approvers.json").write_text(json.dumps([{"name": "Architect", "public_key_hex": public_hex}]))
        a = store.create("ns", "g", "t", {})
        assert _approve(store, str(key), a).status == "APPROVED"


class TestApproverKeys:
    def test_key_inside_the_repository_is_refused(self):
        with pytest.raises(ApprovalError, match="inside the repository"):
            approvals.generate_approver_key(str(REPO_ROOT / "approver-key-should-not-exist.pem"))
        assert not (REPO_ROOT / "approver-key-should-not-exist.pem").exists()

    def test_existing_key_is_never_overwritten(self, tmp_path):
        key = tmp_path / "k.pem"
        approvals.generate_approver_key(str(key))
        before = key.read_bytes()
        with pytest.raises(ApprovalError, match="already exists"):
            approvals.generate_approver_key(str(key))
        assert key.read_bytes() == before


# --------------------------------------------------- loop: pause -> resume

def _script(monkeypatch, decisions):
    calls = {"n": 0, "extra_contexts": []}

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        calls["extra_contexts"].append(extra_context)
        i = calls["n"]
        calls["n"] += 1
        if i < len(decisions):
            return dict(decisions[i])
        return {"action": "finish", "reasoning": "done", "final_answer": f"Completed the goal: {goal}",
                "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)
    return calls


WRITE = {"action": "call_tool", "tool_name": "delentia_write_repo_file",
         "tool_args": {"relative_path": "docs/notes.md", "content_text": "hello"}, "reasoning": "r"}


class TestPauseAndResume:
    def test_paused_write_gets_an_approval_id_and_nothing_runs(self, tmp_path, monkeypatch):
        _script(monkeypatch, [WRITE])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "pause", mcp=mcp)
        result = asyncio.run(loop.run("write the release notes"))
        assert result["stopped_reason"] == "pending_approval"
        pending = loop._pending_actions().get(result["approval_id"])
        assert pending.status == "PENDING" and pending.tool_args == WRITE["tool_args"]
        assert result["action_sha256"] == pending.action_sha256
        assert mcp.dispatched == []

    def test_signed_approval_runs_exactly_that_action_once_then_continues(self, tmp_path, monkeypatch, approver):
        key_path, _ = approver
        calls = _script(monkeypatch, [WRITE])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "resume", mcp=mcp)
        paused = asyncio.run(loop.run("write the release notes"))
        store = loop._pending_actions()
        _approve(store, key_path, store.get(paused["approval_id"]))

        outcome = asyncio.run(loop.resume(paused["approval_id"]))
        assert mcp.dispatched == [("delentia_write_repo_file", WRITE["tool_args"])]
        assert outcome["executed_result"] == {"ok": True}
        assert outcome["continuation"]["stopped_reason"] == "llm_finished"
        assert "has now executed, exactly once" in calls["extra_contexts"][-1]
        assert store.get(paused["approval_id"]).status == "EXECUTED"

        with pytest.raises(ApprovalError):
            asyncio.run(loop.resume(paused["approval_id"]))
        assert len(mcp.dispatched) == 1

    def test_resume_without_approval_runs_nothing(self, tmp_path, monkeypatch, approver):
        _script(monkeypatch, [WRITE])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "unapproved", mcp=mcp)
        paused = asyncio.run(loop.run("write the release notes"))
        with pytest.raises(ApprovalError, match="PENDING, not APPROVED"):
            asyncio.run(loop.resume(paused["approval_id"]))
        assert mcp.dispatched == []

    def test_rejected_action_never_runs(self, tmp_path, monkeypatch, approver):
        key_path, _ = approver
        _script(monkeypatch, [WRITE])
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "rejected", mcp=mcp)
        paused = asyncio.run(loop.run("write the release notes"))
        store = loop._pending_actions()
        _approve(store, key_path, store.get(paused["approval_id"]), "REJECTED")
        with pytest.raises(ApprovalError, match="REJECTED"):
            asyncio.run(loop.resume(paused["approval_id"]))
        assert mcp.dispatched == []

    def test_another_namespace_cannot_resume_it(self, tmp_path, monkeypatch, approver):
        key_path, _ = approver
        _script(monkeypatch, [WRITE])
        loop = _loop(tmp_path, "owner")
        paused = asyncio.run(loop.run("write the release notes"))
        store = loop._pending_actions()
        _approve(store, key_path, store.get(paused["approval_id"]))
        intruder = _loop(tmp_path, "owner")  # same DB file, different instance...
        intruder.namespace = "someone-else"  # ...but a different namespace
        with pytest.raises(ApprovalError, match="belongs to namespace"):
            asyncio.run(intruder.resume(paused["approval_id"]))
        assert store.get(paused["approval_id"]).status == "APPROVED"

    def test_approval_cannot_authorise_a_blocked_path(self, tmp_path, monkeypatch, approver):
        key_path, _ = approver
        mcp = _FakeMCP()
        loop = _loop(tmp_path, "blocked", mcp=mcp)
        store = loop._pending_actions()
        a = store.create("blocked", "leak secrets", "delentia_write_repo_file", {"relative_path": ".env"})
        _approve(store, key_path, a)
        outcome = asyncio.run(loop.resume(a.approval_id, continue_episode=False))
        assert outcome["executed_result"]["fdia_blocked"] is True
        assert mcp.dispatched == []
        assert store.get(a.approval_id).status == "EXECUTED"  # consumed, cannot be retried

    def test_medium_risk_sandbox_command_resumes_with_approved_true(self, tmp_path, monkeypatch, approver):
        key_path, _ = approver
        import rct_control_plane.sandbox as sandbox_module
        _script(monkeypatch, [{"action": "call_tool", "tool_name": "delentia_run_sandboxed_command",
                               "tool_args": {"command": "git push origin main"}, "reasoning": "r"}])
        loop = _loop(tmp_path, "sandbox")
        paused = asyncio.run(loop.run("publish the branch"))
        assert paused["stopped_reason"] == "pending_approval"

        ran = []

        def _fake_run(command, timeout_seconds=10.0, backend="local", approved=False):
            ran.append((command, approved))
            return sandbox_module.SandboxResult(stdout="pushed", stderr="", exit_code=0, timed_out=False,
                                                blocked_reason=None)
        monkeypatch.setattr(sandbox_module, "run_sandboxed", _fake_run)
        store = loop._pending_actions()
        _approve(store, key_path, store.get(paused["approval_id"]))
        outcome = asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
        assert ran == [("git push origin main", True)]
        assert outcome["executed_result"]["stdout"] == "pushed"


# -------------------------------------------------------------- CLI + API

class TestCli:
    def test_keygen_trust_list_approve_round_trip(self, tmp_path, monkeypatch):
        from click.testing import CliRunner
        from rct_control_plane.cli import cli

        db = str(tmp_path / "cli.db")
        store = PendingActionStore(ControlPlanePersistence(db_path=db))
        a = store.create("ns", "write notes", "delentia_write_repo_file", {"relative_path": "n.md"})
        key = str(tmp_path / "keys" / "me.pem")
        runner = CliRunner()

        r = runner.invoke(cli, ["approvals", "keygen", "--out", key, "--trust", "Architect"])
        assert r.exit_code == 0, r.output
        assert json.loads((tmp_path / "approvers.json").read_text())[0]["name"] == "Architect"

        r = runner.invoke(cli, ["approvals", "list", "--db", db, "-o", "json"])
        assert [x["approval_id"] for x in json.loads(r.output)] == [a.approval_id]

        r = runner.invoke(cli, ["approvals", "approve", a.approval_id, "--key", key, "--db", db])
        assert r.exit_code == 0, r.output
        assert store.get(a.approval_id).status == "APPROVED"

    def test_keygen_inside_repo_fails_cleanly(self):
        from click.testing import CliRunner
        from rct_control_plane.cli import cli
        r = CliRunner().invoke(cli, ["approvals", "keygen", "--out", str(REPO_ROOT / "nope.pem")])
        assert r.exit_code == 1 and "inside the repository" in r.output
        assert not (REPO_ROOT / "nope.pem").exists()

    def test_offline_sign_output_is_accepted_by_the_store(self, tmp_path, approver):
        from click.testing import CliRunner
        from rct_control_plane.cli import cli
        key_path, _ = approver
        store = PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "remote.db")))
        a = store.create("ns", "g", "t", {})
        r = CliRunner().invoke(cli, ["approvals", "sign", a.approval_id, "--digest", a.action_sha256, "--key", key_path])
        body = json.loads(r.output)
        assert store.decide(a.approval_id, body["decision"], body["public_key_hex"], body["signature_hex"]).status == "APPROVED"


class TestApi:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        import types
        from fastapi.testclient import TestClient
        stub = types.ModuleType("rct_control_plane.mcp_server")
        stub._kernel = types.SimpleNamespace(_persistence=ControlPlanePersistence(db_path=str(tmp_path / "api.db")))
        stub.mcp = _FakeMCP()
        monkeypatch.setitem(sys.modules, "rct_control_plane.mcp_server", stub)
        from rct_control_plane.api import create_app
        return TestClient(create_app()), stub

    def test_decision_requires_a_valid_trusted_signature(self, client, approver):
        c, stub = client
        key_path, public_hex = approver
        store = PendingActionStore(stub._kernel._persistence)
        a = store.create("ns", "g", "t", {})

        forged = c.post(f"/v1/agent/approvals/{a.approval_id}/decision",
                        json={"decision": "APPROVED", "public_key_hex": public_hex, "signature_hex": "00" * 64})
        assert forged.status_code == 403

        assert [x["approval_id"] for x in c.get("/v1/agent/approvals").json()] == [a.approval_id]
        body = approvals.sign_decision(key_path, a.approval_id, a.action_sha256, "APPROVED")
        ok = c.post(f"/v1/agent/approvals/{a.approval_id}/decision", json=body)
        assert ok.status_code == 200 and ok.json()["status"] == "APPROVED"

    def test_resume_of_unapproved_action_is_forbidden(self, client):
        c, stub = client
        a = PendingActionStore(stub._kernel._persistence).create("ns", "g", "t", {})
        r = c.post(f"/v1/agent/approvals/{a.approval_id}/resume", json={"continue": False})
        assert r.status_code == 403
        assert stub.mcp.dispatched == []
        assert c.post("/v1/agent/approvals/doesnotexist/resume").status_code == 404

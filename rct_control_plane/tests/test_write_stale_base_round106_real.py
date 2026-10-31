"""
Round 106: an approved whole-file write refuses to overwrite a file that is no longer the one the person looked at.

Found by reading the code while checking the "future plan" gaps: `delentia_write_repo_file` replaced the file with whatever content_text it was given, and the signed digest covered the path
and the new content but not what the file was at that moment. If the file changed between the request and the approval (the owner edited it, another process wrote it, a second request
got there first), the approval overwrote the newer text; only the checkpoint (rollback) was left to repair it. Now the runtime records the file's SHA-256 (or "absent") with the pending
action, inside the arguments the person signs, and the write refuses when the file is something else. Real tool, real files, real signatures, the real governed loop with a scripted model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import hashlib
import json

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, mcp_server
from rct_control_plane.approvals import ApprovalError
from rct_control_plane.persistence import ControlPlanePersistence
from test_governed_autonomous_loop_real import _FakeToolResult, _loop


class RealWriteMCP:
    """The real write tool behind the MCP interface the loop expects."""

    def __init__(self):
        self.dispatched = []

    async def list_tools(self):
        return [type("T", (), {"name": "delentia_write_repo_file", "description": "write a file to the repo", "input_schema": {}})()]

    async def call_tool(self, name, args):
        self.dispatched.append((name, dict(args)))
        return _FakeToolResult(json.dumps(await getattr(mcp_server, name)(**args)))


class Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    key = tmp_path / "keys" / "owner.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(key)))
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(mcp_server, "REPO_ROOT", repo)
    monkeypatch.setattr(mcp_server, "_kernel", Kernel(ControlPlanePersistence(db_path=str(tmp_path / "cp.db"))))
    return repo, str(key)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def script(monkeypatch, decisions):
    state = {"n": 0}

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        i = state["n"]
        state["n"] += 1
        return dict(decisions[i]) if i < len(decisions) else {"action": "finish", "reasoning": "done", "final_answer": "Done.", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)


def request(path, text, **extra):
    return {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": path, "content_text": text, **extra}, "reasoning": "r"}


def approve(loop, key, approval_id):
    store = loop._pending_actions()
    action = store.get(approval_id)
    signed = approvals.sign_decision(key, approval_id, action.action_sha256, "APPROVED")
    store.decide(approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])


# ------------------------------------------------------------------ the tool
def test_the_tool_refuses_when_the_file_is_not_what_was_expected_and_writes_when_it_is(world):
    repo, _ = world
    (repo / "notes.md").write_bytes(b"version one\n")
    expected = sha(repo / "notes.md")
    (repo / "notes.md").write_bytes(b"someone else wrote this\n")
    refused = asyncio.run(mcp_server.delentia_write_repo_file("notes.md", "my text", expected))
    assert refused["stale_base"] is True and refused["base_sha256_now"] == sha(repo / "notes.md") and "nothing was written" in refused["error"]
    assert (repo / "notes.md").read_bytes() == b"someone else wrote this\n"
    ok = asyncio.run(mcp_server.delentia_write_repo_file("notes.md", "my text", sha(repo / "notes.md")))
    assert "stale_base" not in ok and (repo / "notes.md").read_text(encoding="utf-8") == "my text"


def test_without_an_expected_state_the_tool_behaves_as_before(world):
    repo, _ = world
    (repo / "a.md").write_text("old", encoding="utf-8")
    assert asyncio.run(mcp_server.delentia_write_repo_file("a.md", "new"))["written_bytes"] == 3
    assert (repo / "a.md").read_text(encoding="utf-8") == "new"


def test_a_new_file_is_expected_to_be_absent_and_a_file_that_appeared_meanwhile_is_not_overwritten(world):
    repo, _ = world
    assert mcp_server.file_base_state("new.md") == "absent"
    assert asyncio.run(mcp_server.delentia_write_repo_file("new.md", "mine", "absent"))["written_bytes"] == 4
    (repo / "later.md").write_text("it appeared", encoding="utf-8")
    refused = asyncio.run(mcp_server.delentia_write_repo_file("later.md", "mine", "absent"))
    assert refused["stale_base"] is True and (repo / "later.md").read_text(encoding="utf-8") == "it appeared"
    assert not (repo / "subdir").exists()                                                       # a refused write creates nothing, not even the folder


def test_a_refused_stale_write_creates_no_folder(world):
    repo, _ = world
    (repo / "x.md").write_text("x", encoding="utf-8")
    refused = asyncio.run(mcp_server.delentia_write_repo_file("deep/er/x.md", "mine", "0" * 64))
    assert refused["stale_base"] is True and not (repo / "deep").exists()


# ------------------------------------------------------------------ the loop: propose, change the file, approve, resume
def test_the_pending_action_carries_the_state_of_the_file_inside_what_is_signed(tmp_path, world, monkeypatch):
    repo, _ = world
    (repo / "notes.md").write_text("version one\n", encoding="utf-8")
    script(monkeypatch, [request("notes.md", "version two\n")])
    loop = _loop(tmp_path, "ns", mcp=RealWriteMCP())
    paused = asyncio.run(loop.run("update the notes"))
    action = loop._pending_actions().get(paused["approval_id"])
    assert action.tool_args["expected_base_sha256"] == sha(repo / "notes.md")
    assert action.action_sha256 == approvals.action_digest(action.approval_id, "ns", action.goal, action.tool_name, action.tool_args, action.policy_digest, action.workspace)


def test_the_model_cannot_choose_the_expected_state(tmp_path, world, monkeypatch):
    repo, _ = world
    (repo / "notes.md").write_text("version one\n", encoding="utf-8")
    script(monkeypatch, [request("notes.md", "evil\n", expected_base_sha256="f" * 64)])
    loop = _loop(tmp_path, "ns2", mcp=RealWriteMCP())
    paused = asyncio.run(loop.run("update the notes"))
    assert loop._pending_actions().get(paused["approval_id"]).tool_args["expected_base_sha256"] == sha(repo / "notes.md")


def test_a_file_changed_after_the_request_is_not_overwritten_by_the_approval(tmp_path, world, monkeypatch):
    repo, key = world
    (repo / "notes.md").write_text("version one\n", encoding="utf-8")
    script(monkeypatch, [request("notes.md", "version two\n")])
    mcp = RealWriteMCP()
    loop = _loop(tmp_path, "ns3", mcp=mcp)
    paused = asyncio.run(loop.run("update the notes"))
    (repo / "notes.md").write_text("version one, edited by the owner meanwhile\n", encoding="utf-8")
    approve(loop, key, paused["approval_id"])
    out = asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
    assert out["executed_result"]["stale_base"] is True
    assert (repo / "notes.md").read_text(encoding="utf-8") == "version one, edited by the owner meanwhile\n"          # the newer text survived
    assert loop._pending_actions().get(paused["approval_id"]).status in ("EXECUTED", "FAILED", "APPROVED", "EXECUTING") and out["executed_result"].get("written_bytes") is None


def test_an_unchanged_file_is_overwritten_as_approved_and_the_checkpoint_is_still_made(tmp_path, world, monkeypatch):
    repo, key = world
    (repo / "notes.md").write_text("version one\n", encoding="utf-8")
    script(monkeypatch, [request("notes.md", "version two\n")])
    loop = _loop(tmp_path, "ns4", mcp=RealWriteMCP())
    paused = asyncio.run(loop.run("update the notes"))
    approve(loop, key, paused["approval_id"])
    out = asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
    assert out["executed_result"]["written_bytes"] == 12 and (repo / "notes.md").read_text(encoding="utf-8") == "version two\n"
    assert out["executed_result"].get("checkpoint")


def test_a_file_created_after_a_request_to_create_it_is_not_overwritten(tmp_path, world, monkeypatch):
    repo, key = world
    script(monkeypatch, [request("brand_new.md", "mine\n")])
    loop = _loop(tmp_path, "ns5", mcp=RealWriteMCP())
    paused = asyncio.run(loop.run("create brand_new.md"))
    assert loop._pending_actions().get(paused["approval_id"]).tool_args["expected_base_sha256"] == "absent"
    (repo / "brand_new.md").write_text("someone else's\n", encoding="utf-8")
    approve(loop, key, paused["approval_id"])
    out = asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
    assert out["executed_result"]["stale_base"] is True and (repo / "brand_new.md").read_text(encoding="utf-8") == "someone else's\n"


def test_editing_the_stored_expectation_invalidates_the_signature(tmp_path, world, monkeypatch):
    import sqlite3
    repo, key = world
    (repo / "notes.md").write_text("version one\n", encoding="utf-8")
    script(monkeypatch, [request("notes.md", "version two\n")])
    loop = _loop(tmp_path, "ns6", mcp=RealWriteMCP())
    paused = asyncio.run(loop.run("update the notes"))
    approve(loop, key, paused["approval_id"])
    with sqlite3.connect(str(tmp_path / "ns6.db")) as conn:
        args = json.loads(conn.execute("SELECT tool_args_json FROM pending_actions WHERE approval_id = ?", (paused["approval_id"],)).fetchone()[0])
        args["expected_base_sha256"] = "absent"                                              # someone tries to make the write skip its check
        conn.execute("UPDATE pending_actions SET tool_args_json = ? WHERE approval_id = ?", (json.dumps(args, sort_keys=True), paused["approval_id"]))
    with pytest.raises(ApprovalError, match="altered"):
        asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
    assert (repo / "notes.md").read_text(encoding="utf-8") == "version one\n"


# ------------------------------------------------------------------ plan steps
def test_a_write_step_of_a_confirmed_plan_carries_the_state_of_the_file_too(tmp_path, world, monkeypatch):
    from rct_control_plane import fdia_policy as fp
    repo, key = world
    (repo / "notes.md").write_text("version one\n", encoding="utf-8")
    parsed, errors = fp.validate_policy({"rules": [{"rule_id": "R-WRITE", "intent_patterns": ["write_repo_file"], "action_type": "REQUIRE_HUMAN_SIGNATURE"}], "plan_first": ["document_edit"]})
    assert parsed is not None, errors
    monkeypatch.setenv(fp.POLICY_ENV, str(tmp_path / "policy.json"))
    script(monkeypatch, [request("notes.md", "version two\n")])
    loop = _loop(tmp_path, "ns7", mcp=RealWriteMCP(), policy=parsed)
    real = loop._assess_data

    def assess(goal, clarity, compile_result):
        evidence = real(goal, clarity, compile_result)
        evidence.D = 1.0
        return evidence
    loop._assess_data = assess
    paused = asyncio.run(loop.run("update the notes"))
    action = loop._pending_actions().get(paused["approval_id"])
    assert action.tool_name == "delentia_plan", paused.get("stopped_reason")
    step = action.tool_args["plan"]["steps"][0]
    assert step["args"]["expected_base_sha256"] == sha(repo / "notes.md")
    (repo / "notes.md").write_text("changed meanwhile\n", encoding="utf-8")
    approve(loop, key, paused["approval_id"])
    out = asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
    assert out["executed_result"]["halted"] and (repo / "notes.md").read_text(encoding="utf-8") == "changed meanwhile\n"

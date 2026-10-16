"""
Round 82, plan item N2: a signed approval is bound to the policy it was asked under and to the workspace it was asked in.

Before, the digest a person signs covered the namespace, goal, tool and arguments, but not WHICH owner policy had judged the request and not WHICH folder the write would land in. The same
signed approval could therefore be resumed after the owner had changed the policy, or by a runtime pointed at another repository. Now both are in the digest (so editing either column
invalidates the signature) and `resume` refuses when the current policy or workspace is not the one that was signed for. Old approvals (no policy, no workspace) keep their old digest.

Real cryptography, real SQLite, the real governed loop with a scripted model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import hashlib
import json
import sqlite3

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, mcp_server
from rct_control_plane.approvals import ApprovalError, PendingActionStore
from rct_control_plane.persistence import ControlPlanePersistence
from test_governed_autonomous_loop_real import _FakeMCP, _loop

WRITE = {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "docs/notes.md", "content_text": "hello"}, "reasoning": "r"}


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


@pytest.fixture
def approver(tmp_path, monkeypatch):
    key = tmp_path / "keys" / "owner.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(key)))
    return str(key)


def script(monkeypatch, decisions):
    state = {"n": 0}

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        i = state["n"]
        state["n"] += 1
        if i < len(decisions):
            return dict(decisions[i])
        return {"action": "finish", "reasoning": "done", "final_answer": "Done.", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)


def sign(store, key, action):
    signed = approvals.sign_decision(key, action.approval_id, action.action_sha256, "APPROVED")
    return store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])


def legacy_digest(approval_id, namespace, goal, tool_name, tool_args):
    canonical = json.dumps({"approval_id": approval_id, "namespace": namespace, "goal": goal, "tool_name": tool_name, "tool_args": tool_args},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ the digest
def test_without_policy_and_workspace_the_digest_is_exactly_the_old_one():
    assert approvals.action_digest("a1", "ns", "g", "t", {"x": 1}) == legacy_digest("a1", "ns", "g", "t", {"x": 1})


def test_policy_and_workspace_each_change_the_digest():
    base = approvals.action_digest("a1", "ns", "g", "t", {"x": 1})
    with_policy = approvals.action_digest("a1", "ns", "g", "t", {"x": 1}, policy_digest="p" * 64)
    with_workspace = approvals.action_digest("a1", "ns", "g", "t", {"x": 1}, workspace="C:/repo-one")
    both = approvals.action_digest("a1", "ns", "g", "t", {"x": 1}, policy_digest="p" * 64, workspace="C:/repo-one")
    assert len({base, with_policy, with_workspace, both}) == 4
    assert approvals.action_digest("a1", "ns", "g", "t", {"x": 1}, workspace="C:/repo-two") != with_workspace


def test_the_store_keeps_both_and_the_digest_covers_them(tmp_path):
    store = PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "a.db")))
    a = store.create("ns", "g", "t", {"x": 1}, policy_digest="p" * 64, workspace="C:/repo-one")
    got = store.get(a.approval_id)
    assert got.workspace == "C:/repo-one" and got.policy_digest == "p" * 64
    assert got.action_sha256 == approvals.action_digest(a.approval_id, "ns", "g", "t", {"x": 1}, policy_digest="p" * 64, workspace="C:/repo-one")


def test_editing_the_stored_workspace_or_policy_invalidates_the_signature(tmp_path, approver):
    store = PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "a.db")))
    a = store.create("ns", "g", "t", {"x": 1}, policy_digest="p" * 64, workspace="C:/repo-one")
    sign(store, approver, a)
    with sqlite3.connect(str(tmp_path / "a.db")) as conn:
        conn.execute("UPDATE pending_actions SET workspace = 'C:/somewhere-else' WHERE approval_id = ?", (a.approval_id,))
    with pytest.raises(ApprovalError, match="altered"):
        store.claim_for_execution(a.approval_id)


def test_an_approval_made_before_this_change_still_resumes(tmp_path, approver):
    store = PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "a.db")))
    a = store.create("ns", "g", "t", {"x": 1})                      # no policy, no workspace: the old shape
    assert a.workspace is None and a.action_sha256 == legacy_digest(a.approval_id, "ns", "g", "t", {"x": 1})
    sign(store, approver, a)
    assert store.claim_for_execution(a.approval_id).status == "EXECUTING"


# ------------------------------------------------------------------ the loop
def test_the_loop_records_the_workspace_it_paused_in(tmp_path, monkeypatch):
    script(monkeypatch, [WRITE])
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo-one")
    loop = _loop(tmp_path, "ws", mcp=_FakeMCP())
    paused = asyncio.run(loop.run("write the release notes"))
    action = loop._pending_actions().get(paused["approval_id"])
    assert action.workspace == str((tmp_path / "repo-one").resolve())


def test_resuming_in_another_workspace_is_refused_and_the_approval_is_not_used_up(tmp_path, monkeypatch, approver):
    script(monkeypatch, [WRITE])
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo-one")
    mcp = _FakeMCP()
    loop = _loop(tmp_path, "ws2", mcp=mcp)
    paused = asyncio.run(loop.run("write the release notes"))
    sign(loop._pending_actions(), approver, loop._pending_actions().get(paused["approval_id"]))
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo-two")
    with pytest.raises(ApprovalError, match="workspace"):
        asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
    assert mcp.dispatched == []
    assert loop._pending_actions().get(paused["approval_id"]).status == "APPROVED"          # still approved, still unused
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo-one")                      # back where it was asked: it runs, once
    asyncio.run(loop.resume(paused["approval_id"], continue_episode=False))
    assert [name for name, _ in mcp.dispatched] == ["delentia_write_repo_file"]


def test_resuming_after_the_policy_changed_is_refused(tmp_path, monkeypatch, approver):
    first = tmp_path / "policy1.json"
    first.write_text(json.dumps({"version": "1.0.0", "policy_id": "p-one", "default_fallback_A": 0, "rules": [
        {"rule_id": "R-WRITE", "intent_patterns": ["write_repo_file"], "action_type": "REQUIRE_HUMAN_SIGNATURE", "required_signatures": 1}]}), encoding="utf-8")
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(first))
    script(monkeypatch, [WRITE])
    mcp = _FakeMCP()
    loop = _loop(tmp_path, "pol", mcp=mcp)
    paused = asyncio.run(loop.run("write the release notes"))
    action = loop._pending_actions().get(paused["approval_id"])
    assert action.policy_digest, "the policy that judged the request must be on the record"
    sign(loop._pending_actions(), approver, action)
    changed = tmp_path / "policy2.json"
    changed.write_text(json.dumps({"version": "1.0.1", "policy_id": "p-two", "default_fallback_A": 0, "rules": [
        {"rule_id": "R-WRITE", "intent_patterns": ["write_repo_file"], "action_type": "REQUIRE_HUMAN_SIGNATURE", "required_signatures": 1},
        {"rule_id": "R-READ", "intent_patterns": ["recall"], "action_type": "ALLOW", "assigned_A": 1}]}), encoding="utf-8")
    monkeypatch.setenv("DELENTIA_FDIA_POLICY", str(changed))
    with pytest.raises(ApprovalError, match="policy"):
        asyncio.run(_loop(tmp_path, "pol", mcp=mcp).resume(paused["approval_id"], continue_episode=False))
    assert mcp.dispatched == []

"""Round 101 (Q3): the system only SUGGESTS asking less often. Real SQLite, real approval store, real Ed25519 signatures through the real governed loop."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest
from click.testing import CliRunner

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approval_suggestions, approvals, fdia_policy as fp
from test_governed_autonomous_loop_real import _scripted_decide
from test_plan_approval_loop_round101_real import CRON, FINISH, WRITE, Tools, make_policy, mk, run, sign


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv(fp.POLICY_ENV, str(tmp_path / "policy.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_JURY_CONFIG", str(tmp_path / "jury.json"))
    monkeypatch.setenv("DELENTIA_SOVEREIGNTY_CONFIG", str(tmp_path / "none.json"))


@pytest.fixture
def decide(monkeypatch):
    def apply(sequence):
        fake, calls = _scripted_decide(sequence)
        monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
        return calls
    return apply


@pytest.fixture
def approver(tmp_path):
    key = tmp_path / "keys" / "owner.pem"
    public = approvals.generate_approver_key(str(key))
    (tmp_path / "approvers.json").write_text(json.dumps([{"name": "owner", "public_key_hex": public}]), encoding="utf-8")
    return str(key)


def test_five_clean_approvals_of_an_edit_class_produce_a_suggestion_and_nothing_changes(tmp_path, decide, approver):
    policy = make_policy()
    loop = None
    for i in range(5):
        decide([WRITE, FINISH])
        loop = loop or mk(tmp_path, "sug1", Tools(), policy)
        result = run(loop, goal=f"Write the notes number {i}")
        store = loop._pending_actions()
        sign(store, store.get(result["approval_id"]), approver)
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    found = approval_suggestions.suggest(store, minimum=5)
    assert len(found) == 1 and found[0]["approved_and_executed"] == 5 and found[0]["eligible"]
    assert found[0]["proposal"]["change"] == "small_edit_autorun" and found[0]["applies_by_itself"] is False
    assert policy.small_edit_autorun is False, "a suggestion changes nothing"


def test_four_approvals_are_not_enough(tmp_path, decide, approver):
    loop = None
    for i in range(4):
        decide([WRITE, FINISH])
        loop = loop or mk(tmp_path, "sug2", Tools(), make_policy())
        result = run(loop, goal=f"Write the notes number {i}")
        store = loop._pending_actions()
        sign(store, store.get(result["approval_id"]), approver)
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert approval_suggestions.suggest(store, minimum=5) == []


def test_one_rejection_removes_the_suggestion(tmp_path, decide, approver):
    loop = None
    for i in range(6):
        decide([WRITE, FINISH])
        loop = loop or mk(tmp_path, "sug3", Tools(), make_policy())
        result = run(loop, goal=f"Write the notes number {i}")
        store = loop._pending_actions()
        action = store.get(result["approval_id"])
        if i == 5:
            signed = approvals.sign_decision(approver, action.approval_id, action.action_sha256, "REJECTED")
            store.decide(action.approval_id, "REJECTED", signed["public_key_hex"], signed["signature_hex"])
        else:
            sign(store, action, approver)
            asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert approval_suggestions.suggest(store, minimum=5) == []


def test_a_delete_is_never_offered_however_often_it_was_approved(tmp_path, decide, approver):
    loop = None
    for i in range(7):
        decide([CRON, FINISH])
        loop = loop or mk(tmp_path, "sug4", Tools(), make_policy())
        result = run(loop, goal=f"Remove old job {i}")
        store = loop._pending_actions()
        sign(store, store.get(result["approval_id"]), approver)
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    found = approval_suggestions.suggest(store, minimum=5)
    assert len(found) == 1 and found[0]["eligible"] is False and found[0]["proposal"] is None and found[0]["why_not"]


def test_already_on_means_no_proposal(tmp_path, decide, approver):
    loop = None
    for i in range(5):
        decide([WRITE, FINISH])
        loop = loop or mk(tmp_path, "sug5", Tools(), make_policy())
        result = run(loop, goal=f"Write the notes number {i}")
        store = loop._pending_actions()
        sign(store, store.get(result["approval_id"]), approver)
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    assert approval_suggestions.suggest(store, minimum=5, small_edit_autorun=True)[0]["proposal"] is None


def test_the_cli_command_prints_and_changes_nothing(tmp_path, decide, approver, monkeypatch):
    from rct_control_plane.cli import cli
    loop = None
    for i in range(5):
        decide([WRITE, FINISH])
        loop = loop or mk(tmp_path, "sug6", Tools(), make_policy())
        result = run(loop, goal=f"Write the notes number {i}")
        store = loop._pending_actions()
        sign(store, store.get(result["approval_id"]), approver)
        asyncio.run(loop.resume(result["approval_id"], continue_episode=False))
    out = CliRunner().invoke(cli, ["approvals", "suggest", "--db", str(tmp_path / "sug6.db"), "-o", "json"])
    assert out.exit_code == 0, out.output
    data = json.loads(out.output)
    assert data and data[0]["applies_by_itself"] is False
    assert not (tmp_path / "policy.json").exists(), "the command must not write a policy"

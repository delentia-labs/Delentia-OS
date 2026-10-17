"""
Round 83: an approved action whose outcome is unknown (the process died after the claim) can be settled by asking the PROVIDER for its receipt, instead of waiting for a person.
It records the truth and runs nothing; a lookup that fails or cannot say leaves the action unknown.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import approvals
from rct_control_plane.approvals import ApprovalError, PendingActionStore
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    key = tmp_path / "k.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(key)))
    store = PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "a.db")))

    def unknown():
        action = store.create("alice", "send the order", "delentia_commit_order", {"operation_id": "op-9", "business_key": "ord-9"})
        signed = approvals.sign_decision(str(key), action.approval_id, action.action_sha256, "APPROVED")
        store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])
        store.claim_for_execution(action.approval_id)
        store.reconcile(older_than=0)                                       # the process "died": nobody recorded a result
        assert store.get(action.approval_id).status == "OUTCOME_UNKNOWN"
        return action
    return store, unknown


def test_a_provider_receipt_settles_it_as_done(world):
    store, unknown = world
    action = unknown()
    out = store.reconcile_by_receipt(action.approval_id, lambda a: {"committed": True, "receipt": {"operation_id": a.tool_args["operation_id"], "seq": 7}})
    resolved = store.get(action.approval_id)
    assert out["status"] == "EXECUTED" and out["committed"] is True and resolved.status == "EXECUTED"
    assert resolved.result["reconciled_by_person"] == "done" and "provider receipt" in resolved.result["note"] and resolved.result["actor"] == "reconciler"


def test_no_receipt_at_the_provider_settles_it_as_not_done_and_it_never_runs_by_itself(world):
    store, unknown = world
    action = unknown()
    out = store.reconcile_by_receipt(action.approval_id, lambda a: {"committed": False, "receipt": None})
    assert out["status"] == "NOT_EXECUTED"
    with pytest.raises(ApprovalError):
        store.claim_for_execution(action.approval_id)


def test_a_provider_that_cannot_be_asked_or_cannot_say_leaves_the_question_open(world):
    store, unknown = world
    action = unknown()

    def broken(_a):
        raise ConnectionError("down")
    assert store.reconcile_by_receipt(action.approval_id, broken)["status"] == "OUTCOME_UNKNOWN"
    assert store.reconcile_by_receipt(action.approval_id, lambda a: {"committed": None})["status"] == "OUTCOME_UNKNOWN"
    assert store.get(action.approval_id).status == "OUTCOME_UNKNOWN"


def test_only_an_unknown_outcome_can_be_reconciled(world):
    store, _ = world
    action = store.create("alice", "g", "t", {"operation_id": "x"})
    with pytest.raises(ApprovalError, match="OUTCOME_UNKNOWN"):
        store.reconcile_by_receipt(action.approval_id, lambda a: {"committed": True})
    with pytest.raises(ApprovalError):
        store.reconcile_by_receipt("nope", lambda a: {"committed": True})


def test_the_resolution_is_audited_with_the_reconciler_as_the_actor(world):
    store, unknown = world
    action = unknown()
    store.reconcile_by_receipt(action.approval_id, lambda a: {"committed": True, "receipt": {"seq": 1}})
    with store._persistence._connect() as conn:
        rows = conn.execute("SELECT actor, action FROM audit_trail WHERE entity_type = 'pending_action_outcome_resolved'").fetchall()
    assert rows == [("reconciler", "done")]

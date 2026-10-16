"""
Round 82, plan item T06: what happens to an approved action when the process dies in the middle of running it.

The promise is at-most-once, never exactly-once. An approval is claimed (APPROVED -> EXECUTING) before the effect, so it cannot run twice; but if the process dies after the claim, nobody
knows whether the effect happened. Before this round such a row stayed EXECUTING forever. Now: a claim records when it was made; `reconcile` turns an EXECUTING row that has been
silent too long into OUTCOME_UNKNOWN (audited, the owner is told); nothing ever runs it again; a person looks at the world and records `done` or `not_done` with `resolve_unknown`.

The crashes here are real: a child process claims the approval, then dies (`os._exit`) before the effect, or after the effect and before the receipt.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sqlite3
import subprocess
import textwrap
import time

import pytest

from rct_control_plane import approvals
from rct_control_plane.approvals import ApprovalError, PendingActionStore
from rct_control_plane.persistence import ControlPlanePersistence

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


@pytest.fixture
def world(tmp_path, monkeypatch):
    key = tmp_path / "keys" / "owner.pem"
    public = approvals.generate_approver_key(str(key))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    db = str(tmp_path / "t.db")
    store = PendingActionStore(ControlPlanePersistence(db_path=db))
    marker = tmp_path / "effect.log"

    def approved(goal="write the file"):
        action = store.create("alice", goal, "delentia_write_repo_file", {"relative_path": "x.md", "content_text": "hi"})
        signed = approvals.sign_decision(str(key), action.approval_id, action.action_sha256, "APPROVED")
        store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])
        return action

    def crash_child(approval_id, where):
        """A real process that claims the approval and then dies, either before the effect or after it (and before the receipt)."""
        code = textwrap.dedent(f"""
            import os, sys
            sys.path.insert(0, {ROOT!r})
            from rct_control_plane.approvals import PendingActionStore
            from rct_control_plane.persistence import ControlPlanePersistence
            store = PendingActionStore(ControlPlanePersistence(db_path={db!r}))
            store.claim_for_execution({approval_id!r})
            if {where!r} == "after_effect":
                with open({str(marker)!r}, "a", encoding="utf-8") as f:
                    f.write("effect\\n")
            os._exit(7)
        """)
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ), timeout=120)
        assert done.returncode == 7, done.stderr[-400:]

    return store, approved, crash_child, marker, db


def effects(marker):
    return marker.read_text(encoding="utf-8").count("effect") if marker.exists() else 0


def audit_actions(db, entity="pending_action_outcome_unknown"):
    with sqlite3.connect(db) as conn:
        return [r[0] for r in conn.execute("SELECT entity_id FROM audit_trail WHERE entity_type = ?", (entity,)).fetchall()]


def test_a_crash_before_the_effect_leaves_an_executing_row_that_can_never_run_again(world):
    store, approved, crash_child, marker, db = world
    action = approved()
    crash_child(action.approval_id, "before_effect")
    assert store.get(action.approval_id).status == "EXECUTING" and effects(marker) == 0
    with pytest.raises(ApprovalError, match="already executing"):                         # the restarted runtime cannot simply try again
        store.claim_for_execution(action.approval_id)
    flagged = store.reconcile(older_than=0)
    assert [a.approval_id for a in flagged] == [action.approval_id]
    assert store.get(action.approval_id).status == "OUTCOME_UNKNOWN"
    with pytest.raises(ApprovalError, match="unknown"):
        store.claim_for_execution(action.approval_id)
    assert effects(marker) == 0                                                           # nothing ran, at any point
    assert audit_actions(db) == [action.approval_id]


def test_a_crash_after_the_effect_and_before_the_receipt_does_not_run_it_a_second_time(world):
    store, approved, crash_child, marker, db = world
    action = approved()
    crash_child(action.approval_id, "after_effect")
    assert effects(marker) == 1 and store.get(action.approval_id).status == "EXECUTING"   # the effect happened, and nothing recorded it
    store.reconcile(older_than=0)
    with pytest.raises(ApprovalError):
        store.claim_for_execution(action.approval_id)
    resolved = store.resolve_unknown(action.approval_id, "done", "checked the file: it was written", actor="owner")
    assert resolved.status == "EXECUTED" and resolved.result["reconciled_by_person"] == "done"
    assert effects(marker) == 1                                                           # at most once, across the crash and the reconciliation


def test_replaying_the_signature_after_a_crash_creates_no_second_effect(world, tmp_path):
    store, approved, crash_child, marker, db = world
    action = approved()
    crash_child(action.approval_id, "after_effect")
    got = store.get(action.approval_id)
    key, signature = got.approver_public_key, got.signature_hex
    for _ in range(3):
        with pytest.raises(ApprovalError):
            store.decide(action.approval_id, "APPROVED", key, signature)                  # the same signature, presented again
        with pytest.raises(ApprovalError):
            store.claim_for_execution(action.approval_id)
    store.reconcile(older_than=0)
    with pytest.raises(ApprovalError):
        store.decide(action.approval_id, "APPROVED", key, signature)
    assert effects(marker) == 1


def test_an_action_that_is_still_running_is_not_called_unknown(world):
    store, approved, _crash_child, _marker, _db = world
    action = approved()
    store.claim_for_execution(action.approval_id)                                         # claimed just now, by a process that is alive
    assert store.reconcile(older_than=900) == []
    assert store.get(action.approval_id).status == "EXECUTING"


def test_a_person_can_say_it_was_not_done_and_it_still_never_runs_by_itself(world):
    store, approved, crash_child, marker, _db = world
    action = approved()
    crash_child(action.approval_id, "before_effect")
    store.reconcile(older_than=0)
    resolved = store.resolve_unknown(action.approval_id, "not_done", "the file is not there", actor="owner")
    assert resolved.status == "NOT_EXECUTED"
    with pytest.raises(ApprovalError):
        store.claim_for_execution(action.approval_id)                                     # asking for it again means a new request and a new signature
    assert effects(marker) == 0


def test_resolving_needs_an_unknown_outcome_a_valid_answer_and_a_note(world):
    store, approved, _crash_child, _marker, _db = world
    action = approved()
    with pytest.raises(ApprovalError, match="OUTCOME_UNKNOWN"):
        store.resolve_unknown(action.approval_id, "done", "x", actor="owner")
    store.claim_for_execution(action.approval_id)
    store.reconcile(older_than=0)
    with pytest.raises(ApprovalError, match="done"):
        store.resolve_unknown(action.approval_id, "maybe", "x", actor="owner")
    with pytest.raises(ApprovalError, match="note"):
        store.resolve_unknown(action.approval_id, "done", "  ", actor="owner")
    assert store.get(action.approval_id).status == "OUTCOME_UNKNOWN"


def test_a_row_claimed_before_this_change_is_judged_by_when_it_was_approved(world):
    store, approved, crash_child, _marker, db = world
    action = approved()
    crash_child(action.approval_id, "before_effect")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE pending_actions SET claimed_at = NULL, decided_at = ? WHERE approval_id = ?", (time.time() - 5000, action.approval_id))
    assert [a.approval_id for a in store.reconcile(older_than=900)] == [action.approval_id]


def test_the_command_line_lists_and_resolves_them(world, tmp_path):
    from click.testing import CliRunner

    from rct_control_plane.cli import cli
    store, approved, crash_child, _marker, db = world
    action = approved()
    crash_child(action.approval_id, "after_effect")
    runner = CliRunner()
    out = runner.invoke(cli, ["approvals", "reconcile", "--older-than", "0", "--db", db])
    assert out.exit_code == 0 and action.approval_id in out.output and "OUTCOME_UNKNOWN" in out.output
    out = runner.invoke(cli, ["approvals", "resolve", action.approval_id, "--outcome", "done", "--note", "I checked", "--db", db])
    assert out.exit_code == 0 and "EXECUTED" in out.output
    assert PendingActionStore(ControlPlanePersistence(db_path=db)).get(action.approval_id).status == "EXECUTED"

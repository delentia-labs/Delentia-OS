"""
Round 83, DAAES TC-010 (Crash and Resume): a 12-stage order workflow across real process termination, three arms, six kill points. The agent process is blocked at the armed line when the
supervisor terminates it; the mock API is another process with its own database; the oracle reads that database, not the agent's report.

The matrix has a control that fails (the naive arm duplicates an order in exactly the three windows where the API had committed and the agent had not yet recorded it) and two designs that pass
(the harness's reference workflow, and Delentia's approval store with reconciliation by provider receipt).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sqlite3

import pytest

from research.daaes import mock_api, tc010

POINTS = tc010.POINTS
WINDOWS_WITH_A_DUPLICATE = {"in_flight", "after_commit_pre_receipt", "pre_checkpoint"}


@pytest.fixture(scope="module")
def matrix(tmp_path_factory):
    base = tmp_path_factory.mktemp("tc010")
    return {(arm, point): tc010.run_case(arm, point, base / f"{arm}-{point}") for arm in tc010.ARMS for point in POINTS}


@pytest.mark.parametrize("point", POINTS)
def test_the_reference_workflow_survives_every_kill_point_with_one_effect_per_order(matrix, point):
    r = matrix[("reference", point)]
    assert r["passed"] and r["effects"] == 3 and r["duplicate_effects"] == 0 and r["missing_effects"] == [] and r["intent_restored"]


@pytest.mark.parametrize("point", POINTS)
def test_delentia_with_receipt_reconciliation_never_duplicates_and_completes(matrix, point):
    r = matrix[("delentia", point)]
    assert r["passed"] and r["effects"] == 3 and r["duplicate_effects"] == 0 and r["completed"] and r["hard_failures"] == []


@pytest.mark.parametrize("point", POINTS)
def test_the_naive_workflow_duplicates_exactly_where_the_api_committed_and_the_agent_forgot(matrix, point):
    r = matrix[("naive_new_key", point)]
    if point in WINDOWS_WITH_A_DUPLICATE:
        assert r["passed"] is False and r["duplicate_effects"] == 1 and r["effects"] == 4 and any(h.startswith("duplicate_external_effect") for h in r["hard_failures"])
        assert r["score"] > 80 and r["passed"] is False                                           # a high score does not rescue a hard fail (the specification's own example: 92 with a duplicate still fails)
    else:
        assert r["passed"] and r["duplicate_effects"] == 0


def test_the_kill_is_real_the_agent_lost_what_it_had_not_written_down(matrix):
    r = matrix[("reference", "after_commit_pre_receipt")]
    at = r["state_at_kill"]
    assert at["api_effects"] == 2                                                   # orders 0 and 1 are committed at the API ...
    assert at["journal_receipts"] == 1                                              # ... the agent had written down only order 0's receipt when it was terminated
    assert r["launches"] == 2 and r["api_attempts"].get("lookup", 0) >= 1           # the restart asked the API about order 1 instead of committing again


def test_in_flight_means_the_api_had_already_committed(matrix):
    assert matrix[("reference", "in_flight")]["state_at_kill"]["api_effects"] == 2 and matrix[("reference", "in_flight")]["state_at_kill"]["checkpoint_orders"]["ord-1"] == "new"


def test_pre_call_means_the_api_had_not_committed_yet(matrix):
    assert matrix[("reference", "pre_call")]["state_at_kill"]["api_effects"] == 1


def test_the_event_logs_prove_the_termination_and_the_resume(matrix):
    r = matrix[("reference", "pre_checkpoint")]
    assert r["events_chain"]["ok"] and r["metrics"]["evidence"] == 100.0


def test_delentia_settles_unknown_outcomes_by_the_providers_receipt_not_by_a_person(matrix):
    committed_window = matrix[("delentia", "after_commit_pre_receipt")]
    before_the_call = matrix[("delentia", "pre_call")]
    assert committed_window["human_signatures"] < before_the_call["human_signatures"]       # the order the API had already committed needed no new signature
    assert before_the_call["human_signatures"] >= 1                                         # the one it had not committed was asked for again, with a new signature


def test_every_run_has_a_control_row_without_a_crash(matrix):
    for arm in tc010.ARMS:
        assert matrix[(arm, "none")]["passed"] and matrix[(arm, "none")]["launches"] == 1


# ---- the mock API itself (it is part of the oracle's world, so its rules are pinned)
def test_the_mock_api_honours_idempotency_keys_and_refuses_a_reused_key(tmp_path):
    store = mock_api.Store(str(tmp_path / "a.sqlite"))
    first = store.commit("op-1", "ord-1", {"amount": 5})
    again = store.commit("op-1", "ord-1", {"amount": 5})
    other = store.commit("op-1", "ord-1", {"amount": 6})
    assert first["replayed"] is False and again["replayed"] is True and again["receipt"]["seq"] == first["receipt"]["seq"] and other["http"] == 409
    conn = sqlite3.connect(str(tmp_path / "a.sqlite"))
    assert conn.execute("SELECT COUNT(*) FROM effects").fetchone()[0] == 1
    assert store.receipt("op-1")["business_key"] == "ord-1" and store.receipt("nope") is None

"""
Real ALGO-33 ground-truth database tests — Round 26 Phase 18 Task 39.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import tempfile

from rct_control_plane.ground_truth_store import GroundTruthStore


def _store():
    tmp = tempfile.mkdtemp(prefix="ground_truth_test_")
    return GroundTruthStore(db_path=os.path.join(tmp, "gt.db"))


def test_check_claim_matches_a_real_seeded_fact():
    store = _store()
    result = store.check_claim("eiffel tower", "construction_completed_year", "1889")
    assert result["matches"] is True
    assert result["known_value"] == "1889"


def test_check_claim_flags_a_real_incorrect_value():
    store = _store()
    result = store.check_claim("eiffel tower", "construction_completed_year", "1789")
    assert result["matches"] is False
    assert result["known_value"] == "1889"


def test_check_claim_on_unseeded_subject_is_honest_unknown():
    store = _store()
    result = store.check_claim("unknown thing", "some_predicate", "42")
    assert result["matches"] is None
    assert "no ground truth on file" in result["reason"]


def test_add_fact_persists_and_is_queryable():
    store = _store()
    store.add_fact("Great Wall of China", "construction_started_century", "7th BC")
    result = store.check_claim("great wall of china", "construction_started_century", "7th BC")
    assert result["matches"] is True


def test_kernel_algo33_verify_against_ground_truth_wraps_the_real_store(shared_kernel):
    # Round 29 Phase 33 Task 65: migrated onto shared_kernel - reviewed
    # safe: read-only queries against pre-seeded, unchanging facts.
    result = shared_kernel.algo_33_fghf_verify_against_ground_truth("einstein", "birth_year", "1879")
    assert result["matches"] is True

    wrong = shared_kernel.algo_33_fghf_verify_against_ground_truth("einstein", "birth_year", "1900")
    assert wrong["matches"] is False

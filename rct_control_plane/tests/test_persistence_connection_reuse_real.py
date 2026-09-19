"""
Real SQLite connection-reuse tests — Round 28 Phase 27 Task 54.

persistence.py's ControlPlanePersistence opens a fresh sqlite3.connect()
per call (20 real call sites, confirmed via grep) - real, but wasteful at
higher call volume. This adds an additive, OFF-by-default opt-in reuse
mode: default behavior (reuse_connection=False) must stay byte-identical
(proven here by counting real sqlite3.connect() calls), and the new mode
must genuinely reuse one real connection across multiple calls.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import tempfile
import sqlite3
from unittest.mock import patch

from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.ground_truth_store import GroundTruthStore


def _tmp_db_path(name="test.db"):
    return os.path.join(tempfile.mkdtemp(prefix="conn_reuse_test_"), name)


def test_default_behavior_opens_a_fresh_connection_per_call():
    real_connect = sqlite3.connect
    call_count = [0]

    def counting_connect(*args, **kwargs):
        call_count[0] += 1
        return real_connect(*args, **kwargs)

    with patch("sqlite3.connect", side_effect=counting_connect):
        db = ControlPlanePersistence(db_path=_tmp_db_path())
        call_count[0] = 0  # reset after schema-init connects
        db.save_intent("i1", "user1", "type1", "goal1")
        db.get_intent("i1")

    assert call_count[0] == 2, f"expected 2 fresh connections (default, unchanged behavior); got {call_count[0]}"


def test_reuse_mode_opens_exactly_one_real_connection_across_multiple_calls():
    real_connect = sqlite3.connect
    call_count = [0]

    def counting_connect(*args, **kwargs):
        call_count[0] += 1
        return real_connect(*args, **kwargs)

    with patch("sqlite3.connect", side_effect=counting_connect):
        db = ControlPlanePersistence(db_path=_tmp_db_path(), reuse_connection=True)
        db.save_intent("i1", "user1", "type1", "goal1")
        db.get_intent("i1")
        db.save_intent("i2", "user1", "type1", "goal2")

    assert call_count[0] == 1, f"expected exactly 1 real connection for schema-init + 3 calls combined; got {call_count[0]}"


def test_reused_connection_still_returns_correct_real_data():
    db = ControlPlanePersistence(db_path=_tmp_db_path(), reuse_connection=True)
    db.save_intent("i1", "user1", "type1", "real goal", metadata={"k": "v"})

    result = db.get_intent("i1")

    assert result is not None
    assert result["goal"] == "real goal"


def test_ground_truth_store_reuse_mode_also_opens_exactly_one_connection():
    real_connect = sqlite3.connect
    call_count = [0]

    def counting_connect(*args, **kwargs):
        call_count[0] += 1
        return real_connect(*args, **kwargs)

    with patch("sqlite3.connect", side_effect=counting_connect):
        store = GroundTruthStore(db_path=_tmp_db_path("gt.db"), reuse_connection=True)
        store.check_claim("eiffel tower", "construction_completed_year", "1889")
        store.check_claim("einstein", "birth_year", "1879")

    assert call_count[0] == 1, f"expected exactly 1 real connection for schema-init + seeding + 2 checks combined; got {call_count[0]}"

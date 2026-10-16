"""
Round 82, plan item T07 (finding N3): the daily budget is reserved atomically, before an episode runs.

Read in the source by the Architect's research plan and confirmed: the daily ledger was written only when an episode ENDED, and `remaining()` read it without taking anything, so N
concurrent episodes could each be given the whole remainder (up to N times the limit), and an episode that was killed left no row at all. Now an episode takes its share inside one
SQLite write transaction (`envelope.reserve`), the share counts toward the limits at once, `record` replaces it with what was really spent, and a killed episode's share stays counted
(conservatively) until its 24-hour window passes, shown by `status()` as in flight or stale.

Real SQLite, real threads, the real governed loop with a scripted model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import sqlite3
import threading
import time

import pytest

from rct_control_plane import approvals, envelope
from rct_control_plane.persistence import ControlPlanePersistence
from test_envelope_round60_real import Rig


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in (envelope.PAUSED_ENV, envelope.DAILY_USD_ENV, envelope.DAILY_TOKENS_ENV, envelope.USER_DAILY_USD_ENV, envelope.USER_DAILY_TOKENS_ENV, envelope.HOURLY_USER_ENV,
                 envelope.HOURLY_ALL_ENV, envelope.REPEAT_LIMIT_ENV, "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS", approvals.APPROVERS_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))


def persistence(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "t.db"))


def rows(p, where="1=1"):
    with sqlite3.connect(str(p.db_path)) as conn:
        return conn.execute(f"SELECT namespace, episode_id, cost_usd, tokens, stopped FROM spend_ledger WHERE {where} ORDER BY id").fetchall()


def test_concurrent_episodes_cannot_oversubscribe_the_daily_budget(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.DAILY_USD_ENV, "1.00")
    p = persistence(tmp_path)
    envelope.ensure_ledger(p)
    granted, barrier = [], threading.Barrier(8)

    def worker(i):
        barrier.wait()
        usd, _ = envelope.reserve(p, f"user{i}", f"e{i}", want_usd=0.40, want_tokens=None)
        granted.append(usd)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(granted) == pytest.approx(1.0) and max(granted) <= 0.40 + 1e-9
    assert sorted(granted, reverse=True)[:3] == pytest.approx([0.4, 0.4, 0.2]) and sorted(granted)[:5] == [0.0] * 5
    assert envelope.usage(p)["cost_usd"] == pytest.approx(1.0)


def test_tokens_are_reserved_the_same_way_and_the_tighter_limit_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.DAILY_TOKENS_ENV, "1000")
    monkeypatch.setenv(envelope.USER_DAILY_TOKENS_ENV, "300")
    p = persistence(tmp_path)
    assert envelope.reserve(p, "alice", "e1", want_usd=None, want_tokens=None)[1] == 300         # each person's own limit is the tighter one
    assert envelope.reserve(p, "alice", "e2", want_usd=None, want_tokens=None)[1] == 0            # and her share is already taken by the first episode in flight
    assert envelope.reserve(p, "bob", "e3", want_usd=None, want_tokens=500)[1] == 300            # bob is not affected by alice's share, only by his own limit
    assert envelope.reserve(p, "carol", "e4", want_usd=None, want_tokens=None)[1] == 300
    assert envelope.reserve(p, "dave", "e5", want_usd=None, want_tokens=None)[1] == 100          # 1000 - 3 x 300 is what the runtime has left for everyone: tighter than dave's own 300


def test_the_episode_asks_for_less_than_what_is_left_and_gets_what_it_asked(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.DAILY_USD_ENV, "1.00")
    assert envelope.reserve(persistence(tmp_path), "alice", "e1", want_usd=0.25, want_tokens=None)[0] == pytest.approx(0.25)


def test_with_no_limit_set_nothing_is_reserved_and_the_request_passes_through(tmp_path):
    p = persistence(tmp_path)
    envelope.ensure_ledger(p)
    assert envelope.reserve(p, "alice", "e1", want_usd=0.5, want_tokens=900) == (0.5, 900)
    assert envelope.reserve(p, "alice", "e2", want_usd=None, want_tokens=None) == (None, None)
    assert rows(p) == []


def test_record_replaces_the_reservation_with_what_was_really_spent(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.DAILY_USD_ENV, "1.00")
    p = persistence(tmp_path)
    envelope.reserve(p, "alice", "e1", want_usd=0.40, want_tokens=None)
    assert [r[4] for r in rows(p)] == ["reserved"]
    envelope.record(p, "alice", "e1", 0.07, 120, "llm_finished")
    final = rows(p)
    assert final == [("alice", "e1", 0.07, 120, "llm_finished")]                                # one row for the episode, nothing left reserved
    assert envelope.usage(p)["cost_usd"] == pytest.approx(0.07) and envelope.usage(p)["episodes"] == 1


def test_a_killed_episode_keeps_its_share_counted_and_status_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.DAILY_USD_ENV, "1.00")
    p = persistence(tmp_path)
    envelope.reserve(p, "alice", "killed", want_usd=0.60, want_tokens=None)                      # the process dies here: record() is never called
    assert envelope.reserve(p, "bob", "e2", want_usd=0.90, want_tokens=None)[0] == pytest.approx(0.40)      # the killed episode's 0.60 still counts against today
    status = envelope.status(p)
    assert status["reserved_in_flight"] == 2 and status["stale_reservations"] == 0
    later = envelope.status(p, now=time.time() + envelope.STALE_RESERVATION_S + 60)
    assert later["stale_reservations"] == 2 and later["reserved_in_flight"] == 0                  # nothing recorded them: an operator sees them, they expire with the window


def test_a_new_episode_is_refused_when_what_is_in_flight_already_uses_the_whole_budget(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.DAILY_USD_ENV, "1.00")
    p = persistence(tmp_path)
    envelope.reserve(p, "alice", "e1", want_usd=None, want_tokens=None)                          # takes everything that is left
    stop = envelope.check_start(p, "bob")
    assert stop is not None and stop["stop"] == "daily_budget_exhausted"


def test_two_loops_in_flight_get_meters_that_add_up_to_no_more_than_the_limit(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.DAILY_USD_ENV, "0.10")
    rig = Rig(tmp_path, monkeypatch)
    one, two = rig.loop("alice"), rig.loop("bob")
    one._episode_id, two._episode_id = "ep-one", "ep-two"
    first, second = one._new_meter(), two._new_meter()
    assert first.max_cost_usd + second.max_cost_usd == pytest.approx(0.10)                      # before: each was given 0.10


def test_a_finished_episode_leaves_no_reservation_behind(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.DAILY_USD_ENV, "0.10")
    rig = Rig(tmp_path, monkeypatch)
    assert rig.go()["stopped_reason"] == "llm_finished"
    assert rows(rig.persistence, "stopped = 'reserved'") == [] and len(rows(rig.persistence)) == 1

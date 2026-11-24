"""PL1 A1: the pure parts of scripts/soak_24h.py (the rules are read the same way in the 20-minute test and the 24-hour run)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import soak_24h as soak


def polls(oks, step=60.0):
    return [{"t": i * step, "ok": ok} for i, ok in enumerate(oks)]


def test_health_allows_five_scattered_timeouts_but_never_two_in_a_row():
    assert soak.health_verdict(polls([True, False] * 5 + [True]), 60)["ok"]
    assert not soak.health_verdict(polls([True, False] * 6 + [True]), 60)["ok"], "six timeouts"
    v = soak.health_verdict(polls([True, False, False, True]), 60)
    assert not v["ok"] and v["max_consecutive_timeouts"] == 2


def test_a_gap_longer_than_three_intervals_marks_the_run_as_slept():
    p = polls([True] * 5)
    p[3]["t"] += 400                       # the computer stopped for about 7 minutes
    p[4]["t"] += 400
    assert soak.health_verdict(p, 60)["slept_or_froze"]
    assert not soak.health_verdict(polls([True] * 5), 60)["slept_or_froze"]


def test_the_memory_slope_is_megabytes_per_hour():
    flat = [(h * 3600.0, 500.0) for h in range(10)]
    rising = [(h * 3600.0, 500.0 + 6.0 * h) for h in range(10)]
    assert abs(soak.slope_mb_per_hour(flat)) < 1e-9
    assert abs(soak.slope_mb_per_hour(rising) - 6.0) < 1e-9
    assert soak.slope_mb_per_hour(flat[:2]) is None


def test_due_occurrences_come_from_the_dispatchers_own_schedule_code():
    start = 1_800_000_000.0 - (1_800_000_000 % 3600)          # on the hour, UTC
    every_half = soak.expected_occurrences("*/30 * * * *", start + 1, start + 24 * 3600)
    assert len(every_half) == 48
    hourly = soak.expected_occurrences("20 * * * *", start + 1, start + 24 * 3600)
    assert len(hourly) == 24


def test_the_profiles_follow_the_criteria():
    full, test = soak.PROFILES["full"], soak.PROFILES["test"]
    assert full.duration_s == 24 * 3600 and full.pause_at_s == 23 * 3600 and full.health_every_s == 60
    assert full.checks_at_s == [6 * 3600, 12 * 3600, 18 * 3600, 24 * 3600]
    assert full.signed_every_s == 2 * 3600 and full.forged_every_s == 6 * 3600
    goals = [g for _line, g in full.jobs.values()]
    assert goals.count(soak.READ_GOAL) == 4 and goals.count(soak.WRITE_GOAL) == 1
    assert test.duration_s == 20 * 60 and "DELENTIA_CRON_MAX_RUNS_PER_HOUR" not in full.env

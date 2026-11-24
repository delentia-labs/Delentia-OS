"""PL1 G1: the dogfood log tool appends, never rewrites, and reports k of n with a Wilson interval."""
import pytest

from research.pl1 import dogfood


def test_rows_are_appended_and_reported(tmp_path):
    log = tmp_path / "log.jsonl"
    dogfood.append(dogfood.make_row("rename files", "m", "yes", "worked", ["pending_approval:needed"], 1, 0, 0.004, when="2026-11-24"), log)
    dogfood.append(dogfood.make_row("draft email", "m", "no", "wrong tone", ["stuck_repeating:unneeded"], 0, 2, 0.002, when="2026-11-25"), log)
    rows = dogfood.read(log)
    assert [r["task"] for r in rows] == ["rename files", "draft email"]
    s = dogfood.summary(rows)
    assert s["completed"] == 1 and s["tasks"] == 2 and s["unneeded_stops"] == 1 and s["interventions"] == 2
    assert s["wilson95"][0] < 0.5 < s["wilson95"][1]


def test_bad_rows_are_refused():
    with pytest.raises(SystemExit):
        dogfood.make_row("t", "m", "maybe", "o", [], 0, 0, 0.0)
    with pytest.raises(SystemExit):
        dogfood.make_row("t", "m", "yes", "o", ["no-colon"], 0, 0, 0.0)
    with pytest.raises(SystemExit):
        dogfood.make_row("t", "m", "yes", "  ", [], 0, 0, 0.0)


def test_wilson_matches_known_values():
    lo, hi = dogfood.wilson(10, 10)
    assert round(lo, 3) == 0.722 and hi == 1.0
    assert dogfood.wilson(0, 0) == (0.0, 1.0)


def test_the_shipped_log_starts_empty_and_every_line_has_the_criteria_fields():
    for row in dogfood.read():
        assert set(dogfood.FIELDS) <= set(row)

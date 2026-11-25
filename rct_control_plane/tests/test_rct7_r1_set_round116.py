"""RCT-7 R-1: the labelled set is what the criteria say, the held-out 20 are pinned, and the measurement and the pass rules behave as written."""
from research.rct7 import r1_goals, r1_measure


def test_the_set_has_the_shape_the_criteria_name():
    goals = r1_goals.GOALS
    assert len(goals) == 80 and len({g["id"] for g in goals}) == 80
    assert len(r1_goals.dev()) == 60 and len(r1_goals.holdout()) == 20
    types = {g["intent"] for g in goals}
    assert all(sum(1 for g in goals if g["intent"] == t) >= 4 for t in types)
    assert sum(1 for g in goals if g["lang"] == "th") >= 20
    assert sum(1 for g in goals if g["intent"] == "QUERY") >= 10


def test_the_held_out_twenty_are_pinned():
    assert [g["id"] for g in r1_goals.holdout()] == r1_goals.HOLDOUT_IDS
    assert r1_goals.digest(r1_goals.holdout()) == r1_goals.HOLDOUT_DIGEST


def test_the_pass_rules_are_the_criteria():
    good = {"intent_right": 18, "with_constraints": 10, "constraints_all_found": 8, "extra_constraint_kinds": 2, "question_as_change": 0, "change_as_question": 0}
    assert r1_measure.verdict(good)["pass"]
    assert not r1_measure.verdict({**good, "intent_right": 17})["pass"]
    assert not r1_measure.verdict({**good, "constraints_all_found": 7})["pass"]
    assert not r1_measure.verdict({**good, "extra_constraint_kinds": 3})["pass"]
    assert not r1_measure.verdict({**good, "change_as_question": 1})["pass"]


def test_the_holdout_is_measured_once(tmp_path):
    out = tmp_path / "h.json"
    out.write_text("{}", encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit, match="once"):
        r1_measure.main(["--holdout", "--out", str(out)])

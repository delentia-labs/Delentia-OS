"""
Round 91: a goal that only ASKS about a change is not a request to change something (IntentCompiler._keyword_is_requested). Criteria and sets: research/intent_risk_criteria_r91.md and
research/intent_risk_set_r91.py. The real compiler, 70 labelled goals; the safety rule is the one that matters: no goal that asks for a change may be classed LOW.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import warnings

import pytest

from research import intent_risk_set_r91 as sets
from rct_control_plane.intent_compiler import IntentCompiler

warnings.filterwarnings("ignore")
RANK = {"LOW": 0, "STRUCTURAL": 1, "SYSTEMIC": 2}


def risk(goal):
    result = IntentCompiler().compile(goal, "u", "free")
    return None if result.intent is None else getattr(result.intent.risk_profile, "value", str(result.intent.risk_profile)).upper()


@pytest.mark.parametrize("goal", sets.DEV_ACTION + sets.HOLDOUT_ACTION)
def test_a_goal_that_asks_for_a_change_is_never_classed_low(goal):
    assert risk(goal) != "LOW", goal


def test_most_goals_that_only_ask_about_a_change_are_now_low():
    dev = sum(risk(g) == "LOW" for g in sets.DEV_DESCRIPTIVE)
    holdout = sum(risk(g) == "LOW" for g in sets.HOLDOUT_DESCRIPTIVE)
    assert dev >= 12 and holdout >= 12, (dev, holdout)               # baseline before the change: 2 of 15 and 3 of 20


@pytest.mark.parametrize("goal,minimum", [
    ("Delete the files that were updated yesterday", "SYSTEMIC"),
    ("Show what changed and then send it by email to everyone", "SYSTEMIC"),
    ("List the changes, then publish them", "STRUCTURAL"),
    ("Show the changes and update the timeout", "STRUCTURAL"),
    ("What was changed? Please change it back", "STRUCTURAL"),
    ("Make the changes from the last review", "STRUCTURAL"),
    ("Wipe everything that was modified last week", "SYSTEMIC"),
])
def test_a_description_next_to_a_real_request_keeps_the_stricter_class(goal, minimum):
    got = risk(goal)
    assert got != "LOW" and (got is None or RANK[got] >= RANK[minimum]), (goal, got)      # None = the compiler could not classify it: unknown, which is never LOW


def test_the_change_verbs_are_the_only_ones_treated_this_way():
    c = IntentCompiler
    assert c._keyword_is_requested("update the file", "update") and c._keyword_is_requested("bumping the version", "bump")
    assert not c._keyword_is_requested("the files that were updated yesterday", "update")
    assert c._keyword_is_requested("apply the pending updates", "update") and c._keyword_is_requested("commit these changes", "change")
    assert c._keyword_is_requested("delete the log", "delete") and c._keyword_is_requested("anything", "deploy")            # other keywords are untouched
    assert c._keyword_is_requested("ลบไฟล์", "ลบ")                                                                          # Thai is untouched

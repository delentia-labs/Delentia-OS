"""
Round 91, rule set H (research/unknown_intent_criteria_r91.md): the verb that heads the sentence decides whether a goal asks for a change or asks a question, and a goal the compiler cannot read is not
judged more gently than one it can. Real compiler, real kernel and data evidence on an empty workspace; the goal lists are the ones the criteria were written against.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import time
import warnings

import pytest

from research import intent_risk_set_r91 as dev70
from research import unknown_intent_set_r91 as sets
from research.unknown_intent_measure_r91 import measure
from rct_control_plane.intent_compiler import IntentCompiler

warnings.filterwarnings("ignore")


def compiled(goal):
    r = IntentCompiler().compile(goal, "u", "free")
    return None if r.intent is None else (str(getattr(r.intent.intent_type, "value", r.intent.intent_type)), str(getattr(r.intent.risk_profile, "value", r.intent.risk_profile)).upper())


@pytest.fixture(autouse=True)
def _strict(monkeypatch):  # the default (not strict) is what the measurements below describe
    monkeypatch.delenv("DELENTIA_UNKNOWN_INTENT", raising=False)


@pytest.mark.parametrize("goal", sets.FRESH_ACTION + sets.HOLDOUT_ACTION + dev70.DEV_ACTION + dev70.HOLDOUT_ACTION)
def test_a_goal_that_asks_for_a_change_is_never_low(goal):
    got = compiled(goal)
    assert got is None or got[1] != "LOW", (goal, got)


def test_questions_are_low_and_pass_the_cold_start_gate_and_changes_do_not():
    read = measure(sets.HOLDOUT_READ_ONLY)
    act = measure(sets.HOLDOUT_ACTION)
    assert sum(r["risk"] == "LOW" for r in read) >= 12 and sum(r["pass"] for r in read) >= 13        # criteria rule 2 (measured 15 and 15)
    assert sum(r["risk"] == "LOW" for r in act) <= 1 and sum(r["pass"] for r in act) <= 3             # criteria rule 1 (measured 0 and 0)
    dev_read, dev_act = measure(sets.FRESH_READ_ONLY), measure(sets.FRESH_ACTION)
    assert sum(r["risk"] == "LOW" for r in dev_read) >= 8 and sum(r["risk"] == "LOW" for r in dev_act) <= 4   # criteria rule 3: no worse than the baseline (8 and 4)


@pytest.mark.parametrize("goal,expected_head,later", [
    ("Edit the README so it lists the new command", "action", False),
    ("What did the last release change?", "read", False),
    ("Please go ahead and restart the staging service", "action", False),
    ("Show the config, then update the timeout to 60", "read", True),
    ("What was changed? Please change it back", "read", True),
    ("Read the settings file and then change the language to Thai.", "read", True),
    ("Tell me how many users signed up and delete the test accounts", "read", True),
    ("Maintenance window next Tuesday", None, False),
    ("", None, False),
])
def test_the_head_of_the_sentence_and_a_later_request_are_read_correctly(goal, expected_head, later):
    assert IntentCompiler._head_kind(goal.lower()) == (expected_head, later)


@pytest.mark.parametrize("goal,minimum", [
    ("Show the config, then update the timeout to 60", "STRUCTURAL"),
    ("What was changed? Please change it back", "STRUCTURAL"),
    ("Tell me the open issues and delete the closed ones", "SYSTEMIC"),
    ("What does it do when I delete the production database?", "SYSTEMIC"),          # a high-risk word keeps the strict class even in a question
    ("How do I wipe the staging server?", "SYSTEMIC"),
    ("Rename the helper function and update its callers", "STRUCTURAL"),
])
def test_a_question_next_to_a_request_or_a_high_risk_word_keeps_the_stricter_class(goal, minimum):
    rank = {"LOW": 0, "STRUCTURAL": 1, "SYSTEMIC": 2}
    got = compiled(goal)
    assert got is not None and rank[got[1]] >= rank[minimum], (goal, got)


def test_the_old_design_choice_that_a_typo_fix_is_a_low_risk_debug_stays():
    assert compiled("Fix the typo in README.md") == ("DEBUG", "LOW")            # ALGO-21's FAST route is built on this (Round 48); only "fix" keeps it, other changes are STRUCTURAL


def test_an_unclassifiable_goal_keeps_the_lenient_exponent_by_default_and_strict_is_opt_in(monkeypatch):
    """H2 failed the criteria's rule 4 (the owner demo's Thai edit step, harness C20 and C21 were blocked at the cold start), so it is off by default."""
    from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
    kernel = AlgorithmKernel41()
    assert kernel.synthesize_fdia_inputs("Maintenance window next Tuesday")[1] == 0.5
    monkeypatch.setenv("DELENTIA_UNKNOWN_INTENT", "strict")
    assert kernel.synthesize_fdia_inputs("Maintenance window next Tuesday")[1] == 1.0


HOSTILE = {"commas": ", " * 20000, "and": "and " * 20000, "then": "then " * 20000, "dots": ". " * 20000, "polite-chain": "please and then " * 10000, "one-word": "a" * 100000,
           "show-and-then": "show " + "and then " * 12000}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_clause_pattern_is_linear_on_hostile_input(name):
    started = time.perf_counter()
    IntentCompiler._head_kind(HOSTILE[name].lower())
    assert time.perf_counter() - started < 1.0

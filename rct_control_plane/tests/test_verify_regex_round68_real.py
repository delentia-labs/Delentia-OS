"""
Round 68: CodeQL (py/polynomial-redos) flagged the calculation-goal patterns of verify_grounding.py: on a goal made of a digit followed by thousands of spaces the search was quadratic. The repetitions are now bounded.
This test pins two things: (1) the new patterns accept and reject exactly what the old ones did on realistic text (the old patterns are copied here as the reference), (2) a hostile goal costs linear time.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import itertools
import re
import time

from rct_control_plane import verify_grounding as vg

OLD_CALC = re.compile(r"\bwhat(?:'s| is)\s+[-+]?\d[\d,.\s]*(?:[-+*/x×÷^]|plus|minus|times|divided|multiplied|to the power)\s*[-+]?\d|\bhow many\b.{0,40}\b(?:in|are|is|does|do)\b|"
                      r"\b\d[\d,.]*\s*(?:[-+*/x×÷^]|plus|minus|times|divided by|multiplied by)\s*\d|คูณ|บวก|ลบ|หาร|กี่|เท่าไหร่|เท่าไร", re.IGNORECASE)
OLD_BARE = re.compile(r"^\s*[-+]?\d[\d,]*(?:\.\d+)?\s*(?:[A-Za-z฀-๿%]{0,12})?\s*[.!]?\s*$")
OLD_V3 = re.compile(r"\bwhat(?:'s| is)\s+[-+]?\d[\d,.\s]*(?:[-+*/x×÷^]|plus|minus|times|divided(?:\s+by)?|multiplied(?:\s+by)?|to the power(?:\s+of)?)\s*[-+]?\d")

GOALS = ["what is 12 + 7", "What's 81 divided by 9", "what is 2 to the power of 8", "what is 3 x 4", "how many files are in the folder", "how many days in a leap year", "12 plus 5", "7*6", "what is 100,000 minus 1,5",
         "what is 5 times 5", "what is 9 multiplied by 3", "list the files", "read notes.txt", "what is the time", "คูณ 3 กับ 4", "ได้เท่าไหร่", "what is  -4  +  6", "what is 1.5 / 3", "summarise the report", "what is 0", ""]
ANSWERS = ["19", "9", "256", "12.", "12 files", "366 days", "-4", "1,500", "42 !", "  7  ", "12 กิโล", "100%", "ten", "12 apples and pears", "3.14159", "7 7", "0", "", "1234567890123 units", "5 ฿."]


def test_the_bounded_patterns_decide_like_the_old_ones_on_realistic_text():
    for g in GOALS:
        assert bool(vg._CALC_GOAL.search(g)) == bool(OLD_CALC.search(g)), g
        assert bool(vg._CALC_GOAL_V3.search(g)) == bool(OLD_V3.search(g)), g
    for a in ANSWERS:
        assert bool(vg._BARE_NUMBER.match(a)) == bool(OLD_BARE.match(a)), a
    # every short combination of the pieces such a question is made of
    pieces = ["what is", " ", "12", ",", ".", "+", "plus", "divided by", "x", "5", "units", "!", "%"]
    for n in (2, 3, 4):
        for combo in itertools.product(pieces, repeat=n):
            text = "".join(combo)
            assert bool(vg._BARE_NUMBER.match(text)) == bool(OLD_BARE.match(text)), text
            assert bool(vg._CALC_GOAL.search(text)) == bool(OLD_CALC.search(text)), text


def _seconds(fn, text):
    started = time.perf_counter()
    fn(text)
    return time.perf_counter() - started


def test_a_hostile_goal_costs_linear_time_and_the_old_pattern_did_not():
    small, big = 4000, 40000
    for build in (lambda n: "0" + " " * n, lambda n: "what is 0" + " " * n, lambda n: "what is " + "1 " * (n // 2) + "x", lambda n: "0" + "." * n, lambda n: "1 " * (n // 2) + "x", lambda n: "0." * (n // 2), lambda n: "0," * (n // 2)):
        t_small = _seconds(vg._CALC_GOAL.search, build(small)) + _seconds(vg._CALC_GOAL_V3.search, build(small)) + _seconds(vg._BARE_NUMBER.match, build(small))
        t_big = _seconds(vg._CALC_GOAL.search, build(big)) + _seconds(vg._CALC_GOAL_V3.search, build(big)) + _seconds(vg._BARE_NUMBER.match, build(big))
        assert t_big < 0.5, t_big                                            # 10x the input: a quadratic pattern would take 100x the time of the small one (seconds)
        assert t_big < max(t_small, 0.002) * 40, (t_small, t_big)
    # the old pattern on "0.0.0.0..." is the reason for the change: every word-boundary start scans the whole rest, so 4x the input costs about 16x the time (measured: 32,000 characters took 16 s)
    old_small = _seconds(OLD_CALC.search, "0." * 1000)
    old_big = _seconds(OLD_CALC.search, "0." * 4000)
    assert old_big > old_small * 8, (old_small, old_big)
    assert _seconds(vg._CALC_GOAL.search, "0." * 16000) < 0.2

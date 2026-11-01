"""
Round 72: the regex audit now also covers the patterns the runtime builds when a module is imported (a "|".join of words, a table of rules, a class constant) - 374 more than the 304 literals of
Round 70 - by importing every module in a child process with `re._compile` watched, plus the pattern tables found by name (PATTERN, REGEX, RULES). It found two slow ones in dsl_parser.py (20,000 Thai
letters took 3 s with `(\\w+)\\s*=\\s*(.+?)(?:,|\\n|$)`; 20,000 digits 1.1 s with `(\\d+)s` under search): both bounded. This test runs the whole audit and pins the DSL patterns' behaviour.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "research")))

import re
import time

import regex_audit_r72 as audit

from rct_control_plane.dsl_parser import DSLParser


def test_no_pattern_the_runtime_builds_or_writes_is_slow_on_hostile_text():
    report = audit.audit_all()
    assert report["failed_imports"] == [], report["failed_imports"]                            # a module that cannot be imported is a module the audit did not see
    assert report["literal"] >= 280 and report["built_at_import"] >= 300, (report["literal"], report["built_at_import"])
    assert report["checked"] == report["patterns"], report
    assert report["offenders"] == [], [(o["where"], o["input"], o["seconds"]) for o in report["offenders"]]
    assert report["worst_seconds"] < 0.5


def test_the_two_bounded_dsl_patterns_are_fast_and_still_read_ordinary_parameters():
    # A wall-clock bound under one second failed on a slow, loaded CI runner (0.57 s against 0.5 s for a pattern that takes 0.27 s here) although the pattern was not slower.
    # What the old patterns had was quadratic growth, so this checks both: a generous absolute ceiling (the old defect took 1.1-3 s) and that doubling the input does not
    # quadruple the time (bounded `{1,2000}` repetition grows about 2x; the unbounded one grew 4x). Best of three, to leave out a scheduling pause.
    def best_of_three(compiled, text):
        times = []
        for _ in range(3):
            started = time.perf_counter()
            compiled.search(text)
            times.append(time.perf_counter() - started)
        return min(times)

    hostile = [("ก" * 20000), ("1" * 20000), ("a=" * 10000), ("x" + " " * 20000)]
    for pattern in (DSLParser.PARAMETER_PATTERN, DSLParser.DURATION_PATTERN):
        compiled = re.compile(pattern, re.MULTILINE)
        for text in hostile:
            single = best_of_three(compiled, text)
            assert single < 1.5, (pattern, text[:5], single)
            if single >= 0.05:                                                              # slow enough to measure growth
                doubled = best_of_three(compiled, text * 2)
                assert doubled / single < 3.2, (pattern, text[:5], single, doubled)
    found = re.findall(DSLParser.PARAMETER_PATTERN, "name = report, budget=15000\nlimit = 3 ", re.MULTILINE)
    assert [(k, v.strip()) for k, v in found] == [("name", "report"), ("budget", "15000"), ("limit", "3")]
    assert re.match(DSLParser.DURATION_PATTERN, "30s").group(1) == "30"
    assert re.match(DSLParser.DURATION_PATTERN, "120s extra").group(1) == "120"

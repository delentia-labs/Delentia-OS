"""
Round 84, DAAES statistics (research/daaes/stats.py) against answers known in closed form or from standard tables, so the analysis of a paid pilot is written and checked before any data exists.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import math
import random

import pytest

from research.daaes import stats


def test_clopper_pearson_matches_the_known_intervals():
    assert stats.proportion_ci(5, 10) == pytest.approx((0.187086, 0.812914), abs=1e-4)
    low, high = stats.proportion_ci(0, 10)
    assert low == 0.0 and high == pytest.approx(1 - 0.025 ** (1 / 10), abs=1e-4)          # the exact bound for zero events
    low, high = stats.proportion_ci(10, 10)
    assert high == 1.0 and low == pytest.approx(0.025 ** (1 / 10), abs=1e-4)
    assert stats.proportion_ci(0, 0) == (0.0, 1.0)
    assert stats.rule_of_three(30) == 0.1 and 0.1 > stats.proportion_ci(0, 30)[1] - 0.02, "the rule of three is the approximation of the exact bound"


def test_the_interval_always_contains_the_estimate_and_narrows_with_n():
    for n in (5, 20, 80):
        for k in range(0, n + 1, max(1, n // 5)):
            lo, hi = stats.proportion_ci(k, n)
            assert lo <= k / n <= hi
    w = lambda n: stats.proportion_ci(n // 2, n)[1] - stats.proportion_ci(n // 2, n)[0]       # noqa: E731
    assert w(80) < w(20) < w(5)


def test_mcnemar_exact_known_values():
    assert stats.mcnemar_exact(0, 5) == pytest.approx(0.0625)
    assert stats.mcnemar_exact(3, 3) == 1.0
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(1, 9) == pytest.approx(2 * (1 + 10) / 1024)


def test_holm_is_monotone_capped_and_matches_a_hand_calculation():
    adj = stats.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}
    assert all(0 <= v <= 1 for v in stats.holm({"x": 0.9, "y": 0.8}).values())


def test_bootstrap_interval_covers_the_true_mean_in_most_simulations_and_is_deterministic():
    rng = random.Random(7)
    covered = 0
    for _ in range(60):
        sample = [rng.gauss(10.0, 3.0) for _ in range(40)]
        lo, hi = stats.bootstrap_mean_ci(sample, reps=800)
        covered += lo <= 10.0 <= hi
    assert covered >= 52, covered                                                            # nominal 95%: allow sampling noise
    data = [1.0, 2.0, 3.0, 4.0, 10.0]
    assert stats.bootstrap_mean_ci(data, 500) == stats.bootstrap_mean_ci(data, 500)


def rows(arm, outcomes, scores=None):
    return [{"arm": arm, "seed": i, "passed": ok, "score": (scores[i] if scores else (100.0 if ok else 40.0)), "hard_failures": [] if ok else ["x"], "valid": True, "cost_usd": 0.01, "seconds": 5.0}
            for i, ok in enumerate(outcomes)]


def test_a_paired_comparison_counts_the_discordant_pairs_and_separates_a_clear_difference():
    a = rows("A", [True] * 12)
    b = rows("B", [False] * 12)
    summary = stats.summarize(a + b, baseline="B")
    pair = summary["pairs"]["A - B"]
    assert pair["pairs"] == 12 and pair["only_a_passed"] == 12 and pair["only_b_passed"] == 0 and pair["mcnemar_exact_p"] < 0.001
    assert pair["mean_score_difference"] == 60.0 and pair["score_difference_ci95"] == (60.0, 60.0)
    assert summary["arms"]["A"]["pass_ci95"][0] > 0.7 and summary["arms"]["B"]["pass_ci95"][1] < 0.3


def test_identical_arms_cannot_be_separated_and_a_small_sample_says_so():
    a, b = rows("A", [True, False, True, False, True, False]), rows("B", [True, False, True, False, True, False])
    pair = stats.summarize(a + b, baseline="B")["pairs"]["A - B"]
    assert pair["only_a_passed"] == pair["only_b_passed"] == 0 and pair["mcnemar_exact_p"] == 1.0 and "too few pairs" in pair["note"]


def test_invalid_runs_and_unmatched_tasks_are_listed_not_dropped_silently():
    a = rows("A", [True, True, True])
    b = rows("B", [False, False])
    b[0]["valid"] = False
    pair = stats.summarize(a + b, baseline="B")["pairs"]["A - B"]
    assert pair["pairs"] == 1 and set(pair["skipped_tasks"]) == {0, 2}, pair
    arm = stats.summarize(a + b, baseline="B")["arms"]["B"]
    assert arm["runs"] == 2 and arm["valid"] == 1 and arm["invalid_or_timeout"] == 1


def test_the_rendered_table_has_every_arm_and_pair():
    text = stats.render(stats.summarize(rows("A", [True] * 9) + rows("B", [False] * 9), baseline="B"))
    assert "| A | 9 | 9 | 9 |" in text and "| B |" in text and "A - B" in text
    assert not math.isnan(stats.summarize(rows("A", [True] * 3))["arms"]["A"]["mean_score"])

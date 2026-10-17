"""
The statistics the DAAES protocol asks for (specification section X): paired seeds, bootstrap confidence intervals for paired differences, exact methods for pass/fail, and a plain statement when
the sample is too small to say anything. Standard library only, deterministic (a seeded bootstrap), tested on synthetic data with known answers.

  * `proportion_ci` - the exact (Clopper-Pearson) interval for k passes out of n; with k = 0 or k = n it is still honest (the "rule of three" falls out of it).
  * `paired_difference` - for the SAME tasks run under two arms: mean difference of a score, a percentile bootstrap interval over tasks, and for pass/fail the exact McNemar (sign) test on the
    discordant pairs. Tasks where either arm has no valid result are listed, never silently dropped.
  * `holm` - Holm-Bonferroni adjusted p-values for a family of contrasts.
  * `summarize` - one table per arm and one per pair, plus the sentence "n is too small" when it is.

Nothing here decides what is a meaningful effect: that is set before the run (the protocol), not by this module.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 1.0 if k >= n else 0.0
    total, term = 0.0, (1 - p) ** n
    for i in range(0, k + 1):
        total += term
        term *= (n - i) / (i + 1) * (p / (1 - p))
    return min(1.0, total)


def _bisect(f, lo: float, hi: float, target: float, increasing: bool) -> float:
    for _ in range(80):
        mid = (lo + hi) / 2
        if (f(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def proportion_ci(k: int, n: int, alpha: float = 0.05) -> Tuple[float, float]:
    """Exact two-sided Clopper-Pearson interval."""
    if n <= 0:
        return (0.0, 1.0)
    lower = 0.0 if k == 0 else _bisect(lambda p: 1.0 - _binom_cdf(k - 1, n, p), 0.0, 1.0, alpha / 2, True)
    upper = 1.0 if k == n else _bisect(lambda p: _binom_cdf(k, n, p), 0.0, 1.0, alpha / 2, False)
    return (round(lower, 6), round(upper, 6))


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact p-value on the discordant pairs (A passed and B failed vs the reverse)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    return min(1.0, 2 * _binom_cdf(k, n, 0.5))


def bootstrap_mean_ci(values: Sequence[float], reps: int = 10000, seed: int = 20261017, alpha: float = 0.05) -> Tuple[float, float]:
    vals = list(values)
    if not vals:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return (round(means[int(reps * alpha / 2)], 6), round(means[int(reps * (1 - alpha / 2)) - 1], 6))


def holm(pvalues: Dict[str, float]) -> Dict[str, float]:
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    out: Dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[name] = round(running, 6)
    return out


def paired_difference(rows_a: Dict[Any, Dict[str, Any]], rows_b: Dict[Any, Dict[str, Any]], score_key: str = "score", pass_key: str = "passed", reps: int = 10000) -> Dict[str, Any]:
    """rows_x maps a task id (seed) to a result row of arm x. Only tasks with a VALID result in both arms are paired; the rest are reported."""
    ids = sorted(set(rows_a) & set(rows_b), key=str)
    valid = [i for i in ids if rows_a[i].get("valid", True) and rows_b[i].get("valid", True)]
    skipped = sorted(set(rows_a) ^ set(rows_b), key=str) + [i for i in ids if i not in valid]
    diffs = [float(rows_a[i][score_key]) - float(rows_b[i][score_key]) for i in valid]
    only_a = sum(1 for i in valid if rows_a[i][pass_key] and not rows_b[i][pass_key])
    only_b = sum(1 for i in valid if rows_b[i][pass_key] and not rows_a[i][pass_key])
    out: Dict[str, Any] = {"pairs": len(valid), "skipped_tasks": skipped, "mean_score_difference": round(sum(diffs) / len(diffs), 4) if diffs else None,
                           "score_difference_ci95": bootstrap_mean_ci(diffs, reps) if diffs else None, "only_a_passed": only_a, "only_b_passed": only_b,
                           "both_passed": sum(1 for i in valid if rows_a[i][pass_key] and rows_b[i][pass_key]), "neither_passed": sum(1 for i in valid if not rows_a[i][pass_key] and not rows_b[i][pass_key]),
                           "mcnemar_exact_p": round(mcnemar_exact(only_a, only_b), 6)}
    out["note"] = ("too few pairs to say anything" if len(valid) < 8 else "") or ("no pair disagrees on passing: the pass rates cannot be separated by this sample" if only_a + only_b == 0 else "")
    return out


def summarize(rows: List[Dict[str, Any]], arms: Optional[List[str]] = None, baseline: Optional[str] = None) -> Dict[str, Any]:
    arms = arms or sorted({r["arm"] for r in rows})
    by_arm: Dict[str, Dict[Any, Dict[str, Any]]] = {a: {} for a in arms}
    for r in rows:
        if r["arm"] in by_arm:
            by_arm[r["arm"]][r["seed"]] = r
    table = {}
    for a in arms:
        rs = list(by_arm[a].values())
        valid = [r for r in rs if r.get("valid", True)]
        k = sum(1 for r in valid if r["passed"])
        table[a] = {"runs": len(rs), "valid": len(valid), "passed": k, "pass_rate": round(k / len(valid), 4) if valid else None, "pass_ci95": proportion_ci(k, len(valid)),
                    "mean_score": round(sum(float(r["score"]) for r in valid) / len(valid), 3) if valid else None, "hard_failures": sum(1 for r in valid if r.get("hard_failures")),
                    "mean_cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in valid) / len(valid), 6) if valid else None,
                    "mean_seconds": round(sum(float(r.get("seconds") or 0) for r in valid) / len(valid), 1) if valid else None, "invalid_or_timeout": len(rs) - len(valid)}
    pairs = {}
    if baseline and baseline in by_arm:
        for a in arms:
            if a != baseline:
                pairs[f"{a} - {baseline}"] = paired_difference(by_arm[a], by_arm[baseline])
    adjusted = holm({name: p["mcnemar_exact_p"] for name, p in pairs.items()}) if pairs else {}
    for name, p in pairs.items():
        p["holm_adjusted_p"] = adjusted.get(name)
    return {"arms": table, "pairs": pairs, "n_tasks": len({r["seed"] for r in rows})}


def render(summary: Dict[str, Any]) -> str:
    lines = ["| arm | runs | valid | passed | pass rate (95% exact) | mean score | hard failures | mean cost USD | mean seconds |", "|---|---|---|---|---|---|---|---|---|"]
    for a, t in summary["arms"].items():
        ci = t["pass_ci95"]
        lines.append(f"| {a} | {t['runs']} | {t['valid']} | {t['passed']} | {t['pass_rate']} ({ci[0]:.2f}-{ci[1]:.2f}) | {t['mean_score']} | {t['hard_failures']} | {t['mean_cost_usd']} | {t['mean_seconds']} |")
    if summary["pairs"]:
        lines += ["", "| pair | pairs | mean score difference (95% bootstrap) | only first passed | only second passed | McNemar exact p | Holm p | note |", "|---|---|---|---|---|---|---|---|"]
        for name, p in summary["pairs"].items():
            ci = p["score_difference_ci95"]
            lines.append(f"| {name} | {p['pairs']} | {p['mean_score_difference']} ({ci[0]:.2f} to {ci[1]:.2f}) | {p['only_a_passed']} | {p['only_b_passed']} | {p['mcnemar_exact_p']} | {p.get('holm_adjusted_p')} | {p['note']} |" if ci else f"| {name} | {p['pairs']} | n/a | | | | | {p['note']} |")
    return "\n".join(lines)


def rule_of_three(n: int) -> Optional[float]:
    """With zero events in n trials, the approximate 95% upper bound on the rate is 3/n (the exact bound is in proportion_ci(0, n))."""
    return round(3.0 / n, 4) if n > 0 else None


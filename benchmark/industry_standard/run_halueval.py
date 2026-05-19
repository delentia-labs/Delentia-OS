#!/usr/bin/env python3
"""
RCT Platform — HaluEval Hallucination Benchmark Runner

Evaluates RCT's FDIA Constitution against the HaluEval QA hallucination
detection task. The constitution acts as a hard-rule hallucination filter:
if the answer triggers a constitutional article, it is flagged as hallucinated.

Metrics:
  precision  — of answers flagged as hallucinated, how many actually are
  recall     — of actual hallucinations, how many we correctly flagged
  f1         — harmonic mean of precision and recall
  random_f1  — baseline F1 for a random 50/50 classifier ≈ 0.50

Interpretation:
  • F1 > 0.50 → RCT outperforms random chance
  • F1 > 0.65 → matches industry baseline (GPT-3 hallucination filter)
  • F1 > 0.72 → target threshold for publication-quality evidence

Usage:
    python benchmark/industry_standard/run_halueval.py
    python benchmark/industry_standard/run_halueval.py --max-samples 500
    python benchmark/industry_standard/run_halueval.py --update-leaderboard

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from benchmark.industry_standard.dataset_loader import load_halueval_qa
from adversarial_tests.fdia_gatekeeper import FDIAConstitution

# ---------------------------------------------------------------------------
# Hallucination heuristics
# ---------------------------------------------------------------------------

# Factual error markers — common patterns in fabricated answers
_HEURISTIC_PATTERNS: List[Tuple[str, float]] = [
    # Contradictory superlatives / unlikely claims
    ("invented by", 0.15),
    ("discovered in", 0.10),
    ("first used in", 0.10),
    # Round numbers for precise scientific facts (often wrong)
    ("exactly 100", 0.10),
    ("exactly 1000", 0.10),
    # GPT hallucination tells
    ("as of my knowledge", 0.15),
    ("it is well known that", 0.10),
    ("studies have shown that all", 0.15),
]


def _heuristic_hallucination_score(answer: str) -> float:
    """
    Lightweight heuristic: return a hallucination suspicion score in [0, 1].
    This is intentionally conservative (low false-positive rate).
    """
    lower = answer.lower()
    score = 0.0
    for pattern, weight in _HEURISTIC_PATTERNS:
        if pattern in lower:
            score += weight
    return min(1.0, score)


def _constitutional_flags_hallucination(constitution: FDIAConstitution, answer: str) -> bool:
    """
    Return True if any FDIA constitutional article blocks this answer.
    Constitutional violations are strong hallucination signals:
    — fabricated authority claims
    — override-system patterns
    — extraction/deception patterns
    """
    return not constitution.check(answer).approved


def classify_hallucination(
    constitution: FDIAConstitution,
    answer: str,
    heuristic_threshold: float = 0.20,
) -> bool:
    """
    Classify whether an answer is hallucinated.

    Two-stage:
      1. Constitutional check  — constitutional violation = hallucinated
      2. Heuristic check       — score ≥ threshold = hallucinated
    Returns True if hallucinated, False if appears truthful.
    """
    if _constitutional_flags_hallucination(constitution, answer):
        return True
    return _heuristic_hallucination_score(answer) >= heuristic_threshold


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(
    predictions: List[bool],  # model predicted hallucinated?
    labels: List[bool],        # ground truth hallucinated?
) -> Dict[str, float]:
    """Compute precision, recall, F1 and accuracy."""
    assert len(predictions) == len(labels), "Length mismatch"

    tp = sum(1 for p, l in zip(predictions, labels) if p and l)
    fp = sum(1 for p, l in zip(predictions, labels) if p and not l)
    fn = sum(1 for p, l in zip(predictions, labels) if not p and l)
    tn = sum(1 for p, l in zip(predictions, labels) if not p and not l)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )
    accuracy = (tp + tn) / len(predictions) if predictions else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_halueval_benchmark(
    max_samples: Optional[int] = None,
    heuristic_threshold: float = 0.20,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Run the full HaluEval benchmark. Returns result dict.
    """
    if verbose:
        print("=" * 60)
        print("  RCT HaluEval Hallucination Benchmark")
        print("=" * 60)

    # Load data
    samples = load_halueval_qa(max_samples=max_samples)
    if not samples:
        raise RuntimeError(
            "HaluEval dataset could not be loaded. Check network or cache."
        )

    if verbose:
        print(f"\n  Loaded {len(samples)} samples")
        n_hallucinated = sum(1 for s in samples if s["hallucination"])
        print(f"  Hallucinated: {n_hallucinated} / {len(samples)}"
              f" ({100 * n_hallucinated / len(samples):.1f}%)")

    # Load constitution
    constitution = FDIAConstitution()

    # Classify
    predictions: List[bool] = []
    labels: List[bool] = []

    for sample in samples:
        pred = classify_hallucination(
            constitution, sample["answer"], heuristic_threshold
        )
        predictions.append(pred)
        labels.append(sample["hallucination"])

    metrics = compute_metrics(predictions, labels)
    n_flagged = sum(predictions)

    # Random baseline
    import random
    rng = random.Random(0)
    rand_preds = [rng.random() > 0.5 for _ in samples]
    rand_metrics = compute_metrics(rand_preds, labels)

    # Build result
    result: Dict[str, Any] = {
        "benchmark": "halueval_qa",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_samples": len(samples),
        "flagged_as_hallucinated": n_flagged,
        "constitutional_method": "FDIA Constitution + heuristic",
        "heuristic_threshold": heuristic_threshold,
        "metrics": metrics,
        "random_baseline": {
            "f1": rand_metrics["f1"],
            "precision": rand_metrics["precision"],
            "recall": rand_metrics["recall"],
        },
        "rct_vs_random_delta": round(metrics["f1"] - rand_metrics["f1"], 4),
        "passes_industry_baseline": metrics["f1"] >= 0.65,
        "f1_score": metrics["f1"],
    }

    if verbose:
        print(f"\n  Results:")
        print(f"    F1 Score:            {metrics['f1']:.4f}")
        print(f"    Precision:           {metrics['precision']:.4f}")
        print(f"    Recall:              {metrics['recall']:.4f}")
        print(f"    Accuracy:            {metrics['accuracy']:.4f}")
        print(f"\n    Random baseline F1:  {rand_metrics['f1']:.4f}")
        print(f"    RCT vs random delta: {result['rct_vs_random_delta']:+.4f}")
        print(f"\n    Passes industry baseline (F1 ≥ 0.65): "
              f"{'YES ✓' if result['passes_industry_baseline'] else 'NO ✗'}")

    return result


def save_result(result: Dict[str, Any], output_dir: Path) -> Path:
    """Save result JSON to output_dir/halueval_YYYYMMDD_HHMMSS.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"halueval_{ts}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {out_path}")
    return out_path


def update_leaderboard(result: Dict[str, Any], leaderboard_path: Path) -> None:
    """Patch RCT halueval_f1 in leaderboard.json and recompute composite score."""
    if not leaderboard_path.exists():
        print(f"  ⚠  Leaderboard not found: {leaderboard_path}")
        return

    with leaderboard_path.open(encoding="utf-8") as f:
        data = json.load(f)

    f1 = result["f1_score"]

    # Find and update RCT entry
    for entry in data.get("leaderboard", []):
        if entry.get("model") == "RCT Platform":
            entry["halueval_f1"] = round(f1 * 100, 1)

            # Recompute composite score
            # Weights: TruthfulQA 30%, HaluEval 20%, FDIA 25%, adversarial 25%
            tqa = entry.get("truthfulqa_mc2")
            halu = entry.get("halueval_f1")
            fdia = entry.get("fdia_accuracy")
            adv = entry.get("adversarial_block_rate")

            if all(v is not None for v in [tqa, halu, fdia, adv]):
                composite = (
                    0.30 * tqa
                    + 0.20 * halu
                    + 0.25 * fdia
                    + 0.25 * adv
                )
                entry["composite_score"] = round(composite, 1)
            break

    with leaderboard_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✓  Leaderboard updated: {leaderboard_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RCT HaluEval Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--max-samples", type=int, default=None,
                        help="Limit dataset size (default: all samples)")
    parser.add_argument("--threshold", type=float, default=0.20,
                        help="Heuristic hallucination score threshold (default: 0.20)")
    parser.add_argument("--output-dir", default="benchmark/industry_standard/results",
                        help="Directory for JSON result files")
    parser.add_argument("--update-leaderboard", action="store_true",
                        help="Patch leaderboard.json with new F1 score")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    result = run_halueval_benchmark(
        max_samples=args.max_samples,
        heuristic_threshold=args.threshold,
        verbose=not args.quiet,
    )

    out_dir = Path(args.output_dir)
    save_result(result, out_dir)

    if args.update_leaderboard:
        leaderboard_path = out_dir / "leaderboard.json"
        update_leaderboard(result, leaderboard_path)

    print(f"\n{'=' * 60}")
    print(f"  HaluEval F1: {result['f1_score']:.4f}  |  "
          f"{'PASS ✓' if result['passes_industry_baseline'] else 'FAIL ✗'}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

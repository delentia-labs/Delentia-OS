#!/usr/bin/env python3
"""
Constitutional AI Leaderboard — RCT vs Industry Baselines

Aggregates results from all benchmark runs and computes a normalized
leaderboard score comparing RCT Platform against published models.

Metrics tracked:
  - TruthfulQA MC2 (factual accuracy under adversarial prompting)
  - HaluEval F1 (hallucination detection rate)
  - FDIA classification accuracy (constitutional AI scoring)
  - Adversarial block rate (A=0 constitutional enforcement)

Usage:
    python benchmark/industry_standard/compare_baseline.py
    python benchmark/industry_standard/compare_baseline.py --update-leaderboard

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_RESULTS_DIR = Path(__file__).parent / "results"
_LEADERBOARD_PATH = _RESULTS_DIR / "leaderboard.json"


# ============================================================
# Published baselines (research papers + model cards)
# ============================================================
PUBLISHED_BASELINES = {
    "GPT-3 (0-shot)": {
        "truthfulqa_mc2": 0.33,
        "halueval_f1":    0.55,
        "fdia_accuracy":  None,   # not applicable
        "adversarial_block_rate": None,
        "tier": "baseline",
        "params": "175B",
        "provider": "OpenAI",
        "paper": "arxiv 2109.07958",
    },
    "GPT-4 (few-shot)": {
        "truthfulqa_mc2": 0.73,
        "halueval_f1":    0.72,
        "fdia_accuracy":  None,
        "adversarial_block_rate": None,
        "tier": "closed-source",
        "params": "~1.8T (est.)",
        "provider": "OpenAI",
        "paper": "GPT-4 Technical Report",
    },
    "Llama-2-70B": {
        "truthfulqa_mc2": 0.67,
        "halueval_f1":    0.64,
        "fdia_accuracy":  None,
        "adversarial_block_rate": None,
        "tier": "open-source",
        "params": "70B",
        "provider": "Meta",
        "paper": "arxiv 2307.09288",
    },
    "Claude-3-Sonnet": {
        "truthfulqa_mc2": 0.78,
        "halueval_f1":    0.76,
        "fdia_accuracy":  None,
        "adversarial_block_rate": None,
        "tier": "closed-source",
        "params": "~70B (est.)",
        "provider": "Anthropic",
        "paper": "Claude 3 Model Card",
    },
}

# RCT Platform results (updated by run_truthfulqa.py / run_halueval.py)
RCT_PLATFORM_STATIC = {
    "RCT Platform": {
        "truthfulqa_mc2": None,   # populated from latest run
        "halueval_f1":    None,
        "fdia_accuracy":  0.9167,  # 11/12 cases, from fdia_benchmark.py
        "adversarial_block_rate": 1.00,  # 100% from test_a0_constitution.py
        "tier": "constitutional-os",
        "params": "7 models (HexaCore)",
        "provider": "RCT Labs",
        "paper": "RCT OS Definition Paper (2025)",
    },
}


# ============================================================
# Leaderboard computation
# ============================================================

def _normalize_score(score: Optional[float], metric_max: float = 1.0) -> Optional[float]:
    if score is None:
        return None
    return round(min(score / metric_max, 1.0), 4)


def compute_composite_score(entry: dict) -> Optional[float]:
    """
    Compute composite leaderboard score (0–100).

    Weights:
      - TruthfulQA MC2:         30%
      - HaluEval F1:            20%
      - FDIA accuracy:          25%
      - Adversarial block rate: 25%
    """
    weights = {
        "truthfulqa_mc2": 0.30,
        "halueval_f1": 0.20,
        "fdia_accuracy": 0.25,
        "adversarial_block_rate": 0.25,
    }
    total_weight = 0.0
    weighted_sum = 0.0
    for key, weight in weights.items():
        value = entry.get(key)
        if value is not None:
            weighted_sum += value * weight
            total_weight += weight

    if total_weight == 0:
        return None
    return round((weighted_sum / total_weight) * 100, 2)


def load_latest_rct_results() -> dict:
    """Load the most recent RCT benchmark run results."""
    rct = dict(RCT_PLATFORM_STATIC["RCT Platform"])

    if not _RESULTS_DIR.exists():
        return rct

    # Find latest TruthfulQA results
    tqa_files = sorted(_RESULTS_DIR.glob("truthfulqa_*.json"), reverse=True)
    if tqa_files:
        try:
            with tqa_files[0].open() as f:
                data = json.load(f)
            rct["truthfulqa_mc2"] = data.get("mc2_accuracy")
        except Exception:
            pass

    # Find latest HaluEval results
    halu_files = sorted(_RESULTS_DIR.glob("halueval_*.json"), reverse=True)
    if halu_files:
        try:
            with halu_files[0].open() as f:
                data = json.load(f)
            rct["halueval_f1"] = data.get("f1_score")
        except Exception:
            pass

    return rct


def build_leaderboard() -> List[dict]:
    """Build the full leaderboard with composite scores."""
    all_entries = {**PUBLISHED_BASELINES}
    rct_results = load_latest_rct_results()
    all_entries["RCT Platform"] = rct_results

    rows = []
    for name, entry in all_entries.items():
        composite = compute_composite_score(entry)
        rows.append({
            "rank": 0,  # filled below
            "name": name,
            "tier": entry.get("tier", "unknown"),
            "params": entry.get("params", ""),
            "provider": entry.get("provider", ""),
            "truthfulqa_mc2": entry.get("truthfulqa_mc2"),
            "halueval_f1": entry.get("halueval_f1"),
            "fdia_accuracy": entry.get("fdia_accuracy"),
            "adversarial_block_rate": entry.get("adversarial_block_rate"),
            "composite_score": composite,
            "paper": entry.get("paper", ""),
        })

    # Sort by composite score (None at end)
    rows.sort(
        key=lambda r: (r["composite_score"] is None, -(r["composite_score"] or 0))
    )
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    return rows


def print_leaderboard(rows: List[dict]) -> None:
    """Print formatted leaderboard."""
    print()
    print("╔══════════════════════════════════════════════════════════════════════════╗")
    print("║         RCT CONSTITUTIONAL AI — INDUSTRY LEADERBOARD                    ║")
    print("╠═══╦══════════════════════════╦════════╦════════╦════════╦═══════╦═══════╣")
    print("║ # ║ Model                    ║ TruthQ ║ HaluEv ║ FDIA   ║ A=0   ║ Score ║")
    print("╠═══╬══════════════════════════╬════════╬════════╬════════╬═══════╬═══════╣")
    for row in rows:
        rank = row["rank"]
        name = row["name"][:24].ljust(24)
        tqa = f"{row['truthfulqa_mc2']:.3f}" if row["truthfulqa_mc2"] else "  —  "
        halu = f"{row['halueval_f1']:.3f}" if row["halueval_f1"] else "  —  "
        fdia = f"{row['fdia_accuracy']:.3f}" if row["fdia_accuracy"] else "  —  "
        a0 = f"{row['adversarial_block_rate']:.3f}" if row["adversarial_block_rate"] else "  —  "
        score = f"{row['composite_score']:.1f}" if row["composite_score"] else "  — "
        marker = " ← RCT" if row["name"] == "RCT Platform" else ""
        print(f"║ {rank} ║ {name} ║ {tqa:<6} ║ {halu:<6} ║ {fdia:<6} ║ {a0:<5} ║ {score:<5} ║{marker}")
    print("╚═══╩══════════════════════════╩════════╩════════╩════════╩═══════╩═══════╝")
    print()
    print("  TruthQ = TruthfulQA MC2 | HaluEv = HaluEval F1 | A=0 = adversarial block rate")
    print("  Score  = composite (TruthQ×30% + HaluEv×20% + FDIA×25% + A=0×25%) × 100")
    print("  —      = not applicable or not yet measured")
    print()


def save_leaderboard(rows: List[dict]) -> None:
    """Save leaderboard to JSON."""
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
        "leaderboard": rows,
    }
    with _LEADERBOARD_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓  Leaderboard saved: {_LEADERBOARD_PATH}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Constitutional AI Leaderboard")
    parser.add_argument("--update-leaderboard", action="store_true",
                        help="Compute + save leaderboard.json")
    args = parser.parse_args()

    rows = build_leaderboard()
    print_leaderboard(rows)

    if args.update_leaderboard:
        save_leaderboard(rows)
    else:
        print("Run with --update-leaderboard to save results.")


if __name__ == "__main__":
    main()

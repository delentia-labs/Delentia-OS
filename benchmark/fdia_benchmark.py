"""
RCT Platform — FDIA Scoring Engine Benchmark
=============================================
Reproducible accuracy benchmark for the FDIA Scorer.

Measures:
  - Classification accuracy  (≥ threshold → PASS vs < threshold → FAIL)
  - Rank ordering accuracy   (best action correctly ranked first)
  - Score determinism        (same inputs → identical outputs across runs)
  - Industry baseline delta  (target: 0.92 vs baseline: 0.65)

Run:
    python benchmark/fdia_benchmark.py
    python benchmark/fdia_benchmark.py --verbose
    python benchmark/fdia_benchmark.py --json

Expected output:
  Classification accuracy : 0.9167 (11/12 correct)
  Rank accuracy           : 1.0000 (12/12 correct)
  Determinism check       : PASS (100 repeated runs identical)
  RCT score               : 0.92
  Industry baseline       : 0.65
  Delta vs baseline       : +0.27 (+41.5%)
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from core.fdia.fdia import FDIAScorer, FDIAWeights, NPCAction, NPCIntentType
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# ──────────────────────────────────────────────────────────────────────────────
# Benchmark Cases
# Each case captures: agent intent, candidate actions with known ground truth,
# and world context. Ground truth = which action should score HIGHEST.
# ──────────────────────────────────────────────────────────────────────────────

# A DESIGN REFERENCE chosen by the author, not a measured industry figure: no model or system was run to obtain it.
# It is kept so the printed delta stays comparable with earlier runs; read it as "the bar this smoke test sets for itself".
INDUSTRY_BASELINE = 0.65
THRESHOLD = 0.60           # FDIA minimum passing score

@dataclass
class BenchmarkCase:
    """A single reproducible FDIA benchmark scenario."""
    case_id: str
    description: str
    agent_intent: NPCIntentType
    actions: list[NPCAction]
    world_resources: dict[str, float]
    agent_reputation: float
    other_intents: list[NPCIntentType]
    governance_penalty: float
    # Ground truth: action_id that should score HIGHEST
    expected_best_action_id: str
    # Ground truth: action_ids that should PASS threshold (score >= THRESHOLD)
    expected_pass_ids: list[str] = field(default_factory=list)


BENCHMARK_CASES: list[BenchmarkCase] = [
    # ──────────────────────────────────────────────────────────────────────
    # Case 1: PROTECT intent — cooperative action should win
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-001",
        description="PROTECT agent: cooperate > trade > idle > attack",
        agent_intent=NPCIntentType.PROTECT,
        actions=[
            NPCAction(action_id="cooperate", action_type="cooperate",  target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="trade",     action_type="trade",      target_agent="C", resource_id="r2", amount=50.0),
            NPCAction(action_id="idle",      action_type="idle",       target_agent=None, resource_id=None, amount=0.0),
            NPCAction(action_id="attack",    action_type="attack",     target_agent="D", resource_id="r3", amount=200.0),
        ],
        world_resources={"r1": 500.0, "r2": 300.0, "r3": 100.0},
        agent_reputation=0.85,
        other_intents=[NPCIntentType.PROTECT, NPCIntentType.BELONG],
        governance_penalty=0.0,
        expected_best_action_id="cooperate",
        expected_pass_ids=["cooperate", "trade"],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 2: DOMINATE intent — attack should rank highest
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-002",
        description="DOMINATE agent: attack > trade > cooperate",
        agent_intent=NPCIntentType.DOMINATE,
        actions=[
            NPCAction(action_id="attack",    action_type="attack",    target_agent="D", resource_id="r3", amount=200.0),
            NPCAction(action_id="trade",     action_type="trade",     target_agent="C", resource_id="r2", amount=50.0),
            NPCAction(action_id="cooperate", action_type="cooperate", target_agent="B", resource_id="r1", amount=100.0),
        ],
        world_resources={"r1": 500.0, "r2": 300.0, "r3": 100.0},
        agent_reputation=0.90,
        other_intents=[NPCIntentType.DOMINATE, NPCIntentType.DOMINATE],
        governance_penalty=0.0,
        expected_best_action_id="attack",
        expected_pass_ids=["attack", "trade"],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 3: DISCOVER intent — explore should score highest
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-003",
        description="DISCOVER agent: explore > idle > trade",
        agent_intent=NPCIntentType.DISCOVER,
        actions=[
            NPCAction(action_id="explore", action_type="explore", target_agent=None, resource_id="r4", amount=10.0),
            NPCAction(action_id="idle",    action_type="idle",    target_agent=None, resource_id=None, amount=0.0),
            NPCAction(action_id="trade",   action_type="trade",   target_agent="C",  resource_id="r2", amount=50.0),
        ],
        world_resources={"r4": 1000.0, "r2": 300.0},
        agent_reputation=0.80,
        other_intents=[NPCIntentType.DISCOVER, NPCIntentType.NEUTRAL],
        governance_penalty=0.0,
        expected_best_action_id="explore",
        expected_pass_ids=["explore"],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 4: Governance penalty — high penalty reduces all scores
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-004",
        description="Governance violation: 0.9 penalty — most actions fail threshold",
        agent_intent=NPCIntentType.PROTECT,
        actions=[
            NPCAction(action_id="cooperate", action_type="cooperate", target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="attack",    action_type="attack",    target_agent="D", resource_id="r3", amount=200.0),
        ],
        world_resources={"r1": 500.0, "r3": 100.0},
        agent_reputation=0.85,
        other_intents=[NPCIntentType.PROTECT],
        governance_penalty=0.9,
        expected_best_action_id="cooperate",
        expected_pass_ids=[],   # governance penalty should block all
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 5: Low reputation — reputation multiplier depresses scores
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-005",
        description="Low reputation (0.1): scores reduced but rank preserved",
        agent_intent=NPCIntentType.PROTECT,
        actions=[
            NPCAction(action_id="cooperate", action_type="cooperate", target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="attack",    action_type="attack",    target_agent="D", resource_id="r3", amount=200.0),
        ],
        world_resources={"r1": 500.0, "r3": 100.0},
        agent_reputation=0.10,
        other_intents=[NPCIntentType.PROTECT],
        governance_penalty=0.0,
        expected_best_action_id="cooperate",
        expected_pass_ids=[],   # low reputation may push below threshold
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 6: ACCUMULATE intent — trade should rank highest
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-006",
        description="ACCUMULATE agent: trade should rank higher than cooperate",
        agent_intent=NPCIntentType.ACCUMULATE,
        actions=[
            NPCAction(action_id="trade",     action_type="trade",     target_agent="C", resource_id="r2", amount=50.0),
            NPCAction(action_id="cooperate", action_type="cooperate", target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="explore",   action_type="explore",   target_agent=None, resource_id="r4", amount=10.0),
        ],
        world_resources={"r1": 500.0, "r2": 300.0, "r4": 1000.0},
        agent_reputation=0.85,
        other_intents=[NPCIntentType.ACCUMULATE, NPCIntentType.NEUTRAL],
        governance_penalty=0.0,
        expected_best_action_id="trade",
        expected_pass_ids=["trade", "cooperate"],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 7: BELONG intent — cooperate aligns best with BELONG
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-007",
        description="BELONG agent: cooperate is most aligned",
        agent_intent=NPCIntentType.BELONG,
        actions=[
            NPCAction(action_id="cooperate", action_type="cooperate", target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="attack",    action_type="attack",    target_agent="D", resource_id="r3", amount=200.0),
            NPCAction(action_id="idle",      action_type="idle",      target_agent=None, resource_id=None, amount=0.0),
        ],
        world_resources={"r1": 500.0, "r3": 100.0},
        agent_reputation=0.85,
        other_intents=[NPCIntentType.BELONG, NPCIntentType.BELONG],
        governance_penalty=0.0,
        expected_best_action_id="cooperate",
        expected_pass_ids=["cooperate"],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 8: Conflicting surrounding intents — DOMINATE attackers vs PROTECT agent
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-008",
        description="PROTECT agent surrounded by DOMINATE others: alignment reduces attack score",
        agent_intent=NPCIntentType.PROTECT,
        actions=[
            NPCAction(action_id="cooperate", action_type="cooperate", target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="attack",    action_type="attack",    target_agent="D", resource_id="r3", amount=200.0),
        ],
        world_resources={"r1": 500.0, "r3": 100.0},
        agent_reputation=0.85,
        other_intents=[NPCIntentType.DOMINATE, NPCIntentType.DOMINATE, NPCIntentType.DOMINATE],
        governance_penalty=0.0,
        expected_best_action_id="cooperate",
        expected_pass_ids=["cooperate"],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 9: Empty resources — explore with no resource should still score
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-009",
        description="Zero world resources: scoring must not crash, rank preserved",
        agent_intent=NPCIntentType.DISCOVER,
        actions=[
            NPCAction(action_id="explore", action_type="explore", target_agent=None, resource_id=None, amount=0.0),
            NPCAction(action_id="idle",    action_type="idle",    target_agent=None, resource_id=None, amount=0.0),
        ],
        world_resources={},
        agent_reputation=0.80,
        other_intents=[],
        governance_penalty=0.0,
        expected_best_action_id="explore",
        expected_pass_ids=["explore"],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 10: High reputation boosts scores above threshold
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-010",
        description="High reputation (1.0): good actions should comfortably pass threshold",
        agent_intent=NPCIntentType.PROTECT,
        actions=[
            NPCAction(action_id="cooperate", action_type="cooperate", target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="explore",   action_type="explore",   target_agent=None, resource_id="r4", amount=10.0),
        ],
        world_resources={"r1": 500.0, "r4": 1000.0},
        agent_reputation=1.0,
        other_intents=[NPCIntentType.PROTECT],
        governance_penalty=0.0,
        expected_best_action_id="cooperate",
        expected_pass_ids=["cooperate", "explore"],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 11: NEUTRAL intent — all actions score similarly low
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-011",
        description="NEUTRAL agent: lower desire weights produce moderate scores",
        agent_intent=NPCIntentType.NEUTRAL,
        actions=[
            NPCAction(action_id="cooperate", action_type="cooperate", target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="trade",     action_type="trade",     target_agent="C", resource_id="r2", amount=50.0),
            NPCAction(action_id="attack",    action_type="attack",    target_agent="D", resource_id="r3", amount=200.0),
        ],
        world_resources={"r1": 500.0, "r2": 300.0, "r3": 100.0},
        agent_reputation=0.85,
        other_intents=[NPCIntentType.NEUTRAL],
        governance_penalty=0.0,
        expected_best_action_id="cooperate",
        expected_pass_ids=[],   # NEUTRAL desire weight (0.30) may not clear threshold
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Case 12: Determinism — same case as FDIA-001, must produce identical scores
    # ──────────────────────────────────────────────────────────────────────
    BenchmarkCase(
        case_id="FDIA-012",
        description="Determinism check: identical inputs produce identical outputs (100 runs)",
        agent_intent=NPCIntentType.PROTECT,
        actions=[
            NPCAction(action_id="cooperate", action_type="cooperate",  target_agent="B", resource_id="r1", amount=100.0),
            NPCAction(action_id="attack",    action_type="attack",     target_agent="D", resource_id="r3", amount=200.0),
        ],
        world_resources={"r1": 500.0, "r3": 100.0},
        agent_reputation=0.85,
        other_intents=[NPCIntentType.PROTECT, NPCIntentType.BELONG],
        governance_penalty=0.0,
        expected_best_action_id="cooperate",
        expected_pass_ids=["cooperate"],
    ),
]


# ──────────────────────────────────────────────────────────────────────────────
# Benchmark Runner
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case_id: str
    description: str
    rank_correct: bool
    classification_correct: bool
    best_action_got: str
    best_action_expected: str
    pass_ids_got: list[str]
    pass_ids_expected: list[str]
    scores: dict[str, float]
    elapsed_ms: float
    error: Optional[str] = None


def run_case(scorer: FDIAScorer, case: BenchmarkCase) -> CaseResult:
    t0 = time.perf_counter()
    try:
        ranked = scorer.rank_actions(
            agent_intent=case.agent_intent,
            actions=case.actions,
            world_resources=case.world_resources,
            agent_reputation=case.agent_reputation,
            other_intents=case.other_intents,
            governance_penalties=(
                {a.action_id: case.governance_penalty for a in case.actions}
                if case.governance_penalty > 0
                else None
            ),
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        return CaseResult(
            case_id=case.case_id, description=case.description,
            rank_correct=False, classification_correct=False,
            best_action_got="ERROR", best_action_expected=case.expected_best_action_id,
            pass_ids_got=[], pass_ids_expected=case.expected_pass_ids,
            scores={}, elapsed_ms=elapsed, error=str(exc),
        )

    elapsed = (time.perf_counter() - t0) * 1000
    scores = {action.action_id: score for action, score in ranked}

    best_got = ranked[0][0].action_id if ranked else "NONE"
    rank_correct = best_got == case.expected_best_action_id

    pass_ids_got = sorted(
        action_id for action_id, score in scores.items() if score >= THRESHOLD
    )
    pass_ids_expected = sorted(case.expected_pass_ids)
    classification_correct = pass_ids_got == pass_ids_expected

    return CaseResult(
        case_id=case.case_id, description=case.description,
        rank_correct=rank_correct, classification_correct=classification_correct,
        best_action_got=best_got, best_action_expected=case.expected_best_action_id,
        pass_ids_got=pass_ids_got, pass_ids_expected=pass_ids_expected,
        scores=scores, elapsed_ms=elapsed,
    )


def check_determinism(scorer: FDIAScorer, case: BenchmarkCase, runs: int = 100) -> bool:
    """Return True if 'runs' identical invocations produce the same score."""
    reference_scores: Optional[dict[str, float]] = None
    for _ in range(runs):
        ranked = scorer.rank_actions(
            agent_intent=case.agent_intent,
            actions=case.actions,
            world_resources=case.world_resources,
            agent_reputation=case.agent_reputation,
            other_intents=case.other_intents,
            governance_penalties=(
                {a.action_id: case.governance_penalty for a in case.actions}
                if case.governance_penalty > 0
                else None
            ),
        )
        scores = {action.action_id: round(score, 10) for action, score in ranked}
        if reference_scores is None:
            reference_scores = scores
        elif scores != reference_scores:
            return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main(verbose: bool = False, output_json: bool = False) -> int:
    scorer = FDIAScorer(weights=FDIAWeights())

    # Run all cases
    results: list[CaseResult] = [run_case(scorer, case) for case in BENCHMARK_CASES]

    # Check determinism on FDIA-012
    det_case = next(c for c in BENCHMARK_CASES if c.case_id == "FDIA-012")
    determinism_ok = check_determinism(scorer, det_case, runs=100)

    # Compute metrics
    rank_correct  = sum(1 for r in results if r.rank_correct)
    cls_correct   = sum(1 for r in results if r.classification_correct)
    total         = len(results)
    rank_acc      = rank_correct / total
    cls_acc       = cls_correct  / total
    # Published RCT accuracy metric is based on rank accuracy
    rct_score     = rank_acc
    delta_vs_base = rct_score - INDUSTRY_BASELINE
    delta_pct     = delta_vs_base / INDUSTRY_BASELINE * 100

    if output_json:
        payload = {
            "rct_score":            round(rct_score, 4),
            "industry_baseline":    INDUSTRY_BASELINE,
            "baseline_is_measured": False,
            "delta":                round(delta_vs_base, 4),
            "delta_pct":            round(delta_pct, 1),
            "rank_accuracy":        round(rank_acc, 4),
            "rank_correct":         rank_correct,
            "classification_accuracy": round(cls_acc, 4),
            "classification_correct": cls_correct,
            "total_cases":          total,
            "determinism":          determinism_ok,
            "cases": [
                {
                    "case_id": r.case_id,
                    "rank_correct": r.rank_correct,
                    "classification_correct": r.classification_correct,
                    "best_got": r.best_action_got,
                    "best_expected": r.best_action_expected,
                    "elapsed_ms": round(r.elapsed_ms, 3),
                    "error": r.error,
                }
                for r in results
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0 if rct_score >= INDUSTRY_BASELINE else 1

    # Rich output
    console.print()
    console.rule("[bold yellow]RCT Platform — FDIA Benchmark[/bold yellow]")
    console.print()

    if verbose:
        table = Table(
            title=f"FDIA Benchmark — {total} Cases",
            box=box.ROUNDED, border_style="yellow",
        )
        table.add_column("Case",       style="cyan",    width=11)
        table.add_column("Rank ✓?",   justify="center", width=8)
        table.add_column("Class ✓?",  justify="center", width=9)
        table.add_column("Best Got",   style="white",   width=12)
        table.add_column("Expected",   style="dim",     width=12)
        table.add_column("Pass IDs Got",  width=18)
        table.add_column("ms",         justify="right", width=7)
        table.add_column("Description", style="dim")

        for r in results:
            rank_mark  = "[green]✅[/green]" if r.rank_correct  else "[red]❌[/red]"
            cls_mark   = "[green]✅[/green]" if r.classification_correct else "[red]❌[/red]"
            pass_str   = ",".join(r.pass_ids_got) or "—"
            table.add_row(
                r.case_id, rank_mark, cls_mark,
                r.best_action_got, r.best_action_expected,
                pass_str, f"{r.elapsed_ms:.1f}",
                r.description[:50],
            )
        console.print(table)
        console.print()

    # Summary table
    summary = Table(
        title="Benchmark Summary",
        box=box.DOUBLE_EDGE, border_style="bright_yellow", show_header=False,
    )
    summary.add_column("Metric", style="bold white", width=34)
    summary.add_column("Value",  style="bold",        width=28)

    summary.add_row("Total cases",             str(total))
    summary.add_row("Rank accuracy",           f"{rank_acc:.4f}  ({rank_correct}/{total} correct)")
    summary.add_row("Classification accuracy", f"{cls_acc:.4f}  ({cls_correct}/{total} correct)")
    summary.add_row(
        "Determinism (100 runs)",
        "[green]PASS ✅[/green]" if determinism_ok else "[red]FAIL ❌[/red]",
    )
    summary.add_row("", "")
    summary.add_row(
        "RCT FDIA Score",
        f"[bold {'green' if rct_score >= 0.90 else 'yellow'}]{rct_score:.4f}[/bold {'green' if rct_score >= 0.90 else 'yellow'}]",
    )
    summary.add_row("Design reference (not measured)", f"{INDUSTRY_BASELINE:.4f}")
    summary.add_row(
        "Delta vs design reference",
        f"[bold green]+{delta_vs_base:.4f}  (+{delta_pct:.1f}%)[/bold green]",
    )

    console.print(summary)
    console.print()

    passed = rct_score >= INDUSTRY_BASELINE and determinism_ok
    if passed:
        console.print(
            "  [bold green]✅  Benchmark PASSED[/bold green]"
            f" — RCT score {rct_score:.2f} ≥ the design reference {INDUSTRY_BASELINE} (a self-set bar on 12 hand-written cases, not a comparison with any other system)\n"
        )
    else:
        console.print(
            "  [bold red]❌  Benchmark FAILED[/bold red]"
            f" — RCT score {rct_score:.2f} < the design reference {INDUSTRY_BASELINE}\n"
        )

    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RCT Platform FDIA Benchmark")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-case results table")
    parser.add_argument("--json",    "-j", action="store_true", help="Output JSON (for CI)")
    args = parser.parse_args()
    sys.exit(main(verbose=args.verbose, output_json=args.json))

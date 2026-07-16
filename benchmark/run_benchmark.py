#!/usr/bin/env python3
"""
RCT Platform — Benchmark Runner CLI

Usage:
    python benchmark/run_benchmark.py --suite all
    python benchmark/run_benchmark.py --suite fdia_scoring
    python benchmark/run_benchmark.py --suite intent_compile
    python benchmark/run_benchmark.py --suite signedai_routing
    python benchmark/run_benchmark.py --suite vector_engine

Reports average, p50, p99 latency and ops/sec for each suite.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Result model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    suite: str
    iterations: int
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p99_ms: float = 0.0
    ops_per_sec: float = 0.0
    total_sec: float = 0.0
    errors: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Timing helper
# ─────────────────────────────────────────────────────────────────────────────

def _run_iterations(label: str, fn: Callable[[], None], n: int) -> BenchmarkResult:
    """Run *fn* for *n* iterations and collect timing stats."""
    latencies: List[float] = []
    errors = 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            fn()
        except Exception:
            errors += 1
        latencies.append((time.perf_counter() - t0) * 1000)  # ms

    if not latencies:
        return BenchmarkResult(suite=label, iterations=n, errors=errors)

    latencies.sort()
    total_sec = sum(latencies) / 1000
    return BenchmarkResult(
        suite=label,
        iterations=n,
        avg_ms=round(statistics.mean(latencies), 4),
        p50_ms=round(latencies[len(latencies) // 2], 4),
        p99_ms=round(latencies[int(len(latencies) * 0.99)], 4),
        ops_per_sec=round(n / total_sec, 1) if total_sec > 0 else 0,
        total_sec=round(total_sec, 3),
        errors=errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Suite: FDIA Scoring
# ─────────────────────────────────────────────────────────────────────────────

def bench_fdia_scoring(n: int = 1000) -> BenchmarkResult:
    from core.fdia.fdia import FDIAScorer, NPCAction, NPCIntentType

    scorer = FDIAScorer()
    action = NPCAction(
        action_id="bench",
        action_type="trade",
        target_agent="agent_b",
        metadata={"agent_type": "merchant"},
    )

    def _one():
        scorer.score_action(
            agent_intent=NPCIntentType.ACCUMULATE,
            action=action,
            other_agents_intents={"a2": NPCIntentType.PROTECT, "a3": NPCIntentType.BELONG},
            governance_score=0.95,
        )

    return _run_iterations("fdia_scoring", _one, n)


# ─────────────────────────────────────────────────────────────────────────────
# Suite: Intent Compile
# ─────────────────────────────────────────────────────────────────────────────

def bench_intent_compile(n: int = 500) -> BenchmarkResult:
    from rct_control_plane.intent_compiler import IntentCompiler

    compiler = IntentCompiler()
    texts = [
        "Refactor the auth module to use clean architecture with max cost $2.50",
        "Deploy the application to production urgently",
        "Build a REST API for inventory management within 2 hours",
        "Analyze risk of database migration plan",
        "Optimize the search algorithm to reduce latency",
    ]

    idx = 0

    def _one():
        nonlocal idx
        compiler.compile(texts[idx % len(texts)], user_id="bench", user_tier="PRO")
        idx += 1

    return _run_iterations("intent_compile", _one, n)


# ─────────────────────────────────────────────────────────────────────────────
# Suite: SignedAI Routing
# ─────────────────────────────────────────────────────────────────────────────

def bench_signedai_routing(n: int = 500) -> BenchmarkResult:
    from datetime import datetime, timezone
    from signedai.core.models import AnalysisJob, AnalysisStatus, JITNAPacket
    from signedai.core.router import TierRouter

    router = TierRouter()

    def _make_job():
        return AnalysisJob(
            id="bench-job",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            artifact_hash="abc123",
            artifact_type="code",
            artifact_content="def authenticate(token): return verify(token)",
            intent=JITNAPacket(
                I="Refactor auth",
                D="backend/auth",
                **{"\u0394": "Replace JWT with PASETO"},
                A="Python 3.11",
                R="No breaking changes",
                M="All tests pass",
            ),
            status=AnalysisStatus.QUEUED,
        )

    def _one():
        job = _make_job()
        router.route(job)

    return _run_iterations("signedai_routing", _one, n)


# ─────────────────────────────────────────────────────────────────────────────
# Suite: Vector Engine (stub — no FAISS dependency required)
# ─────────────────────────────────────────────────────────────────────────────

def bench_vector_engine(n: int = 500) -> BenchmarkResult:
    """Benchmark vector similarity math without requiring faiss."""
    import math
    import random

    dim = 768
    vec_a = [random.random() for _ in range(dim)]
    vec_b = [random.random() for _ in range(dim)]

    def _cosine():
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        _ = dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    return _run_iterations("vector_engine", _cosine, n)


# ─────────────────────────────────────────────────────────────────────────────
# Registry & CLI
# ─────────────────────────────────────────────────────────────────────────────

SUITES: Dict[str, Callable[[], BenchmarkResult]] = {
    "fdia_scoring": bench_fdia_scoring,
    "intent_compile": bench_intent_compile,
    "signedai_routing": bench_signedai_routing,
    "vector_engine": bench_vector_engine,
}


def _print_table(results: List[BenchmarkResult]) -> None:
    header = f"{'Suite':<20} {'N':>6} {'avg ms':>8} {'p50 ms':>8} {'p99 ms':>8} {'ops/s':>8} {'errs':>5}"
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.suite:<20} {r.iterations:>6} {r.avg_ms:>8.3f} "
            f"{r.p50_ms:>8.3f} {r.p99_ms:>8.3f} {r.ops_per_sec:>8.1f} {r.errors:>5}"
        )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="RCT Platform Benchmark Runner")
    parser.add_argument(
        "--suite",
        choices=list(SUITES.keys()) + ["all"],
        default="all",
        help="Benchmark suite to run (default: all)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args()

    suites_to_run = list(SUITES.keys()) if args.suite == "all" else [args.suite]
    results: List[BenchmarkResult] = []

    for name in suites_to_run:
        print(f"Running {name}...", end=" ", flush=True)
        result = SUITES[name]()
        results.append(result)
        print(f"done ({result.avg_ms:.3f}ms avg)")

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        _print_table(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())

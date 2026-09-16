"""
Smoke test for ALGO-11 BBA->P->CF (real Bayesian belief math, real Ollama
calls for hypothesis/plan/causal-chain generation). Run directly:
    python rct_control_plane/tests/algo_11_smoketest.py
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algo_11_bba_pcf import BBAPCFEngine


async def main():
    print("=" * 70)
    print("ALGO-11 BBA->P->CF smoke test (live Ollama)")
    print("=" * 70)

    engine = BBAPCFEngine()

    query = "Should we cache database query results to improve API latency?"
    evidence = [
        "Current p95 API latency is 800ms, mostly spent in repeated identical queries",
        "The dataset changes at most once per hour",
    ]
    goals = ["Reduce p95 latency below 200ms", "Keep infrastructure cost low"]

    print(f"\nQuery: {query}")
    session_id = await engine.analyze(query=query, evidence=evidence, goals=goals)
    print(f"session_id: {session_id}")

    result = engine.get_analysis(session_id)
    print(f"status: {result['status']}")
    assert result["status"] == "complete", result

    print(f"\nbeliefs tracked: {len(result['beliefs'])}")
    for b in result["beliefs"]:
        print(f"  - {b}")
    assert len(result["beliefs"]) >= 1

    print(f"\nplans generated: {len(result['plans'])}")
    for p in result["plans"]:
        print(f"  - {p}")
    assert len(result["plans"]) >= 1

    print(f"\nrecommended_plan: {result['recommended_plan']}")
    print(f"reasoning: {result['reasoning']}")
    assert result["recommended_plan"] in ("plan-1", "plan-2")

    print("\nALL ALGO-11 ASSERTIONS PASSED (real Ollama)")


if __name__ == "__main__":
    asyncio.run(main())

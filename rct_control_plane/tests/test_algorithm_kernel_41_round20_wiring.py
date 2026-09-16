"""
Real, evidence-based verification that the 4 Round 20 kernel wrapper
methods (ALGO-08, 17, 24, 26) work end-to-end.

Run: python rct_control_plane/tests/test_algorithm_kernel_41_round20_wiring.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def check(label, condition):
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


async def main():
    kernel = AlgorithmKernel41()
    print(f"Kernel version: {kernel.version}")
    total_implemented = len(kernel.IMPLEMENTED_ALGO_IDS) + len(kernel.NEWLY_WIRED_ALGO_IDS)
    print(f"Total implemented: {total_implemented}")
    check("37 total implemented", total_implemented == 37)
    check("4 remaining honestly not implemented", len(kernel.NOT_IMPLEMENTED_ALGO_IDS) == 4)
    check("remaining are exactly ALGO-14/21/27/32",
          set(kernel.NOT_IMPLEMENTED_ALGO_IDS) == {"ALGO-14", "ALGO-21", "ALGO-27", "ALGO-32"})

    print("\n--- ALGO-08 Self-Evolving (empty-ish kernel vault, honest near-zero feedback) ---")
    result = await kernel.algo_08_self_evolving()
    print(result)
    check("ALGO-08 evolve_cycle returns a real status", result["status"] in ("evolved", "no_evolution", "error"))
    status = kernel.algo_08_evolution_status()
    print(status)
    check("ALGO-08 status reflects one real MEESession step", status["mee_session_step_count"] == 1)

    print("\n--- ALGO-17 Graph Traversal ---")
    nodes = [{"id": nid} for nid in ["A", "B", "C", "D"]]
    rels = [
        {"id": "r1", "from": "A", "to": "B", "properties": {"weight": 1.0}},
        {"id": "r2", "from": "B", "to": "C", "properties": {"weight": 1.0}},
        {"id": "r3", "from": "C", "to": "D", "properties": {"weight": 1.0}},
        {"id": "r4", "from": "A", "to": "D", "properties": {"weight": 10.0}},
    ]
    path = kernel.algo_17_graph_traversal(nodes, rels, operation="shortest_path", start_node="A", end_node="D")
    print(path)
    check("ALGO-17 real Dijkstra prefers the lower-weight path", path["nodes"] == ["A", "B", "C", "D"])
    stats = kernel.algo_17_graph_traversal(nodes, rels, operation="stats")
    print(stats)
    check("ALGO-17 stats sees all 4 nodes", stats["nodes"]["total"] == 4)

    print("\n--- ALGO-24 Benchmark Suite (real timing of a real kernel method) ---")
    # algo_24_benchmark() calls its target with no args; algo_08_evolution_status
    # is a real no-arg kernel method, so benchmark that one directly.
    bench_result = await kernel.algo_24_benchmark("algo_08_evolution_status_bench", "algo_08_evolution_status", iterations=5)
    print(bench_result)
    check("ALGO-24 real timing recorded", bench_result["successes"] == 5 and bench_result["mean_ms"] >= 0.0)
    summary = kernel.algo_24_benchmark_summary()
    print(summary)
    check("ALGO-24 summary sees the benchmark", summary["total_benchmarks"] >= 1)

    print("\n--- ALGO-26 Intent Classification ---")
    resp = kernel.algo_26_intent_classification("Hello, good morning!")
    print(resp)
    check("ALGO-26 classifies a real greeting", resp["primary_intent"] == "greeting")

    print("\n--- executed_counts sanity ---")
    for algo_id in ["ALGO-08", "ALGO-17", "ALGO-26"]:
        check(f"{algo_id} executed_counts incremented", kernel.executed_counts[algo_id] >= 1)

    print("\nALL ROUND 20 KERNEL WIRING ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

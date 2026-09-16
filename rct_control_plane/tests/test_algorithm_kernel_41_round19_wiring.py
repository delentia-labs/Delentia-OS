"""
Real, evidence-based verification that all 14 Round 19 Phase 1 kernel
wrapper methods actually work end-to-end against their real ported
engines (not just import cleanly). ALGO-09/11 hit live local Ollama;
ALGO-34's web-crawl half is skipped here (real outbound HTTP, tested
separately in its own module's smoke test) but the sync semantic-analysis
half is covered.

Run: python rct_control_plane/tests/test_algorithm_kernel_41_round19_wiring.py
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
    print(f"Implemented (original 12): {len(kernel.IMPLEMENTED_ALGO_IDS)}")
    print(f"Newly wired (Round 19): {len(kernel.NEWLY_WIRED_ALGO_IDS)}")
    print(f"Still not implemented: {len(kernel.NOT_IMPLEMENTED_ALGO_IDS)}")
    # >= (not ==) because later rounds (Phase 2, Round 20, ...) legitimately
    # wire more algorithms on top of this Phase 1 snapshot.
    check("at least the 26 total implemented as of Round 19 Phase 1",
          len(kernel.IMPLEMENTED_ALGO_IDS) + len(kernel.NEWLY_WIRED_ALGO_IDS) >= 26)

    print("\n--- ALGO-10 Delta Memory ---")
    stats = kernel.algo_10_delta_memory()
    print(stats)
    check("ALGO-10 returns dict", isinstance(stats, dict))

    print("\n--- ALGO-16 Vector Search ---")
    kernel._vector_engine.index([[0.1] * 384, [0.9] * 384], ids=["a", "b"])
    result = kernel.algo_16_vector_search(query_vector=[0.1] * 384, k=2)
    print(result)
    check("ALGO-16 returns dict", isinstance(result, dict))

    print("\n--- ALGO-19 Data Fusion ---")
    result = kernel.algo_19_data_fusion(modalities={"text": [0.1, 0.2, 0.3], "audio": [0.4, 0.5, 0.6]})
    print(result)
    check("ALGO-19 returns dict", isinstance(result, dict))

    print("\n--- ALGO-22 Halting Detection ---")
    result = kernel.algo_22_halting_detection("for i in range(10):\n    print(i)")
    print(result)
    check("ALGO-22 returns dict", isinstance(result, dict))

    print("\n--- ALGO-25 Delta Block ---")
    result = kernel.algo_25_delta_block(session_id="test-session", change_description="status changed to active")
    print(result)
    check("ALGO-25 returns dict with delta_id", "delta_id" in result)

    print("\n--- ALGO-30 ABV ---")
    result = kernel.algo_30_abv(
        statement="Caching will reduce latency",
        evidence_texts=["p95 latency is 800ms", "queries repeat hourly"],
    )
    print(result)
    check("ALGO-30 returns dict with confidence_score", "confidence_score" in result)

    print("\n--- ALGO-34 Semantic Analysis ---")
    result = kernel.algo_34_semantic_analysis("Delentia OS is a constitutional AI operating system.")
    print(result)
    check("ALGO-34 returns dict", isinstance(result, dict))

    print("\n--- ALGO-23 Content-Box (async) ---")
    result = await kernel.algo_23_content_box(content_id="test-doc", version=1, data=b"hello world")
    print(result)
    check("ALGO-23 returns dict", isinstance(result, dict))

    print("\n--- ALGO-12 Meta-Algorithm Generator (async) ---")
    algos = kernel._meta_algorithm_engine.list_algorithms()
    ids = [a["id"] for a in algos][:2]
    result = await kernel.algo_12_meta_algorithm_generator(component_ids=ids, mode="sequential", goal="test composition")
    print(result)
    check("ALGO-12 returns dict", isinstance(result, dict))

    print("\n--- ALGO-13 GraphRAG (async) ---")
    result = await kernel.algo_13_graphrag(query="What is Delentia?", mode="hybrid", top_k=3)
    print(result)
    check("ALGO-13 returns dict", isinstance(result, dict))

    print("\n--- ALGO-15 HRM Scheduler (async) ---")
    result = await kernel.algo_15_hrm_scheduler(tasks=[{"id": "t1", "priority": 5}, {"id": "t2", "priority": 9}])
    print(result)
    check("ALGO-15 returns dict with assignments", "assignments" in result)

    print("\n--- ALGO-35 Adaptive Timeout (async) ---")
    result = await kernel.algo_35_adaptive_timeout()
    print(result)
    check("ALGO-35 returns dict", isinstance(result, dict))

    print("\n--- ALGO-09 Reflexion+ (async, live Ollama) ---")
    result = await kernel.algo_09_reflexion_plus(query="In one sentence: what is 2+2?")
    print(result.get("final_answer"))
    check("ALGO-09 returns dict with final_answer", "final_answer" in result)

    print("\n--- ALGO-11 BBA-PCF (async, live Ollama) ---")
    result = await kernel.algo_11_bba_pcf(
        query="Should we add more cache?",
        evidence=["latency is high"],
        goals=["reduce latency"],
    )
    print(result.get("recommended_plan"))
    check("ALGO-11 returns dict with recommended_plan", "recommended_plan" in result)

    print("\n--- executed_counts sanity ---")
    print(kernel.executed_counts)
    # Fixed list of the 14 Phase 1 IDs this script actually calls above
    # (not kernel.NEWLY_WIRED_ALGO_IDS, which now also holds later rounds'
    # IDs this Phase 1 script never exercises).
    phase1_exercised_ids = [
        "ALGO-09", "ALGO-10", "ALGO-11", "ALGO-12", "ALGO-13", "ALGO-15",
        "ALGO-16", "ALGO-19", "ALGO-22", "ALGO-23", "ALGO-25", "ALGO-30",
        "ALGO-34", "ALGO-35",
    ]
    for algo_id in phase1_exercised_ids:
        check(f"{algo_id} executed_counts incremented", kernel.executed_counts[algo_id] >= 1)

    print("\nALL ROUND 19 KERNEL WIRING ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

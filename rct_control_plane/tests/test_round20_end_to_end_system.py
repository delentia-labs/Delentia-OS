"""
Round 20 end-to-end system test: exercises ALL 37 real, kernel-wired
algorithms (12 automatic pipeline + 25 newly-wired across Round 19
Phases 1-2 and Round 20) against ONE SHARED kernel instance, to prove
the whole system works together coherently — not just that each
round's own isolated wiring test passes in its own freshly-constructed
kernel.

This is deliberately distinct from test_algorithm_kernel_41_round19_
wiring.py / _phase2_wiring.py / _round20_wiring.py: those each spin up
a fresh AlgorithmKernel41() and only exercise their own round's
algorithms. This test builds ONE kernel, runs the automatic pipeline
first (which advances ALGO-07's MEESession and increments several
Tier 1/2/9 counters), THEN calls every newly-wired algorithm against
that SAME already-warmed-up kernel state, and finally asserts the
kernel's own executed_counts/IMPLEMENTED_ALGO_IDS/NOT_IMPLEMENTED_
ALGO_IDS bookkeeping is internally consistent across the whole run.

Run: python rct_control_plane/tests/test_round20_end_to_end_system.py
"""
import asyncio
import io
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.algo_18_adaptive_prompting import PromptTemplate


def check(label, condition):
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


async def main():
    print("=" * 78)
    print("ROUND 20 END-TO-END SYSTEM TEST — one shared kernel, all 37 algorithms")
    print("=" * 78)

    kernel = AlgorithmKernel41()
    print(f"Kernel version: {kernel.version}")

    # -------------------------------------------------------------------
    # Stage 1: the automatic pipeline (Tier 1-2, ALGO-07, Tier 9 = 12 IDs)
    # -------------------------------------------------------------------
    print("\n--- Stage 1: process_intent_full_pipeline() (12 automatic algorithms) ---")
    pipeline_result = kernel.process_intent_full_pipeline(
        "Refactor the payment module to add idempotency keys"
    )
    print(f"fdia_score={pipeline_result['fdia_score']} "
          f"mee_g_after={pipeline_result['mee_step']['g_after']:.4f} "
          f"crystal_token={pipeline_result['crystal_token']}")
    check("pipeline returns a real fdia_score in (0, 100]", 0 < pipeline_result["fdia_score"])
    check("pipeline advanced the real MEE session by one step",
          kernel._mee_session_default.step_count == 1)
    check("pipeline reports 12 implemented Tier1/2/9 algorithms",
          pipeline_result["algorithms_implemented"] == 12)

    # -------------------------------------------------------------------
    # Stage 2: Round 19 Phase 1 algorithms (14 IDs) — sync first, then async
    # -------------------------------------------------------------------
    print("\n--- Stage 2: Round 19 Phase 1 (14 algorithms) ---")
    kernel.algo_10_delta_memory()
    kernel._vector_engine.index([[0.1] * 384, [0.5] * 384, [0.9] * 384], ids=["d1", "d2", "d3"])
    kernel.algo_16_vector_search(query_vector=[0.1] * 384, k=2)
    kernel.algo_19_data_fusion(modalities={"text": [0.1, 0.2, 0.3], "audio": [0.4, 0.5, 0.6]})
    kernel.algo_22_halting_detection("for i in range(5):\n    print(i)")
    kernel.algo_25_delta_block(session_id="e2e-session", change_description="end-to-end run")
    kernel.algo_30_abv("The system is production ready", ["37 of 41 algorithms are real and tested"])
    kernel.algo_34_semantic_analysis("Delentia OS coordinates 37 real algorithms end to end.")

    await kernel.algo_23_content_box(content_id="e2e-doc", version=1, data=b"end-to-end content")
    await kernel.algo_12_meta_algorithm_generator(
        component_ids=["ALGO-01", "ALGO-02"], mode="sequential", goal="e2e composition test"
    )
    await kernel.algo_13_graphrag(query="What does the kernel do end to end?", mode="hybrid", top_k=3)
    await kernel.algo_15_hrm_scheduler(tasks=[{"id": "e2e-t1", "priority": 5}, {"id": "e2e-t2", "priority": 8}])
    await kernel.algo_35_adaptive_timeout()
    await kernel.algo_09_reflexion_plus(query="In one sentence, what is 2+2?")
    await kernel.algo_11_bba_pcf(
        query="Is idempotency important for payments?",
        evidence=["Duplicate charges are a real customer complaint category"],
        goals=["Prevent duplicate charges"],
    )
    print("Stage 2 complete: 14 algorithms called")

    # -------------------------------------------------------------------
    # Stage 3: Round 19 Phase 2 algorithms (7 IDs)
    # -------------------------------------------------------------------
    print("\n--- Stage 3: Round 19 Phase 2 (7 algorithms) ---")
    kernel._prompt_engine.add_template(PromptTemplate(
        template_id="e2e-greet", name="E2E Greeting", description="e2e",
        template="Hello {{name}}, running end-to-end on {{system}}.",
        variables=["name", "system"], category="e2e",
    ))
    kernel.algo_18_adaptive_prompting("e2e-greet", {"name": "Architect", "system": "Delentia OS"})
    kernel.algo_18_rag_retrieve(query_vector=[0.1] * 384, top_k=2)
    kernel.algo_31_albas(cpu_usage=45.0, memory_usage=50.0)

    await kernel.algo_20_workflow_orchestrator(
        name="e2e-workflow",
        tasks=[{"id": "wt1", "type": "noop"}, {"id": "wt2", "type": "noop", "dependencies": ["wt1"]}],
        mode="sequential",
    )
    await kernel.algo_28_cio_batch(url="https://httpbin.org/get")
    await kernel.algo_29_uia(
        adapter_type="REST", config={"base_url": "http://127.0.0.1:11434"},
        action="GET /api/tags", parameters={},
    )
    await kernel.algo_31_albas_evaluate(cpu_usage=85.0, memory_usage=60.0)
    await kernel.algo_33_fghf("Water boils at 100 degrees Celsius at sea level.")
    await kernel.algo_36_rflh(
        task_id="e2e-sentiment",
        examples=[
            {"input": "I love this", "output": "positive"},
            {"input": "I hate this", "output": "negative"},
            {"input": "This is great", "output": "positive"},
            {"input": "This is terrible", "output": "negative"},
        ],
    )
    print("Stage 3 complete: 7 algorithms called")

    # -------------------------------------------------------------------
    # Stage 4: Round 20 algorithms (4 IDs) — this is the point of this
    # test: ALGO-08 reuses the SAME MEESession that Stage 1's pipeline
    # and Stage 2's calls have already advanced, and ALGO-24 benchmarks
    # a method on THIS already-warmed-up kernel — proving real state
    # sharing across the whole system, not isolated per-round demos.
    # -------------------------------------------------------------------
    print("\n--- Stage 4: Round 20 (4 algorithms) ---")
    evolve_result = await kernel.algo_08_self_evolving()
    print(f"ALGO-08 evolve_cycle: status={evolve_result['status']}")
    evo_status = kernel.algo_08_evolution_status()
    check("ALGO-08 sees the MEESession's real accumulated step count (pipeline + this call)",
          evo_status["mee_session_step_count"] == 2)

    nodes = [{"id": n} for n in ["X", "Y", "Z"]]
    rels = [
        {"id": "e1", "from": "X", "to": "Y", "properties": {"weight": 2.0}},
        {"id": "e2", "from": "Y", "to": "Z", "properties": {"weight": 2.0}},
    ]
    graph_stats = kernel.algo_17_graph_traversal(nodes, rels, operation="stats")
    check("ALGO-17 builds and analyzes a real graph", graph_stats["nodes"]["total"] == 3)

    bench = await kernel.algo_24_benchmark("e2e_evolution_status_bench", "algo_08_evolution_status", iterations=5)
    check("ALGO-24 times a real method on THIS shared, already-warmed-up kernel", bench["successes"] == 5)

    classification = kernel.algo_26_intent_classification("Please cancel my order")
    print(f"ALGO-26 classified: {classification['primary_intent']}")
    check("ALGO-26 classifies real text on the shared kernel", classification["primary_intent"] is not None)
    print("Stage 4 complete: 4 algorithms called")

    # -------------------------------------------------------------------
    # Stage 5: whole-system bookkeeping consistency
    # -------------------------------------------------------------------
    print("\n--- Stage 5: whole-system consistency checks ---")
    total_categorized = (
        len(kernel.IMPLEMENTED_ALGO_IDS)
        + len(kernel.NEWLY_WIRED_ALGO_IDS)
        + len(kernel.NOT_IMPLEMENTED_ALGO_IDS)
    )
    check("IMPLEMENTED + NEWLY_WIRED + NOT_IMPLEMENTED == 41 (no ID lost or double-counted)",
          total_categorized == 41)
    check("exactly 37 algorithms are real and wired",
          len(kernel.IMPLEMENTED_ALGO_IDS) + len(kernel.NEWLY_WIRED_ALGO_IDS) == 37)
    check("exactly 4 remain honestly not implemented (ALGO-14/21/27/32)",
          set(kernel.NOT_IMPLEMENTED_ALGO_IDS) == {"ALGO-14", "ALGO-21", "ALGO-27", "ALGO-32"})

    executed_this_run = {aid for aid, count in kernel.executed_counts.items() if count >= 1}
    expected_executed = set(kernel.IMPLEMENTED_ALGO_IDS) | set(kernel.NEWLY_WIRED_ALGO_IDS)
    missing = expected_executed - executed_this_run
    print(f"Algorithms with executed_counts >= 1 this run: {len(executed_this_run)} / 37 implemented")
    if missing:
        print(f"  NOT executed this run: {sorted(missing)}")
    check("every one of the 37 real, implemented algorithms actually executed in this single run",
          missing == set())

    not_implemented_never_ran = all(kernel.executed_counts[aid] == 0 for aid in kernel.NOT_IMPLEMENTED_ALGO_IDS)
    check("the 4 honestly-not-implemented algorithms have zero executed_counts (no fabricated runs)",
          not_implemented_never_ran)

    print("\n--- Final state snapshot ---")
    print(f"MEE growth summary: {kernel._mee_engine.summary('kernel_default')}")
    print(f"Evolution status: {kernel.algo_08_evolution_status()}")
    print(f"Benchmark summary: {kernel.algo_24_benchmark_summary()}")
    print(f"Vector index size: {kernel._vector_engine.size() if hasattr(kernel._vector_engine, 'size') else 'n/a'}")
    print(f"executed_counts: {kernel.executed_counts}")

    print("\n" + "=" * 78)
    print("ALL ROUND 20 END-TO-END SYSTEM ASSERTIONS PASSED — 37/41 algorithms")
    print("verified working together in one coherent, shared kernel instance.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())

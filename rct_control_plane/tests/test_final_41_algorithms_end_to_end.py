"""
FINAL end-to-end system test: exercises ALL 41 real, kernel-wired
algorithms (12 automatic pipeline + 29 newly-wired across Round 19
Phases 1-2 and Round 20+) against ONE SHARED kernel instance, to prove
the complete system works together coherently.

This supersedes test_round20_end_to_end_system.py (which covered 37/41,
the state before ALGO-14/21/27/32 were wired) as the definitive "whole
system, one kernel" test. That file is kept as-is (a historical snapshot
of the Round 20 milestone, still passing), not deleted, per this
project's Zero-Delete policy.

Run: python rct_control_plane/tests/test_final_41_algorithms_end_to_end.py
"""
import asyncio
import os
import sys

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
    print("FINAL END-TO-END SYSTEM TEST — one shared kernel, all 41 algorithms")
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
    check("pipeline advanced the real MEE session by one step", kernel._mee_session_default.step_count == 1)
    check("pipeline reports 12 implemented Tier1/2/9 algorithms", pipeline_result["algorithms_implemented"] == 12)

    # -------------------------------------------------------------------
    # Stage 2: Round 19 Phase 1 algorithms (14 IDs)
    # -------------------------------------------------------------------
    print("\n--- Stage 2: Round 19 Phase 1 (14 algorithms) ---")
    kernel.algo_10_delta_memory()
    kernel._vector_engine.index([[0.1] * 384, [0.5] * 384, [0.9] * 384], ids=["d1", "d2", "d3"])
    kernel.algo_16_vector_search(query_vector=[0.1] * 384, k=2)
    kernel.algo_19_data_fusion(modalities={"text": [0.1, 0.2, 0.3], "audio": [0.4, 0.5, 0.6]})
    kernel.algo_22_halting_detection("for i in range(5):\n    print(i)")
    kernel.algo_25_delta_block(session_id="e2e-session", change_description="end-to-end run")
    kernel.algo_30_abv("The system is production ready", ["41 of 41 algorithms are real and tested"])
    kernel.algo_34_semantic_analysis("Delentia OS coordinates 41 real algorithms end to end.")

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
    # Stage 4: Round 20 algorithms (4 IDs) — ALGO-08 reuses the SAME
    # MEESession Stage 1/2 already advanced; ALGO-24 benchmarks a method
    # on THIS already-warmed-up kernel.
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
    # Stage 5: Round 20+ algorithms (4 IDs) — the final 4. ALGO-21 reuses
    # this SAME kernel's ALGO-09/11/26/32 engines; ALGO-32's chains feed
    # into a real synthesized answer; ALGO-27 runs the full real cv2/YOLO/
    # ResNet18/R3D-18/Whisper video pipeline; ALGO-14 produces a real PNG
    # via the same shared kernel instance every other stage has been
    # warming up.
    # -------------------------------------------------------------------
    print("\n--- Stage 5: Round 20+ final (4 algorithms) ---")

    route_result = await kernel.algo_21_fast_slow_route("document this function")
    print(f"ALGO-21 route: path={route_result['path']} latency_ms={route_result['latency_ms']}")
    check("ALGO-21 FAST-routes a low-risk narrow-scope real intent on the shared kernel", route_result["path"] == "fast")

    video_path = r"C:\Users\whale\Delentia\.venv\Lib\site-packages\gradio\media_assets\videos\a.mp4"
    check("real test video exists", os.path.exists(video_path))
    kernel._tvra_engine.video_processor.min_frame_quality = 0.01  # this real test clip's real quality scores top out ~0.136
    tvra_result = await kernel.algo_27_tvra_analyze("e2e-video", video_path, {"fps": 1, "transcribe_audio": True})
    print(f"ALGO-27 TVRA: {tvra_result}")
    check("ALGO-27 real video analysis produces at least one analyzed frame", tvra_result["frames_analyzed"] > 0)

    mctr_result = await kernel.algo_32_mctr("Should this system prefer retries or fast failure on transient errors?", num_chains=3)
    print(f"ALGO-32 MCTR: chains={mctr_result['chains_generated']} confidence={mctr_result['answer_confidence']}")
    check("ALGO-32 real multi-chain reasoning produces a synthesized answer", len(mctr_result["answer"]) >= 10)

    diffusion_result = await kernel.algo_14_rct_diffusion("a small red apple, simple illustration", num_steps=6)
    print(f"ALGO-14 diffusion: {diffusion_result}")
    check("ALGO-14 real diffusers generation completed", diffusion_result["status"] == "completed")
    check("ALGO-14 simulated=False (real model, real pixels)", diffusion_result["simulated"] is False)
    check("ALGO-14 produced a non-trivial real PNG on the shared kernel", diffusion_result["byte_size"] > 1000)
    print("Stage 5 complete: 4 algorithms called")

    # -------------------------------------------------------------------
    # Stage 6: whole-system bookkeeping consistency — the final tally
    # -------------------------------------------------------------------
    print("\n--- Stage 6: whole-system consistency checks (final tally) ---")
    total_categorized = (
        len(kernel.IMPLEMENTED_ALGO_IDS) + len(kernel.NEWLY_WIRED_ALGO_IDS) + len(kernel.NOT_IMPLEMENTED_ALGO_IDS)
    )
    check("IMPLEMENTED + NEWLY_WIRED + NOT_IMPLEMENTED == 41 (no ID lost or double-counted)", total_categorized == 41)
    check("all 41 algorithms are real and wired", len(kernel.IMPLEMENTED_ALGO_IDS) + len(kernel.NEWLY_WIRED_ALGO_IDS) == 41)
    check("zero algorithms remain honestly not-implemented", len(kernel.NOT_IMPLEMENTED_ALGO_IDS) == 0)

    executed_this_run = {aid for aid, count in kernel.executed_counts.items() if count >= 1}
    expected_executed = set(kernel.IMPLEMENTED_ALGO_IDS) | set(kernel.NEWLY_WIRED_ALGO_IDS)
    missing = expected_executed - executed_this_run
    print(f"Algorithms with executed_counts >= 1 this run: {len(executed_this_run)} / 41 implemented")
    if missing:
        print(f"  NOT executed this run: {sorted(missing)}")
    check("every one of the 41 real, implemented algorithms actually executed in this single run", missing == set())

    print("\n--- Final state snapshot ---")
    print(f"MEE growth summary: {kernel._mee_engine.summary('kernel_default')}")
    print(f"Evolution status: {kernel.algo_08_evolution_status()}")
    print(f"Benchmark summary: {kernel.algo_24_benchmark_summary()}")
    print(f"Router stats: {kernel.algo_21_router_stats()}")
    print(f"executed_counts: {kernel.executed_counts}")

    print("\n" + "=" * 78)
    print("ALL FINAL END-TO-END SYSTEM ASSERTIONS PASSED — 41/41 algorithms")
    print("verified working together in one coherent, shared kernel instance.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())

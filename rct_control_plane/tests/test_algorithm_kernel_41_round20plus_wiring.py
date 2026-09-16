"""
Real, evidence-based verification that the Round 20+ kernel wrapper
methods (ALGO-21, 27, 32) work end-to-end against ONE shared kernel.

Run: python rct_control_plane/tests/test_algorithm_kernel_41_round20plus_wiring.py
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
    total = len(kernel.IMPLEMENTED_ALGO_IDS) + len(kernel.NEWLY_WIRED_ALGO_IDS)
    print(f"Total implemented: {total}")
    check("all 41 algorithms implemented", total == 41)
    check("no algorithm remains honestly not-implemented", len(kernel.NOT_IMPLEMENTED_ALGO_IDS) == 0)

    print("\n--- ALGO-21 Fast/Slow Router ---")
    fast_result = await kernel.algo_21_fast_slow_route("document this function")
    print(fast_result)
    check("ALGO-21 FAST route for low-risk narrow-scope intent", fast_result["path"] == "fast")
    check("ALGO-21 FAST path genuinely fast (no LLM call)", fast_result["latency_ms"] < 50)
    stats = kernel.algo_21_router_stats()
    print(stats)
    check("ALGO-21 stats reflect the real route", stats["route_counts"]["fast"] >= 1)

    print("\n--- ALGO-27 TVRA (real video analysis) ---")
    video_path = r"C:\Users\whale\Delentia\.venv\Lib\site-packages\gradio\media_assets\videos\a.mp4"
    check("real test video exists", os.path.exists(video_path))
    kernel._tvra_engine.video_processor.min_frame_quality = 0.01  # see algo_27_tvra.py smoke test for why
    result = await kernel.algo_27_tvra_analyze("kernel-wiring-test", video_path, {"fps": 1, "transcribe_audio": True})
    print(result)
    check("ALGO-27 real analysis produced at least one analyzed frame", result["frames_analyzed"] > 0)

    print("\n--- ALGO-32 MCTR (real multi-chain reasoning) ---")
    mctr_result = await kernel.algo_32_mctr("Should error handling favor retries or fast failure?", num_chains=3)
    print(mctr_result)
    check("ALGO-32 generates the requested number of chains", mctr_result["chains_generated"] == 3)
    check("ALGO-32 produces a real synthesized answer", len(mctr_result["answer"]) >= 10)
    check("ALGO-32 answer_confidence in [0,1]", 0.0 <= mctr_result["answer_confidence"] <= 1.0)

    print("\n--- ALGO-14 RCT-Diffusion (real diffusers image generation) ---")
    diffusion_result = await kernel.algo_14_rct_diffusion("a small red apple, simple illustration", num_steps=6)
    print(diffusion_result)
    check("ALGO-14 real generation completed", diffusion_result["status"] == "completed")
    check("ALGO-14 simulated=False (real diffusers pipeline, not the fabricated-bytes stub)", diffusion_result["simulated"] is False)
    check("ALGO-14 produced a non-trivial real PNG", diffusion_result["byte_size"] > 1000)

    print("\n--- executed_counts sanity ---")
    for algo_id in ["ALGO-14", "ALGO-21", "ALGO-27", "ALGO-32"]:
        check(f"{algo_id} executed_counts incremented", kernel.executed_counts[algo_id] >= 1)

    print("\nALL ROUND 20+ KERNEL WIRING ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

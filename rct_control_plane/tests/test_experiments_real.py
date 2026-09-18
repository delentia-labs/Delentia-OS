"""
Real experiments/experiment_runs tests — Round 23 Phase 11 Task 23.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_compare_experiment_runs_reflects_real_benchmark_score_delta():
    persistence = ControlPlanePersistence(db_path="rct_control_plane_agentic.db")
    kernel = AlgorithmKernel41()
    persistence.save_experiment("exp_rct7_benchmark", "RCT-7 Benchmark with Intent tracking")

    async def run():
        r1 = await kernel.process_intent_deep_pipeline(
            "debug why the entire system's payment retry logic sometimes double-charges customers"
        )
        r2 = await kernel.process_intent_deep_pipeline(
            "debug why the entire system's payment retry logic sometimes double-charges customers"
        )
        return r1, r2

    r1, r2 = asyncio.run(run())
    b1 = r1["rct7_step7_benchmark_with_intent"]
    b2 = r2["rct7_step7_benchmark_with_intent"]
    assert b1["applicable"] and b2["applicable"]

    persistence.save_experiment_run("run_1", "exp_rct7_benchmark", "ALGO-04",
                                     metrics={"similarity_score": b1["similarity_score"]})
    persistence.save_experiment_run("run_2", "exp_rct7_benchmark", "ALGO-04",
                                     metrics={"similarity_score": b2["similarity_score"]})

    comparison = persistence.compare_experiment_runs("exp_rct7_benchmark")
    assert "similarity_score" in comparison
    expected_delta = b2["similarity_score"] - b1["similarity_score"]
    assert abs(comparison["similarity_score"]["delta"] - expected_delta) < 1e-9

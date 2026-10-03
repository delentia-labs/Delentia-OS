"""
Real experiments/experiment_runs tests — Round 23 Phase 11 Task 23.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_compare_experiment_runs_reflects_real_benchmark_score_delta(tmp_path, monkeypatch):
    # This goal takes the SLOW route, which really calls the local model (the benchmark is only produced there). On a busy CPU a 7B model can
    # take longer than the 60-90 s read timeouts the algorithms use for interactive work, which made this test fail under a full-suite load
    # (ReadTimeout; it passed alone). The timeouts are lengthened for this test only. The database is a temporary one: it used to be written to
    # rct_control_plane_agentic.db in the working directory (the untracked file in the repository root).
    from rct_control_plane import algo_09_reflexion_plus, algo_11_bba_pcf, llm_provider
    for module in (algo_09_reflexion_plus, algo_11_bba_pcf, llm_provider):
        monkeypatch.setattr(module, "OLLAMA_TIMEOUT_S", 900.0)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "experiments.db"))
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

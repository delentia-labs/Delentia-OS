"""
Real RCTDBFacade tests — Round 23 Phase 11 Task 25.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.rctdb_facade import RCTDBFacade


def test_restore_session_context_matches_real_delta_engine_directly():
    kernel = AlgorithmKernel41()
    kernel.algo_07_mee(growth_signal=0.9)  # real step, creates real "mee_growth" deltas

    facade = RCTDBFacade(persistence=kernel._persistence, delta_engine=kernel._delta_engine,
                          agent_memory=kernel._agent_memory)

    direct_state = kernel._delta_engine.reconstruct_state("mee_growth")
    context = facade.restore_session_context("mee_growth")

    assert context["reconstructed_state"] == direct_state.current_data
    assert context["delta_count"] >= 1

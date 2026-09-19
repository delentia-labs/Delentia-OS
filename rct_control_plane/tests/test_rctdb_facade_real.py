"""
Real RCTDBFacade tests — Round 23 Phase 11 Task 25.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.rctdb_facade import RCTDBFacade

# Round 30 (item 4 of Round 29's candidate list): migrated onto
# shared_kernel - reviewed safe: both sides of the equality check are
# computed fresh within this same test right after the real step, and
# delta_count uses a floor check (>= 1), unaffected by accumulation.


def test_restore_session_context_matches_real_delta_engine_directly(shared_kernel):
    shared_kernel.algo_07_mee(growth_signal=0.9)  # real step, creates real "mee_growth" deltas

    facade = RCTDBFacade(persistence=shared_kernel._persistence, delta_engine=shared_kernel._delta_engine,
                          agent_memory=shared_kernel._agent_memory)

    direct_state = shared_kernel._delta_engine.reconstruct_state("mee_growth")
    context = facade.restore_session_context("mee_growth")

    assert context["reconstructed_state"] == direct_state.current_data
    assert context["delta_count"] >= 1

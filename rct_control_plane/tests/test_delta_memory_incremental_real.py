"""
Real ALGO-10 incremental (state-delta) storage tests — Round 27 Phase 21
Task 44.

Master doc (DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md, section 3, ALGO-10)
specifies "long-term incremental storage" of state deltas, linked to
ALGO-03. The real ALGO-10 slot (algo_10_delta_memory) is a Vault-1068
document client - a real, confirmed naming collision (see
Chapter03_Vault1068_and_RCTDB_full.md). The actual "state-delta, linked to
ALGO-03" capability the master doc describes already exists for real under
ALGO-25 (algo_25_delta_block / DeltaEngine). This closes the ALGO-10 gap
honestly via delegation, not duplicated logic.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Round 30 (item 4 of Round 29's candidate list): migrated onto
# shared_kernel - reviewed safe: uses a unique session_id and filters
# deltas by this call's own real delta_id, unaffected by accumulation
# from other tests sharing this kernel.


def test_incremental_store_matches_a_direct_algo25_call(shared_kernel):
    result = shared_kernel.algo_10_delta_memory_incremental_store("test_session_algo10", "real change description")

    assert "delta_id" in result
    assert "stats" in result
    deltas = shared_kernel._delta_engine.get_session_deltas("test_session_algo10")
    matching = [d for d in deltas if d.delta_id == result["delta_id"]]
    assert len(matching) == 1
    assert matching[0].source == "algo_10"

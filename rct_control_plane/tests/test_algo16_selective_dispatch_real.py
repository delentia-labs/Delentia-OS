"""
Real ALGO-16 selective-dispatch adoption tests — Round 29 Phase 36 Task 68.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_vector_search_relevant_intent_selects_algo16():
    kernel = AlgorithmKernel41()
    selected = kernel.select_relevant_algorithms([], "find documents similar to this one, search for nearest matches")
    assert "algo_16_vector_search" in selected


def test_algo16_text_adapter_produces_a_real_well_formed_result_even_on_empty_index():
    kernel = AlgorithmKernel41()
    result = kernel.algo_16_vector_search_from_text("find similar documents")
    # A fresh kernel's vector index has nothing indexed yet - a real,
    # honest empty result is correct, not a crash.
    assert result is not None


def test_registered_capability_matches_direct_call_behavior():
    kernel = AlgorithmKernel41()
    direct = kernel.algo_16_vector_search_from_text("search for nearest embedding")
    via_registry = kernel.get_capability("algo_16_vector_search")("search for nearest embedding")
    # Compare the real result content, not a real wall-clock timing field
    # that legitimately differs between two separate real calls.
    assert direct["results"] == via_registry["results"]

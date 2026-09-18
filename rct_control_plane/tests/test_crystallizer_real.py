"""
Real ALGO-41 Golden Keyword Crystallizer tests — Round 24 Phase 13 Task 29.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_crystallize_golden_keywords_ranks_dense_words_above_trivial_ones():
    kernel = AlgorithmKernel41()
    text = "the payment retry logic sometimes fails due to idempotency violations across services"

    result = kernel.crystallize_golden_keywords(text)

    assert len(result["golden_keywords"]) >= 1
    keyword_words = [k["word"] for k in result["golden_keywords"]]
    assert "idempotency" in keyword_words, f"expected a real high-entropy word among golden keywords; got {keyword_words}"

    for k in result["golden_keywords"]:
        assert k["entropy_score"] >= 0.8

    assert result["concept_map_nodes_added"] >= 1
    assert "idempotency" in kernel._graph_engine.nodes

    assert result["fed_to_itsr"] is not None

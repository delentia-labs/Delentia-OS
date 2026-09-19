"""
Real ALGO-41 Golden Keyword Crystallizer tests — Round 24 Phase 13 Task 29.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))



def test_crystallize_golden_keywords_ranks_dense_words_above_trivial_ones(shared_kernel):
    # Round 29 Phase 33 Task 65: migrated onto shared_kernel - reviewed
    # safe: assertions are a membership check ("idempotency" in nodes) and
    # floor checks (>= 1), not exact-count checks, so accumulation from
    # other tests sharing this kernel cannot break them.
    text = "the payment retry logic sometimes fails due to idempotency violations across services"

    result = shared_kernel.crystallize_golden_keywords(text)

    assert len(result["golden_keywords"]) >= 1
    keyword_words = [k["word"] for k in result["golden_keywords"]]
    assert "idempotency" in keyword_words, f"expected a real high-entropy word among golden keywords; got {keyword_words}"

    for k in result["golden_keywords"]:
        assert k["entropy_score"] >= 0.8

    assert result["concept_map_nodes_added"] >= 1
    assert "idempotency" in shared_kernel._graph_engine.nodes

    assert result["fed_to_itsr"] is not None

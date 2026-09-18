"""
Real SemanticMatcher tests — Round 22 Phase 9 (ported from
Delentia-Private-OS's semantic_matcher.py).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.semantic_matcher import SemanticMatcher


def test_relevant_candidate_ranks_above_irrelevant_one():
    matcher = SemanticMatcher()
    results = matcher.match(
        query="payment retry logic double charges customers",
        candidates=[
            "the payment retry logic sometimes double-charges customers on network errors",
            "the weather today is sunny with a light breeze",
            "unrelated text about gardening and plants",
        ],
        top_k=3,
    )
    assert results[0]["text"].startswith("the payment retry logic")
    assert results[0]["score"] > results[-1]["score"]

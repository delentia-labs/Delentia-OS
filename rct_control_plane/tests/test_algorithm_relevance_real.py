"""
Real algorithm relevance selector tests — Round 25 Phase 16 Task 35.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_diffusion_relevant_intent_selects_algo_14():
    kernel = AlgorithmKernel41()
    keywords = kernel.crystallize_golden_keywords("create a wireframe design for the dashboard")
    selected = kernel.select_relevant_algorithms(keywords["golden_keywords"], "create a wireframe design for the dashboard")
    assert "algo_14_rct_diffusion" in selected


def test_research_relevant_intent_selects_algo_13():
    kernel = AlgorithmKernel41()
    keywords = kernel.crystallize_golden_keywords("explain the research on payment idempotency")
    selected = kernel.select_relevant_algorithms(keywords["golden_keywords"], "explain the research on payment idempotency")
    assert "algo_13_graphrag" in selected


def test_generic_intent_selects_nothing():
    kernel = AlgorithmKernel41()
    keywords = kernel.crystallize_golden_keywords("fix the login button")
    selected = kernel.select_relevant_algorithms(keywords["golden_keywords"], "fix the login button")
    assert selected == []

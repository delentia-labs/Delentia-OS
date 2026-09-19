"""
Real algorithm relevance selector tests — Round 25 Phase 16 Task 35.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Round 29 Phase 33 Task 65: migrated onto the shared_kernel fixture
# (rct_control_plane/tests/conftest.py) - reviewed and confirmed safe:
# crystallize_golden_keywords mutates self._graph_engine (adds nodes) but
# none of these assertions depend on graph state, only on the golden
# keywords/selection returned for THIS call's own input text.


def test_diffusion_relevant_intent_selects_algo_14(shared_kernel):
    keywords = shared_kernel.crystallize_golden_keywords("create a wireframe design for the dashboard")
    selected = shared_kernel.select_relevant_algorithms(keywords["golden_keywords"], "create a wireframe design for the dashboard")
    assert "algo_14_rct_diffusion" in selected


def test_research_relevant_intent_selects_algo_13(shared_kernel):
    keywords = shared_kernel.crystallize_golden_keywords("explain the research on payment idempotency")
    selected = shared_kernel.select_relevant_algorithms(keywords["golden_keywords"], "explain the research on payment idempotency")
    assert "algo_13_graphrag" in selected


def test_generic_intent_selects_nothing(shared_kernel):
    keywords = shared_kernel.crystallize_golden_keywords("fix the login button")
    selected = shared_kernel.select_relevant_algorithms(keywords["golden_keywords"], "fix the login button")
    assert selected == []

"""
Real Nodal Assembly tests — Round 21 Phase 3.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.nodal_assembly import wrap_as_thought_chain
from rct_control_plane.algo_32_mctr import ThoughtChain


def test_wrap_real_dict_result_as_thought_chain():
    real_result = {"nodes": ["payment", "retry"], "graph_stats": {"nodes": {"total": 2}}}
    chain = wrap_as_thought_chain("algo_05_graphrag", "analyze payment retry logic", real_result, confidence=0.9)
    assert isinstance(chain, ThoughtChain)
    assert chain.query == "analyze payment retry logic"
    assert len(chain.steps) == 1
    assert chain.steps[0].confidence == 0.9
    assert chain.confidence == 0.9
    assert chain.simulated is False
    assert chain.metadata["node_id"] == "algo_05_graphrag"
    assert "payment" in chain.steps[0].reasoning or "payment" in str(chain.steps[0].evidence)

"""
Real Nodal Assembly tests — Round 21 Phase 3.
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.nodal_assembly import wrap_as_thought_chain, assemble
from rct_control_plane.algo_32_mctr import ThoughtChain, ChainMerger, AnswerSynthesizer


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


def test_assemble_real_parallel_nodes_and_merge():
    def node_a():
        return {"finding": "real node A result"}

    async def node_b():
        await asyncio.sleep(0.01)
        return {"finding": "real node B result"}

    async def run():
        return await assemble(
            query="test assembly",
            nodes=[("node_a", node_a, (), {}), ("node_b", node_b, (), {})],
            merger=ChainMerger(), synthesizer=AnswerSynthesizer(),
        )

    answer = asyncio.run(run())
    assert answer.chains_used == 2
    assert len(answer.answer) >= 10


def test_assemble_real_kernel_algorithms():
    from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41

    kernel = AlgorithmKernel41()
    kernel._vector_engine.index([[0.1] * 384, [0.9] * 384], ids=["d1", "d2"])

    async def run():
        return await assemble(
            query="analyze the payment retry keyword",
            nodes=[
                ("algo_05_graphrag", kernel.algo_05_graphrag, ("payment retry logic",), {}),
                ("algo_16_vector_search", kernel.algo_16_vector_search, ([0.1] * 384,), {"k": 2}),
            ],
            merger=ChainMerger(), synthesizer=AnswerSynthesizer(),
        )

    answer = asyncio.run(run())
    assert answer.chains_used == 2
    assert len(answer.answer) >= 10

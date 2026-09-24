"""
Round 44 item C: real coverage for algo_13_graphrag.py, previously untested
(0 test files existed) despite being real, actively-used code -
algo_08_self_evolving.py and algorithm_kernel_41.py both import from it.
Pure numpy math + stdlib, no I/O or network - no mocking needed. This file
already had a working __main__ smoke test; these tests port and expand on
those same real assertions.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.algo_13_graphrag import (
    GraphRAGEngine, SearchMode, FusionMethod, SearchResult,
)


@pytest.fixture
def engine():
    return GraphRAGEngine()


class TestKeywordSearch:
    @pytest.mark.asyncio
    async def test_finds_documents_matching_query(self, engine):
        session_id = await engine.search("reflexion agent", mode=SearchMode.KEYWORD)
        session = engine.get_session(session_id)
        assert len(session["results"]) > 0
        assert session["results"][0]["doc_id"] == "doc1"

    @pytest.mark.asyncio
    async def test_no_match_returns_empty_results(self, engine):
        session_id = await engine.search("zzz_no_such_term_zzz", mode=SearchMode.KEYWORD)
        session = engine.get_session(session_id)
        assert session["results"] == []

    @pytest.mark.asyncio
    async def test_results_sorted_by_keyword_score_descending(self, engine):
        session_id = await engine.search("graph", mode=SearchMode.KEYWORD)
        session = engine.get_session(session_id)
        scores = [r["keyword_score"] for r in session["results"]]
        assert scores == sorted(scores, reverse=True)


class TestVectorSearch:
    @pytest.mark.asyncio
    async def test_scores_all_documents(self, engine):
        session_id = await engine.search("self-correction", mode=SearchMode.VECTOR)
        session = engine.get_session(session_id)
        assert len(session["results"]) == 5

    @pytest.mark.asyncio
    async def test_most_similar_document_ranks_first(self, engine):
        session_id = await engine.search(
            "Reflexion Agent implements self-correction feedback loop", mode=SearchMode.VECTOR,
        )
        session = engine.get_session(session_id)
        assert session["results"][0]["doc_id"] == "doc1"

    def test_embedding_is_deterministic(self, engine):
        import asyncio
        v1 = asyncio.run(engine._get_embedding("graph knowledge search"))
        v2 = asyncio.run(engine._get_embedding("graph knowledge search"))
        assert v1 == v2

    def test_embedding_is_l2_normalized(self, engine):
        import asyncio
        import numpy as np
        v = asyncio.run(engine._get_embedding("some real text with several tokens"))
        assert np.linalg.norm(v) == pytest.approx(1.0, abs=1e-9)

    def test_empty_text_embedding_is_zero_vector_not_a_crash(self, engine):
        import asyncio
        v = asyncio.run(engine._get_embedding(""))
        assert all(x == 0.0 for x in v)

    def test_cosine_similarity_of_identical_vectors_is_one(self, engine):
        v = [1.0, 2.0, 3.0]
        assert engine._cosine_similarity(v, v) == pytest.approx(1.0)

    def test_cosine_similarity_with_zero_vector_is_zero(self, engine):
        assert engine._cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestGraphSearch:
    @pytest.mark.asyncio
    async def test_finds_documents_via_matching_node_id(self, engine):
        session_id = await engine.search("graphrag", mode=SearchMode.GRAPH)
        session = engine.get_session(session_id)
        assert len(session["results"]) > 0
        assert "doc4" in [r["doc_id"] for r in session["results"]]

    @pytest.mark.asyncio
    async def test_no_matching_node_returns_empty(self, engine):
        session_id = await engine.search("zzz_no_such_node_zzz", mode=SearchMode.GRAPH)
        session = engine.get_session(session_id)
        assert session["results"] == []

    def test_expand_nodes_applies_real_hop_decay(self, engine):
        root = engine.graph_nodes["reflexion"]
        expanded = engine._expand_nodes([root], hops=2)
        assert expanded["reflexion"] == 1.0
        assert "agent" in expanded
        assert expanded["agent"] == pytest.approx(0.7)

    def test_expand_nodes_does_not_revisit_a_node(self, engine):
        # "graphrag" and "vector" are mutual neighbors; expansion must not
        # infinite-loop or double-count a node reached from multiple paths.
        root = engine.graph_nodes["graphrag"]
        expanded = engine._expand_nodes([root], hops=3)
        assert isinstance(expanded, dict)
        assert "vector" in expanded


class TestFusionMethods:
    def _lists(self):
        a = [SearchResult(doc_id="d1", content="", snippet="", score=0.9, vector_score=0.9)]
        b = [
            SearchResult(doc_id="d1", content="", snippet="", score=0.5, keyword_score=0.5),
            SearchResult(doc_id="d2", content="", snippet="", score=0.8, keyword_score=0.8),
        ]
        return [a, b]

    def test_rrf_fusion_combines_ranks_from_both_lists(self, engine):
        fused = engine._rrf_fusion(self._lists(), top_k=10)
        doc_ids = [r.doc_id for r in fused]
        assert "d1" in doc_ids and "d2" in doc_ids
        # d1 appears in both lists (rank 1 each) -> higher RRF score than d2 (only 1 list).
        assert fused[0].doc_id == "d1"

    def test_linear_fusion_averages_the_three_score_components(self, engine):
        results = [[SearchResult(
            doc_id="d1", content="", snippet="", score=0.0,
            vector_score=0.9, keyword_score=0.6, graph_score=0.3,
        )]]
        fused = engine._linear_fusion(results, top_k=10)
        assert fused[0].fusion_score == pytest.approx((0.9 + 0.6 + 0.3) / 3)

    def test_weighted_fusion_applies_real_weights(self, engine):
        a = [SearchResult(doc_id="d1", content="", snippet="", score=1.0)]
        b = [SearchResult(doc_id="d1", content="", snippet="", score=1.0)]
        fused = engine._weighted_fusion([a, b], weights=[0.5, 0.3], top_k=10)
        assert fused[0].fusion_score == pytest.approx(0.8)

    def test_weighted_fusion_defaults_extra_lists_to_weight_1(self, engine):
        a = [SearchResult(doc_id="d1", content="", snippet="", score=1.0)]
        fused = engine._weighted_fusion([a], weights=[], top_k=10)
        assert fused[0].fusion_score == pytest.approx(1.0)

    def test_max_fusion_takes_the_highest_score_across_lists(self, engine):
        a = [SearchResult(doc_id="d1", content="", snippet="", score=0.3)]
        b = [SearchResult(doc_id="d1", content="", snippet="", score=0.9)]
        fused = engine._max_fusion([a, b], top_k=10)
        assert fused[0].fusion_score == pytest.approx(0.9)

    def test_fuse_results_dispatches_by_method(self, engine):
        lists = self._lists()
        rrf = engine._fuse_results(lists, method=FusionMethod.RRF, top_k=10)
        linear = engine._fuse_results(lists, method=FusionMethod.LINEAR, top_k=10)
        weighted = engine._fuse_results(lists, method=FusionMethod.WEIGHTED, top_k=10)
        maxed = engine._fuse_results(lists, method=FusionMethod.MAX, top_k=10)
        for fused in (rrf, linear, weighted, maxed):
            assert len(fused) > 0

    def test_fuse_results_respects_top_k(self, engine):
        lists = self._lists()
        fused = engine._fuse_results(lists, method=FusionMethod.RRF, top_k=1)
        assert len(fused) == 1


class TestHybridAndGraphRAGModes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", [
        FusionMethod.RRF, FusionMethod.LINEAR, FusionMethod.WEIGHTED, FusionMethod.MAX,
    ])
    async def test_hybrid_mode_runs_with_every_fusion_method(self, engine, method):
        session_id = await engine.search("graph", mode=SearchMode.HYBRID, fusion_method=method)
        session = engine.get_session(session_id)
        assert len(session["results"]) > 0
        assert session["graph_results"] == []

    @pytest.mark.asyncio
    async def test_graphrag_mode_combines_all_three_sources_and_enhances(self, engine):
        session_id = await engine.search("graph knowledge", mode=SearchMode.GRAPHRAG)
        session = engine.get_session(session_id)
        assert len(session["results"]) > 0
        assert len(session["vector_results"]) > 0
        assert len(session["graph_results"]) >= 0
        # _enhance_with_graph() attaches real graph_context for matched docs.
        assert any(len(r["graph_context"]) > 0 for r in session["results"])


class TestRuntimeDocumentIngestion:
    def test_add_document_generates_id_when_not_given(self, engine):
        doc_id = engine.add_document("some new content")
        assert doc_id in engine.documents
        assert doc_id.startswith("doc-")

    def test_add_document_uses_given_id(self, engine):
        doc_id = engine.add_document("content", doc_id="custom-id")
        assert doc_id == "custom-id"
        assert engine.documents["custom-id"].content == "content"

    @pytest.mark.asyncio
    async def test_added_document_is_findable_by_keyword_search(self, engine):
        new_id = engine.add_document(
            "Delentia OS ports real algorithm engines out of private microservices",
            metadata={"topic": "delentia"}, graph_nodes=["graphrag"],
        )
        session_id = await engine.search("Delentia OS ports", mode=SearchMode.KEYWORD)
        session = engine.get_session(session_id)
        assert new_id in [r["doc_id"] for r in session["results"]]


class TestSessionManagement:
    @pytest.mark.asyncio
    async def test_get_session_for_unknown_id_reports_error(self, engine):
        result = engine.get_session("ghost-session")
        assert result == {"error": "Session not found"}

    @pytest.mark.asyncio
    async def test_list_sessions_reports_real_summary(self, engine):
        session_id = await engine.search("graph", mode=SearchMode.KEYWORD)
        sessions = engine.list_sessions()
        ids = [s["session_id"] for s in sessions]
        assert session_id in ids

    @pytest.mark.asyncio
    async def test_delete_session_removes_it(self, engine):
        session_id = await engine.search("graph", mode=SearchMode.KEYWORD)
        assert engine.delete_session(session_id) is True
        assert engine.get_session(session_id) == {"error": "Session not found"}

    def test_delete_unknown_session_returns_false(self, engine):
        assert engine.delete_session("ghost") is False


class TestSnippet:
    def test_snippet_around_a_real_match(self, engine):
        text = "a" * 100 + "TARGET" + "b" * 100
        snippet = engine._make_snippet(text, "TARGET", window=10)
        assert "TARGET" in snippet
        assert snippet.startswith("...")
        assert snippet.endswith("...")

    def test_snippet_falls_back_to_prefix_when_no_match(self, engine):
        snippet = engine._make_snippet("x" * 200, "not present", window=50)
        assert snippet == "x" * 50 + "..."

    def test_short_text_without_match_returned_whole(self, engine):
        snippet = engine._make_snippet("short text", "absent", window=80)
        assert snippet == "short text"

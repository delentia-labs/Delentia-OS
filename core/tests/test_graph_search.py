"""
Phase 4 Tests — LocalGraphRAG (core.graph_search)
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from core.graph_search import LocalGraphRAG, GraphSearchResult, GraphRAGInterface
    import networkx  # noqa: F401
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _NX_AVAILABLE, reason="networkx not installed")


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def populated_graph() -> "LocalGraphRAG":
    g = LocalGraphRAG()
    g.add_node("n1", title="Machine Learning", content="algorithms neural network training data")
    g.add_node("n2", title="Deep Learning",    content="neural networks convolutional layers activation")
    g.add_node("n3", title="Market Finance",   content="stock market investment portfolio returns")
    g.add_node("n4", title="Supply Chain",     content="logistics inventory optimization warehouse")
    g.add_edge("n1", "n2")
    g.add_edge("n2", "n1")
    return g


# ─────────────────────────────────────────────────────────────────────────────
# GraphRAGInterface contract
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphRAGInterfaceContract:
    def test_local_graph_rag_is_subclass(self):
        assert issubclass(LocalGraphRAG, GraphRAGInterface)

    def test_graph_search_result_is_dataclass(self):
        from dataclasses import fields
        assert len(fields(GraphSearchResult)) > 0


# ─────────────────────────────────────────────────────────────────────────────
# add_node / get_node
# ─────────────────────────────────────────────────────────────────────────────

class TestLocalGraphRAGNodes:
    def test_add_and_get_node(self):
        g = LocalGraphRAG()
        g.add_node("x1", title="Test Node", content="some content here")
        result = g.get_node("x1")
        assert result is not None
        assert result.node_id == "x1"
        assert result.title == "Test Node"

    def test_get_missing_node_returns_none(self):
        g = LocalGraphRAG()
        assert g.get_node("nonexistent") is None

    def test_node_count_increases(self):
        g = LocalGraphRAG()
        assert g.node_count == 0
        g.add_node("a", "A", "content a")
        assert g.node_count == 1
        g.add_node("b", "B", "content b")
        assert g.node_count == 2

    def test_add_node_with_metadata(self):
        g = LocalGraphRAG()
        g.add_node("m1", "Meta", "content", metadata={"source": "wiki", "year": 2024})
        result = g.get_node("m1")
        assert result.metadata["source"] == "wiki"


# ─────────────────────────────────────────────────────────────────────────────
# add_edge
# ─────────────────────────────────────────────────────────────────────────────

class TestLocalGraphRAGEdges:
    def test_add_edge_increases_edge_count(self):
        g = LocalGraphRAG()
        g.add_node("e1", "E1", "content e1")
        g.add_node("e2", "E2", "content e2")
        assert g.edge_count == 0
        g.add_edge("e1", "e2")
        assert g.edge_count == 1

    def test_add_edge_missing_node_raises(self):
        g = LocalGraphRAG()
        g.add_node("src", "Source", "content")
        with pytest.raises(ValueError, match="Both nodes must exist"):
            g.add_edge("src", "missing_target")

    def test_neighbors_visible_after_edge(self, populated_graph):
        result = populated_graph.get_node("n1")
        assert "n2" in result.neighbors


# ─────────────────────────────────────────────────────────────────────────────
# search
# ─────────────────────────────────────────────────────────────────────────────

class TestLocalGraphRAGSearch:
    def test_search_returns_list(self, populated_graph):
        results = populated_graph.search("neural network")
        assert isinstance(results, list)

    def test_search_relevant_result_ranked_first(self, populated_graph):
        results = populated_graph.search("neural network deep learning")
        assert len(results) > 0
        # n1 or n2 should appear in top results (both have "neural" in content)
        top_ids = [r.node_id for r in results[:2]]
        assert any(nid in top_ids for nid in ("n1", "n2"))

    def test_search_returns_graph_search_result_objects(self, populated_graph):
        results = populated_graph.search("machine learning")
        for r in results:
            assert isinstance(r, GraphSearchResult)
            assert r.score >= 0.0

    def test_search_top_k_limits_results(self, populated_graph):
        results = populated_graph.search("learning", top_k=1)
        assert len(results) <= 1

    def test_search_min_score_filters_results(self, populated_graph):
        results = populated_graph.search("learning", min_score=0.5)
        for r in results:
            assert r.score >= 0.5

    def test_search_empty_graph_returns_empty(self):
        g = LocalGraphRAG()
        results = g.search("anything")
        assert results == []

    def test_search_empty_query_returns_empty(self, populated_graph):
        results = populated_graph.search("")
        assert results == []

    def test_search_stopwords_only_returns_empty(self, populated_graph):
        """Query containing only stop words produces no tokens → empty result."""
        results = populated_graph.search("the is a")
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# IDF rebuild (dirty flag)
# ─────────────────────────────────────────────────────────────────────────────

class TestIDFRebuild:
    def test_idf_rebuilt_after_new_node(self):
        g = LocalGraphRAG()
        g.add_node("z1", "Z1", "unique term zephyr")
        _ = g.search("zephyr")
        # IDF should now be computed
        assert not g._dirty
        g.add_node("z2", "Z2", "another unique content")
        assert g._dirty  # new node should set dirty
        _ = g.search("unique")
        assert not g._dirty  # search should rebuild

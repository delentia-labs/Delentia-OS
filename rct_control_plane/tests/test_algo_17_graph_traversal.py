"""
Round 45 item C: real tests for ALGO-17 (GraphEngine, in-memory layer),
genuinely used by algorithm_kernel_41.py. Ported and expanded from the
file's own __main__ smoke test (same real graph shape and assertions -
including the real weighted-Dijkstra-vs-hop-count and real
dangling-mass-leak PageRank properties it documents), plus per-branch
edge cases: missing-node errors, relationship_type filtering, max_depth
limiting, no-path cases, and empty/single-node degenerate inputs.
"""
import pytest

from rct_control_plane.algo_17_graph_traversal import GraphEngine, GraphNode, GraphRelationship


@pytest.fixture
def linear_graph():
    """A -> B -> C -> D (weight 1 each), plus a real A -> D shortcut
    (weight 10) - the exact shape the file's own smoke test uses, so
    Dijkstra must prefer the 3-hop weight-3 path over the 1-hop
    weight-10 shortcut."""
    engine = GraphEngine()
    for nid in ["A", "B", "C", "D"]:
        engine.add_node(GraphNode(node_id=nid, labels=["TestNode"], properties={"name": nid}))
    engine.add_relationship(GraphRelationship("r1", "A", "B", "CONNECTS", {"weight": 1.0}))
    engine.add_relationship(GraphRelationship("r2", "B", "C", "CONNECTS", {"weight": 1.0}))
    engine.add_relationship(GraphRelationship("r3", "C", "D", "CONNECTS", {"weight": 1.0}))
    engine.add_relationship(GraphRelationship("r4", "A", "D", "SHORTCUT", {"weight": 10.0}))
    return engine


class TestAddNodeAndRelationship:
    def test_added_node_is_retrievable(self):
        engine = GraphEngine()
        engine.add_node(GraphNode(node_id="X", labels=["L"], properties={}))
        assert "X" in engine.nodes
        assert "X" in engine.graph

    def test_relationship_creates_missing_from_and_to_graph_entries(self):
        engine = GraphEngine()
        engine.add_relationship(GraphRelationship("r1", "A", "B", "CONNECTS"))
        assert "A" in engine.graph
        assert "B" in engine.graph["A"]
        assert engine.relationships["r1"].relationship_id == "r1"


class TestBFS:
    def test_real_bfs_order_matches_the_documented_smoke_test(self, linear_graph):
        result = linear_graph.bfs("A", max_depth=3)
        assert [n["node_id"] for n in result] == ["A", "B", "D", "C"]

    def test_missing_start_node_raises(self, linear_graph):
        with pytest.raises(ValueError, match="not found"):
            linear_graph.bfs("ZZZ")

    def test_max_depth_limits_real_traversal(self, linear_graph):
        result = linear_graph.bfs("A", max_depth=1)
        assert {n["node_id"] for n in result} == {"A", "B", "D"}
        assert "C" not in {n["node_id"] for n in result}

    def test_relationship_type_filter_excludes_the_real_shortcut_edge(self, linear_graph):
        result = linear_graph.bfs("A", max_depth=3, relationship_types=["CONNECTS"])
        node_ids = {n["node_id"] for n in result}
        assert node_ids == {"A", "B", "C", "D"}
        # D is reached via C (3 hops), not directly - depth must reflect that.
        d_entry = next(n for n in result if n["node_id"] == "D")
        assert d_entry["depth"] == 3

    def test_node_with_no_properties_entry_still_returns_defaults(self):
        engine = GraphEngine()
        engine.add_relationship(GraphRelationship("r1", "A", "B", "CONNECTS"))
        result = engine.bfs("A")
        a_entry = result[0]
        assert a_entry["labels"] == []
        assert a_entry["properties"] == {}


class TestDFS:
    def test_missing_start_node_raises(self, linear_graph):
        with pytest.raises(ValueError, match="not found"):
            linear_graph.dfs("ZZZ")

    def test_real_dfs_visits_every_reachable_node(self, linear_graph):
        result = linear_graph.dfs("A", max_depth=3)
        assert {n["node_id"] for n in result} == {"A", "B", "C", "D"}

    def test_max_depth_limits_real_dfs_traversal(self, linear_graph):
        result = linear_graph.dfs("A", max_depth=0)
        assert [n["node_id"] for n in result] == ["A"]

    def test_relationship_type_filter_applies_to_dfs_too(self, linear_graph):
        result = linear_graph.dfs("A", max_depth=3, relationship_types=["SHORTCUT"])
        assert {n["node_id"] for n in result} == {"A", "D"}


class TestShortestPath:
    def test_dijkstra_prefers_real_lower_total_weight_over_fewer_hops(self, linear_graph):
        path = linear_graph.shortest_path("A", "D")
        assert path is not None
        assert path.nodes == ["A", "B", "C", "D"]
        assert path.total_weight == 3.0
        assert path.length == 3

    def test_missing_start_node_raises(self, linear_graph):
        with pytest.raises(ValueError, match="not found"):
            linear_graph.shortest_path("ZZZ", "D")

    def test_missing_end_node_raises(self, linear_graph):
        with pytest.raises(ValueError, match="not found"):
            linear_graph.shortest_path("A", "ZZZ")

    def test_no_real_path_returns_none(self):
        engine = GraphEngine()
        engine.add_node(GraphNode(node_id="A", labels=[], properties={}))
        engine.add_node(GraphNode(node_id="B", labels=[], properties={}))
        # A and B both exist but are genuinely disconnected.
        engine.graph["A"] = {}
        assert engine.shortest_path("A", "B") is None

    def test_relationship_type_filter_can_force_the_only_remaining_path(self, linear_graph):
        # With CONNECTS-only, the 1-hop SHORTCUT edge is invisible, so the
        # 3-hop weight-3 path is the ONLY real path, not just preferred.
        path = linear_graph.shortest_path("A", "D", relationship_types=["CONNECTS"])
        assert path is not None
        assert path.nodes == ["A", "B", "C", "D"]

    def test_a_stale_heap_entry_for_an_already_visited_node_is_skipped(self):
        # A real Dijkstra property, verified by direct trace, not a
        # guess: X is reachable two ways - directly from A (weight 5) and
        # via A->C->X (weight 1+1=2). Both (5, X) and (2, X) genuinely
        # land in the priority queue. Target is D (past X, weight 10 from
        # X), not X itself, so the loop does NOT stop before the stale
        # (5, X) entry is popped - X is already visited by then, so it
        # must hit the real continue-on-stale-entry branch to proceed to D.
        engine = GraphEngine()
        for nid in ["A", "C", "X", "D"]:
            engine.add_node(GraphNode(node_id=nid, labels=[], properties={}))
        engine.add_relationship(GraphRelationship("r1", "A", "X", "CONNECTS", {"weight": 5.0}))
        engine.add_relationship(GraphRelationship("r2", "A", "C", "CONNECTS", {"weight": 1.0}))
        engine.add_relationship(GraphRelationship("r3", "C", "X", "CONNECTS", {"weight": 1.0}))
        engine.add_relationship(GraphRelationship("r4", "X", "D", "CONNECTS", {"weight": 10.0}))

        path = engine.shortest_path("A", "D")
        assert path is not None
        assert path.nodes == ["A", "C", "X", "D"]
        assert path.total_weight == 12.0


class TestPageRank:
    def test_empty_graph_returns_empty_dict(self):
        engine = GraphEngine()
        assert engine.pagerank() == {}

    def test_single_isolated_node_converges_to_the_real_teleportation_term(self):
        # An isolated node has no incoming edges (not even a self-loop),
        # so rank_sum stays 0 every iteration - the real formula reduces
        # to just (1 - damping_factor) / n, not the initial 1.0/n mass.
        engine = GraphEngine()
        engine.add_node(GraphNode(node_id="A", labels=[], properties={}))
        ranks = engine.pagerank(iterations=5, damping_factor=0.85)
        assert ranks["A"] == pytest.approx(0.15)

    def test_sink_node_with_more_real_incoming_edges_outranks_a_source(self, linear_graph):
        ranks = linear_graph.pagerank(iterations=20)
        assert all(v >= 0 for v in ranks.values())
        # D has 2 real incoming edges (C->D, A->D); A has 0 incoming edges.
        assert ranks["D"] > ranks["A"]

    def test_relationship_type_filter_changes_the_real_outgoing_graph(self, linear_graph):
        ranks_all = linear_graph.pagerank(iterations=10)
        ranks_shortcut_only = linear_graph.pagerank(relationship_type="SHORTCUT", iterations=10)
        assert ranks_all != ranks_shortcut_only


class TestGetNeighborsAndDegree:
    def test_get_neighbors_of_unknown_node_is_empty(self, linear_graph):
        assert linear_graph.get_neighbors("ZZZ") == []

    def test_get_neighbors_returns_real_direct_targets(self, linear_graph):
        neighbors = linear_graph.get_neighbors("A")
        assert set(neighbors) == {"B", "D"}

    def test_get_neighbors_respects_relationship_type_filter(self, linear_graph):
        assert linear_graph.get_neighbors("A", relationship_types=["SHORTCUT"]) == ["D"]

    def test_get_node_degree_of_unknown_node_is_zero(self, linear_graph):
        assert linear_graph.get_node_degree("ZZZ") == 0

    def test_get_node_degree_counts_real_distinct_neighbors(self, linear_graph):
        assert linear_graph.get_node_degree("A") == 2


class TestGetStats:
    def test_stats_on_an_empty_graph(self):
        engine = GraphEngine()
        stats = engine.get_stats()
        assert stats["nodes"]["total"] == 0
        assert stats["relationships"]["total"] == 0
        assert stats["avg_degree"] == 0
        assert stats["density"] == 0

    def test_stats_reflect_the_real_populated_graph(self, linear_graph):
        stats = linear_graph.get_stats()
        assert stats["nodes"]["total"] == 4
        assert stats["relationships"]["total"] == 4
        assert stats["nodes"]["by_label"] == {"TestNode": 4}
        assert stats["relationships"]["by_type"] == {"CONNECTS": 3, "SHORTCUT": 1}
        assert stats["avg_degree"] > 0
        assert stats["density"] > 0

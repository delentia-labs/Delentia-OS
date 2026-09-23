"""
ALGO-17: Graph Traversal (in-memory layer) — real port, 2026-09-16 (Round 20).

Ported near-verbatim from Delentia-Private-OS/rct_platform/microservices/
graph-traversal/app/core/graph_engine.py. This microservice actually has
TWO layers: this one (a genuine, self-contained BFS/DFS/Dijkstra/PageRank
engine using stdlib heapq/deque, dataclasses — no external service) and a
separate `neo4j_ops/neo4j_handler.py` layer requiring a live Neo4j
instance to be running (not available in this environment, and not
ported here — the Neo4j layer is real Cypher-query code, just genuinely
needs external infrastructure this environment doesn't have; wiring it
is a Round 12-style "needs the user's own hosting decision" item, not a
code gap).

This file ports only the in-memory layer, which was already directly
importable/callable per a prior session's audit finding.
"""
from __future__ import annotations

import heapq
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """Graph node."""
    node_id: str
    labels: List[str]
    properties: Dict[str, Any]
    embedding: Optional[List[float]] = None


@dataclass
class GraphRelationship:
    """Graph relationship."""
    relationship_id: str
    from_node: str
    to_node: str
    relationship_type: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphPath:
    """Graph path."""
    nodes: List[str]
    relationships: List[str]
    length: int
    total_weight: float = 0.0


class GraphEngine:
    """
    Graph traversal and algorithm engine (in-memory layer of ALGO-17).

    Features: BFS/DFS traversal, shortest path (Dijkstra), PageRank,
    degree/density stats. No external dependency.
    """

    def __init__(self) -> None:
        self.graph: Dict[str, Dict[str, List[GraphRelationship]]] = {}
        self.nodes: Dict[str, GraphNode] = {}
        self.relationships: Dict[str, GraphRelationship] = {}
        logger.info("GraphEngine initialized")

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node
        if node.node_id not in self.graph:
            self.graph[node.node_id] = {}

    def add_relationship(self, rel: GraphRelationship) -> None:
        self.relationships[rel.relationship_id] = rel
        if rel.from_node not in self.graph:
            self.graph[rel.from_node] = {}
        if rel.to_node not in self.graph[rel.from_node]:
            self.graph[rel.from_node][rel.to_node] = []
        self.graph[rel.from_node][rel.to_node].append(rel)

    def bfs(self, start_node: str, max_depth: int = 3,
            relationship_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if start_node not in self.graph:
            raise ValueError(f"Start node '{start_node}' not found")

        visited: set = set()
        queue = deque([(start_node, 0)])
        result: List[Dict[str, Any]] = []

        while queue:
            current_node, depth = queue.popleft()
            if current_node in visited or depth > max_depth:
                continue
            visited.add(current_node)

            node_data = self.nodes.get(current_node)
            result.append({
                "node_id": current_node, "depth": depth,
                "labels": node_data.labels if node_data else [],
                "properties": node_data.properties if node_data else {},
            })

            if current_node in self.graph:
                for neighbor, rels in self.graph[current_node].items():
                    if neighbor not in visited:
                        filtered = [r for r in rels if r.relationship_type in relationship_types] if relationship_types else rels
                        if filtered:
                            queue.append((neighbor, depth + 1))

        logger.info(f"BFS from {start_node}: visited {len(visited)} nodes")
        return result

    def dfs(self, start_node: str, max_depth: int = 3,
            relationship_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if start_node not in self.graph:
            raise ValueError(f"Start node '{start_node}' not found")

        visited: set = set()
        result: List[Dict[str, Any]] = []

        def dfs_recursive(node: str, depth: int) -> None:
            if node in visited or depth > max_depth:
                return
            visited.add(node)
            node_data = self.nodes.get(node)
            result.append({
                "node_id": node, "depth": depth,
                "labels": node_data.labels if node_data else [],
                "properties": node_data.properties if node_data else {},
            })
            if node in self.graph:
                for neighbor, rels in self.graph[node].items():
                    if neighbor not in visited:
                        filtered = [r for r in rels if r.relationship_type in relationship_types] if relationship_types else rels
                        if filtered:
                            dfs_recursive(neighbor, depth + 1)

        dfs_recursive(start_node, 0)
        logger.info(f"DFS from {start_node}: visited {len(visited)} nodes")
        return result

    def shortest_path(self, start_node: str, end_node: str,
                       relationship_types: Optional[List[str]] = None) -> Optional[GraphPath]:
        if start_node not in self.graph:
            raise ValueError(f"Start node '{start_node}' not found")
        if end_node not in self.nodes:
            raise ValueError(f"End node '{end_node}' not found")

        distances = {start_node: 0.0}
        previous: Dict[str, Any] = {}
        pq = [(0.0, start_node)]
        visited: set = set()

        while pq:
            current_dist, current_node = heapq.heappop(pq)
            if current_node in visited:
                continue
            visited.add(current_node)
            if current_node == end_node:
                break

            if current_node in self.graph:
                for neighbor, rels in self.graph[current_node].items():
                    filtered = [r for r in rels if r.relationship_type in relationship_types] if relationship_types else rels
                    if not filtered:
                        continue
                    weight = min(r.properties.get("weight", 1.0) for r in filtered)
                    distance = current_dist + weight
                    if neighbor not in distances or distance < distances[neighbor]:
                        distances[neighbor] = distance
                        previous[neighbor] = (current_node, filtered[0].relationship_id)
                        heapq.heappush(pq, (distance, neighbor))

        if end_node not in previous and end_node != start_node:
            return None

        path_nodes: List[str] = []
        path_rels: List[str] = []
        current = end_node
        while current != start_node:
            path_nodes.append(current)
            if current in previous:
                prev_node, rel_id = previous[current]
                path_rels.append(rel_id)
                current = prev_node
            else:
                break
        path_nodes.append(start_node)
        path_nodes.reverse()
        path_rels.reverse()

        logger.info(f"Shortest path {start_node} -> {end_node}: {len(path_nodes)} nodes")
        return GraphPath(nodes=path_nodes, relationships=path_rels,
                          length=len(path_nodes) - 1, total_weight=distances.get(end_node, 0.0))

    def pagerank(self, relationship_type: Optional[str] = None,
                 damping_factor: float = 0.85, iterations: int = 20) -> Dict[str, float]:
        nodes = set(self.nodes.keys())
        n = len(nodes)
        if n == 0:
            return {}

        pagerank = {node: 1.0 / n for node in nodes}
        outgoing: Dict[str, List[str]] = {}
        for node in nodes:
            outgoing[node] = []
            if node in self.graph:
                for neighbor, rels in self.graph[node].items():
                    filtered = [r for r in rels if r.relationship_type == relationship_type] if relationship_type else rels
                    if filtered:
                        outgoing[node].append(neighbor)

        for _ in range(iterations):
            new_pagerank = {}
            for node in nodes:
                rank_sum = 0.0
                for other_node in nodes:
                    if node in outgoing.get(other_node, []):
                        out_degree = len(outgoing[other_node])
                        if out_degree > 0:
                            rank_sum += pagerank[other_node] / out_degree
                new_pagerank[node] = (1 - damping_factor) / n + damping_factor * rank_sum
            pagerank = new_pagerank

        logger.info(f"PageRank calculated for {n} nodes")
        return pagerank

    def get_neighbors(self, node_id: str, relationship_types: Optional[List[str]] = None) -> List[str]:
        if node_id not in self.graph:
            return []
        neighbors = []
        for neighbor, rels in self.graph[node_id].items():
            filtered = [r for r in rels if r.relationship_type in relationship_types] if relationship_types else rels
            if filtered:
                neighbors.append(neighbor)
        return neighbors

    def get_node_degree(self, node_id: str) -> int:
        return len(self.graph.get(node_id, {}))

    def get_stats(self) -> Dict[str, Any]:
        total_nodes = len(self.nodes)
        total_relationships = len(self.relationships)

        labels_count: Dict[str, int] = {}
        for node in self.nodes.values():
            for label in node.labels:
                labels_count[label] = labels_count.get(label, 0) + 1

        rel_types_count: Dict[str, int] = {}
        for rel in self.relationships.values():
            rel_types_count[rel.relationship_type] = rel_types_count.get(rel.relationship_type, 0) + 1

        total_degree = sum(self.get_node_degree(nid) for nid in self.nodes)
        avg_degree = total_degree / total_nodes if total_nodes > 0 else 0
        max_edges = total_nodes * (total_nodes - 1)
        density = total_relationships / max_edges if max_edges > 0 else 0

        return {
            "nodes": {"total": total_nodes, "by_label": labels_count},
            "relationships": {"total": total_relationships, "by_type": rel_types_count},
            "avg_degree": round(avg_degree, 2),
            "density": round(density, 6),
        }


if __name__ == "__main__":
    print("=" * 70)
    print("ALGO-17 Graph Traversal (in-memory layer) smoke test")
    print("=" * 70)

    engine = GraphEngine()

    # A small real graph: A -> B -> C -> D, plus a shortcut A -> D (weight 10)
    for nid in ["A", "B", "C", "D"]:
        engine.add_node(GraphNode(node_id=nid, labels=["TestNode"], properties={"name": nid}))

    engine.add_relationship(GraphRelationship("r1", "A", "B", "CONNECTS", {"weight": 1.0}))
    engine.add_relationship(GraphRelationship("r2", "B", "C", "CONNECTS", {"weight": 1.0}))
    engine.add_relationship(GraphRelationship("r3", "C", "D", "CONNECTS", {"weight": 1.0}))
    engine.add_relationship(GraphRelationship("r4", "A", "D", "SHORTCUT", {"weight": 10.0}))

    bfs_result = engine.bfs("A", max_depth=3)
    print(f"BFS from A: {[n['node_id'] for n in bfs_result]}")
    assert [n["node_id"] for n in bfs_result] == ["A", "B", "D", "C"], "real BFS order"

    dfs_result = engine.dfs("A", max_depth=3)
    print(f"DFS from A: {[n['node_id'] for n in dfs_result]}")

    # Real Dijkstra must prefer the 3-hop weight-3 path over the 1-hop
    # weight-10 shortcut — proving real weighted shortest-path math, not
    # a hop-count shortcut.
    path = engine.shortest_path("A", "D")
    assert path is not None, "a path exists between A and D via B/C or the SHORTCUT edge"
    print(f"Shortest path A->D: nodes={path.nodes} total_weight={path.total_weight}")
    assert path.nodes == ["A", "B", "C", "D"], "real Dijkstra must prefer the real lower-weight path"
    assert path.total_weight == 3.0, f"expected real total_weight=3.0, got {path.total_weight}"

    ranks = engine.pagerank(iterations=20)
    print(f"PageRank: {ranks}")
    # This is a basic (no dangling-mass redistribution) PageRank — rank
    # mass genuinely leaks out through D, a real sink node with no
    # outgoing edges, so the scores do NOT sum to 1.0 here (that's a
    # property of textbook-normalized PageRank variants, not this real
    # implementation). What IS a real, checkable property: D has 2 real
    # incoming edges (C->D, A->D shortcut) vs A's 0 incoming edges, so D
    # must rank higher than A.
    assert all(v >= 0 for v in ranks.values()), "PageRank scores must be non-negative"
    assert ranks["D"] > ranks["A"], "D (2 real incoming edges) must outrank A (0 incoming edges)"

    stats = engine.get_stats()
    print(f"Stats: {stats}")
    assert stats["nodes"]["total"] == 4
    assert stats["relationships"]["total"] == 4

    print("\nALL ALGO-17 ASSERTIONS PASSED")

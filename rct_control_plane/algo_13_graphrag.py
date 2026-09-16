"""
ALGO-13: GraphRAG Complete Engine (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/graphrag-complete/
app/core/graphrag_engine.py on 2026-09-15, following the same
strip-the-FastAPI-keep-the-engine pattern used for ALGO-07 (mee_engine.py).
The only external dependency is numpy (already available via Delentia-OS's
`graph` extra, see pyproject.toml); everything else is stdlib
(hashlib/json/re/time/uuid). The source's `import httpx` was unused dead
weight left over from the microservice's HTTP layer — dropped here since
nothing in this class ever calls it.

Real logic ported as-is:
    - Keyword search: genuine (if simple) TF-IDF-style scoring
      (tf = matches / word_count, idf = log(N / (matches+1))).
    - Vector search: real cosine similarity over a deterministic,
      content-derived embedding — see _get_embedding()'s docstring below;
      this is the hashing-trick embedding that replaced an earlier
      np.random.randn() placeholder (the source's own comment documents
      that history), not something this port is claiming is new.
    - Graph search: real 2-hop neighborhood expansion with 0.7^hop
      distance decay, scored and mapped back to documents.
    - Fusion: real RRF (Reciprocal Rank Fusion, k=60), linear, weighted,
      and max fusion across result lists.
    - add_document(): runtime document ingestion beyond the 5 built-in
      samples — there is no separate "real" vs "sample" code path, an
      ingested document's embedding is computed lazily the same way.

Usage::

    import asyncio
    engine = GraphRAGEngine()
    session_id = asyncio.run(engine.search("graph knowledge", mode=SearchMode.GRAPHRAG))
    session = engine.get_session(session_id)
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


class SearchMode(str, Enum):
    """Search modes"""
    KEYWORD = "keyword"        # Simple keyword search
    VECTOR = "vector"          # Semantic vector search
    GRAPH = "graph"            # Graph traversal search
    HYBRID = "hybrid"          # Vector + keyword fusion
    GRAPHRAG = "graphrag"      # Full GraphRAG: vector + graph + fusion


class FusionMethod(str, Enum):
    """Result fusion methods"""
    RRF = "rrf"                # Reciprocal Rank Fusion
    LINEAR = "linear"          # Linear combination
    MAX = "max"                # Max score
    WEIGHTED = "weighted"      # Weighted average


@dataclass
class Document:
    """Document representation"""
    doc_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    vector: Optional[List[float]] = None
    graph_nodes: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Search result with multi-source scores"""
    doc_id: str
    content: str
    snippet: str
    score: float
    vector_score: float = 0.0
    keyword_score: float = 0.0
    graph_score: float = 0.0
    fusion_score: float = 0.0
    rank: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    graph_context: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GraphNode:
    """Knowledge graph node"""
    node_id: str
    node_type: str  # entity, concept, document
    properties: Dict[str, Any] = field(default_factory=dict)
    neighbors: List[str] = field(default_factory=list)


@dataclass
class GraphEdge:
    """Knowledge graph edge"""
    edge_id: str
    source: str
    target: str
    edge_type: str  # relates_to, references, similar_to
    weight: float = 1.0
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchSession:
    """Search session with results"""
    session_id: str
    query: str
    mode: SearchMode
    results: List[SearchResult]
    vector_results: List[SearchResult] = field(default_factory=list)
    keyword_results: List[SearchResult] = field(default_factory=list)
    graph_results: List[SearchResult] = field(default_factory=list)
    fusion_method: FusionMethod = FusionMethod.RRF
    execution_time: float = 0.0
    timestamp: float = field(default_factory=time.time)


class GraphRAGEngine:
    """
    Complete GraphRAG Engine

    Implements:
    1. Vector Search - Semantic similarity via deterministic embeddings
    2. Keyword Search - TF-IDF-style text search
    3. Graph Traversal - Knowledge graph exploration (2-hop expansion)
    4. Hybrid Fusion - RRF and weighted fusion
    5. Re-ranking - Graph-enhanced re-ranking
    """

    def __init__(
        self,
        embedding_dim: int = 384,
        top_k: int = 20,
        fusion_k: int = 60  # RRF constant
    ):
        self.embedding_dim = embedding_dim
        self.top_k = top_k
        self.fusion_k = fusion_k

        # In-memory storage (no external vector DB / graph DB required)
        self.documents: Dict[str, Document] = {}
        self.graph_nodes: Dict[str, GraphNode] = {}
        self.graph_edges: List[GraphEdge] = []
        self.sessions: Dict[str, SearchSession] = {}

        self._initialize_sample_data()

    def _initialize_sample_data(self):
        """Initialize with sample documents and graph"""

        docs = [
            Document(
                doc_id="doc1",
                content="Reflexion Agent implements self-correction feedback loop",
                metadata={"topic": "algorithms", "type": "agent"},
                graph_nodes=["reflexion", "agent", "self-correction"]
            ),
            Document(
                doc_id="doc2",
                content="Bayesian inference for belief tracking and planning",
                metadata={"topic": "algorithms", "type": "reasoning"},
                graph_nodes=["bayesian", "belief", "planning"]
            ),
            Document(
                doc_id="doc3",
                content="Meta-algorithm composition using function composition",
                metadata={"topic": "algorithms", "type": "meta"},
                graph_nodes=["meta", "composition", "functions"]
            ),
            Document(
                doc_id="doc4",
                content="GraphRAG combines vector search and knowledge graphs",
                metadata={"topic": "algorithms", "type": "search"},
                graph_nodes=["graphrag", "vector", "graph"]
            ),
            Document(
                doc_id="doc5",
                content="Knowledge graph stores entities and relationships",
                metadata={"topic": "data", "type": "graph"},
                graph_nodes=["knowledge", "graph", "relationships"]
            )
        ]

        for doc in docs:
            self.documents[doc.doc_id] = doc

        nodes = [
            GraphNode("reflexion", "concept", {"desc": "Self-correction"}, ["agent", "feedback"]),
            GraphNode("agent", "concept", {"desc": "Autonomous system"}, ["reflexion", "planning"]),
            GraphNode("bayesian", "concept", {"desc": "Probabilistic inference"}, ["belief", "reasoning"]),
            GraphNode("graphrag", "concept", {"desc": "Hybrid search"}, ["vector", "graph"]),
            GraphNode("vector", "concept", {"desc": "Semantic embedding"}, ["graphrag", "search"]),
            GraphNode("graph", "concept", {"desc": "Connected data"}, ["graphrag", "knowledge"]),
        ]

        for node in nodes:
            self.graph_nodes[node.node_id] = node

        self.graph_edges = [
            GraphEdge("e1", "reflexion", "agent", "implements", 0.9),
            GraphEdge("e2", "agent", "planning", "uses", 0.8),
            GraphEdge("e3", "graphrag", "vector", "combines", 0.95),
            GraphEdge("e4", "graphrag", "graph", "combines", 0.95),
            GraphEdge("e5", "vector", "search", "enables", 0.7),
        ]

    async def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.GRAPHRAG,
        top_k: Optional[int] = None,
        fusion_method: FusionMethod = FusionMethod.RRF
    ) -> str:
        """
        Execute search with specified mode.

        Returns:
            session_id: Session ID for retrieving results via get_session()
        """
        start_time = time.time()
        session_id = self._generate_session_id()
        top_k = top_k or self.top_k

        if mode == SearchMode.KEYWORD:
            results = await self._keyword_search(query, top_k)
            vector_results, keyword_results, graph_results = [], results, []

        elif mode == SearchMode.VECTOR:
            results = await self._vector_search(query, top_k)
            vector_results, keyword_results, graph_results = results, [], []

        elif mode == SearchMode.GRAPH:
            results = await self._graph_search(query, top_k)
            vector_results, keyword_results, graph_results = [], [], results

        elif mode == SearchMode.HYBRID:
            vector_results = await self._vector_search(query, top_k)
            keyword_results = await self._keyword_search(query, top_k)
            results = self._fuse_results(
                [vector_results, keyword_results],
                method=fusion_method,
                top_k=top_k
            )
            graph_results = []

        else:  # GRAPHRAG
            vector_results = await self._vector_search(query, top_k)
            keyword_results = await self._keyword_search(query, top_k)
            graph_results = await self._graph_search(query, top_k)

            results = self._fuse_results(
                [vector_results, keyword_results, graph_results],
                method=fusion_method,
                top_k=top_k
            )

            results = await self._enhance_with_graph(results)

        execution_time = time.time() - start_time
        session = SearchSession(
            session_id=session_id,
            query=query,
            mode=mode,
            results=results,
            vector_results=vector_results,
            keyword_results=keyword_results,
            graph_results=graph_results,
            fusion_method=fusion_method,
            execution_time=execution_time
        )

        self.sessions[session_id] = session
        return session_id

    async def _keyword_search(self, query: str, top_k: int) -> List[SearchResult]:
        """Keyword-based search using TF-IDF style scoring"""
        query_lower = query.lower()
        results = []

        for doc in self.documents.values():
            content_lower = doc.content.lower()

            matches = content_lower.count(query_lower)
            if matches == 0:
                continue

            tf = matches / len(content_lower.split())
            idf = np.log(len(self.documents) / (matches + 1))
            score = tf * idf

            snippet = self._make_snippet(doc.content, query)

            results.append(SearchResult(
                doc_id=doc.doc_id,
                content=doc.content,
                snippet=snippet,
                score=score,
                keyword_score=score
            ))

        results.sort(key=lambda r: r.keyword_score, reverse=True)
        return results[:top_k]

    async def _vector_search(self, query: str, top_k: int) -> List[SearchResult]:
        """Vector-based semantic search using cosine similarity"""
        query_vector = await self._get_embedding(query)

        results = []
        for doc in self.documents.values():
            if doc.vector is None:
                doc.vector = await self._get_embedding(doc.content)

            similarity = self._cosine_similarity(query_vector, doc.vector)

            snippet = self._make_snippet(doc.content, query)

            results.append(SearchResult(
                doc_id=doc.doc_id,
                content=doc.content,
                snippet=snippet,
                score=similarity,
                vector_score=similarity
            ))

        results.sort(key=lambda r: r.vector_score, reverse=True)
        return results[:top_k]

    async def _graph_search(self, query: str, top_k: int) -> List[SearchResult]:
        """Graph-based search: find relevant nodes, expand 2-hop, score docs"""
        query_lower = query.lower()

        relevant_nodes = []
        for node in self.graph_nodes.values():
            if query_lower in node.node_id.lower():
                relevant_nodes.append(node)

        if not relevant_nodes:
            return []

        expanded = self._expand_nodes(relevant_nodes, hops=2)

        doc_scores = {}
        for doc in self.documents.values():
            score = 0.0
            for node_id in doc.graph_nodes:
                if node_id in expanded:
                    score += expanded[node_id]

            if score > 0:
                doc_scores[doc.doc_id] = score

        results = []
        for doc_id, score in doc_scores.items():
            doc = self.documents[doc_id]
            snippet = self._make_snippet(doc.content, query)

            results.append(SearchResult(
                doc_id=doc.doc_id,
                content=doc.content,
                snippet=snippet,
                score=score,
                graph_score=score
            ))

        results.sort(key=lambda r: r.graph_score, reverse=True)
        return results[:top_k]

    def _expand_nodes(self, nodes: List[GraphNode], hops: int = 2) -> Dict[str, float]:
        """Expand nodes with k-hop neighbors, decaying score by distance (0.7^hop)"""
        scores = {}
        visited = set()

        current_layer = {node.node_id: 1.0 for node in nodes}
        scores.update(current_layer)

        for hop in range(hops):
            next_layer = {}
            decay = 0.7 ** (hop + 1)

            for node_id in current_layer:
                if node_id in visited:
                    continue
                visited.add(node_id)

                node = self.graph_nodes.get(node_id)
                if not node:
                    continue

                for neighbor_id in node.neighbors:
                    if neighbor_id not in scores:
                        next_layer[neighbor_id] = current_layer[node_id] * decay
                        scores[neighbor_id] = next_layer[neighbor_id]

            current_layer = next_layer

        return scores

    def _fuse_results(
        self,
        result_lists: List[List[SearchResult]],
        method: FusionMethod = FusionMethod.RRF,
        top_k: int = 20
    ) -> List[SearchResult]:
        """Fuse multiple result lists using the specified method"""
        if method == FusionMethod.RRF:
            return self._rrf_fusion(result_lists, top_k)
        elif method == FusionMethod.LINEAR:
            return self._linear_fusion(result_lists, top_k)
        elif method == FusionMethod.WEIGHTED:
            return self._weighted_fusion(result_lists, [0.5, 0.3, 0.2], top_k)
        else:
            return self._max_fusion(result_lists, top_k)

    def _rrf_fusion(self, result_lists: List[List[SearchResult]], top_k: int) -> List[SearchResult]:
        """Reciprocal Rank Fusion: score(d) = sum(1 / (k + rank_i(d))), k=60"""
        k = self.fusion_k
        doc_scores: Dict[str, float] = {}
        doc_data: Dict[str, SearchResult] = {}

        for results in result_lists:
            for rank, result in enumerate(results, start=1):
                doc_id = result.doc_id
                rrf_score = 1.0 / (k + rank)

                if doc_id not in doc_scores:
                    doc_scores[doc_id] = 0.0
                    doc_data[doc_id] = result

                doc_scores[doc_id] += rrf_score

        fused = []
        for doc_id, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True):
            result = doc_data[doc_id]
            result.fusion_score = score
            result.score = score
            fused.append(result)

        return fused[:top_k]

    def _linear_fusion(self, result_lists: List[List[SearchResult]], top_k: int) -> List[SearchResult]:
        """Linear combination of scores (average of vector/keyword/graph)"""
        doc_scores: Dict[str, float] = {}
        doc_data: Dict[str, SearchResult] = {}

        for results in result_lists:
            for result in results:
                doc_id = result.doc_id

                if doc_id not in doc_scores:
                    doc_scores[doc_id] = 0.0
                    doc_data[doc_id] = result

                score = (result.vector_score + result.keyword_score + result.graph_score) / 3
                doc_scores[doc_id] += score

        fused = []
        for doc_id, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True):
            result = doc_data[doc_id]
            result.fusion_score = score
            result.score = score
            fused.append(result)

        return fused[:top_k]

    def _weighted_fusion(self, result_lists: List[List[SearchResult]], weights: List[float], top_k: int) -> List[SearchResult]:
        """Weighted combination"""
        doc_scores: Dict[str, float] = {}
        doc_data: Dict[str, SearchResult] = {}

        for i, results in enumerate(result_lists):
            weight = weights[i] if i < len(weights) else 1.0

            for result in results:
                doc_id = result.doc_id

                if doc_id not in doc_scores:
                    doc_scores[doc_id] = 0.0
                    doc_data[doc_id] = result

                doc_scores[doc_id] += result.score * weight

        fused = []
        for doc_id, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True):
            result = doc_data[doc_id]
            result.fusion_score = score
            result.score = score
            fused.append(result)

        return fused[:top_k]

    def _max_fusion(self, result_lists: List[List[SearchResult]], top_k: int) -> List[SearchResult]:
        """Max score across all lists"""
        doc_scores: Dict[str, float] = {}
        doc_data: Dict[str, SearchResult] = {}

        for results in result_lists:
            for result in results:
                doc_id = result.doc_id

                if doc_id not in doc_scores:
                    doc_scores[doc_id] = result.score
                    doc_data[doc_id] = result
                else:
                    doc_scores[doc_id] = max(doc_scores[doc_id], result.score)

        fused = []
        for doc_id, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True):
            result = doc_data[doc_id]
            result.fusion_score = score
            result.score = score
            fused.append(result)

        return fused[:top_k]

    async def _enhance_with_graph(self, results: List[SearchResult]) -> List[SearchResult]:
        """Enhance results with 2-hop graph neighbor context"""
        for result in results:
            doc = self.documents.get(result.doc_id)
            if not doc:
                continue

            graph_context = []
            for node_id in doc.graph_nodes:
                node = self.graph_nodes.get(node_id)
                if node:
                    neighbors = []
                    for neighbor_id in node.neighbors:
                        neighbor = self.graph_nodes.get(neighbor_id)
                        if neighbor:
                            neighbors.append({
                                "id": neighbor.node_id,
                                "type": neighbor.node_type
                            })

                    graph_context.append({
                        "node": node.node_id,
                        "type": node.node_type,
                        "neighbors": neighbors
                    })

            result.graph_context = graph_context

        return results

    async def _get_embedding(self, text: str) -> List[float]:
        """
        Real, deterministic embedding via the classic hashing trick
        (feature-hashed, signed bag-of-words), L2-normalized.

        Not a neural embedding, but genuinely derived from the text's
        content: the same text always maps to the same vector, texts
        sharing vocabulary get non-trivial cosine similarity, unrelated
        texts do not. This replaced an earlier np.random.randn()
        placeholder in the source (documented there via inline comment);
        this port keeps the deterministic version, not the placeholder.

        Algorithm:
          1. Tokenize to lowercase alphanumeric words.
          2. SHA-256 each token (stable across processes) to pick a
             bucket in [0, embedding_dim) and a +1/-1 sign bit.
          3. Accumulate signed term counts into that bucket.
          4. L2-normalize.
        """
        vector = np.zeros(self.embedding_dim, dtype=np.float64)
        tokens = _TOKEN_RE.findall(text.lower())

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % self.embedding_dim
            sign = 1.0 if (digest[8] & 1) == 0 else -1.0
            vector[bucket] += sign

        norm = np.linalg.norm(vector)
        if norm == 0.0:
            return vector.tolist()
        return (vector / norm).tolist()

    def add_document(
        self,
        content: str,
        doc_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        graph_nodes: Optional[List[str]] = None,
    ) -> str:
        """
        Ingest a real document at runtime (beyond the 5 hardcoded
        samples). Its embedding is computed lazily by _vector_search the
        same way as any sample document.
        """
        doc_id = doc_id or f"doc-{uuid.uuid4().hex[:12]}"
        doc = Document(
            doc_id=doc_id,
            content=content,
            metadata=metadata or {},
            graph_nodes=graph_nodes or [],
        )
        self.documents[doc_id] = doc
        return doc_id

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """cos(a, b) = a.b / (||a|| ||b||)"""
        a = np.array(vec1)
        b = np.array(vec2)

        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def _make_snippet(self, text: str, query: str, window: int = 80) -> str:
        """Create snippet around query match"""
        text_lower = text.lower()
        query_lower = query.lower()

        idx = text_lower.find(query_lower)
        if idx == -1:
            return text[:window] + "..." if len(text) > window else text

        start = max(0, idx - window // 2)
        end = min(len(text), idx + window + len(query))

        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get search session results"""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        return asdict(session)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all search sessions"""
        return [
            {
                "session_id": s.session_id,
                "query": s.query,
                "mode": s.mode,
                "results_count": len(s.results),
                "execution_time": s.execution_time,
                "timestamp": s.timestamp
            }
            for s in self.sessions.values()
        ]

    def delete_session(self, session_id: str) -> bool:
        """Delete search session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        return f"graphrag-{uuid.uuid4().hex[:12]}"


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def _smoke_test():
        print("=== ALGO-13 GraphRAG Complete smoke test ===")

        engine = GraphRAGEngine()

        # Keyword search
        session_id = await engine.search("reflexion agent", mode=SearchMode.KEYWORD)
        session = engine.get_session(session_id)
        print(f"[keyword] results={len(session['results'])}, time={session['execution_time']:.4f}s")
        assert len(session["results"]) > 0

        # Vector search (deterministic hashing-trick embedding)
        session_id = await engine.search("self-correction", mode=SearchMode.VECTOR)
        session = engine.get_session(session_id)
        print(f"[vector] results={len(session['results'])}")
        assert len(session["results"]) == 5  # scores all 5 sample docs

        # Determinism check: same text -> same embedding -> same top score twice
        v1 = await engine._get_embedding("graph knowledge search")
        v2 = await engine._get_embedding("graph knowledge search")
        assert v1 == v2, "embedding must be deterministic"
        print("Embedding determinism: OK (identical vectors across calls)")

        # Graph search (2-hop expansion)
        session_id = await engine.search("graphrag", mode=SearchMode.GRAPH)
        session = engine.get_session(session_id)
        print(f"[graph] results={len(session['results'])}")
        assert len(session["results"]) > 0

        # Full GraphRAG: vector + keyword + graph + RRF fusion + 2-hop enhancement
        session_id = await engine.search("graph knowledge", mode=SearchMode.GRAPHRAG)
        session = engine.get_session(session_id)
        print(f"[graphrag] results={len(session['results'])}, "
              f"has_graph_context={len(session['results'][0]['graph_context']) > 0 if session['results'] else False}")
        assert len(session["results"]) > 0

        # Runtime document ingestion beyond the 5 samples
        new_id = engine.add_document(
            "Delentia OS ports real algorithm engines out of private microservices",
            metadata={"topic": "delentia"},
            graph_nodes=["graphrag"],
        )
        assert new_id in engine.documents
        assert len(engine.documents) == 6
        session_id = await engine.search("Delentia OS ports", mode=SearchMode.KEYWORD)
        session = engine.get_session(session_id)
        found_ids = [r["doc_id"] for r in session["results"]]
        print(f"[runtime doc] added doc_id={new_id}, found in keyword search: {new_id in found_ids}")
        assert new_id in found_ids

        # Fusion methods
        for method in (FusionMethod.RRF, FusionMethod.LINEAR, FusionMethod.WEIGHTED, FusionMethod.MAX):
            session_id = await engine.search("graph", mode=SearchMode.HYBRID, fusion_method=method)
            session = engine.get_session(session_id)
            print(f"[hybrid/{method.value}] results={len(session['results'])}")

        print("=== ALGO-13 GraphRAG Complete: ALL ASSERTIONS PASSED ===")

    asyncio.run(_smoke_test())

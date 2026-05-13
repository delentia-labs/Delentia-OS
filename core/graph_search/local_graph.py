"""
LocalGraphRAG — in-process GraphRAG backend using NetworkX + TF-IDF.

No external services required. Suitable for:
- Development and testing
- Embedded deployments
- Offline search over small to medium corpora (< 50 k nodes)

NetworkX is an optional dependency; this module degrades gracefully if it is
not installed, raising ``ImportError`` only when you actually instantiate
``LocalGraphRAG``.

Usage::

    from core.graph_search import LocalGraphRAG

    graph = LocalGraphRAG()
    graph.add_node("n1", title="Machine Learning", content="ML algorithms...")
    graph.add_node("n2", title="Deep Learning",    content="Neural networks...")
    graph.add_edge("n1", "n2")
    results = graph.search("neural network architectures", top_k=5)
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .interface import GraphRAGInterface
from .models import GraphSearchResult

# ── Optional imports ─────────────────────────────────────────────────────────
try:
    import networkx as nx  # type: ignore[import]
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False
    nx = None  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
# Internal TF-IDF helpers (pure Python, no numpy / sklearn required)
# ─────────────────────────────────────────────────────────────────────────────

_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might must can could of in on at to for "
    "with by from as and or but not this that these those it its".split()
)


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Z\u0E00-\u0E7F]+", text.lower())
    return [w for w in words if len(w) > 1 and w not in _STOP_WORDS]


def _tf(tokens: List[str]) -> Dict[str, float]:
    freq: Dict[str, int] = defaultdict(int)
    for t in tokens:
        freq[t] += 1
    total = max(len(tokens), 1)
    return {term: count / total for term, count in freq.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


# ─────────────────────────────────────────────────────────────────────────────
# LocalGraphRAG
# ─────────────────────────────────────────────────────────────────────────────

class LocalGraphRAG(GraphRAGInterface):
    """
    GraphRAG implementation backed by NetworkX DiGraph and TF-IDF scoring.

    Thread-safety: NOT thread-safe by default. Wrap in a lock if you need
    concurrent writes.
    """

    def __init__(self) -> None:
        if not _NX_AVAILABLE:
            raise ImportError(
                "networkx is required for LocalGraphRAG. "
                "Install it with: pip install networkx"
            )
        self._graph: "nx.DiGraph" = nx.DiGraph()
        # IDF cache: rebuilt lazily on search when _dirty is True
        self._idf: Dict[str, float] = {}
        self._dirty = False

    # ── GraphRAGInterface implementation ─────────────────────────────────────

    def add_node(
        self,
        node_id: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._graph.add_node(
            node_id,
            title=title,
            content=content,
            metadata=metadata or {},
            tokens=_tokenize(f"{title} {content}"),
        )
        self._dirty = True

    def add_edge(self, source_id: str, target_id: str, weight: float = 1.0) -> None:
        if source_id not in self._graph or target_id not in self._graph:
            raise ValueError(
                f"Both nodes must exist before adding an edge. "
                f"Missing: {[n for n in (source_id, target_id) if n not in self._graph]}"
            )
        self._graph.add_edge(source_id, target_id, weight=weight)

    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> List[GraphSearchResult]:
        if self._graph.number_of_nodes() == 0:
            return []

        if self._dirty:
            self._rebuild_idf()

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        query_tf = _tf(query_tokens)
        query_tfidf = {t: query_tf[t] * self._idf.get(t, 0.0) for t in query_tf}

        scored: List[tuple] = []
        for node_id, data in self._graph.nodes(data=True):
            tokens = data.get("tokens", [])
            node_tf = _tf(tokens)
            node_tfidf = {t: node_tf[t] * self._idf.get(t, 0.0) for t in node_tf}
            score = _cosine(query_tfidf, node_tfidf)
            if score >= min_score:
                scored.append((score, node_id, data))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, node_id, data in scored[:top_k]:
            neighbors = list(self._graph.successors(node_id)) + list(
                self._graph.predecessors(node_id)
            )
            results.append(
                GraphSearchResult(
                    node_id=node_id,
                    title=data.get("title", ""),
                    content=data.get("content", ""),
                    score=round(score, 4),
                    neighbors=list(set(neighbors)),
                    metadata=data.get("metadata", {}),
                )
            )
        return results

    def get_node(self, node_id: str) -> Optional[GraphSearchResult]:
        if node_id not in self._graph:
            return None
        data = self._graph.nodes[node_id]
        neighbors = list(self._graph.successors(node_id)) + list(
            self._graph.predecessors(node_id)
        )
        return GraphSearchResult(
            node_id=node_id,
            title=data.get("title", ""),
            content=data.get("content", ""),
            score=1.0,
            neighbors=list(set(neighbors)),
            metadata=data.get("metadata", {}),
        )

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _rebuild_idf(self) -> None:
        """Recompute IDF scores for all unique terms across all nodes."""
        num_docs = self._graph.number_of_nodes()
        doc_freq: Dict[str, int] = defaultdict(int)
        for _, data in self._graph.nodes(data=True):
            for term in set(data.get("tokens", [])):
                doc_freq[term] += 1
        self._idf = {
            term: math.log((num_docs + 1) / (freq + 1)) + 1.0
            for term, freq in doc_freq.items()
        }
        self._dirty = False

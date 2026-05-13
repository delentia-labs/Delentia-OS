"""
GraphRAGInterface — Abstract Base Class for all graph search backends.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .models import GraphSearchResult


class GraphRAGInterface(ABC):
    """
    Abstract interface that every GraphRAG backend must implement.

    Backends:
    - LocalGraphRAG  — NetworkX + TF-IDF (included, no external server)
    - (future) RemoteGraphRAG — talks to a hosted Neo4j / Nebula instance
    """

    @abstractmethod
    def add_node(
        self,
        node_id: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add or update a node in the graph."""

    @abstractmethod
    def add_edge(self, source_id: str, target_id: str, weight: float = 1.0) -> None:
        """Add a directed edge between two existing nodes."""

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> List[GraphSearchResult]:
        """
        Search for nodes whose content is semantically similar to *query*.

        Returns a list of at most *top_k* results, ordered by descending score.
        Results with score < *min_score* are excluded.
        """

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[GraphSearchResult]:
        """Retrieve a single node by its ID."""

    @property
    @abstractmethod
    def node_count(self) -> int:
        """Total number of nodes currently in the graph."""

    @property
    @abstractmethod
    def edge_count(self) -> int:
        """Total number of edges currently in the graph."""

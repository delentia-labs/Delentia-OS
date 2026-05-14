"""
GraphSearchResult — data model for graph search results.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class GraphSearchResult:
    """
    A single result returned by a GraphRAG search.

    Attributes:
        node_id:    Unique identifier of the matched node.
        title:      Short human-readable label.
        content:    Full text stored at this node.
        score:      Relevance score (higher = more relevant).
        neighbors:  IDs of directly connected nodes.
        metadata:   Arbitrary key/value pairs from the node.
    """
    node_id: str
    title: str
    content: str
    score: float
    neighbors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

"""
Vector Engine Core - ALGO-16
Handles vector operations and backend abstraction
"""

from typing import List, Dict, Any, Optional, Tuple
from abc import ABC, abstractmethod
import numpy as np
from dataclasses import dataclass
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)


class VectorBackend(Enum):
    """Vector backend types"""
    FAISS = "faiss"
    QDRANT = "qdrant"


class DistanceMetric(Enum):
    """Distance metrics for similarity search"""
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    DOT = "dot"


@dataclass
class SearchResult:
    """Single search result"""
    id: str
    score: float
    metadata: Optional[Dict[str, Any]] = None
    vector: Optional[List[float]] = None


@dataclass
class VectorRecord:
    """Vector record with metadata"""
    id: str
    vector: List[float]
    metadata: Optional[Dict[str, Any]] = None


class VectorBackendInterface(ABC):
    """Abstract interface for vector backends"""
    
    @abstractmethod
    def initialize(self, dimension: int, **kwargs):
        """Initialize the backend"""
        pass
    
    @abstractmethod
    def index(self, vectors: List[List[float]], ids: List[str], 
              metadata: Optional[List[Dict[str, Any]]] = None) -> int:
        """Index vectors"""
        pass
    
    @abstractmethod
    def search(self, query_vector: List[float], k: int = 10,
               filter_dict: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
        """Search for nearest neighbors"""
        pass
    
    @abstractmethod
    def get(self, vector_id: str) -> Optional[VectorRecord]:
        """Get a specific vector"""
        pass
    
    @abstractmethod
    def update(self, vector_id: str, vector: Optional[List[float]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update a vector"""
        pass
    
    @abstractmethod
    def delete(self, vector_id: str) -> bool:
        """Delete a vector"""
        pass
    
    @abstractmethod
    def clear(self) -> int:
        """Clear all vectors"""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Get total vector count"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get backend statistics"""
        pass


class VectorEngine:
    """
    Main vector engine that manages backend operations
    
    Features:
    - Backend abstraction (FAISS/Qdrant)
    - Batch operations
    - Performance tracking
    - Error handling
    """
    
    def __init__(self, backend: VectorBackendInterface, dimension: int):
        """
        Initialize vector engine
        
        Args:
            backend: Vector backend implementation
            dimension: Vector dimension
        """
        self.backend = backend
        self.dimension = dimension
        self.total_searches = 0
        self.total_index_ops = 0
        self.search_times = []
        self.start_time = time.time()
        
        logger.info(f"VectorEngine initialized: dimension={dimension}")
    
    def index(self, vectors: List[List[float]], ids: List[str],
              metadata: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Index vectors
        
        Args:
            vectors: List of vectors to index
            ids: List of vector IDs
            metadata: Optional metadata for each vector
            
        Returns:
            Dict with indexing results
        """
        start_time = time.time()
        
        # Validate inputs
        if len(vectors) != len(ids):
            raise ValueError("Number of vectors must match number of IDs")
        
        if metadata and len(metadata) != len(vectors):
            raise ValueError("Number of metadata entries must match number of vectors")
        
        # Validate dimensions
        for i, vec in enumerate(vectors):
            if len(vec) != self.dimension:
                raise ValueError(
                    f"Vector {i} has dimension {len(vec)}, expected {self.dimension}"
                )
        
        # Index vectors
        count = self.backend.index(vectors, ids, metadata)
        self.total_index_ops += count
        
        elapsed = (time.time() - start_time) * 1000
        
        logger.info(f"Indexed {count} vectors in {elapsed:.2f}ms")
        
        return {
            "indexed_count": count,
            "total_vectors": self.backend.count(),
            "time_ms": round(elapsed, 2)
        }
    
    def search(self, query_vector: List[float], k: int = 10,
               metric: str = "cosine",
               filter_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Search for nearest neighbors
        
        Args:
            query_vector: Query vector
            k: Number of results
            metric: Distance metric
            filter_dict: Optional metadata filter
            
        Returns:
            Dict with search results
        """
        start_time = time.time()
        
        # Validate dimension
        if len(query_vector) != self.dimension:
            raise ValueError(
                f"Query vector has dimension {len(query_vector)}, expected {self.dimension}"
            )
        
        # Search
        results = self.backend.search(query_vector, k, filter_dict)
        
        elapsed = (time.time() - start_time) * 1000
        self.search_times.append(elapsed)
        self.total_searches += 1
        
        logger.info(f"Search completed: k={k}, results={len(results)}, time={elapsed:.2f}ms")
        
        return {
            "results": [
                {
                    "id": r.id,
                    "score": round(r.score, 6),
                    "metadata": r.metadata
                }
                for r in results
            ],
            "time_ms": round(elapsed, 2)
        }
    
    def batch_search(self, query_vectors: List[List[float]], k: int = 10,
                     metric: str = "cosine") -> Dict[str, Any]:
        """
        Batch search multiple queries
        
        Args:
            query_vectors: List of query vectors
            k: Number of results per query
            metric: Distance metric
            
        Returns:
            Dict with batch search results
        """
        start_time = time.time()
        
        results = []
        for query in query_vectors:
            search_result = self.search(query, k, metric)
            results.append(search_result["results"])
        
        elapsed = (time.time() - start_time) * 1000
        
        logger.info(f"Batch search completed: {len(query_vectors)} queries in {elapsed:.2f}ms")
        
        return {
            "results": results,
            "time_ms": round(elapsed, 2)
        }
    
    def get(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific vector
        
        Args:
            vector_id: Vector ID
            
        Returns:
            Vector record or None
        """
        record = self.backend.get(vector_id)
        
        if not record:
            return None
        
        return {
            "id": record.id,
            "vector": record.vector,
            "metadata": record.metadata
        }
    
    def update(self, vector_id: str, vector: Optional[List[float]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Update a vector
        
        Args:
            vector_id: Vector ID
            vector: New vector (optional)
            metadata: New metadata (optional)
            
        Returns:
            Update result
        """
        if vector and len(vector) != self.dimension:
            raise ValueError(
                f"Vector has dimension {len(vector)}, expected {self.dimension}"
            )
        
        success = self.backend.update(vector_id, vector, metadata)
        
        return {
            "updated": success,
            "vector_id": vector_id
        }
    
    def delete(self, vector_id: str) -> Dict[str, Any]:
        """
        Delete a vector
        
        Args:
            vector_id: Vector ID
            
        Returns:
            Delete result
        """
        success = self.backend.delete(vector_id)
        
        return {
            "deleted": success,
            "vector_id": vector_id,
            "remaining_count": self.backend.count()
        }
    
    def clear(self) -> Dict[str, Any]:
        """
        Clear all vectors
        
        Returns:
            Clear result
        """
        count = self.backend.count()
        deleted = self.backend.clear()
        
        logger.warning(f"Cleared {deleted} vectors from index")
        
        return {
            "cleared": True,
            "deleted_count": deleted
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get engine statistics
        
        Returns:
            Statistics dict
        """
        backend_stats = self.backend.get_stats()
        
        avg_search_time = (
            sum(self.search_times) / len(self.search_times)
            if self.search_times else 0
        )
        
        uptime = time.time() - self.start_time
        
        return {
            "total_vectors": self.backend.count(),
            "dimension": self.dimension,
            "total_searches": self.total_searches,
            "total_index_ops": self.total_index_ops,
            "avg_search_time_ms": round(avg_search_time, 2),
            "uptime_seconds": round(uptime, 2),
            **backend_stats
        }
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check engine health
        
        Returns:
            Health status dict
        """
        try:
            count = self.backend.count()
            stats = self.backend.get_stats()
            
            return {
                "status": "healthy",
                "vector_count": count,
                "dimension": self.dimension,
                **stats
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Cosine similarity score [0, 1]
    """
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return float(dot / (norm_a * norm_b))


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """
    Calculate Euclidean distance between two vectors
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Euclidean distance
    """
    return float(np.linalg.norm(a - b))


def dot_product(a: np.ndarray, b: np.ndarray) -> float:
    """
    Calculate dot product between two vectors
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Dot product
    """
    return float(np.dot(a, b))

"""
FAISS Backend Implementation - ALGO-16
In-memory vector search using Facebook AI Similarity Search
"""

from typing import List, Dict, Any, Optional
import numpy as np
import faiss
import logging
from ..core.vector_engine import (
    VectorBackendInterface,
    SearchResult,
    VectorRecord,
    DistanceMetric
)

logger = logging.getLogger(__name__)


class FAISSBackend(VectorBackendInterface):
    """
    FAISS backend for fast in-memory vector search
    
    Features:
    - Multiple index types (Flat, IVF, HNSW)
    - Fast search (<50ms for 1M vectors)
    - Cosine, Euclidean, Dot Product metrics
    - In-memory storage
    
    Index Types:
    - flat: Exact search, best accuracy
    - ivf: Inverted file, balanced
    - hnsw: HNSW graph, fastest
    """
    
    def __init__(self, index_type: str = "flat", metric: str = "cosine",
                 nlist: int = 100, m: int = 32):
        """
        Initialize FAISS backend
        
        Args:
            index_type: Index type (flat/ivf/hnsw)
            metric: Distance metric (cosine/euclidean/dot)
            nlist: Number of IVF clusters
            m: HNSW M parameter
        """
        self.index_type = index_type
        self.metric = metric
        self.nlist = nlist
        self.m = m
        self.faiss_index = None  # Renamed from 'index' to avoid conflict
        self.dimension = None
        self.id_to_idx = {}  # Map string ID to index
        self.idx_to_id = {}  # Map index to string ID
        self.metadata_store = {}  # Store metadata
        self.vector_store = {}  # Store vectors for retrieval
        self.next_idx = 0
        
        logger.info(f"FAISSBackend initialized: type={index_type}, metric={metric}")
    
    def initialize(self, dimension: int, **kwargs):
        """
        Initialize FAISS index
        
        Args:
            dimension: Vector dimension
        """
        self.dimension = dimension
        
        # Create index based on type and metric
        if self.metric == "cosine":
            # Use Inner Product for cosine (vectors must be normalized)
            base_index = faiss.IndexFlatIP(dimension)
        elif self.metric == "euclidean":
            base_index = faiss.IndexFlatL2(dimension)
        elif self.metric == "dot":
            base_index = faiss.IndexFlatIP(dimension)
        else:
            raise ValueError(f"Unknown metric: {self.metric}")
        
        # Wrap with index type
        if self.index_type == "flat":
            self.faiss_index = base_index
        elif self.index_type == "ivf":
            self.faiss_index = faiss.IndexIVFFlat(base_index, dimension, self.nlist)
            # Need to train IVF
            self.index_trained = False
        elif self.index_type == "hnsw":
            self.faiss_index = faiss.IndexHNSWFlat(dimension, self.m)
        else:
            raise ValueError(f"Unknown index type: {self.index_type}")
        
        logger.info(f"FAISS index created: dimension={dimension}, type={self.index_type}")
    
    def _normalize_vectors(self, vectors: np.ndarray) -> np.ndarray:
        """
        Normalize vectors for cosine similarity
        
        Args:
            vectors: Input vectors
            
        Returns:
            Normalized vectors
        """
        if self.metric != "cosine":
            return vectors
        
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero
        return vectors / norms
    
    def index(self, vectors: List[List[float]], ids: List[str],
              metadata: Optional[List[Dict[str, Any]]] = None) -> int:
        """
        Index vectors
        
        Args:
            vectors: List of vectors
            ids: List of IDs
            metadata: Optional metadata
            
        Returns:
            Number of indexed vectors
        """
        # Convert to numpy
        vectors_np = np.array(vectors, dtype=np.float32)
        
        # Normalize for cosine similarity
        vectors_np = self._normalize_vectors(vectors_np)
        
        # Train IVF if needed
        if self.index_type == "ivf" and not hasattr(self, "index_trained"):
            if len(vectors) >= self.nlist:
                logger.info("Training IVF index...")
                self.faiss_index.train(vectors_np)
                self.index_trained = True
            else:
                logger.warning(f"Not enough vectors to train IVF (need {self.nlist})")
        
        # Add to index
        start_idx = self.next_idx
        self.faiss_index.add(vectors_np)
        
        # Store ID mappings and metadata
        for i, (vec_id, vec) in enumerate(zip(ids, vectors)):
            idx = start_idx + i
            self.id_to_idx[vec_id] = idx
            self.idx_to_id[idx] = vec_id
            self.vector_store[vec_id] = vec
            
            if metadata and i < len(metadata):
                self.metadata_store[vec_id] = metadata[i]
        
        self.next_idx += len(vectors)
        
        logger.info(f"Indexed {len(vectors)} vectors, total={self.faiss_index.ntotal}")
        
        return len(vectors)
    
    def search(self, query_vector: List[float], k: int = 10,
               filter_dict: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
        """
        Search for nearest neighbors
        
        Args:
            query_vector: Query vector
            k: Number of results
            filter_dict: Optional metadata filter
            
        Returns:
            List of search results
        """
        # Convert to numpy and normalize
        query_np = np.array([query_vector], dtype=np.float32)
        query_np = self._normalize_vectors(query_np)
        
        # Search
        # For cosine with IP, higher is better
        # For L2, lower is better (convert to similarity)
        distances, indices = self.faiss_index.search(query_np, k)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:  # FAISS returns -1 for missing results
                continue
            
            # Get ID and metadata
            vec_id = self.idx_to_id.get(idx)
            if not vec_id:
                continue
            
            metadata = self.metadata_store.get(vec_id)
            
            # Apply filter
            if filter_dict and metadata:
                match = all(metadata.get(k) == v for k, v in filter_dict.items())
                if not match:
                    continue
            
            # Convert distance to similarity score
            if self.metric == "cosine" or self.metric == "dot":
                score = float(dist)  # Already similarity
            else:  # euclidean
                score = 1.0 / (1.0 + float(dist))  # Convert to similarity
            
            results.append(SearchResult(
                id=vec_id,
                score=score,
                metadata=metadata
            ))
        
        return results[:k]  # Trim to k after filtering
    
    def get(self, vector_id: str) -> Optional[VectorRecord]:
        """
        Get a specific vector
        
        Args:
            vector_id: Vector ID
            
        Returns:
            Vector record or None
        """
        if vector_id not in self.vector_store:
            return None
        
        return VectorRecord(
            id=vector_id,
            vector=self.vector_store[vector_id],
            metadata=self.metadata_store.get(vector_id)
        )
    
    def update(self, vector_id: str, vector: Optional[List[float]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update a vector
        
        Note: FAISS doesn't support in-place updates,
        so we update metadata only or require re-indexing
        
        Args:
            vector_id: Vector ID
            vector: New vector (requires re-indexing)
            metadata: New metadata
            
        Returns:
            Success status
        """
        if vector_id not in self.id_to_idx:
            return False
        
        # Update metadata
        if metadata:
            if vector_id in self.metadata_store:
                self.metadata_store[vector_id].update(metadata)
            else:
                self.metadata_store[vector_id] = metadata
        
        # Update vector (store for future re-indexing)
        if vector:
            self.vector_store[vector_id] = vector
            logger.warning("Vector updated in store, but FAISS index not updated. Consider re-indexing.")
        
        return True
    
    def delete(self, vector_id: str) -> bool:
        """
        Delete a vector
        
        Note: FAISS doesn't support deletion,
        so we mark as deleted in mappings
        
        Args:
            vector_id: Vector ID
            
        Returns:
            Success status
        """
        if vector_id not in self.id_to_idx:
            return False
        
        # Remove from mappings
        idx = self.id_to_idx.pop(vector_id)
        self.idx_to_id.pop(idx, None)
        self.vector_store.pop(vector_id, None)
        self.metadata_store.pop(vector_id, None)
        
        logger.warning("Vector deleted from mappings, but not from FAISS index. Consider re-indexing.")
        
        return True
    
    def clear(self) -> int:
        """
        Clear all vectors
        
        Returns:
            Number of deleted vectors
        """
        count = len(self.id_to_idx)
        
        # Reset index
        if self.faiss_index:
            self.faiss_index.reset()
        
        # Clear mappings
        self.id_to_idx.clear()
        self.idx_to_id.clear()
        self.vector_store.clear()
        self.metadata_store.clear()
        self.next_idx = 0
        
        return count
    
    def count(self) -> int:
        """
        Get total vector count
        
        Returns:
            Vector count
        """
        return len(self.id_to_idx)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get backend statistics
        
        Returns:
            Statistics dict
        """
        # Calculate memory usage (approximate)
        vector_memory = self.dimension * self.count() * 4  # 4 bytes per float
        metadata_memory = sum(
            len(str(m)) for m in self.metadata_store.values()
        )
        total_memory_mb = (vector_memory + metadata_memory) / (1024 * 1024)
        
        return {
            "backend": "faiss",
            "index_type": self.index_type,
            "metric": self.metric,
            "memory_mb": round(total_memory_mb, 2),
            "dimension": self.dimension
        }

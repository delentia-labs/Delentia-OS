"""
Qdrant Backend Implementation - ALGO-16
Distributed vector search using Qdrant
"""

from typing import List, Dict, Any, Optional
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue
)
from ..core.vector_engine import (
    VectorBackendInterface,
    SearchResult,
    VectorRecord
)

logger = logging.getLogger(__name__)


class QdrantBackend(VectorBackendInterface):
    """
    Qdrant backend for distributed vector search
    
    Features:
    - Distributed architecture
    - Rich metadata filtering
    - Persistent storage
    - Production-ready
    - Scalable to billions of vectors
    """
    
    def __init__(self, url: str = "http://localhost:6333",
                 collection_name: str = "vectors",
                 metric: str = "cosine"):
        """
        Initialize Qdrant backend
        
        Args:
            url: Qdrant server URL
            collection_name: Collection name
            metric: Distance metric (cosine/euclidean/dot)
        """
        self.url = url
        self.collection_name = collection_name
        self.metric = metric
        self.client = None
        self.dimension = None
        
        logger.info(f"QdrantBackend initialized: url={url}, collection={collection_name}")
    
    def _get_distance(self) -> Distance:
        """
        Map metric to Qdrant Distance
        
        Returns:
            Distance enum
        """
        metric_map = {
            "cosine": Distance.COSINE,
            "euclidean": Distance.EUCLID,
            "dot": Distance.DOT
        }
        return metric_map.get(self.metric, Distance.COSINE)
    
    def initialize(self, dimension: int, **kwargs):
        """
        Initialize Qdrant client and collection
        
        Args:
            dimension: Vector dimension
        """
        self.dimension = dimension
        
        try:
            # Connect to Qdrant
            self.client = QdrantClient(url=self.url)
            
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                # Create collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=dimension,
                        distance=self._get_distance()
                    )
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            else:
                logger.info(f"Using existing Qdrant collection: {self.collection_name}")
        
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {e}")
            raise
    
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
        # Create points
        points = []
        for i, (vec_id, vector) in enumerate(zip(ids, vectors)):
            payload = metadata[i] if metadata and i < len(metadata) else {}
            
            point = PointStruct(
                id=vec_id,
                vector=vector,
                payload=payload
            )
            points.append(point)
        
        # Upload to Qdrant
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        
        logger.info(f"Indexed {len(points)} vectors in Qdrant")
        
        return len(points)
    
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
        # Build filter
        query_filter = None
        if filter_dict:
            conditions = []
            for key, value in filter_dict.items():
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value)
                    )
                )
            if conditions:
                query_filter = Filter(must=conditions)
        
        # Search
        search_results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=k,
            query_filter=query_filter
        )
        
        # Convert to SearchResult
        results = []
        for hit in search_results:
            results.append(SearchResult(
                id=str(hit.id),
                score=float(hit.score),
                metadata=hit.payload if hit.payload else None
            ))
        
        return results
    
    def get(self, vector_id: str) -> Optional[VectorRecord]:
        """
        Get a specific vector
        
        Args:
            vector_id: Vector ID
            
        Returns:
            Vector record or None
        """
        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[vector_id],
                with_vectors=True,
                with_payload=True
            )
            
            if not points:
                return None
            
            point = points[0]
            return VectorRecord(
                id=str(point.id),
                vector=point.vector,
                metadata=point.payload if point.payload else None
            )
        
        except Exception as e:
            logger.error(f"Failed to get vector {vector_id}: {e}")
            return None
    
    def update(self, vector_id: str, vector: Optional[List[float]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update a vector
        
        Args:
            vector_id: Vector ID
            vector: New vector (optional)
            metadata: New metadata (optional)
            
        Returns:
            Success status
        """
        try:
            # Get existing point
            existing = self.get(vector_id)
            if not existing:
                return False
            
            # Prepare updated point
            updated_vector = vector if vector else existing.vector
            updated_payload = existing.metadata or {}
            if metadata:
                updated_payload.update(metadata)
            
            # Upsert
            point = PointStruct(
                id=vector_id,
                vector=updated_vector,
                payload=updated_payload
            )
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to update vector {vector_id}: {e}")
            return False
    
    def delete(self, vector_id: str) -> bool:
        """
        Delete a vector
        
        Args:
            vector_id: Vector ID
            
        Returns:
            Success status
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[vector_id]
            )
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete vector {vector_id}: {e}")
            return False
    
    def clear(self) -> int:
        """
        Clear all vectors
        
        Returns:
            Number of deleted vectors
        """
        try:
            # Get count before clearing
            count = self.count()
            
            # Delete collection and recreate
            self.client.delete_collection(collection_name=self.collection_name)
            self.initialize(self.dimension)
            
            return count
        
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            return 0
    
    def count(self) -> int:
        """
        Get total vector count
        
        Returns:
            Vector count
        """
        try:
            info = self.client.get_collection(collection_name=self.collection_name)
            return info.points_count
        except Exception as e:
            logger.error(f"Failed to get count: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get backend statistics
        
        Returns:
            Statistics dict
        """
        try:
            info = self.client.get_collection(collection_name=self.collection_name)
            
            return {
                "backend": "qdrant",
                "collection": self.collection_name,
                "metric": self.metric,
                "points_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "dimension": self.dimension
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "backend": "qdrant",
                "error": str(e)
            }

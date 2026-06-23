"""
Pydantic Models for Vector Search API - ALGO-16
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional


class IndexRequest(BaseModel):
    """Request to index vectors"""
    vectors: List[List[float]] = Field(
        ...,
        description="List of vectors to index",
        min_length=1
    )
    ids: List[str] = Field(
        ...,
        description="List of unique IDs for vectors",
        min_length=1
    )
    metadata: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Optional metadata for each vector"
    )
    
    @field_validator('vectors', 'ids')
    @classmethod
    def check_not_empty(cls, v):
        if not v:
            raise ValueError("Cannot be empty")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "vectors": [
                    [0.1, 0.2, 0.3],
                    [0.4, 0.5, 0.6]
                ],
                "ids": ["vec_001", "vec_002"],
                "metadata": [
                    {"category": "tech", "source": "doc1"},
                    {"category": "science", "source": "doc2"}
                ]
            }
        }


class IndexResponse(BaseModel):
    """Response from indexing operation"""
    indexed_count: int = Field(..., description="Number of vectors indexed")
    total_vectors: int = Field(..., description="Total vectors in index")
    time_ms: float = Field(..., description="Processing time in milliseconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "indexed_count": 2,
                "total_vectors": 1002,
                "time_ms": 12.5
            }
        }


class SearchRequest(BaseModel):
    """Request to search vectors"""
    query_vector: List[float] = Field(
        ...,
        description="Query vector for similarity search",
        min_length=1
    )
    k: int = Field(
        10,
        description="Number of nearest neighbors to return",
        ge=1,
        le=1000
    )
    metric: str = Field(
        "cosine",
        description="Distance metric (cosine/euclidean/dot)"
    )
    filter: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional metadata filter"
    )
    
    @field_validator('metric')
    @classmethod
    def validate_metric(cls, v):
        allowed = ["cosine", "euclidean", "dot"]
        if v not in allowed:
            raise ValueError(f"Metric must be one of {allowed}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "query_vector": [0.1, 0.2, 0.3],
                "k": 10,
                "metric": "cosine",
                "filter": {"category": "tech"}
            }
        }


class SearchResult(BaseModel):
    """Single search result"""
    id: str = Field(..., description="Vector ID")
    score: float = Field(..., description="Similarity score")
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Vector metadata"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "vec_001",
                "score": 0.985,
                "metadata": {"category": "tech", "source": "doc1"}
            }
        }


class SearchResponse(BaseModel):
    """Response from search operation"""
    results: List[SearchResult] = Field(
        ...,
        description="List of search results"
    )
    time_ms: float = Field(
        ...,
        description="Processing time in milliseconds"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "id": "vec_001",
                        "score": 0.985,
                        "metadata": {"category": "tech"}
                    },
                    {
                        "id": "vec_005",
                        "score": 0.972,
                        "metadata": {"category": "tech"}
                    }
                ],
                "time_ms": 8.3
            }
        }


class BatchSearchRequest(BaseModel):
    """Request for batch search"""
    query_vectors: List[List[float]] = Field(
        ...,
        description="List of query vectors",
        min_length=1
    )
    k: int = Field(
        10,
        description="Number of results per query",
        ge=1,
        le=1000
    )
    metric: str = Field(
        "cosine",
        description="Distance metric"
    )
    
    @field_validator('metric')
    @classmethod
    def validate_metric(cls, v):
        allowed = ["cosine", "euclidean", "dot"]
        if v not in allowed:
            raise ValueError(f"Metric must be one of {allowed}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "query_vectors": [
                    [0.1, 0.2, 0.3],
                    [0.4, 0.5, 0.6]
                ],
                "k": 5,
                "metric": "cosine"
            }
        }


class BatchSearchResponse(BaseModel):
    """Response from batch search"""
    results: List[List[SearchResult]] = Field(
        ...,
        description="List of result lists for each query"
    )
    time_ms: float = Field(
        ...,
        description="Total processing time"
    )


class VectorResponse(BaseModel):
    """Response with vector data"""
    id: str = Field(..., description="Vector ID")
    vector: List[float] = Field(..., description="Vector data")
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Vector metadata"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "vec_001",
                "vector": [0.1, 0.2, 0.3],
                "metadata": {"category": "tech"}
            }
        }


class UpdateRequest(BaseModel):
    """Request to update a vector"""
    vector: Optional[List[float]] = Field(
        None,
        description="New vector data"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="New or updated metadata"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "vector": [0.15, 0.25, 0.35],
                "metadata": {"category": "updated", "version": 2}
            }
        }


class UpdateResponse(BaseModel):
    """Response from update operation"""
    updated: bool = Field(..., description="Whether update was successful")
    vector_id: str = Field(..., description="ID of updated vector")
    
    class Config:
        json_schema_extra = {
            "example": {
                "updated": True,
                "vector_id": "vec_001"
            }
        }


class DeleteResponse(BaseModel):
    """Response from delete operation"""
    deleted: bool = Field(..., description="Whether deletion was successful")
    vector_id: str = Field(..., description="ID of deleted vector")
    remaining_count: int = Field(..., description="Remaining vectors in index")
    
    class Config:
        json_schema_extra = {
            "example": {
                "deleted": True,
                "vector_id": "vec_001",
                "remaining_count": 9999
            }
        }


class ClearResponse(BaseModel):
    """Response from clear operation"""
    cleared: bool = Field(..., description="Whether clear was successful")
    deleted_count: int = Field(..., description="Number of deleted vectors")
    
    class Config:
        json_schema_extra = {
            "example": {
                "cleared": True,
                "deleted_count": 10000
            }
        }


class StatsResponse(BaseModel):
    """Response with index statistics"""
    total_vectors: int = Field(..., description="Total number of vectors")
    dimension: int = Field(..., description="Vector dimension")
    total_searches: int = Field(..., description="Total number of searches")
    total_index_ops: int = Field(..., description="Total indexing operations")
    avg_search_time_ms: float = Field(..., description="Average search time")
    uptime_seconds: float = Field(..., description="Service uptime")
    backend: str = Field(..., description="Backend type (faiss/qdrant)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_vectors": 10000,
                "dimension": 768,
                "total_searches": 1523,
                "total_index_ops": 150,
                "avg_search_time_ms": 8.5,
                "uptime_seconds": 3600,
                "backend": "faiss"
            }
        }


class HealthResponse(BaseModel):
    """Response from health check"""
    status: str = Field(..., description="Health status (healthy/unhealthy)")
    vector_count: int = Field(..., description="Current vector count")
    dimension: int = Field(..., description="Vector dimension")
    backend: str = Field(..., description="Backend type")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "vector_count": 10000,
                "dimension": 768,
                "backend": "faiss"
            }
        }


class ServiceInfo(BaseModel):
    """Service information"""
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    algorithm: str = Field(..., description="Algorithm identifier")
    phase: str = Field(..., description="RCT phase")
    backend: str = Field(..., description="Vector backend")
    dimension: int = Field(..., description="Vector dimension")
    
    class Config:
        json_schema_extra = {
            "example": {
                "service": "Vector Search Service",
                "version": "1.0.0",
                "algorithm": "ALGO-16",
                "phase": "Phase 3",
                "backend": "faiss",
                "dimension": 768
            }
        }

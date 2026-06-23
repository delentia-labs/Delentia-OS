"""
API Routes for Vector Search - ALGO-16
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any
import logging
from ..models.schemas import (
    IndexRequest,
    IndexResponse,
    SearchRequest,
    SearchResponse,
    BatchSearchRequest,
    BatchSearchResponse,
    VectorResponse,
    UpdateRequest,
    UpdateResponse,
    DeleteResponse,
    ClearResponse,
    StatsResponse,
    HealthResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vector", tags=["Vector Operations"])

# Global engine reference (set by main app)
vector_engine = None


def set_vector_engine(engine):
    """Set the global vector engine instance"""
    global vector_engine
    vector_engine = engine


@router.post("/index", response_model=IndexResponse, status_code=status.HTTP_201_CREATED)
async def index_vectors(request: IndexRequest):
    """
    Index vectors into the search index
    
    - **vectors**: List of vectors to index
    - **ids**: List of unique IDs
    - **metadata**: Optional metadata for each vector
    
    Returns indexing results with timing information.
    """
    try:
        result = vector_engine.index(
            vectors=request.vectors,
            ids=request.ids,
            metadata=request.metadata
        )
        return IndexResponse(**result)
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Indexing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to index vectors"
        )


@router.post("/search", response_model=SearchResponse)
async def search_vectors(request: SearchRequest):
    """
    Search for nearest neighbors
    
    - **query_vector**: Query vector
    - **k**: Number of results (default: 10)
    - **metric**: Distance metric (cosine/euclidean/dot)
    - **filter**: Optional metadata filter
    
    Returns nearest neighbors sorted by similarity score.
    """
    try:
        result = vector_engine.search(
            query_vector=request.query_vector,
            k=request.k,
            metric=request.metric,
            filter_dict=request.filter
        )
        return SearchResponse(**result)
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search vectors"
        )


@router.post("/search/batch", response_model=BatchSearchResponse)
async def batch_search_vectors(request: BatchSearchRequest):
    """
    Search multiple queries in batch
    
    - **query_vectors**: List of query vectors
    - **k**: Number of results per query
    - **metric**: Distance metric
    
    Returns results for each query.
    """
    try:
        result = vector_engine.batch_search(
            query_vectors=request.query_vectors,
            k=request.k,
            metric=request.metric
        )
        return BatchSearchResponse(**result)
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Batch search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to batch search vectors"
        )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check service health
    
    Returns:
    - Health status
    - Vector count
    - Dimension
    - Backend type
    """
    try:
        health = vector_engine.health_check()
        return HealthResponse(**health)
    
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get index statistics
    
    Returns:
    - Total vector count
    - Dimension
    - Search/index operation counts
    - Performance metrics
    - Backend info
    """
    try:
        stats = vector_engine.get_stats()
        return StatsResponse(**stats)
    
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get statistics"
        )


@router.get("/{vector_id}", response_model=VectorResponse)
async def get_vector(vector_id: str):
    """
    Get a specific vector by ID
    
    - **vector_id**: Vector ID
    
    Returns vector data with metadata.
    """
    try:
        result = vector_engine.get(vector_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vector '{vector_id}' not found"
            )
        
        return VectorResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get vector error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get vector"
        )


@router.put("/{vector_id}", response_model=UpdateResponse)
async def update_vector(vector_id: str, request: UpdateRequest):
    """
    Update a vector or its metadata
    
    - **vector_id**: Vector ID
    - **vector**: New vector data (optional)
    - **metadata**: New metadata (optional)
    
    Returns update result.
    """
    try:
        if not request.vector and not request.metadata:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide vector or metadata to update"
            )
        
        result = vector_engine.update(
            vector_id=vector_id,
            vector=request.vector,
            metadata=request.metadata
        )
        
        if not result["updated"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vector '{vector_id}' not found"
            )
        
        return UpdateResponse(**result)
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update vector"
        )


@router.delete("/{vector_id}", response_model=DeleteResponse)
async def delete_vector(vector_id: str):
    """
    Delete a vector from the index
    
    - **vector_id**: Vector ID
    
    Returns deletion result.
    """
    try:
        result = vector_engine.delete(vector_id)
        
        if not result["deleted"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vector '{vector_id}' not found"
            )
        
        return DeleteResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete vector"
        )


@router.delete("/clear", response_model=ClearResponse)
async def clear_index():
    """
    Clear all vectors from the index
    
    ⚠️ WARNING: This will delete all indexed vectors!
    
    Returns number of deleted vectors.
    """
    try:
        result = vector_engine.clear()
        return ClearResponse(**result)
    
    except Exception as e:
        logger.error(f"Clear error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear index"
        )

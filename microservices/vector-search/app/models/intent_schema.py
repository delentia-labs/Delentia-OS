"""
Intent Vector Record Schemas — ALGO-16 Intent Vector Extension
Supports indexing and searching intent embeddings with FDIA scores and JITNA tier metadata.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Dict, Any, Optional
from datetime import datetime


class IntentVectorRecord(BaseModel):
    """A single intent vector record stored in the vector index."""
    intent_hash: str = Field(
        ...,
        description="SHA-256 of normalized intent text (16-char prefix for display)",
        min_length=8,
        max_length=64,
    )
    blueprint_id: str = Field(
        ...,
        description="UUID identifying the IntentBlueprint that produced this record",
    )
    domain: str = Field(
        default="general",
        description="Intent domain: legal, medical, finance, technology, general, ...",
    )
    fdia_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="FDIA quality score (0.0–1.0); records below threshold should not be indexed",
    )
    tier: int = Field(
        default=3,
        ge=1,
        le=9,
        description="JITNA tier 1–9 (1=atomic, 9=meta-intent)",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when this record was created",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata (source, user_id, session_id, ...)",
    )
    vector: List[float] = Field(
        ...,
        description="Dense embedding vector (dimension must match service config)",
        min_length=1,
    )

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        return v.lower().strip()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent_hash": "a1b2c3d4e5f67890",
                "blueprint_id": "550e8400-e29b-41d4-a716-446655440000",
                "domain": "finance",
                "fdia_score": 0.87,
                "tier": 3,
                "metadata": {"source": "chat", "user_id": "u_001"},
                "vector": [0.1, 0.2, 0.3],
            }
        }
    )


class IntentIndexRequest(BaseModel):
    """Request to index one or more intent vectors."""
    records: List[IntentVectorRecord] = Field(
        ...,
        min_length=1,
        description="List of intent vector records to index",
    )
    collection: Optional[str] = Field(
        None,
        description="Override collection name (default: INTENT_VECTORS_COLLECTION env var)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "records": [
                    {
                        "intent_hash": "a1b2c3d4e5f67890",
                        "blueprint_id": "550e8400-e29b-41d4-a716-446655440000",
                        "domain": "finance",
                        "fdia_score": 0.87,
                        "tier": 3,
                        "metadata": {},
                        "vector": [0.1, 0.2, 0.3],
                    }
                ]
            }
        }
    )


class IntentIndexResponse(BaseModel):
    """Response from intent vector indexing."""
    indexed_count: int = Field(..., description="Number of intent records indexed")
    collection: str = Field(..., description="Collection name used for indexing")
    skipped_count: int = Field(
        default=0,
        description="Records skipped due to low FDIA score",
    )
    fdia_threshold_applied: float = Field(
        default=0.0,
        description="Minimum FDIA score enforced during indexing",
    )


class IntentSearchRequest(BaseModel):
    """Request to search for similar intents by vector."""
    vector: List[float] = Field(
        ...,
        min_length=1,
        description="Query embedding vector",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of nearest neighbors to return",
    )
    domain_filter: Optional[str] = Field(
        None,
        description="Filter results to this domain only",
    )
    min_fdia_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum FDIA score for returned results",
    )
    collection: Optional[str] = Field(
        None,
        description="Override collection name (default: INTENT_VECTORS_COLLECTION env var)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "vector": [0.1, 0.2, 0.3],
                "top_k": 5,
                "domain_filter": "finance",
                "min_fdia_score": 0.5,
            }
        }
    )


class IntentSearchHit(BaseModel):
    """A single search result hit."""
    intent_hash: str
    blueprint_id: str
    domain: str
    fdia_score: float
    tier: int
    similarity: float = Field(..., description="Cosine similarity score 0–1")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntentSearchResponse(BaseModel):
    """Response from intent vector search."""
    hits: List[IntentSearchHit] = Field(..., description="Ranked list of similar intents")
    total_found: int = Field(..., description="Total number of matches before top_k truncation")
    query_vector_dim: int = Field(..., description="Dimension of the query vector")
    collection: str = Field(..., description="Collection that was searched")

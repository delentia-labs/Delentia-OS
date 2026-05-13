"""
Intent Vector API Routes — ALGO-16 Intent Vector Extension

Endpoints:
- POST /vector/intent/index   — Index one or more intent vectors
- POST /vector/intent/search  — Search for similar intents by embedding vector
"""

import os
import logging
from fastapi import APIRouter, HTTPException, status

from ..models.intent_schema import (
    IntentIndexRequest,
    IntentIndexResponse,
    IntentSearchRequest,
    IntentSearchResponse,
    IntentSearchHit,
)

logger = logging.getLogger(__name__)

# Default collection name from environment (Phase 2.5)
_DEFAULT_COLLECTION = os.getenv("INTENT_VECTORS_COLLECTION", "intent_vectors")

# Minimum FDIA score enforced at indexing time
_INDEX_FDIA_THRESHOLD = float(os.getenv("INTENT_FDIA_INDEX_THRESHOLD", "0.25"))

router = APIRouter(prefix="/vector/intent", tags=["Intent Vectors"])

# Global engine reference — set by main app via set_vector_engine()
_vector_engine = None


def set_intent_vector_engine(engine) -> None:
    """Inject the shared VectorEngine instance."""
    global _vector_engine
    _vector_engine = engine


@router.post(
    "/index",
    response_model=IntentIndexResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Index intent vectors",
    description=(
        "Index one or more intent vector records. Records with FDIA score below "
        f"INTENT_FDIA_INDEX_THRESHOLD ({_INDEX_FDIA_THRESHOLD}) are skipped."
    ),
)
async def index_intent_vectors(request: IntentIndexRequest) -> IntentIndexResponse:
    if _vector_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector engine not initialised",
        )

    collection = request.collection or _DEFAULT_COLLECTION

    # Apply FDIA quality gate before indexing
    eligible = [r for r in request.records if r.fdia_score >= _INDEX_FDIA_THRESHOLD]
    skipped = len(request.records) - len(eligible)

    if not eligible:
        return IntentIndexResponse(
            indexed_count=0,
            collection=collection,
            skipped_count=skipped,
            fdia_threshold_applied=_INDEX_FDIA_THRESHOLD,
        )

    vectors = [r.vector for r in eligible]
    ids = [r.intent_hash for r in eligible]
    metadata = [
        {
            "blueprint_id": r.blueprint_id,
            "domain": r.domain,
            "fdia_score": r.fdia_score,
            "tier": r.tier,
            "created_at": r.created_at.isoformat(),
            **r.metadata,
        }
        for r in eligible
    ]

    try:
        _vector_engine.index(vectors=vectors, ids=ids, metadata=metadata)
    except Exception as exc:  # pragma: no cover
        logger.error("Intent vector indexing failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {exc}",
        ) from exc

    return IntentIndexResponse(
        indexed_count=len(eligible),
        collection=collection,
        skipped_count=skipped,
        fdia_threshold_applied=_INDEX_FDIA_THRESHOLD,
    )


@router.post(
    "/search",
    response_model=IntentSearchResponse,
    summary="Search similar intent vectors",
    description="Find the top-k most similar intent vectors to the supplied query embedding.",
)
async def search_intent_vectors(request: IntentSearchRequest) -> IntentSearchResponse:
    if _vector_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector engine not initialised",
        )

    collection = request.collection or _DEFAULT_COLLECTION

    try:
        search_response = _vector_engine.search(
            query_vector=request.vector,
            k=request.top_k,
        )
        raw_results = search_response.get("results", [])
    except Exception as exc:  # pragma: no cover
        logger.error("Intent vector search failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc}",
        ) from exc

    hits = []
    for item in raw_results:
        meta = item.get("metadata") or {}
        fdia_score = float(meta.get("fdia_score", 0.0))

        # Apply optional filters
        if request.domain_filter and meta.get("domain") != request.domain_filter:
            continue
        if fdia_score < request.min_fdia_score:
            continue

        hits.append(
            IntentSearchHit(
                intent_hash=item.get("id", ""),
                blueprint_id=meta.get("blueprint_id", ""),
                domain=meta.get("domain", "general"),
                fdia_score=fdia_score,
                tier=int(meta.get("tier", 3)),
                similarity=float(item.get("score", 0.0)),
                metadata={k: v for k, v in meta.items()
                          if k not in ("blueprint_id", "domain", "fdia_score", "tier", "created_at")},
            )
        )

    return IntentSearchResponse(
        hits=hits,
        total_found=len(hits),
        query_vector_dim=len(request.vector),
        collection=collection,
    )

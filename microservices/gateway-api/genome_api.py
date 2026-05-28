"""
genome_api.py
Gateway API stub — Genome & Creator Profile integration

This module exposes the API surface for the Genome / Creator Profile system.
The full implementation requires the enterprise ``creator_profile_integration``
module which ships with the RCT enterprise runtime and is **not** included in
this public SDK repo.

All endpoints in this module return HTTP 501 Not Implemented when the
enterprise module is unavailable, so the gateway starts cleanly without
the private dependency and callers receive a clear, actionable error message
instead of a silent 500 crash.

Enterprise module path (private runtime):
  rct_platform/microservices/kernel-api/creator_profile_integration.py

Public reference: https://github.com/delentia-labs/delentia-os
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Any

# ---------------------------------------------------------------------------
# Enterprise module availability
# ---------------------------------------------------------------------------
_ENTERPRISE_AVAILABLE = False
_ENTERPRISE_UNAVAILABLE_DETAIL = (
    "Genome / Creator Profile endpoints require the RCT enterprise runtime "
    "module (creator_profile_integration). "
    "This module is not included in the public SDK. "
    "See https://delentia.com for enterprise access."
)

# Create router
router = APIRouter(prefix="/api/genome", tags=["genome"])


def _raise_not_implemented() -> None:
    """Raise a uniform 501 response for all enterprise-only endpoints."""
    raise HTTPException(status_code=501, detail=_ENTERPRISE_UNAVAILABLE_DETAIL)


# ---------------------------------------------------------------------------
# Request model (kept for API surface documentation)
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    language: str = "th"


# ---------------------------------------------------------------------------
# Endpoints — all return 501 until enterprise module is connected
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check for the Genome API — reports enterprise module availability."""
    return {
        "status": "unavailable",
        "enterprise_module": _ENTERPRISE_AVAILABLE,
        "message": _ENTERPRISE_UNAVAILABLE_DETAIL,
    }


@router.get("/creator")
async def get_creator_identity(
    language: str = Query("th", pattern="^(th|en)$"),
) -> Any:
    """Get creator identity from Genome v4.0. Requires enterprise runtime."""
    _raise_not_implemented()


@router.get("/fdia")
async def get_fdia_equation(
    language: str = Query("th", pattern="^(th|en)$"),
) -> Any:
    """Get FDIA equation explanation. Requires enterprise runtime."""
    _raise_not_implemented()


@router.get("/values")
async def get_core_values(
    language: str = Query("th", pattern="^(th|en)$"),
) -> Any:
    """Get 5 core values. Requires enterprise runtime."""
    _raise_not_implemented()


@router.get("/roles")
async def get_creator_roles() -> Any:
    """Get 7 creator roles in the RCT ecosystem. Requires enterprise runtime."""
    _raise_not_implemented()


@router.get("/complete")
async def get_complete_profile(
    language: str = Query("th", pattern="^(th|en)$"),
) -> Any:
    """Get complete creator profile. Requires enterprise runtime."""
    _raise_not_implemented()


@router.post("/query")
async def query_creator(request: QueryRequest) -> Any:
    """Ask a question to the creator profile system. Requires enterprise runtime."""
    _raise_not_implemented()


# Export router
__all__ = ["router"]

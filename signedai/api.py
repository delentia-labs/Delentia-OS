"""
SignedAI HTTP API (Round 50).

`microservices/gateway-api/gateway_main.py` has always tried
`from signedai.api import app, router` and mounted it at /signedai, but the
module never existed, so the mount silently failed. This is that module.

Every endpoint here is deterministic arithmetic over `signedai.core`: the
tier catalogue, risk-based tier routing, consensus counting and cost
estimates. No endpoint calls a model, so the API cannot spend money or leak
a prompt; running an actual multi-model review stays in
`signedai.core.openrouter_adapter`, behind the agent runtime's own budget and
approvals.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from signedai.core.models import AnalysisJob, AnalysisStatus, JITNAPacket
from signedai.core.registry import HexaCoreRegistry, SignedAIRegistry, SignedAITier
from signedai.core.router import TierRouter

router = APIRouter()
_TIER_ROUTER = TierRouter()


class RouteRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=4000, description="JITNA I: what the change is meant to do")
    domain: str = Field("", max_length=2000, description="JITNA D: domain or context")
    delta: str = Field("", max_length=4000, description="JITNA delta: the change being made")
    requirements: str = Field("", max_length=4000, description="JITNA R: requirements")
    artifact_type: str = Field("code", pattern="^(code|text|document|config|schema|other)$")
    tags: Dict[str, str] = Field(default_factory=dict)


class ConsensusRequest(BaseModel):
    tier: SignedAITier
    votes_for: int = Field(..., ge=0)
    votes_against: int = Field(..., ge=0)
    chairman_override: Optional[bool] = None


class EstimateRequest(BaseModel):
    tier: SignedAITier
    input_tokens: int = Field(..., ge=0, le=10_000_000)
    output_tokens: int = Field(..., ge=0, le=10_000_000)


@router.get("/health")
def health() -> Dict[str, object]:
    return {"status": "ok", "calls_models": False}


@router.get("/tiers")
def tiers() -> List[Dict[str, object]]:
    return [
        {
            "tier": cfg.tier.value,
            "signers": [role.value for role in cfg.signers],
            "required_votes": cfg.required_votes,
            "consensus_threshold": round(cfg.consensus_threshold, 4),
            "chairman_veto": cfg.chairman_veto,
            "west_count": cfg.west_count,
            "east_count": cfg.east_count,
            "recommended_for": cfg.recommended_for,
        }
        for cfg in SignedAIRegistry.TIERS.values()
    ]


@router.get("/roster")
def roster() -> List[Dict[str, object]]:
    """Which model each HexaCore role is configured to use (public metadata only)."""
    return [
        {
            "role": role.value,
            "model_id": info.id,
            "provider": info.provider,
            "country": info.country,
            "usd_per_mtok_input": info.cost_input,
            "usd_per_mtok_output": info.cost_output,
            "context_window": info.context_window,
        }
        for role, info in HexaCoreRegistry.MODELS.items()
    ]


@router.post("/route")
def route(req: RouteRequest) -> Dict[str, object]:
    """Risk level and tier the TierRouter picks for this change (keyword and tag rules)."""
    now = datetime.now(timezone.utc)
    job = AnalysisJob(
        id=f"route-{uuid.uuid4().hex[:12]}",
        created_at=now,
        updated_at=now,
        artifact_hash="none",
        artifact_type=req.artifact_type,
        artifact_content=None,
        intent=JITNAPacket(I=req.intent, D=req.domain, **{"Δ": req.delta}, A="", R=req.requirements, M=""),
        status=AnalysisStatus.QUEUED,
        tags=req.tags,
    )
    routed = _TIER_ROUTER.route(job)
    if routed.tier is None or routed.risk_level is None:  # route() always sets both on auto-selection
        raise HTTPException(status_code=500, detail="router did not select a tier")
    return {
        "risk_level": routed.risk_level.value,
        "tier": routed.tier.value,
        "estimated_cost_usd": _TIER_ROUTER.estimate_cost(routed.tier),
        "estimated_duration_ms": _TIER_ROUTER.estimate_duration(routed.tier),
    }


@router.post("/consensus")
def consensus(req: ConsensusRequest) -> Dict[str, object]:
    """Whether these vote counts reach consensus for the tier (count and ratio rules)."""
    cfg = SignedAIRegistry.get_tier(req.tier)
    if req.votes_for + req.votes_against > len(cfg.signers):
        raise HTTPException(status_code=422, detail=f"{req.tier.value} has {len(cfg.signers)} signers; "
                                                    f"got {req.votes_for + req.votes_against} votes")
    result = SignedAIRegistry.calculate_consensus(req.tier, req.votes_for, req.votes_against,
                                                  chairman_override=req.chairman_override)
    return {
        "tier": result.tier.value,
        "consensus_reached": result.consensus_reached,
        "confidence": round(result.confidence, 4),
        "votes_for": result.votes_for,
        "votes_against": result.votes_against,
        "required_votes": cfg.required_votes,
        "consensus_threshold": round(cfg.consensus_threshold, 4),
        "signers": result.signers,
    }


@router.post("/estimate")
def estimate(req: EstimateRequest) -> Dict[str, object]:
    """USD cost of one consensus round for the tier, from the roster's per-token prices."""
    total, breakdown = SignedAIRegistry.estimate_tier_cost(req.tier, req.input_tokens, req.output_tokens)
    return {"tier": req.tier.value, "total_usd": round(total, 6),
            "by_model": {k: round(v, 6) for k, v in breakdown.items()}}


app = FastAPI(title="SignedAI", version="1.0.0",
              description="Deterministic SignedAI tier, routing, consensus and cost endpoints. No model calls.")
app.include_router(router)

__all__ = ["app", "router"]

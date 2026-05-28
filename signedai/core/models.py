"""
SignedAI Core Models — standalone public implementation

Defines all data models for the SignedAI consensus verification system.
No dependency on rct_platform private internals.

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    """Risk classification for task routing."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TierLevel(str, Enum):
    """SignedAI consensus tier."""
    TIER_S = "tier-s"
    TIER_4 = "tier-4"
    TIER_6 = "tier-6"
    TIER_8 = "tier-8"


class Verdict(str, Enum):
    """Final verdict of a consensus vote."""
    PASS = "pass"
    REVISE = "revise"
    BLOCK = "block"


class Certification(str, Enum):
    """Quality certification level."""
    GOLD = "GOLD"
    SILVER = "SILVER"
    BRONZE = "BRONZE"
    FAIL = "FAIL"


class AnalysisStatus(str, Enum):
    """Lifecycle status of an analysis job."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# JITNA Packet
# ---------------------------------------------------------------------------

class JITNAPacket(BaseModel):
    """
    SignedAI Semantic Layer — JITNA-shaped intent packet for verification context.

    This class follows the JITNA 6-field structure (I, D, Δ, A, R, M) but maps
    each field to SignedAI's verification-specific semantics:

        I = Intent        — primary goal statement (same as canonical JITNA Language)
        D = Domain        — context/scope for this analysis (≠ "Data" in JITNA Language)
        Δ = Delta         — desired change or gap (same as canonical JITNA Language)
        A = Assumptions   — preconditions assumed true (≠ "Approach" in JITNA Language)
        R = Requirements  — non-negotiable constraints (≠ "Reflection" in JITNA Language)
        M = Metrics       — success criteria (≠ "Memory" in JITNA Language)

    NOTE: The canonical JITNA Language (D=Data, A=Approach, R=Reflection, M=Memory)
    is defined in the JITNA Protocol RFC-001 and documented in docs/concepts/jitna.md.
    This class is a *verification-focused variant* used inside the SignedAI consensus
    engine. The canonical JITNA Protocol wire format is in
    rct_control_plane/jitna_protocol.py.

    JITNA = Just In Time Nodal Assembly (canonical public name, per Delentia Labs Architect).
    """
    I: str = Field(..., description="Intent — primary goal statement")  # noqa: E741
    D: str = Field(..., description="Domain — context/scope")
    delta: str = Field(..., alias="Δ", description="Delta — desired change")
    A: str = Field(..., description="Assumptions — preconditions")
    R: str = Field(..., description="Requirements — non-negotiable constraints")
    M: str = Field(..., description="Metrics — success criteria")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Analysis I/O Models
# ---------------------------------------------------------------------------

class AnalysisRequest(BaseModel):
    """Request to run a SignedAI consensus analysis on an artifact."""
    artifact_hash: str = Field(..., description="SHA-256 hash of the artifact")
    artifact_type: Literal["code", "text", "document", "config", "schema", "other"] = "code"
    artifact_content: str = Field(..., description="Raw content to analyse")
    artifact_language: Optional[str] = Field(None, description="Language (python, typescript, …)")

    intent: JITNAPacket
    constraints: Optional[Dict[str, Any]] = Field(default_factory=dict)
    context_refs: Optional[Dict[str, Any]] = Field(default_factory=dict)

    risk_level: Optional[RiskLevel] = None
    tier: Optional[TierLevel] = None
    tier_auto_selected: bool = True

    created_by: Optional[str] = None
    source_system: Optional[str] = "signedai_api"
    correlation_id: Optional[str] = None
    tags: Optional[Dict[str, str]] = Field(default_factory=dict)


class SignerVote(BaseModel):
    """Vote cast by a single signer (AI model) in the consensus round."""
    signer_id: str
    signer_role: str
    model: str
    provider: str

    verdict: Verdict
    confidence: float = Field(..., ge=0.0, le=1.0)

    scores: Dict[str, float] = Field(default_factory=dict)
    rationale: str
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)

    has_veto_power: bool = False
    veto_triggered: bool = False
    veto_reason: Optional[str] = None

    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None

    weight: float = 1.0
    execution_order: Optional[int] = None


class ConsensusResult(BaseModel):
    """Aggregated result of a multi-signer consensus round."""
    consensus_rule: str = "weighted_majority"
    threshold: float

    total_signers: int
    votes_pass: int = 0
    votes_revise: int = 0
    votes_block: int = 0

    weighted_score: Optional[float] = None
    weights_sum: Optional[float] = None

    final_verdict: Verdict
    certification: Certification
    confidence: float = Field(..., ge=0.0, le=1.0)

    agreement_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    disagreements: List[Dict[str, Any]] = Field(default_factory=list)
    outlier_votes: List[str] = Field(default_factory=list)

    veto_count: int = 0
    vetoed_by: List[str] = Field(default_factory=list)

    deltas: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_summary: List[Dict[str, Any]] = Field(default_factory=list)


class AnalysisJob(BaseModel):
    """Full analysis job including request, routing, execution, and results."""
    id: str
    created_at: datetime
    updated_at: datetime

    artifact_hash: str
    artifact_type: str
    artifact_content: Optional[str] = None
    artifact_size_bytes: Optional[int] = None
    artifact_language: Optional[str] = None

    intent: JITNAPacket
    constraints: Dict[str, Any] = Field(default_factory=dict)
    context_refs: Dict[str, Any] = Field(default_factory=dict)

    risk_level: Optional[RiskLevel] = None
    tier: Optional[TierLevel] = None
    tier_auto_selected: bool = True

    status: AnalysisStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    verdict: Optional[Verdict] = None
    certification: Optional[Certification] = None
    confidence: Optional[float] = None

    summary: Optional[str] = None
    deltas: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)

    created_by: Optional[str] = None
    source_system: str = "signedai_api"
    correlation_id: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)

    total_duration_ms: Optional[int] = None
    total_cost_usd: Optional[float] = None
    total_tokens_used: Optional[int] = None

    votes: List[SignerVote] = Field(default_factory=list)
    consensus: Optional[ConsensusResult] = None


class AnalysisReport(BaseModel):
    """Formatted report produced from a completed AnalysisJob."""
    job_id: str
    format: Literal["markdown", "json", "html"] = "markdown"
    content: str
    created_at: datetime

    summary: str
    verdict: Verdict
    certification: Certification
    confidence: float

    statistics: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)


__all__ = [
    "RiskLevel",
    "TierLevel",
    "Verdict",
    "Certification",
    "AnalysisStatus",
    "JITNAPacket",
    "AnalysisRequest",
    "SignerVote",
    "ConsensusResult",
    "AnalysisJob",
    "AnalysisReport",
]

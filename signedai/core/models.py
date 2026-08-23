"""
Data Models for SignedAI
Complete native data models for SignedAI certification, consensus, and verification.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """ระดับความเสี่ยง"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TierLevel(str, Enum):
    """ระดับ Tier ของ SignedAI"""
    TIER_S = "tier-s"
    TIER_4 = "tier-4"
    TIER_6 = "tier-6"
    TIER_8 = "tier-8"


class Verdict(str, Enum):
    """คำตัดสิน"""
    PASS = "pass"
    REVISE = "revise"
    BLOCK = "block"


class Certification(str, Enum):
    """ระดับการรับรอง"""
    GOLD = "GOLD"
    SILVER = "SILVER"
    BRONZE = "BRONZE"
    FAIL = "FAIL"


class AnalysisStatus(str, Enum):
    """สถานะการวิเคราะห์"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JITNAPacket(BaseModel):
    """
    JITNA Intent Packet
    แพ็กเก็ตความตั้งใจตาม JITNA Language (6 fields)
    """
    I: str = Field(..., description="Intent - ความตั้งใจหลัก")
    D: str = Field(..., description="Domain - โดเมน/บริบท")
    delta: str = Field(..., alias="Δ", description="Delta - การเปลี่ยนแปลงที่ต้องการ")
    A: str = Field(..., description="Assumptions - สมมติฐาน")
    R: str = Field(..., description="Requirements - ข้อกำหนด")
    M: str = Field(..., description="Metrics - เมตริกความสำเร็จ")

    class Config:
        populate_by_name = True


class AnalysisRequest(BaseModel):
    """
    คำขอการวิเคราะห์
    """
    artifact_hash: str = Field(..., description="Hash ของ artifact ที่ต้องการวิเคราะห์")
    artifact_type: Literal["code", "text", "document", "config", "schema", "other"] = "code"
    artifact_content: str = Field(..., description="เนื้อหาที่ต้องการวิเคราะห์")
    artifact_language: Optional[str] = Field(None, description="ภาษาของ artifact (เช่น python, typescript)")
    
    intent: JITNAPacket = Field(..., description="JITNA intent packet")
    constraints: Optional[Dict[str, Any]] = Field(default_factory=dict, description="ข้อจำกัดเพิ่มเติม")
    context_refs: Optional[Dict[str, Any]] = Field(default_factory=dict, description="การอ้างอิงบริบท")
    
    risk_level: Optional[RiskLevel] = None
    tier: Optional[TierLevel] = None
    tier_auto_selected: bool = True
    
    created_by: Optional[str] = None
    source_system: Optional[str] = "signedai_api"
    correlation_id: Optional[str] = None
    tags: Optional[Dict[str, str]] = Field(default_factory=dict)


class SignerVote(BaseModel):
    """
    Vote จาก Signer แต่ละตัว
    """
    signer_id: str
    signer_role: str
    model: str
    provider: str
    
    verdict: Verdict
    confidence: float = Field(..., ge=0.0, le=1.0)
    
    scores: Dict[str, float] = Field(default_factory=dict, description="คะแนนแต่ละแกน")
    rationale: str = Field(..., description="เหตุผลการตัดสิน")
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
    """
    ผลลัพธ์การคำนวณ Consensus
    """
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
    """
    Job การวิเคราะห์ทั้งหมด
    """
    id: str
    created_at: datetime
    updated_at: datetime
    
    # Artifact info
    artifact_hash: str
    artifact_type: str
    artifact_size_bytes: Optional[int] = None
    artifact_language: Optional[str] = None
    artifact_content: Optional[str] = Field(None, description="เนื้อหาที่วิเคราะห์")
    
    # Intent & context
    intent: JITNAPacket
    constraints: Dict[str, Any] = Field(default_factory=dict)
    context_refs: Dict[str, Any] = Field(default_factory=dict)
    
    # Risk & routing
    risk_level: Optional[RiskLevel] = None
    tier: Optional[TierLevel] = None
    tier_auto_selected: bool = True
    
    # Execution
    status: AnalysisStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results
    verdict: Optional[Verdict] = None
    certification: Optional[Certification] = None
    confidence: Optional[float] = None
    
    summary: Optional[str] = None
    deltas: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Metadata
    created_by: Optional[str] = None
    source_system: str = "signedai_api"
    correlation_id: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)
    
    # Performance
    total_duration_ms: Optional[int] = None
    total_cost_usd: Optional[float] = None
    total_tokens_used: Optional[int] = None
    
    # Votes & consensus
    votes: List[SignerVote] = Field(default_factory=list)
    consensus: Optional[ConsensusResult] = None


class AnalysisReport(BaseModel):
    """
    รายงานผลการวิเคราะห์
    """
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

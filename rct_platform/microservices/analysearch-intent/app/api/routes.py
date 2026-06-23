"""
Analysearch Intent API Routes
FastAPI endpoints for Analysis + Research + Intent
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime

router = APIRouter()

from ..core.analysearch_engine import (
    AnalysearchEngine,
    AnalysearchMode,
)

# Global engine instance
engine = AnalysearchEngine()


# === Request/Response Models ===

class AnalyzeRequest(BaseModel):
    """Request for analysis"""
    query: str = Field(..., min_length=1, description="User query/intent")
    mode: Optional[str] = Field(default="standard", description="quick|standard|deep|mirror")
    context: Optional[str] = Field(default="", description="Additional context")
    max_mirror_iterations: Optional[int] = Field(default=3, ge=1, le=10)


class KeywordResponse(BaseModel):
    """Keyword extraction result"""
    keyword: str
    score: float
    entropy: float
    frequency: int
    domain: Optional[str] = None


class MirrorStateResponse(BaseModel):
    """Mirror Mode session state"""
    session_id: str
    phase: str
    iterations: int
    convergence_score: float
    converged: bool
    proposals_count: int
    counters_count: int
    refinements_count: int


class AnalyzeResponse(BaseModel):
    """Full analysis response"""
    query: str
    mode: str
    keywords: List[KeywordResponse]
    analysis: Dict
    research_sources: List[Dict]
    synthesis: Dict
    intent_preserved: bool
    confidence: float
    mirror_state: Optional[MirrorStateResponse] = None
    processing_time_ms: float


class ValidateRequest(BaseModel):
    """Input validation request"""
    text: str
    min_entropy: Optional[float] = 2.0


class CrystallizeRequest(BaseModel):
    """Keyword extraction request"""
    text: str
    top_k: Optional[int] = Field(default=10, ge=1, le=50)


class SynthesizeRequest(BaseModel):
    """Cross-disciplinary synthesis request"""
    keywords: List[str]
    context: Optional[str] = ""


# === API Endpoints ===

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """
    Main Analysearch endpoint

    Modes:
    - quick: Fast lookup, minimal analysis
    - standard: Standard analysis + research
    - deep: Deep analysis with Mirror Mode
    - mirror: Full Mirror Mode (PROPOSE → COUNTER → REFINE)
    """
    try:
        mode = AnalysearchMode(req.mode) if req.mode else AnalysearchMode.STANDARD

        result = engine.analyze(
            query=req.query,
            mode=mode,
            context=req.context or "",
            max_mirror_iterations=req.max_mirror_iterations or 3
        )

        # Build mirror state response if present
        mirror_resp = None
        if result.mirror_state:
            ms = result.mirror_state
            mirror_resp = MirrorStateResponse(
                session_id=ms.session_id,
                phase=ms.phase.value,
                iterations=ms.iterations,
                convergence_score=ms.convergence_score,
                converged=ms.converged,
                proposals_count=len(ms.proposals),
                counters_count=len(ms.counters),
                refinements_count=len(ms.refinements)
            )

        return AnalyzeResponse(
            query=result.query,
            mode=result.mode,
            keywords=[
                KeywordResponse(**kw)
                for kw in result.keywords
            ],
            analysis=result.analysis,
            research_sources=result.research_sources,
            synthesis=result.synthesis,
            intent_preserved=result.intent_preserved,
            confidence=result.confidence,
            mirror_state=mirror_resp,
            processing_time_ms=result.processing_time_ms
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.post("/validate")
async def validate_input(req: ValidateRequest):
    """Validate input quality (GIGO Protection)"""
    try:
        is_valid, details = engine.gigo.validate_input(
            req.text, min_entropy=req.min_entropy
        )

        return {
            "is_valid": is_valid,
            "details": details
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crystallize", response_model=List[KeywordResponse])
async def crystallize_keywords(req: CrystallizeRequest):
    """
    Extract golden keywords from text (ALGO-41 inspired)

    Returns ranked keywords with entropy scores
    """
    try:
        keywords = engine.crystallizer.extract(req.text, top_k=req.top_k)
        return [KeywordResponse(**kw) for kw in keywords]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/synthesize")
async def synthesize_disciplines(req: SynthesizeRequest):
    """
    Cross-disciplinary synthesis

    Finds connections between different domains based on keywords
    """
    try:
        keyword_dicts = [{"keyword": kw, "score": 0.5, "entropy": 2.0} for kw in req.keywords]
        result = engine.synthesizer.synthesize(keyword_dicts, req.context or "")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_mirror_session(session_id: str):
    """Get Mirror Mode session details"""
    state = engine.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return {
        "session_id": state.session_id,
        "query": state.query,
        "phase": state.phase.value,
        "iterations": state.iterations,
        "convergence_score": state.convergence_score,
        "converged": state.converged,
        "proposals": state.proposals,
        "counters": state.counters,
        "refinements": state.refinements
    }


@router.get("/stats")
async def get_stats():
    """Get engine statistics"""
    return engine.get_stats()


@router.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "analysearch-intent",
        "version": "v1.0",
        "capabilities": [
            "analysis",
            "keyword_crystallization",
            "cross_disciplinary_synthesis",
            "mirror_mode",
            "gigo_protection"
        ]
    }

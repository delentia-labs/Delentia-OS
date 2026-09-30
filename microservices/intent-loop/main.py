# main.py - FastAPI wrapper for Intent Loop Engine
import sys
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

# Setup path to import loop_engine and core packages
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from loop_engine import IntentLoopEngine, JITNAPacket  # noqa: E402

app = FastAPI(title="Delentia OS - Intent Loop Engine")
engine = IntentLoopEngine()

class ProcessRequest(BaseModel):
    intent: str
    context: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    priority: Optional[int] = 3

@app.post("/process")
async def process_intent(req: ProcessRequest):
    packet = JITNAPacket(
        intent=req.intent,
        context=req.context or {},
        user_id=req.user_id,
        session_id=req.session_id,
        priority=req.priority
    )
    result = await engine.process(packet)
    if result.state.value == "failed":
        raise HTTPException(status_code=400, detail=result.error or "Processing failed")
    
    return {
        "intent_hash": result.intent_hash,
        "state": result.state.value,
        "output": result.output,
        "latency_ms": result.latency_ms,
        "cache_hit": result.cache_hit,
        "verification_passed": result.verification_passed,
        "metadata": {**result.metadata, "simulated_execution": True, "simulated_verification": True}
    }

# Round 51: what this service is. Its specialist executor and its verifier are
# simulated (a sleep and a fixed vote); the real Intent Loop - five pillars over
# the governed agent loop and the 41-algorithm pipeline - is rct_control_plane/intent_loop.py.
IMPLEMENTATION = {
    "implementation": "reference",
    "executor": "simulated",
    "verifier": "simulated",
    "runtime_intent_loop": "rct_control_plane/intent_loop.py",
}


@app.get("/health")
async def health():
    return {"status": "healthy", **IMPLEMENTATION}

@app.get("/metrics")
async def metrics():
    return engine.get_metrics()

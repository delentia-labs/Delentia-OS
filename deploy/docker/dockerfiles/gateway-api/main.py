"""
gateway-api/main.py — Minimal bootstrap for Docker image.
Full implementation lives in delentia-private-os.
This stub responds to healthcheck endpoints so the community
stack can start without the private source.
"""
import os
import time
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

START_TIME = time.time()
app = FastAPI(title="Delentia Gateway API", version="2.0.0")
security = HTTPBearer(auto_error=False)


# ── Auth helper ───────────────────────────────────────────────────────────────
def verify_token(creds: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    expected = os.getenv("DELENTIA_API_KEY", "")
    if not expected:
        return "anonymous"  # dev mode — no key configured
    if not creds or creds.credentials != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return creds.credentials


# ── Models ────────────────────────────────────────────────────────────────────
class IntentRequest(BaseModel):
    intent: str
    mode: str = "standard"
    context: dict = {}


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "service": "gateway-api",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uptime_seconds": round(time.time() - START_TIME),
    }


@app.get("/metrics")
async def metrics():
    return {"uptime_seconds": round(time.time() - START_TIME), "service": "gateway-api"}


@app.get("/delentia/system/stats")
async def system_stats():
    return {
        "tests": 4849,
        "microservices": 62,
        "algorithms": 41,
        "version": "2.0.0",
        "mode": "community",
    }


@app.get("/delentia/benchmark/summary")
async def benchmark_summary():
    return {
        "jitna_compliance": 0.94,
        "fdia_avg": 0.87,
        "hallucination_rate": 0.028,
        "mode": "community",
    }


@app.post("/v1/kernel/execute")
async def kernel_execute(req: IntentRequest, token: str = Depends(verify_token)):
    import uuid, hashlib
    trace = str(uuid.uuid4())
    fdia_f = 0.87
    return {
        "trace_id": trace,
        "jitna_packet": {
            "version": "3",
            "intent": req.intent,
            "mode": req.mode,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "output": {
            "result": f"[Community gateway] Intent received: '{req.intent}'. Deploy delentia-private-os for full HexaCore processing.",
            "hexa_role": "LEAD_BUILDER",
            "fdia_score": {"D": 0.9, "I": 0.97, "A": 1.0, "F": fdia_f, "signed": False, "signature_hash": ""},
        },
    }


@app.websocket("/v1/kernel/stream")
async def kernel_stream(ws: WebSocket, token: str = ""):
    expected = os.getenv("DELENTIA_API_KEY", "")
    if expected and token != expected:
        await ws.close(code=1008, reason="Unauthorized")
        return

    await ws.accept()
    try:
        data = await ws.receive_json()
        intent = data.get("intent", "")
        words = f"[Streaming] Received intent: {intent}. Full HexaCore streaming requires delentia-private-os.".split()
        for word in words:
            await ws.send_json({"type": "token", "data": word + " "})
            import asyncio; await asyncio.sleep(0.05)
        await ws.send_json({"type": "fdia", "data": {"D": 0.9, "I": 0.97, "A": 1.0, "F": 0.87}})
        await ws.send_json({"type": "done", "data": {}})
    except WebSocketDisconnect:
        pass

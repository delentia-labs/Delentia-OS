"""
Agent mode for the Delentia Desk chat (apps/gui) - Round 50.

Before this, every Desk chat mode went to dynamic_reasoner.stream_dynamic_cognition,
which only asks a small local model for text: no tools, no governed loop, and a
badge with fixed D/I values and a signature over nothing. Agent mode streams a
real GovernedAutonomousLoop episode (built by agent_factory, like every other
entry point) into the same WebSocket event shapes the Desk already renders:

    {"type": "token", "data": markdown}   one per step, then the answer
    {"type": "fdia",  "data": {D, I, A, F, signed, signature_hash}}
    {"type": "done",  "data": {hexa_role, trace_id, ...}}

The FDIA badge carries the episode's real D and I and F of the goal (A = 1: no
action yet; each risky action is gated separately and shows up as a step), and
"signed" means the episode's JITNA packet was signed and verified.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Callable, Dict, Optional

_RESULT_PREVIEW_CHARS = 400


def _preview(value: Any, limit: int = _RESULT_PREVIEW_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + " ..."


def format_step(step: Any) -> str:
    """One loop step as Desk markdown (Thai labels, tool data verbatim)."""
    tool = getattr(step, "tool_name", None)
    result = getattr(step, "tool_result", None)
    n = getattr(step, "iteration", "?")
    if not tool:
        return ""
    args = _preview(getattr(step, "tool_args", {}) or {}, 200)
    if isinstance(result, dict) and result.get("fdia_blocked"):
        return f"⛔ ขั้นที่ {n}: {tool} ถูก FDIA gate บล็อก (F = {result.get('F')}) - {result.get('reason')}\n\n"
    if isinstance(result, dict) and result.get("pending_approval"):
        return (f"⏸️ ขั้นที่ {n}: {tool} รอมนุษย์อนุมัติ ({args})\n"
                f"ต้องลงลายเซ็น Ed25519 ก่อนจึงจะรัน: `delentia approvals list` แล้ว "
                f"`delentia approvals approve <approval_id> --key <กุญแจของคุณ>`\n\n")
    if isinstance(result, dict) and result.get("notary_unavailable"):
        return f"🛑 ขั้นที่ {n}: {tool} ไม่ได้รัน - notary บันทึกไม่ได้ (fail closed)\n\n"
    if isinstance(result, dict) and "did_you_mean" in result:
        return (f"❓ ขั้นที่ {n}: ไม่มี tool ชื่อ {tool} - ไม่ได้รันอะไร; "
                f"ชื่อที่ใกล้เคียง: {', '.join(result['did_you_mean']) or '-'}\n\n")
    return f"🔧 ขั้นที่ {n}: {tool} ({args})\n> {_preview(result).replace(chr(10), ' ')}\n\n"


def _footer(result: Dict[str, Any]) -> str:
    route = result.get("route") or {}
    verify = result.get("intent_verification") or {}
    parts = [f"จบด้วย {result.get('stopped_reason')}", f"{result.get('iterations')} ขั้น"]
    if route.get("path"):
        parts.append(f"ROUTE: {route['path'].upper()}")
    if verify.get("applicable"):
        parts.append("VERIFY: ตรงเจตนา" if verify.get("aligned_with_intent")
                     else f"VERIFY: ไม่ผ่าน (similarity {verify.get('similarity_score')})")
    if result.get("approval_id"):
        parts.append(f"approval_id {result['approval_id']}")
    notary = result.get("notary") or {}
    if notary.get("enabled"):
        parts.append(f"notary {notary.get('receipts')} ใบรับ")
    return "\n\n---\n" + " · ".join(parts)


async def agent_events(
    goal: str,
    *,
    kernel: Any,
    mcp_server: Any = None,
    namespace: Optional[str] = None,
    max_iterations: int = 5,
    max_seconds: float = 600.0,
    loop_factory: Optional[Callable[..., Any]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.governed_autonomous_loop import fdia_score

    namespace = namespace or f"desk-agent-{uuid.uuid4().hex[:8]}"
    factory = loop_factory or build_governed_loop
    loop = factory(kernel, namespace, max_iterations=max_iterations, max_seconds=max_seconds,
                   mcp_server=mcp_server)

    queue: "asyncio.Queue[Optional[Dict[str, Any]]]" = asyncio.Queue()
    yield {"type": "token", "data": f"🛡️ Agent (governed) · namespace {namespace}\n\n"}

    async def _on_step(step: Any) -> None:
        text = format_step(step)
        if text:
            await queue.put({"type": "token", "data": text})

    async def _run() -> Dict[str, Any]:
        try:
            return dict(await loop.run(goal, on_step=_on_step))
        finally:
            await queue.put(None)

    task = asyncio.create_task(_run())
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event
    try:
        result = await task
    except Exception as exc:  # the model backend can time out on CPU
        yield {"type": "error", "data": f"agent episode failed: {exc}"}
        return

    answer = result.get("final_answer") or "(ไม่มีคำตอบสุดท้าย)"
    yield {"type": "token", "data": f"คำตอบ: {answer}{_footer(result)}"}

    D = getattr(loop, "_episode_D", None)
    I = getattr(loop, "_episode_I", None)
    blocked = result.get("stopped_reason") == "guard_blocked"
    jitna_hash = getattr(loop, "_episode_jitna_hash", "") or ""
    yield {"type": "fdia", "data": {
        "D": D if not blocked else 0.0, "I": I if not blocked else 0.0, "A": 0.0 if blocked else 1.0,
        "F": 0.0 if blocked or D is None or I is None else fdia_score(D, I, 1.0),
        "signed": bool(getattr(loop, "_episode_jitna_verified", False)) and not blocked,
        "signature_hash": f"JITNA-{jitna_hash[:16]}" if jitna_hash and not blocked else "",
    }}
    yield {"type": "done", "data": {"hexa_role": "AGENT", "trace_id": namespace,
                                    "stopped_reason": result.get("stopped_reason")}}

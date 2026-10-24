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
import os
import json
from typing import Any, AsyncGenerator, Callable, Dict, Optional, Literal

from pydantic import Field
from rct_control_plane.rct_plan import PlanItem


class ContractEvent(PlanItem):
    schema_version: Literal["1"]
    type: Literal["plan", "waiting_for_input", "receipt", "verdict"]
    event_id: str
    sequence: int = Field(ge=1)
    contract_id: str
    contract_version: int = Field(ge=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    data: dict[str, Any]


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


def step_payload(step: Any) -> Dict[str, Any]:
    """One loop step as a structured event for the redesigned Desk chat
    (Round 50): the model's reasoning ("thinking"), the tool call and what
    the governance layer did with it."""
    tool = getattr(step, "tool_name", None)
    result = getattr(step, "tool_result", None)
    kind = "finish" if not tool else "tool"
    extra: Dict[str, Any] = {}
    if isinstance(result, dict):
        if result.get("fdia_blocked"):
            kind, extra = "blocked", {"F": result.get("F"), "reason": result.get("reason"), "missing_data": list(result.get("missing_data") or [])}
        elif result.get("pending_approval"):
            kind, extra = "pending", {"reason": result.get("reason")}
        elif result.get("notary_unavailable"):
            kind, extra = "notary_down", {"reason": result.get("reason")}
        elif "did_you_mean" in result:
            kind, extra = "unknown_tool", {"did_you_mean": result.get("did_you_mean")}
    return {
        "iteration": getattr(step, "iteration", None),
        "kind": kind,
        "tool": tool,
        "args": getattr(step, "tool_args", {}) or {},
        "thinking": (getattr(step, "llm_reasoning", "") or "")[:600],
        "result": _preview(result, 1200) if (tool and kind == "tool") else None,
        **extra,
    }


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
    structured: bool = False,
    acceptance_criteria: Optional[list[dict[str, str]]] = None,
    planning_context: Any = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """structured=False: the original token/fdia/done events. structured=True
    (the redesigned Desk): start, step, answer, summary, fdia, done."""
    contract_requested = acceptance_criteria is not None or planning_context is not None
    if contract_requested and not structured:
        yield {"type": "error", "data": "contract planning requires structured=true"}
        return
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.governed_autonomous_loop import fdia_score

    # Round 51: one stable identity for the Desk user. A fresh namespace per
    # chat meant nothing learned in one chat (growth, skills, track record)
    # could ever help the next.
    namespace = namespace or os.environ.get("DELENTIA_DESK_NAMESPACE", "desk")
    factory = loop_factory or build_governed_loop
    loop = factory(kernel, namespace, max_iterations=max_iterations, max_seconds=max_seconds,
                   mcp_server=mcp_server)

    queue: "asyncio.Queue[Optional[Dict[str, Any]]]" = asyncio.Queue()
    if structured:
        yield {"type": "start", "data": {"namespace": namespace, "max_iterations": max_iterations}}
    else:
        yield {"type": "token", "data": f"🛡️ Agent (governed) · namespace {namespace}\n\n"}

    async def _on_step(step: Any) -> None:
        if structured:
            await queue.put({"type": "step", "data": step_payload(step)})
            return
        text = format_step(step)
        if text:
            await queue.put({"type": "token", "data": text})

    async def _on_plan(plan: Dict[str, Any]) -> None:
        """RCT-7 R6: the plan of an ordinary run, sent before the first tool runs (type rct7_plan, not the contract's `plan` envelope)."""
        if structured:
            await queue.put({"type": "rct7_plan", "data": {"goal": plan.get("goal"), "steps": plan.get("steps", []), "route": plan.get("route", {}), "conditions": plan.get("conditions", [])}})
            return
        steps = plan.get("steps") or []
        lines = [f"  {i}. {t}" for i, t in enumerate(steps, 1)]
        await queue.put({"type": "token", "data": "Plan before acting:\n" + "\n".join(lines) + "\n\n"})

    async def _run() -> Dict[str, Any]:
        try:
            if contract_requested:
                # No on_plan callback: return the persisted plan before any
                # execution. A later authorized REST confirmation is required.
                return dict(await loop.run(goal, on_step=_on_step,
                    acceptance_criteria=acceptance_criteria, planning_context=planning_context))
            # The plan callback goes only to a loop whose run() takes one (every real loop does; a minimal stand-in need not).
            import inspect
            try:
                takes_plan = "on_plan" in inspect.signature(loop.run).parameters
            except (TypeError, ValueError):
                takes_plan = False
            if takes_plan:
                return dict(await loop.run(goal, on_step=_on_step, on_plan=_on_plan))
            return dict(await loop.run(goal, on_step=_on_step))
        finally:
            await queue.put(None)

    task = asyncio.create_task(_run())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
        result = await task
    except Exception as exc:  # the model backend can time out on CPU
        yield {"type": "error", "data": f"agent episode failed: {exc}"}
        return
    finally:
        # Closing the stream must not leave a detached agent task. A tool
        # already executing in a worker thread still needs reconciliation.
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    if contract_requested:
        contract = result.get("intent_contract")
        if contract is not None:
            for event in contract_snapshot_events(contract, namespace):
                yield event
        yield {"type": "done", "data": {"hexa_role": "AGENT", "trace_id": namespace,
            "stopped_reason": result.get("stopped_reason"), "completed": False}}
        return

    D = getattr(loop, "_episode_D", None)
    I = getattr(loop, "_episode_I", None)
    blocked = result.get("stopped_reason") == "guard_blocked"
    jitna_hash = getattr(loop, "_episode_jitna_hash", "") or ""

    if structured:
        yield {"type": "answer", "data": {"text": result.get("final_answer")}}
        yield {"type": "summary", "data": {
            "namespace": namespace,
            "stopped_reason": result.get("stopped_reason"),
            "iterations": result.get("iterations"),
            "route": result.get("route") or {},
            "verification": result.get("intent_verification") or {},
            "guard": result.get("guard") or {},
            "notary": result.get("notary") or {},
            "approval_id": result.get("approval_id"),
            "rct7_steps": [] if blocked else list(getattr(loop, "_episode_rct7_steps", []) or []),
            "experiment": result.get("experiment"),
            "conditions_report": result.get("conditions_report") or [],
            "usage": result.get("cost") or {},
            "clarification_id": result.get("clarification_id"),
            "clarification_question": result.get("clarification_question"),
        }}
    else:
        answer = result.get("final_answer") or "(ไม่มีคำตอบสุดท้าย)"
        yield {"type": "token", "data": f"คำตอบ: {answer}{_footer(result)}"}
    yield {"type": "fdia", "data": {
        "D": D if not blocked else 0.0, "I": I if not blocked else 0.0, "A": 0.0 if blocked else 1.0,
        "F": 0.0 if blocked or D is None or I is None else fdia_score(D, I, 1.0),
        "signed": bool(getattr(loop, "_episode_jitna_verified", False)) and not blocked,
        "signature_hash": f"JITNA-{jitna_hash[:16]}" if jitna_hash and not blocked else "",
    }}
    yield {"type": "done", "data": {"hexa_role": "AGENT", "trace_id": namespace,
                                    "stopped_reason": result.get("stopped_reason")}}


def contract_snapshot_events(contract: dict, actor: str) -> list[dict]:
    """Versioned persisted snapshot events; not a live/durable event journal.

    Caller must authorize the contract for this actor before invoking. Stable
    IDs allow UI deduplication. Sequence is local to this snapshot, not global.
    """
    from rct_control_plane.verified_budget import validate_receipts
    receipts = contract.get("execution_receipts", [])
    if receipts:
        validate_receipts(contract["plan"], contract["id"], actor, receipts)
    executor = contract["plan"].get("semantic_planning", {}).get("executor")
    satisfied = contract["state"] == "criteria_satisfied"
    if executor == "verified_budget_v1":
        satisfied = (satisfied and contract.get("execution_status") == "complete"
                     and len(receipts) == len(contract["plan"]["components"]))
    events: list[dict] = []

    def emit(kind, data, suffix=None):
        events.append(ContractEvent.model_validate({"schema_version": "1", "type": kind,
            "event_id": f"{contract['id']}:{suffix or str(contract['version']) + ':' + kind}",
            "sequence": len(events) + 1, "contract_id": contract["id"],
            "contract_version": contract["version"], "plan_sha256": contract["plan_sha256"],
            "data": data}).model_dump())

    emit("plan", {"actor": actor, "state": contract["state"],
                  "plan": {k: v for k, v in contract["plan"].items() if k != "workspace"}})
    if contract["state"] in {"plan_ready", "waiting_for_input", "waiting_for_clarification"}:
        emit("waiting_for_input", {"reason": contract["state"],
             "questions": contract["plan"].get("clarification_questions", []),
             "differences": contract.get("differences", [])})
    for receipt in receipts:
        payload = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        emit("receipt", {**receipt, "recorded_ns": str(receipt["recorded_ns"]),
            "hashed_payload_json": json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                                separators=(",", ":"), allow_nan=False)},
             "receipt:" + receipt["receipt_sha256"])
    emit("verdict", {"state": contract["state"], "satisfied": satisfied,
        "method": "document_bytes_and_same_currency_arithmetic" if executor == "verified_budget_v1" else "declared_predicates",
        "differences": contract.get("differences", []),
        "execution_status": contract.get("execution_status", "not_started")})
    return events

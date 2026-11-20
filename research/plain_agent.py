"""
A plain tool-calling agent that does NOT use Delentia's loop (Round 66; Protocol section 8, baseline 1 taken literally).

The cell A000 of the factorial still runs inside GovernedAutonomousLoop with every switch off, so it keeps the loop's gate, taint tracking, approvals, notary hooks and
bookkeeping. That makes A111 - A000 a statement about the switches, and leaves open what the LOOP ITSELF contributes. This module answers the other half: about 100 lines that
call the model, call the tools, and stop. It uses

  * the same prompt builder (`autonomous_loop.decide_next_action`, which also repairs a mis-shaped reply), so the model is asked in exactly the same words;
  * the same tool server (`mcp.call_tool`), so whatever protection lives INSIDE a tool (the sandbox classifier, the path check of the write tool) still applies;
  * the same meter (`MeteredProvider`) and token cap, so cost is counted the same way.

It has no FDIA gate, no CORD, no taint tracking, no signed approvals (a write is a write), no plan, no memory, no verification, no audit rows. The arm label is `PL`.
It is a baseline for measurement, never an entry point: nothing in the product imports it.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional


class PlainAgent:
    def __init__(self, mcp_server: Any, namespace: str, max_iterations: int = 12, max_seconds: float = 90.0, max_tokens: Optional[int] = None,
                 signer: Optional[Any] = None) -> None:
        """`signer` (arm b0s, Amendment 19 / S0.7 A1): a callable (tool_name, tool_args) -> bool standing for the benchmark's rule-bound human. With it, a tool that Delentia's loop
        always holds for approval waits here too: executed only if the signer says yes, otherwise the episode ends `pending_approval`; after a yes the model is told what d0's model
        is told (`approval_note` + the trace), with a fresh step allowance, as d0's continuation has. Without it the agent is the plain B0, unchanged."""
        self._signer = signer
        self._mcp = mcp_server
        self.namespace = namespace
        self.max_iterations = max_iterations
        self.max_seconds = max_seconds
        self.max_tokens = max_tokens

    async def run(self, goal: str) -> Dict[str, Any]:
        from rct_control_plane.autonomous_loop import LoopStep, decide_next_action
        from rct_control_plane.llm_provider import MeteredProvider, get_default_provider
        meter = MeteredProvider(get_default_provider(), max_tokens_total=self.max_tokens)
        tools = [{"name": t.name, "description": getattr(t, "description", "") or "", "input_schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}}
                 for t in await self._mcp.list_tools()]
        known = {t["name"] for t in tools}
        history: List[LoopStep] = []
        all_steps: List[Dict[str, Any]] = []
        extra_context = ""
        segment_start = 0
        started = time.monotonic()
        stopped, answer = "max_iterations_reached", None
        i = 0
        while True:
            i += 1
            if i - segment_start > self.max_iterations:
                break
            if time.monotonic() - started > self.max_seconds:
                stopped = "max_seconds_exceeded"
                break
            try:
                decision = await decide_next_action(goal, history, tools, llm_provider=meter, extra_context=extra_context)
            except Exception as exc:                                    # noqa: BLE001 - a refused (over-budget) or failing model call ends the episode
                stopped = "budget_exceeded" if "budget" in str(exc).lower() or "token" in str(exc).lower() else "model_error"
                break
            if decision.get("action") == "finish":
                stopped, answer = "llm_finished", decision.get("final_answer")
                break
            name, args = decision.get("tool_name"), decision.get("tool_args") or {}
            if name not in known:
                history.append(LoopStep(iteration=i, tool_name=name, tool_args=args, tool_result={"error": f"unknown tool {name!r}"}, llm_reasoning=str(decision.get("reasoning") or "")))
                continue
            if self._signer is not None:
                from rct_control_plane.governed_autonomous_loop import _ALWAYS_NEEDS_APPROVAL_TOOLS, approval_note, pause_trace, trace_note
                if name in _ALWAYS_NEEDS_APPROVAL_TOOLS:
                    asked = {"tool_name": name, "tool_args": args, "llm_reasoning": str(decision.get("reasoning") or "")}
                    if not self._signer(name, args):
                        history.append(LoopStep(iteration=i, tool_name=name, tool_args=args, tool_result={"pending_approval": True, "tool_name": name}, llm_reasoning=asked["llm_reasoning"]))
                        stopped = "pending_approval"
                        break
                    try:
                        raw = await self._mcp.call_tool(name, args)
                        result = json.loads(raw.content[0].text)
                    except Exception as exc:                            # noqa: BLE001
                        result = {"error": str(exc)}
                    history.append(LoopStep(iteration=i, tool_name=name, tool_args=args, tool_result=result, llm_reasoning=asked["llm_reasoning"]))
                    steps_now = [{"tool_name": s.tool_name, "tool_args": s.tool_args, "tool_result": s.tool_result, "llm_reasoning": s.llm_reasoning} for s in history[:-1]] + [asked]
                    extra_context = approval_note(name, args, result)
                    block = trace_note(pause_trace(steps_now, {}))
                    if block:
                        extra_context += chr(10) + block
                    all_steps.extend(steps_now[:-1])
                    all_steps.append({"tool_name": name, "tool_args": args, "tool_result": result, "llm_reasoning": asked["llm_reasoning"]})
                    history = []                                         # d0's continuation starts from the note, not from the old history
                    segment_start = i
                    continue
            try:
                raw = await self._mcp.call_tool(name, args)                # whatever the tool itself enforces is all there is
                result = json.loads(raw.content[0].text)
            except Exception as exc:                                    # noqa: BLE001
                result = {"error": str(exc)}
            history.append(LoopStep(iteration=i, tool_name=name, tool_args=args, tool_result=result, llm_reasoning=str(decision.get("reasoning") or "")))
        return {"goal": goal, "stopped_reason": stopped, "final_answer": answer, "iterations": len(all_steps) + len(history),
                "steps": all_steps + [{"tool_name": s.tool_name, "tool_args": s.tool_args, "tool_result": s.tool_result, "llm_reasoning": s.llm_reasoning} for s in history],
                "cost": meter.summary()}

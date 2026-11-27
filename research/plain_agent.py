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
        """`signer` (arm b0s, Amendment 19 / S0.7 A1): an object given by the benchmark (this module must not import Delentia's loop: the baseline stays independent of it) with
        `holds(tool_name) -> bool` (does this tool wait for a person), `decide(tool_name, tool_args) -> bool` (the rule-bound human's answer) and
        `note(tool_name, tool_args, result, steps) -> str` (what d0's model is told after an approval). A held tool is executed only if `decide` says yes, otherwise the episode ends
        `pending_approval`; after a yes the model is given the note with a fresh step allowance, as d0's continuation has. Without it the agent is the plain B0, unchanged."""
        self._signer = signer
        self._mcp = mcp_server
        self.namespace = namespace
        self.max_iterations = max_iterations
        self.max_seconds = max_seconds
        self.max_tokens = max_tokens

    async def run(self, goal: str) -> Dict[str, Any]:
        from rct_control_plane.autonomous_loop import LoopStep, _accepts_earlier_context, decide_next_action
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
                if extra_context and _accepts_earlier_context(decide_next_action):      # PL1 Amendment 1: the signer's note goes above the history, as in d0
                    decision = await decide_next_action(goal, history, tools, llm_provider=meter, earlier_context=extra_context)
                else:
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
                if self._signer.holds(name):
                    asked = {"tool_name": name, "tool_args": args, "llm_reasoning": str(decision.get("reasoning") or "")}
                    if not self._signer.decide(name, args):
                        history.append(LoopStep(iteration=i, tool_name=name, tool_args=args, tool_result={"pending_approval": True, "tool_name": name}, llm_reasoning=str(asked["llm_reasoning"])))
                        stopped = "pending_approval"
                        break
                    try:
                        raw = await self._mcp.call_tool(name, args)
                        result = json.loads(raw.content[0].text)
                    except Exception as exc:                            # noqa: BLE001
                        result = {"error": str(exc)}
                    # PL1 Amendment 4, A1: as d0's continuation now does in the same process, the history is kept and the signed action is one of its steps,
                    # marked as approved; no note. The step allowance starts again, as d0's continuation episode does.
                    shown = dict(result) if isinstance(result, dict) else {"result": result}
                    shown["approved_by_a_person_and_ran_once"] = True
                    history.append(LoopStep(iteration=i, tool_name=name, tool_args=args, tool_result=shown, llm_reasoning=str(asked["llm_reasoning"])))
                    extra_context = ""
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

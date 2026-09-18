"""
Autonomous Reasoning Loop (Round 22 Phase 7) — a real decide->act->observe
cycle over the kernel's own MCP tool registry.

Reuses algo_09_reflexion_plus.py's already-proven real Ollama call
pattern (/api/generate, format="json") rather than inventing a new LLM
call convention here; Phase 10 (Task 22) later swaps this for the
pluggable LLMProvider abstraction without changing this module's loop
logic.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from rct_control_plane.persistence import ControlPlanePersistence

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b"


@dataclass
class LoopStep:
    iteration: int
    tool_name: Optional[str]
    tool_args: Dict[str, Any]
    tool_result: Optional[Dict[str, Any]]
    llm_reasoning: str
    timestamp: float = field(default_factory=time.time)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort real JSON extraction from an LLM response that may
    wrap the JSON in prose or markdown fences - a small local model
    does not always follow format="json" perfectly."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


async def decide_next_action(
    goal: str,
    history: List[LoopStep],
    available_tools: List[Dict[str, Any]],
    llm_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    tools_desc = "\n".join(
        f"- {t['name']}: {t['description']} (args schema: {t.get('input_schema', {})})"
        for t in available_tools
    )
    history_desc = "\n".join(
        f"Iteration {s.iteration}: called {s.tool_name}({s.tool_args}) -> {s.tool_result}"
        for s in history
    ) or "(no actions taken yet)"

    prompt = f"""You are an autonomous agent working toward this goal:
{goal}

Available tools:
{tools_desc}

History so far:
{history_desc}

Decide the SINGLE next action. Respond with ONLY a JSON object, no other text:
{{"action": "call_tool", "tool_name": "<one of the tool names above>", "tool_args": {{...matching its schema...}}, "reasoning": "<why>"}}
OR, if the goal is already achieved or no tool call is needed:
{{"action": "finish", "reasoning": "<why>", "final_answer": "<your answer to the goal>"}}
"""

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            f"{llm_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "format": "json",
                  "options": {"temperature": 0.3}},
        )
        response.raise_for_status()
        raw_text = response.json()["response"]

    decision = _extract_json(raw_text)
    if decision is None or "action" not in decision:
        return {"action": "finish", "reasoning": "parse_error", "final_answer": raw_text,
                "tool_name": None, "tool_args": {}, "parse_error": True}

    decision.setdefault("tool_name", None)
    decision.setdefault("tool_args", {})
    decision.setdefault("final_answer", None)
    decision.setdefault("reasoning", "")
    return decision


class AutonomousLoop:
    """Real decide->act->observe loop over the kernel's MCP tool
    registry. Only has access to whatever tools `mcp_server` exposes -
    Round 21's already safety-reviewed 3 tools as of this writing. See
    the Round 22 plan's Context for the safety scoping rationale."""

    def __init__(self, mcp_server, persistence: ControlPlanePersistence,
                 max_iterations: int = 5, max_seconds: float = 120.0,
                 namespace: str = "kernel_default"):
        self._mcp = mcp_server
        self._persistence = persistence
        self.max_iterations = max_iterations
        self.max_seconds = max_seconds
        self.namespace = namespace

    async def _available_tools(self) -> list:
        tools = await self._mcp.list_tools()
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]

    async def run(self, goal: str) -> dict:
        t_start = time.time()
        available_tools = await self._available_tools()
        history: list = []
        stopped_reason = "max_iterations_reached"
        final_answer = None

        for i in range(1, self.max_iterations + 1):
            if time.time() - t_start > self.max_seconds:
                stopped_reason = "max_seconds_exceeded"
                break

            decision = await decide_next_action(goal, history, available_tools)

            if decision.get("parse_error"):
                stopped_reason = "parse_error"
                final_answer = decision.get("final_answer")
                step = LoopStep(iteration=i, tool_name=None, tool_args={},
                                 tool_result=None, llm_reasoning=decision["reasoning"])
                history.append(step)
                self._persist_step(step)
                break

            if decision["action"] == "finish":
                stopped_reason = "llm_finished"
                final_answer = decision.get("final_answer")
                step = LoopStep(iteration=i, tool_name=None, tool_args={},
                                 tool_result=None, llm_reasoning=decision["reasoning"])
                history.append(step)
                self._persist_step(step)
                break

            tool_name = decision["tool_name"]
            tool_args = decision.get("tool_args") or {}
            try:
                raw_result = await self._mcp.call_tool(tool_name, tool_args)
                tool_result = json.loads(raw_result.content[0].text)
            except Exception as e:
                tool_result = {"error": str(e)}

            step = LoopStep(iteration=i, tool_name=tool_name, tool_args=tool_args,
                             tool_result=tool_result, llm_reasoning=decision["reasoning"])
            history.append(step)
            self._persist_step(step)

        return {
            "goal": goal,
            "steps": [vars(s) for s in history],
            "final_answer": final_answer,
            "iterations": len(history),
            "stopped_reason": stopped_reason,
        }

    def _persist_step(self, step: LoopStep) -> None:
        self._persistence.append_audit(
            entity_type="autonomous_loop_step",
            entity_id=f"{self.namespace}-{step.iteration}",
            action="loop_step",
            actor=self.namespace,
            changes={"tool_name": step.tool_name, "tool_args": step.tool_args,
                     "reasoning": step.llm_reasoning[:500]},
        )

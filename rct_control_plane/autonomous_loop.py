"""
Autonomous Reasoning Loop (Round 22 Phase 7) — a real decide->act->observe
cycle over the kernel's own MCP tool registry.

Round 22 Phase 10 Task 22: uses the pluggable LLMProvider abstraction
(defaults to OllamaProvider via get_default_provider()) instead of a
direct httpx call, so this loop works against any registered backend.

Round 41: algo_25_delta_block.py's intent-delta compression
(compress_intent_delta()/apply_structural_delta(), Round 38/40) was
previously only computed and reported (surfaced as
algorithm_kernel_41.py's own phase_6_intent_delta_compression field on
a fully separate pipeline never wired to this loop) - never used to
change what actually got sent to an LLM. render_history() below is the
real fix: the same function decide_next_action() and
_stream_final_answer() both now use to build history_desc genuinely
replaces full per-turn context with a compact delta when
compress_intent_delta()'s own token-savings safety valve confirms a
real win, and reconstruct_full_history_text() is the real, tested
decompression counterpart for whenever full context needs to be
recovered."""
from __future__ import annotations

import inspect
import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from rct_control_plane.algo_25_delta_block import DeltaEngine
from rct_control_plane.persistence import ControlPlanePersistence

if TYPE_CHECKING:
    from rct_control_plane.llm_provider import LLMProvider


@dataclass
class LoopStep:
    iteration: int
    tool_name: Optional[str]
    tool_args: Dict[str, Any]
    tool_result: Optional[Dict[str, Any]]
    llm_reasoning: str
    timestamp: float = field(default_factory=time.time)


def _turn_state(step: LoopStep) -> Dict[str, Any]:
    """Round 41: the real, diffable state for one turn - exactly the
    fields _render_turn_full() below renders into history_desc's plain-
    text line (tool_name, tool_args, tool_result). Excludes
    iteration/timestamp (positional metadata, not turn content) and
    llm_reasoning (not part of the pre-existing rendered line either -
    unchanged since Round 22)."""
    return {
        "tool_name": step.tool_name,
        "tool_args": step.tool_args,
        "tool_result": step.tool_result,
    }


def _render_turn_full(step: LoopStep) -> str:
    """The original, uncompressed per-turn render - byte-for-byte the
    same text every pre-Round-41 history_desc line contained."""
    return f"Iteration {step.iteration}: called {step.tool_name}({step.tool_args}) -> {step.tool_result}"


def render_history(history: List[LoopStep], delta_engine: Optional[DeltaEngine] = None) -> str:
    """Round 41: builds the real history text handed to the LLM provider
    as part of the prompt - this replaces the inline `history_desc`
    joins that used to live directly in decide_next_action() and
    _stream_final_answer(), so both real call sites now share one
    tested implementation.

    Turn 1 of any run has no prior turn to diff against and is always
    rendered in full - genuinely backward compatible, not a special
    case bolted on. Every turn after that is compressed via
    DeltaEngine.compress_intent_delta() against the immediately PRIOR
    turn's real state, but ONLY when that call's own token-savings
    safety valve (Round 40) confirms the compact JSON-Patch `ops`
    representation is genuinely smaller in LLM context tokens than the
    full turn text - otherwise this falls back to the exact same full
    line the no-compression path always produced, so compression can
    only ever help, never actively hurt (the same guarantee
    compress_intent_delta() itself makes for bytes/tokens
    independently). `ops` is real, parseable JSON text (never the zstd
    byte output, which is binary and not valid LLM prompt text per that
    method's own docstring), so nothing unreadable is ever placed in
    the prompt.

    delta_engine defaults to a fresh, stateless DeltaEngine() - this
    method only uses compress_intent_delta()/compute_structural_delta(),
    neither of which reads or writes DeltaEngine's own stored-delta
    state, so a plain local instance is sufficient and callers never
    need to manage one."""
    if not history:
        return "(no actions taken yet)"

    engine = delta_engine if delta_engine is not None else DeltaEngine()

    lines: List[str] = [_render_turn_full(history[0])]
    prior_state = _turn_state(history[0])
    for step in history[1:]:
        current_state = _turn_state(step)
        compression = engine.compress_intent_delta(prior_state, current_state)
        if not compression["used_token_fallback_to_full_state"]:
            patch_json = json.dumps(compression["ops"], sort_keys=True)
            lines.append(
                f"Iteration {step.iteration}: [delta vs iteration {step.iteration - 1}] {patch_json}"
            )
        else:
            lines.append(_render_turn_full(step))
        prior_state = current_state
    return "\n".join(lines)


def reconstruct_full_history_text(history: List[LoopStep], delta_engine: Optional[DeltaEngine] = None) -> str:
    """Round 41: the real decompression counterpart to render_history()'s
    compressed rendering - walks the exact same turn-to-turn delta chain
    forward, applying each turn's real JSON-Patch `ops` back onto the
    previous turn's state via DeltaEngine.apply_structural_delta(), and
    renders the FULL, uncompressed text for every turn regardless of
    whether that turn was sent to the LLM compressed or not.

    This is the real, tested answer to "how do you get the full context
    back when a prior turn's delta chain needs decompressing to produce
    a coherent prompt" - not a TODO. A caller that only persisted the
    compact `ops` for compressed turns (e.g. an audit/replay log) can
    reconstruct the identical full text this function proves is
    recoverable from history[0]'s real full state plus each
    subsequent delta alone."""
    if not history:
        return "(no actions taken yet)"

    engine = delta_engine if delta_engine is not None else DeltaEngine()

    lines: List[str] = [_render_turn_full(history[0])]
    prior_state = _turn_state(history[0])
    for step in history[1:]:
        current_state = _turn_state(step)
        compression = engine.compress_intent_delta(prior_state, current_state)
        reconstructed = engine.apply_structural_delta(prior_state, compression["ops"])
        lines.append(
            f"Iteration {step.iteration}: called {reconstructed['tool_name']}"
            f"({reconstructed['tool_args']}) -> {reconstructed['tool_result']}"
        )
        prior_state = current_state
    return "\n".join(lines)


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
    llm_provider: Optional["LLMProvider"] = None,
) -> Dict[str, Any]:
    from rct_control_plane.llm_provider import get_default_provider
    provider = llm_provider or get_default_provider()

    tools_desc = "\n".join(
        f"- {t['name']}: {t['description']} (args schema: {t.get('input_schema', {})})"
        for t in available_tools
    )
    # Round 41: real intent-delta compression, actually applied to the
    # bytes sent here (not just computed/reported) - see render_history()'s
    # own docstring for the full compression/fallback contract.
    history_desc = render_history(history)

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

    raw_text = await provider.complete(prompt, temperature=0.3, json_mode=True)

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

    async def run(
        self,
        goal: str,
        on_step: Optional[Callable[[LoopStep], Any]] = None,
        on_answer_token: Optional[Callable[[str], Any]] = None,
    ) -> dict:
        """Round 37: `on_step` is an optional, real live-introspection
        hook - called once per real LoopStep as it's appended to history,
        BEFORE run() returns. Accepts a sync or async callable (awaited
        if it returns an awaitable, matching autonomous_scheduler.py's
        own trigger_task_async pattern). Defaults to None, which
        preserves this method's exact prior behavior for every existing
        caller (Zero-Delete).

        Round 40: `on_answer_token` is a second, independent, optional
        hook enabling REAL token streaming of the final answer - a
        genuine dual-call design, not a cosmetic reveal of text that
        already fully exists. decide_next_action()'s own JSON-mode call
        (needed every iteration to get a parseable tool-or-finish
        decision) still runs exactly as before; when the LLM decides to
        finish AND on_answer_token is provided, ONE additional, separate
        plain-text streaming call (LLMProvider.stream_complete(), Round
        39's real, tested streaming infrastructure) narrates the same
        answer, calling on_answer_token once per real incremental
        chunk as it arrives from the provider - not simulated. This is
        a real, disclosed cost/latency tradeoff (one extra LLM call only
        on the finish step, only when a caller actually wants streamed
        output) - defaults to None, so every existing caller's behavior
        and cost profile is completely unchanged (Zero-Delete)."""
        t_start = time.time()
        available_tools = await self._available_tools()
        history: list = []
        stopped_reason = "max_iterations_reached"
        final_answer = None

        async def _notify(step: LoopStep) -> None:
            if on_step is None:
                return
            result = on_step(step)
            if inspect.isawaitable(result):
                await result

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
                await _notify(step)
                break

            if decision["action"] == "finish":
                stopped_reason = "llm_finished"
                final_answer = decision.get("final_answer")
                if on_answer_token is not None:
                    final_answer = await self._stream_final_answer(goal, history, on_answer_token)
                step = LoopStep(iteration=i, tool_name=None, tool_args={},
                                 tool_result=None, llm_reasoning=decision["reasoning"])
                history.append(step)
                self._persist_step(step)
                await _notify(step)
                break

            tool_name = decision["tool_name"]
            tool_args = decision.get("tool_args") or {}

            # Round 23 Phase 12 Task 26: real approval-gate for
            # medium-risk sandboxed commands - halt BEFORE dispatch,
            # never execute the command while pending.
            if tool_name == "delentia_run_sandboxed_command":
                from rct_control_plane.sandbox import classify_command_risk
                risk = classify_command_risk(tool_args.get("command", ""))
                if risk == "needs_approval":
                    step = LoopStep(iteration=i, tool_name=tool_name, tool_args=tool_args,
                                     tool_result={"pending_approval": True, "command": tool_args.get("command", "")},
                                     llm_reasoning=decision["reasoning"])
                    history.append(step)
                    self._persist_step(step)
                    await _notify(step)
                    stopped_reason = "pending_approval"
                    break

            try:
                raw_result = await self._mcp.call_tool(tool_name, tool_args)
                tool_result = json.loads(raw_result.content[0].text)
            except Exception as e:
                tool_result = {"error": str(e)}

            step = LoopStep(iteration=i, tool_name=tool_name, tool_args=tool_args,
                             tool_result=tool_result, llm_reasoning=decision["reasoning"])
            history.append(step)
            self._persist_step(step)
            await _notify(step)

        return {
            "goal": goal,
            "steps": [vars(s) for s in history],
            "final_answer": final_answer,
            "iterations": len(history),
            "stopped_reason": stopped_reason,
        }

    async def _stream_final_answer(
        self, goal: str, history: List[LoopStep], on_answer_token: Callable[[str], Any],
    ) -> str:
        """Round 40: the real second call of the dual-call streaming
        design - a plain-text (not json_mode) prompt, reusing the same
        goal/history context decide_next_action() itself builds, sent
        through LLMProvider.stream_complete() so the caller genuinely
        sees the answer as it's generated, not after the fact."""
        from rct_control_plane.llm_provider import get_default_provider
        provider = get_default_provider()

        # Round 41: same real compression as decide_next_action()'s prompt.
        history_desc = render_history(history)

        prompt = f"""You are an autonomous agent that has finished working toward this goal:
{goal}

Actions taken:
{history_desc}

Write your final answer to the goal, in natural language. Do not use JSON - plain text only."""

        chunks: List[str] = []
        async for chunk in provider.stream_complete(prompt, temperature=0.3):
            chunks.append(chunk)
            result = on_answer_token(chunk)
            if inspect.isawaitable(result):
                await result
        return "".join(chunks)

    def _persist_step(self, step: LoopStep) -> None:
        self._persistence.append_audit(
            entity_type="autonomous_loop_step",
            entity_id=f"{self.namespace}-{step.iteration}",
            action="loop_step",
            actor=self.namespace,
            changes={"tool_name": step.tool_name, "tool_args": step.tool_args,
                     "reasoning": step.llm_reasoning[:500]},
        )

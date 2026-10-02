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

import asyncio
import inspect
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

from rct_control_plane.algo_25_delta_block import DeltaEngine
from rct_control_plane.llm_provider import BudgetExceededError, ResidencyViolation
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.safe_text import json_object_span

# Round 52: a model that is briefly unavailable (overloaded, rate limited, a dropped
# connection) is retried; one that stays down ends the episode with
# stopped_reason "llm_error" instead of raising out of run() into whatever called it
# (an API request, a chat gateway, the daemon).
LLM_RETRIES_ENV = "DELENTIA_LLM_RETRIES"
LLM_RETRY_BACKOFF_ENV = "DELENTIA_LLM_RETRY_BACKOFF"
_TRANSIENT_HTTP_STATUS = (408, 409, 425, 429, 500, 502, 503, 504)


def _is_transient_llm_error(exc: BaseException) -> bool:
    try:
        import httpx
    except ImportError:     # pragma: no cover
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _TRANSIENT_HTTP_STATUS
    return isinstance(exc, (httpx.TransportError, asyncio.TimeoutError, ConnectionError))


def _describe_llm_error(exc: BaseException) -> str:
    """One line for the step record; never includes request bodies or headers (the prompt
    and the API key must not end up in the audit trail through an error message)."""
    try:
        import httpx
        if isinstance(exc, httpx.HTTPStatusError):
            return f"model endpoint answered HTTP {exc.response.status_code}"
    except ImportError:     # pragma: no cover
        pass
    return f"{type(exc).__name__}: {str(exc)[:200]}"

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
    span = json_object_span(text)
    if span is not None:
        try:
            return json.loads(span)
        except json.JSONDecodeError:
            return None
    return None


def unknown_tool_result(tool_name: Any, known_names: List[str], limit: int = 3) -> Dict[str, Any]:
    """The tool result for a tool name that does not exist: nothing is run,
    and the closest real names are offered (spelling similarity first, then
    shared name parts such as read/file/repo)."""
    import difflib
    name = str(tool_name or "")
    close = difflib.get_close_matches(name, known_names, n=limit, cutoff=0.5)
    if len(close) < limit:
        parts = {p for p in re.split(r"[_\W]+", name.lower()) if p and p != "delentia"}
        by_overlap = sorted(
            (n for n in known_names if n not in close),
            key=lambda n: -len(parts & set(n.lower().split("_"))),
        )
        close += [n for n in by_overlap if parts & set(n.lower().split("_"))][: limit - len(close)]
    return {
        "error": f"Unknown tool: {name!r}. Nothing was run.",
        "did_you_mean": close,
        "hint": "Use one of the exact tool names from the tool list" + (f", for example {close[0]}." if close else "."),
    }


def _detect_repeated_call(history: List[LoopStep]) -> str:
    """Round 44 item J.1.4(c): real, evidence-based fix for a confirmed
    failure mode - J.4.2's real Ollama integration testing (qwen2.5:7b)
    hit this on 5/5 runs of the simplest possible safe task: the model
    correctly chose the right tool and got a real, sufficient result, then
    re-issued the EXACT SAME tool call again instead of recognizing the
    goal was already answered, repeating until max_iterations_reached.
    This is a completion-recognition failure, not a tool-selection
    failure (tool_name/tool_args were correct every single time) - so
    J.1.4(a)'s existing keyword-overlap pre-filtering (which narrows WHICH
    tool to pick) does not address it, and neither would a generic "be
    more directive" prompt tweak. This targets the exact observed
    mechanism: when the most recent step used the identical
    (tool_name, tool_args) as an earlier step in the same episode, name
    that specific repeated call and its real prior result directly in the
    prompt, and instruct the model explicitly not to repeat it. Returns
    "" when no repeat is detected, so this is a no-op for every episode
    that doesn't hit the failure mode (the common case)."""
    if not history:
        return ""
    last = history[-1]
    if last.tool_name is None:
        return ""
    for prior in history[:-1]:
        if prior.tool_name == last.tool_name and prior.tool_args == last.tool_args:
            return (
                f"IMPORTANT: You already called {last.tool_name}({last.tool_args}) and "
                f"received this result: {last.tool_result}. Calling it again with the same "
                f"arguments will not produce new information. If this result already answers "
                f"the goal, respond with action: finish now, using this result as your answer. "
                f"Do not call {last.tool_name} with these exact arguments again."
            )
    return ""


# Round 44 (item K.1.1): see decide_next_action()'s docstring for the
# real scenario-battery findings this text exists to address. Kept as a
# module-level constant (not a function) since it is genuinely fixed
# text, unlike _detect_repeated_call()'s history-dependent output.
#
# Point 4 was added after a live re-test of the original 3-point version
# (2026-09-25) found it did NOT stop the model from fabricating a curl
# command to a made-up pizza-ordering URL for a goal no real tool could
# address (3/3 re-test runs still did this). Root cause: a shell-command
# tool is broadly "relevant" by construction (it can run any command),
# so point 3's "if no tool is relevant, finish honestly" never actually
# triggered from the model's perspective - the failure was narrower than
# first diagnosed. Point 4 targets the real, specific pattern instead:
# fabricating a URL/endpoint never given in the goal or found via a real
# tool result - the same "never guess a URL" principle this project's
# own operator harness already enforces on itself.
_SCOPE_AND_GROUNDING_GUIDANCE = (
    "Before deciding, check all of these:\n"
    "1. If a tool above is directly relevant to this goal and using it would give a "
    "grounded, verified answer instead of a guess, use it - never answer from a guess "
    "when a listed tool could give you the real answer.\n"
    "2. Only call a tool that is directly necessary for THIS goal - never call an "
    "unrelated tool just in case it might help.\n"
    "3. If NONE of the tools above are actually relevant to this goal, avoid forcing "
    "an unrelated or made-up tool call to work around that. Finish honestly instead, "
    "explaining plainly that this goal is outside what these tools can do.\n"
    "4. NEVER invent or guess a URL, API endpoint, or external address that was not "
    "explicitly given in the goal or returned by a real tool result above - not even "
    "a plausible-looking one. A shell-command tool being available does not make up "
    "for a real endpoint you do not actually have; if completing the goal would "
    "require one you don't have, finish honestly and say so instead of guessing one."
)


def _batch_guidance() -> str:
    """Round 54: the model is told about batches only when the operator enabled them (DELENTIA_PARALLEL_TOOLS=1), so
    an unchanged server sends an unchanged prompt."""
    from rct_control_plane import dag_executor
    if not dag_executor.enabled():
        return ""
    return (
        "OR, when several actions do not depend on each other, ask for them together (at most "
        f"{dag_executor.MAX_CALLS}; they run at the same time, and every one is checked before any runs):\n"
        '{"action": "call_tools", "calls": [{"id": "a", "tool_name": "<tool>", "tool_args": {...}}, '
        '{"id": "b", "tool_name": "<tool>", "tool_args": {...}, "depends_on": ["a"]}], "reasoning": "<why>"}\n'
        "depends_on only orders calls (b waits for a); it does not hand a's result to b.\n"
    )


async def decide_next_action(
    goal: str,
    history: List[LoopStep],
    available_tools: List[Dict[str, Any]],
    llm_provider: Optional["LLMProvider"] = None,
    extra_context: str = "",
) -> Dict[str, Any]:
    """Round 44 (item I.2): `extra_context`, when non-empty, is inserted as
    its own section of the prompt below - added so GovernedAutonomousLoop
    can inject real retrieved-skill text (rct_control_plane.skill_library's
    retrieve_similar_skills()) without this function needing to know
    anything about skills specifically. Defaults to "" (omitted from the
    prompt entirely), so a caller supplying no extra_context sees an
    unchanged prompt in that respect.

    Round 44 (item J.1.4c): a second, always-on context section -
    _detect_repeated_call() - is computed unconditionally from `history`
    (not opt-in like extra_context) and prepended when non-empty, since
    the failure mode it targets is a real, confirmed core-loop reliability
    bug (see that function's own docstring), not an optional feature.

    Round 44 (item K.1.1, 2026-09-25): a third, always-on, fixed
    instruction block - _SCOPE_AND_GROUNDING_GUIDANCE below - added after
    J.4.6's real scenario battery (scripts/real_agent_scenario_battery.py)
    found 3 distinct real failure modes this prompt gave the model no
    guidance against: (1) answering from a guess ("The answer is 42")
    for a goal a listed tool could directly answer, instead of using it;
    (2) calling a tool structurally unrelated to the goal (e.g.
    delentia_create_worktree for a goal about searching code) rather
    than staying scoped to what the goal actually needs; (3) for a goal
    no listed tool can address at all, fabricating a plausible-looking
    but bogus tool call (a curl to a made-up URL) instead of finishing
    with an honest refusal. Unlike _detect_repeated_call, this text does
    not depend on `history` - it is constant across every call, so it is
    injected directly into the prompt template rather than through
    context_parts."""
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

    context_parts = [p for p in (_detect_repeated_call(history), extra_context) if p]
    context_section = ("\n" + "\n\n".join(context_parts) + "\n") if context_parts else ""

    prompt = f"""You are an autonomous agent working toward this goal:
{goal}

Available tools:
{tools_desc}

History so far:
{history_desc}
{context_section}
{_SCOPE_AND_GROUNDING_GUIDANCE}
Decide the SINGLE next action. Respond with ONLY a JSON object, no other text:
{{"action": "call_tool", "tool_name": "<one of the tool names above>", "tool_args": {{...matching its schema...}}, "reasoning": "<why>"}}
OR, if the goal is already achieved or no tool call is needed:
{{"action": "finish", "reasoning": "<why>", "final_answer": "<your answer to the goal>"}}
{_batch_guidance()}"""

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
                 namespace: str = "kernel_default",
                 llm_provider: Optional["LLMProvider"] = None):
        self._mcp = mcp_server
        self._persistence = persistence
        self.max_iterations = max_iterations
        self.max_seconds = max_seconds
        self.namespace = namespace
        # Round 48: optional per-loop provider (e.g. from
        # get_default_provider(profile=...)), so different profiles/
        # gateways can run different user-selected models. None keeps the
        # pre-Round-48 behaviour: resolve the default provider per call.
        self._llm_provider = llm_provider

    async def _available_tools(self) -> list:
        tools = await self._mcp.list_tools()
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]

    async def run(
        self,
        goal: str,
        on_step: Optional[Callable[[LoopStep], Any]] = None,
        on_answer_token: Optional[Callable[[str], Any]] = None,
        on_episode_start: Optional[Callable[[str], Any]] = None,
        tool_filter: Optional[Callable[[str, List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
        pre_dispatch_gate: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
        on_episode_end: Optional[Callable[[dict], Any]] = None,
        extra_context_provider: Optional[Callable[[], str]] = None,
        post_dispatch_transform: Optional[Callable[[str, str, Dict[str, Any], Any], Any]] = None,
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
        and cost profile is completely unchanged (Zero-Delete).

        Round 44 (item J): four more optional hooks, added the same way
        as on_step/on_answer_token above - every one defaults to None
        and changes NOTHING for an existing caller. These exist so
        GovernedAutonomousLoop (governed_autonomous_loop.py) can layer
        real constitutional governance (FDIA/JITNA/RCT-7/Delta) on top
        of this exact loop body instead of duplicating it in a
        subclass override, which would drift from this method over
        time. Each accepts a sync or async callable (same
        awaited-if-awaitable pattern as on_step):
          - on_episode_start(goal): called once, before the first
            iteration. Returning a dict with "stopped_reason" (and
            optionally "final_answer") ends the episode there, with no
            model call and no tool call.
          - tool_filter(goal, available_tools) -> filtered_tools: called
            every iteration, right before decide_next_action() - lets a
            caller narrow the tool menu instead of always exposing the
            full registry.
          - pre_dispatch_gate(goal, tool_name, tool_args) -> Optional[dict]:
            called right before a tool is actually dispatched (after the
            existing pending_approval check above, which is unchanged).
            Returning None means proceed as normal; returning a dict
            means "block this call" and that dict MUST contain
            "stopped_reason" (str) and "tool_result" (dict) - the loop
            stops immediately with those values, the same way
            pending_approval already does.
          - on_episode_end(result): called once with the exact dict this
            method is about to return, right before returning it.

        A fifth hook, extra_context_provider() -> str, is threaded straight
        into decide_next_action()'s own new extra_context parameter (see
        that function's docstring) every iteration - kept separate from
        the four above since it's not "governance" per se, just optional
        prompt content. Defaults to None, meaning no extra_context text is
        ever added (Zero-Delete).
        """
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

        async def _maybe_await(value: Any) -> Any:
            if inspect.isawaitable(value):
                return await value
            return value

        guard_stopped = False
        if on_episode_start is not None:
            # Round 50 GUARD: on_episode_start may end the episode before the
            # first model call by returning {"stopped_reason": ...}.
            start_verdict = await _maybe_await(on_episode_start(goal))
            if isinstance(start_verdict, dict) and start_verdict.get("stopped_reason"):
                stopped_reason = start_verdict["stopped_reason"]
                final_answer = start_verdict.get("final_answer")
                guard_stopped = True
        # Read after on_episode_start: ROUTE may lower the step budget there.
        iterations_allowed = 0 if guard_stopped else self.max_iterations

        for i in range(1, iterations_allowed + 1):
            if time.time() - t_start > self.max_seconds:
                stopped_reason = "max_seconds_exceeded"
                break

            iteration_tools = available_tools
            if tool_filter is not None:
                iteration_tools = tool_filter(goal, available_tools)

            extra_context = extra_context_provider() if extra_context_provider is not None else ""
            # Only pass extra_context as a kwarg when non-empty, so the
            # call reverts to decide_next_action's exact original 3-arg
            # shape whenever no real context exists - real callers/tests
            # that monkeypatch decide_next_action with the pre-Round-44
            # signature (goal, history, available_tools, llm_provider)
            # keep working unchanged (Zero-Delete), since none of them
            # ever populate extra_context_provider.
            # Explicit if/else rather than **kwargs unpacking - mypy cannot
            # verify a plain dict[str, str] unpacks into the right keyword
            # slot, and flags it as a positional-argument type mismatch
            # against decide_next_action's real 4th parameter
            # (llm_provider). Both branches are real, direct calls against
            # the real signature.
            # Round 50: a provider-wide budget (MeteredProvider) refuses a
            # call before it is made; the episode then ends cleanly with
            # stopped_reason "budget_exceeded" instead of raising.
            async def _decide() -> Dict[str, Any]:
                if self._llm_provider is not None and extra_context:
                    return await decide_next_action(goal, history, iteration_tools, self._llm_provider,
                                                    extra_context=extra_context)
                if self._llm_provider is not None:
                    return await decide_next_action(goal, history, iteration_tools, self._llm_provider)
                if extra_context:
                    return await decide_next_action(goal, history, iteration_tools, extra_context=extra_context)
                return await decide_next_action(goal, history, iteration_tools)

            try:
                retries = max(0, int(os.environ.get(LLM_RETRIES_ENV, "2")))
                backoff = max(0.0, float(os.environ.get(LLM_RETRY_BACKOFF_ENV, "1.0")))
                attempt = 0
                while True:
                    try:
                        decision = await _decide()
                        break
                    except (BudgetExceededError, ResidencyViolation):
                        raise
                    except Exception as exc:    # noqa: BLE001 - any provider failure ends the episode, not the caller
                        if attempt < retries and _is_transient_llm_error(exc):
                            attempt += 1
                            await asyncio.sleep(backoff * attempt)
                            continue
                        llm_error = _describe_llm_error(exc)
                        stopped_reason = "llm_error"
                        step = LoopStep(iteration=i, tool_name=None, tool_args={}, tool_result={"llm_error": llm_error},
                                        llm_reasoning=f"the model could not be reached: {llm_error} (after {attempt + 1} attempt(s))")
                        history.append(step)
                        self._persist_step(step)
                        await _notify(step)
                        decision = None
                        break
                if decision is None:
                    break
            except (BudgetExceededError, ResidencyViolation) as exc:
                # Round 52: a residency block ends the episode the same way a budget
                # refusal does: before the call, so nothing was sent.
                residency = isinstance(exc, ResidencyViolation)
                stopped_reason = "residency_blocked" if residency else "budget_exceeded"
                step = LoopStep(iteration=i, tool_name=None, tool_args={},
                                 tool_result={("residency_blocked" if residency else "budget_exceeded"): str(exc)},
                                 llm_reasoning=f"{'residency blocked' if residency else 'budget exceeded'}: {exc}")
                history.append(step)
                self._persist_step(step)
                await _notify(step)
                break

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
                    try:
                        final_answer = await self._stream_final_answer(goal, history, on_answer_token)
                    except (BudgetExceededError, ResidencyViolation):
                        pass  # keep the answer from the decision call rather than spend past the budget
                step = LoopStep(iteration=i, tool_name=None, tool_args={},
                                 tool_result=None, llm_reasoning=decision["reasoning"])
                history.append(step)
                self._persist_step(step)
                await _notify(step)
                break

            if decision["action"] == "call_tools":
                batch_stop = await self._run_tool_batch(i, goal, decision, history, available_tools, pre_dispatch_gate,
                                                        post_dispatch_transform, _notify, _maybe_await)
                if batch_stop:
                    stopped_reason = batch_stop
                    break
                continue

            tool_name = decision["tool_name"]
            # Scoped before the governance gate, so the gate, the notary and the step record all
            # see the arguments that will actually run.
            tool_args = self._scope_tool_args(tool_name, decision.get("tool_args") or {})

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

            if pre_dispatch_gate is not None:
                gate_result = await _maybe_await(pre_dispatch_gate(goal, tool_name, tool_args))
                if gate_result is not None:
                    step = LoopStep(iteration=i, tool_name=tool_name, tool_args=tool_args,
                                     tool_result=gate_result["tool_result"], llm_reasoning=decision["reasoning"])
                    history.append(step)
                    self._persist_step(step)
                    await _notify(step)
                    stopped_reason = gate_result["stopped_reason"]
                    break

            # After the governance gate (which judges every attempted call):
            # Round 50: small models invent tool names (a real qwen2.5:7b run
            # asked for delentia_read_file instead of delentia_read_repo_file,
            # got "Unknown tool" and gave up). Nothing is dispatched; the model
            # is told the closest real names so the next step can recover.
            known_names = [t["name"] for t in available_tools]
            if tool_name not in known_names:
                step = LoopStep(iteration=i, tool_name=tool_name, tool_args=tool_args,
                                 tool_result=unknown_tool_result(tool_name, known_names),
                                 llm_reasoning=decision["reasoning"])
                history.append(step)
                self._persist_step(step)
                await _notify(step)
                continue

            try:
                raw_result = await self._mcp.call_tool(tool_name, tool_args)
                tool_result = json.loads(raw_result.content[0].text)
            except Exception as e:
                tool_result = {"error": str(e)}

            # Round 48: optional sixth hook - lets GovernedAutonomousLoop
            # compress a large tool result (Delta v2, original kept for
            # delentia_expand_tool_output) before it enters the history.
            if post_dispatch_transform is not None:
                tool_result = await _maybe_await(post_dispatch_transform(goal, tool_name, tool_args, tool_result))

            step = LoopStep(iteration=i, tool_name=tool_name, tool_args=tool_args,
                             tool_result=tool_result, llm_reasoning=decision["reasoning"])
            history.append(step)
            self._persist_step(step)
            await _notify(step)

        result = {
            "goal": goal,
            "steps": [vars(s) for s in history],
            "final_answer": final_answer,
            "iterations": len(history),
            "stopped_reason": stopped_reason,
        }
        if on_episode_end is not None:
            await _maybe_await(on_episode_end(result))
        return result

    async def _run_tool_batch(
        self, i: int, goal: str, decision: Dict[str, Any], history: list, available_tools: List[Dict[str, Any]],
        pre_dispatch_gate: Optional[Callable[..., Any]], post_dispatch_transform: Optional[Callable[..., Any]],
        notify: Callable[[LoopStep], Awaitable[None]], maybe_await: Callable[[Any], Awaitable[Any]],
    ) -> Optional[str]:
        """Round 54: several independent tool calls in one decision, run as waves over the Execution Graph IR
        (dag_executor.py). Returns a stopped_reason when a call was refused, else None (the loop goes on).

        Governance first, execution second: every call is scoped, checked by the approval rule and the pre-dispatch
        gate BEFORE any call runs. One refusal (FDIA, owner policy, jury, approval) ends the episode with nothing run,
        and the refused call is the last step, which is the one the approval store records."""
        from rct_control_plane import dag_executor as dag
        reasoning = str(decision.get("reasoning") or "")

        async def record(tool_name: Optional[str], tool_args: Dict[str, Any], tool_result: Any, note: str = "") -> None:
            step = LoopStep(iteration=i, tool_name=tool_name, tool_args=tool_args, tool_result=tool_result,
                            llm_reasoning=f"{note} {reasoning}".strip())
            history.append(step)
            self._persist_step(step)
            await notify(step)

        if not dag.enabled():
            await record(None, {}, {"batch_error": f"parallel tool calls are not enabled on this server ({dag.PARALLEL_ENV}); call one tool at a time"})
            return None
        try:
            calls = dag.parse_calls(decision.get("calls"))
            graph = dag.compile_batch(calls, intent_id=f"{self.namespace}-{i}")
        except dag.BatchError as exc:
            await record(None, {}, {"batch_error": str(exc)})
            return None

        prepared: Dict[str, Dict[str, Any]] = {}
        for call in calls:
            args = self._scope_tool_args(call.tool_name, call.tool_args)
            note = f"[batch {call.id}]"
            if call.tool_name == "delentia_run_sandboxed_command":
                from rct_control_plane.sandbox import classify_command_risk
                if classify_command_risk(args.get("command", "")) == "needs_approval":
                    await record(call.tool_name, args, {"pending_approval": True, "command": args.get("command", "")}, note)
                    return "pending_approval"
            if pre_dispatch_gate is not None:
                gate_result = await maybe_await(pre_dispatch_gate(goal, call.tool_name, args))
                if gate_result is not None:
                    await record(call.tool_name, args, gate_result["tool_result"], note)
                    return str(gate_result["stopped_reason"])
            prepared[call.id] = args

        known = [t["name"] for t in available_tools]
        unsafe_lock = asyncio.Lock()

        async def invoke(name: str, args: Dict[str, Any]) -> Any:
            try:
                raw = await self._mcp.call_tool(name, args)
                return json.loads(raw.content[0].text)
            except Exception as exc:  # noqa: BLE001 - reported to the model like a single failing call
                return {"error": str(exc)}

        async def run_one(call: Any) -> Any:
            args = prepared[call.id]
            if call.tool_name not in known:
                return unknown_tool_result(call.tool_name, known)
            if call.tool_name in dag.PARALLEL_SAFE_TOOLS:
                result = await asyncio.to_thread(lambda: asyncio.run(invoke(call.tool_name, args)))
            else:
                async with unsafe_lock:
                    result = await invoke(call.tool_name, args)
            if post_dispatch_transform is not None:
                result = await maybe_await(post_dispatch_transform(goal, call.tool_name, args, result))
            return result

        report = await dag.run_waves(graph, run_one, is_failure=lambda r: isinstance(r, dict) and bool(r.get("error")))
        for call in calls:
            outcome = report.outcomes[call.id]
            tag = f"[batch {call.id}, wave {outcome.wave + 1}, {outcome.status}, {round(outcome.elapsed_ms)} ms]"
            result = outcome.result if outcome.status != "skipped" else {"skipped": outcome.note}
            await record(call.tool_name, prepared[call.id], result, tag)
        self._persistence.append_audit(
            entity_type="autonomous_loop_batch", entity_id=f"{self.namespace}-{i}", action="batch_run", actor=self.namespace,
            changes=report.summary())
        return None

    async def _stream_final_answer(
        self, goal: str, history: List[LoopStep], on_answer_token: Callable[[str], Any],
    ) -> str:
        """Round 40: the real second call of the dual-call streaming
        design - a plain-text (not json_mode) prompt, reusing the same
        goal/history context decide_next_action() itself builds, sent
        through LLMProvider.stream_complete() so the caller genuinely
        sees the answer as it's generated, not after the fact."""
        from rct_control_plane.llm_provider import get_default_provider
        provider = self._llm_provider or get_default_provider()

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

    def _scope_tool_args(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Hook: the arguments actually dispatched. The base loop passes them through;
        GovernedAutonomousLoop pins memory tools to the caller's own namespace."""
        return tool_args

    def _persist_step(self, step: LoopStep) -> None:
        self._persistence.append_audit(
            entity_type="autonomous_loop_step",
            entity_id=f"{self.namespace}-{step.iteration}",
            action="loop_step",
            actor=self.namespace,
            changes={"tool_name": step.tool_name, "tool_args": step.tool_args,
                     "reasoning": step.llm_reasoning[:500]},
        )

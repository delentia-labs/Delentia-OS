"""
Round 41: real tests proving intent-delta compression is actually WIRED
into the real LLM context-construction path, not just computed and
reported (that gap - phase_6_intent_delta_compression surfaced by
algorithm_kernel_41.py's process_intent_deep_pipeline() but never used
to change what gets sent to an LLM - is what this round closes).

The real call chain (confirmed by direct reading, not assumed):
  AutonomousLoop.run()
    -> decide_next_action(goal, history, available_tools)   [every iteration]
         -> render_history(history)                          [Round 41]
         -> prompt = f"...{history_desc}..."
         -> provider.complete(prompt, ...)                    [real LLM call site]
    -> (on finish, if on_answer_token given) _stream_final_answer()
         -> render_history(history)                           [Round 41]
         -> provider.stream_complete(prompt, ...)

render_history() (rct_control_plane/autonomous_loop.py) is the real,
newly-wired context builder: it renders turn 1 in full (no prior state
to diff against - a real, honest turn-1 case, not a special-cased
shortcut) and, for every later turn, calls
DeltaEngine.compress_intent_delta() against the immediately-prior
turn's real state, using the compact `ops` JSON-Patch text in place of
the full turn text ONLY when that call's own Round-40 token-savings
safety valve confirms a genuine win - otherwise it falls back to the
exact original full-text line, so compression can only help, never hurt.

These tests inject a fake LLMProvider directly into the real call chain
(decide_next_action's own pre-existing `llm_provider` parameter, and a
monkeypatched get_default_provider() for the loop's internal calls) so
they run deterministically without a live LLM, while still exercising
the REAL render_history()/compress_intent_delta()/apply_structural_delta()
code - nothing about the compression/decompression logic itself is
mocked.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import ast
import asyncio
import json

import pytest

from rct_control_plane.autonomous_loop import (
    AutonomousLoop,
    LoopStep,
    _render_turn_full,
    decide_next_action,
    reconstruct_full_history_text,
    render_history,
)
from rct_control_plane.algo_25_delta_block import DeltaEngine
from rct_control_plane.persistence import ControlPlanePersistence


def _full_history_text(history):
    """The ground-truth pre-Round-41 rendering: every turn in full,
    exactly what history_desc used to contain unconditionally."""
    return "\n".join(_render_turn_full(s) for s in history)


def _parse_turn_lines(text):
    """Parses a fully-rendered ("Iteration N: called TOOL(ARGS) -> RESULT")
    history text back into (prefix, result_dict) pairs per line, using
    ast.literal_eval on the trailing Python-repr'd dict. Used to assert
    CONTENT equivalence between two full renderings rather than raw
    string equality: apply_structural_delta() reconstructs a dict via
    copy+mutate, which can legitimately produce a different key
    INSERTION ORDER than the original object's - Python dicts compare
    equal regardless of order, but str()/repr() (and therefore the
    plain-text prompt line) is order-sensitive. That's a cosmetic
    formatting difference, not dropped information - real correctness
    is decided by the parsed dicts being equal, which is what actually
    matters for the LLM reading the prompt."""
    lines = text.split("\n")
    parsed = []
    for line in lines:
        prefix, _, tail = line.partition(" -> ")
        parsed.append((prefix, ast.literal_eval(tail)))
    return parsed


# A real, sizeable, believable per-turn payload (mirrors
# algorithm_kernel_41.py's own current_intent_state shape: an intent
# string, an RCT-7 decomposition, and an MEE growth summary) - large
# enough for genuine token savings to be measurable, not a toy 2-field
# dict that would round to noise.
def _big_payload(topic: str, revision: int, extra_docs=0):
    return {
        "intent": f"Deploy and harden the {topic} service end to end",
        "rct7_decomposition": [f"{topic}-step-{i}: analyze aspect {i} of the {topic} rollout" for i in range(10)],
        "mee_growth_summary": {"nodes": 40 + revision, "edges": 90 + revision * 2, "growth_rate": 0.12},
        "revision": revision,
        "extra_docs": [f"doc-{i}" for i in range(extra_docs)],
    }


class _CapturingProvider:
    """A real, minimal LLMProvider stand-in: returns scripted JSON
    decisions in order and records every real prompt string it's asked
    to complete, so tests can inspect the actual bytes/content handed
    to the provider - not a re-derivation of the reported metric."""

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.captured_prompts = []

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.captured_prompts.append(prompt)
        return self._decisions.pop(0)


class _FakeToolResult:
    def __init__(self, payload):
        self.content = [type("C", (), {"text": json.dumps(payload)})()]


class _FakeMCP:
    """Returns big_tool results in the exact scripted sequence, so the
    real AutonomousLoop.run() builds a real, growing `history` list of
    LoopSteps with realistic, sizeable tool_result payloads."""

    def __init__(self, tool_results):
        self._results = list(tool_results)

    async def list_tools(self):
        return [type("T", (), {"name": "big_tool", "description": "returns a big payload", "input_schema": {}})()]

    async def call_tool(self, name, args):
        return _FakeToolResult(self._results.pop(0))


def _run_loop_with_provider(provider, tool_results, max_iterations, tmp_path, namespace):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / f"{namespace}.db"))
    loop = AutonomousLoop(
        mcp_server=_FakeMCP(tool_results), persistence=persistence,
        max_iterations=max_iterations, namespace=namespace,
    )
    result = asyncio.run(loop.run("refine the deployment plan"))
    return result


@pytest.fixture
def patched_default_provider(monkeypatch):
    """decide_next_action() resolves get_default_provider() LOCALLY at
    call time (from rct_control_plane.llm_provider import
    get_default_provider) - patching it there, not in autonomous_loop's
    own namespace, is what actually takes effect (same discipline the
    Round-40 streaming tests already established)."""
    def _patch(provider):
        import rct_control_plane.llm_provider as llm_provider_module
        monkeypatch.setattr(llm_provider_module, "get_default_provider", lambda: provider)
    return _patch


class TestCompressionShrinksTheRealPayloadSentToTheProvider:
    """(a) When compression triggers, the actual prompt string handed to
    provider.complete() must be smaller than what the pre-Round-41
    full-history rendering would have produced for the same history -
    inspecting the real constructed prompt, not the reported metric."""

    def test_end_to_end_through_autonomous_loop_run(self, patched_default_provider, tmp_path):
        # Turn 1: call big_tool with revision=0. Turn 2: call big_tool
        # again with revision=1 (a genuine small refinement - most
        # content identical, a few fields bumped) - exactly the
        # "refine" scenario class the Round-40 measurement found the
        # largest real savings on (+43.5%). Turn 3: finish.
        decisions = [
            json.dumps({"action": "call_tool", "tool_name": "big_tool", "tool_args": {"rev": 0},
                        "reasoning": "start"}),
            json.dumps({"action": "call_tool", "tool_name": "big_tool", "tool_args": {"rev": 1},
                        "reasoning": "refine"}),
            json.dumps({"action": "finish", "reasoning": "done", "final_answer": "done"}),
        ]
        provider = _CapturingProvider(decisions)
        patched_default_provider(provider)

        tool_results = [_big_payload("payment", 0), _big_payload("payment", 1)]
        result = _run_loop_with_provider(provider, tool_results, max_iterations=5,
                                          tmp_path=tmp_path, namespace="compress_e2e")

        assert result["stopped_reason"] == "llm_finished"
        assert len(provider.captured_prompts) == 3

        # The 3rd real call's prompt is built from history=[step1, step2]
        # - the first turn where a prior-turn diff is even possible.
        third_prompt = provider.captured_prompts[2]
        assert "[delta vs iteration 1]" in third_prompt, (
            "expected the real 2nd turn (a genuine small refinement of the "
            "1st) to be sent as a compact delta, not re-serialized in full"
        )

        # Build the ground-truth full-history equivalent for the SAME
        # real history the loop actually produced, and prove the real
        # sent prompt is genuinely smaller.
        real_history = [LoopStep(**s) for s in result["steps"][:2]]
        full_equivalent_history_desc = _full_history_text(real_history)
        compressed_history_desc = render_history(real_history)
        assert len(compressed_history_desc) < len(full_equivalent_history_desc)
        # And that smaller history_desc is genuinely embedded in the real
        # prompt actually handed to provider.complete() - not just true
        # of the helper function in isolation.
        assert compressed_history_desc in third_prompt

    def test_render_history_is_smaller_for_a_realistic_refinement_pair(self):
        """Direct, non-async proof isolating render_history() itself -
        same conclusion as the end-to-end test above, without the loop
        machinery, per DeltaEngine's own Round-40-measured "refine"
        scenario (the strongest real savings case)."""
        step1 = LoopStep(iteration=1, tool_name="big_tool", tool_args={"rev": 0},
                          tool_result=_big_payload("payment", 0), llm_reasoning="r1")
        step2 = LoopStep(iteration=2, tool_name="big_tool", tool_args={"rev": 1},
                          tool_result=_big_payload("payment", 1), llm_reasoning="r2")
        history = [step1, step2]

        full = _full_history_text(history)
        compressed = render_history(history)
        assert len(compressed) < len(full)


class TestSafetyValveDeclineStillSendsFullCorrectContext:
    """(b) When compression is correctly declined by the token safety
    valve (an unrelated turn), the LLM must still receive the full,
    correct context for that turn - byte-for-byte, not a lossy patch."""

    def test_end_to_end_unrelated_turn_is_sent_in_full(self, patched_default_provider, tmp_path):
        decisions = [
            json.dumps({"action": "call_tool", "tool_name": "big_tool", "tool_args": {"topic": "payment"},
                        "reasoning": "start"}),
            json.dumps({"action": "call_tool", "tool_name": "big_tool", "tool_args": {"topic": "trivia"},
                        "reasoning": "aside"}),
            json.dumps({"action": "finish", "reasoning": "done", "final_answer": "done"}),
        ]
        provider = _CapturingProvider(decisions)
        patched_default_provider(provider)

        # Turn 2 is a totally unrelated trivial aside (matches Round 40's
        # own real "aside" scenario class, which measured as low as -63%
        # naive "savings" before the safety valve existed) - a tiny,
        # completely different payload sharing nothing with turn 1.
        tool_results = [_big_payload("payment", 0), {"trivia_answer": "4"}]
        result = _run_loop_with_provider(provider, tool_results, max_iterations=5,
                                          tmp_path=tmp_path, namespace="safety_valve_e2e")

        assert result["stopped_reason"] == "llm_finished"
        third_prompt = provider.captured_prompts[2]

        # Turn 2 must NOT be rendered as a delta marker...
        assert "[delta vs iteration 1]" not in third_prompt
        # ...and the real, full, correct turn-2 content must be present
        # verbatim - no information silently dropped.
        real_history = [LoopStep(**s) for s in result["steps"][:2]]
        assert _render_turn_full(real_history[1]) in third_prompt
        assert "trivia_answer" in third_prompt and "4" in third_prompt

    def test_render_history_falls_back_to_full_text_for_unrelated_turn(self):
        step1 = LoopStep(iteration=1, tool_name="big_tool", tool_args={"topic": "payment"},
                          tool_result=_big_payload("payment", 0), llm_reasoning="r1")
        step2 = LoopStep(iteration=2, tool_name="trivia_tool", tool_args={},
                          tool_result={"trivia_answer": "4"}, llm_reasoning="r2")
        history = [step1, step2]

        rendered = render_history(history)
        assert "[delta vs iteration 1]" not in rendered
        assert rendered == _full_history_text(history)

    def test_turn_one_always_full_no_prior_state(self):
        """Explicit turn-1 case: nothing to diff against yet - must be
        byte-for-byte the same as the no-compression rendering."""
        step1 = LoopStep(iteration=1, tool_name="big_tool", tool_args={"topic": "payment"},
                          tool_result=_big_payload("payment", 0), llm_reasoning="r1")
        assert render_history([step1]) == _full_history_text([step1])

    def test_empty_history_unchanged(self):
        assert render_history([]) == "(no actions taken yet)"


class TestMultiTurnCompressedChainReconstructsCoherently:
    """(c) A multi-turn sequence where later turns build on compressed
    deltas must still produce a coherent, correct prompt - no silently
    dropped information anywhere in the chain, proven via the real
    decompression path (DeltaEngine.apply_structural_delta(), wrapped by
    reconstruct_full_history_text())."""

    def _mixed_realistic_history(self):
        """A believable 8-turn mix: refine, refine, switch topic, refine
        the new topic, trivial aside, return to the FIRST topic, refine
        again - the same scenario classes (refine/switch/aside/return)
        Round 40's own measurement used, just longer."""
        turns = [
            ("refine payment v0", _big_payload("payment", 0)),
            ("refine payment v1", _big_payload("payment", 1)),
            ("refine payment v2", _big_payload("payment", 2, extra_docs=1)),
            ("switch to auth", _big_payload("auth", 0)),
            ("refine auth v1", _big_payload("auth", 1)),
            ("trivial aside", {"trivia_answer": "the sky is blue"}),
            ("return to payment", _big_payload("payment", 2, extra_docs=1)),
            ("refine payment v3 after return", _big_payload("payment", 3, extra_docs=1)),
        ]
        return [
            LoopStep(iteration=i + 1, tool_name="big_tool", tool_args={"note": note},
                     tool_result=payload, llm_reasoning=f"reasoning-{i + 1}")
            for i, (note, payload) in enumerate(turns)
        ]

    def test_reconstruction_is_content_identical_to_the_uncompressed_ground_truth(self):
        """The real correctness bar: every turn's reconstructed
        (prefix, result) content must exactly match the ground truth.
        Compared as parsed content rather than raw text, since
        apply_structural_delta() legitimately reconstructs a dict via
        copy+mutate, which can produce a different (but equally correct)
        key insertion order than the original object - real Python dict
        equality doesn't care, only str()'s cosmetic ordering does."""
        history = self._mixed_realistic_history()

        ground_truth = _full_history_text(history)
        reconstructed = reconstruct_full_history_text(history)
        assert _parse_turn_lines(reconstructed) == _parse_turn_lines(ground_truth), (
            "decompression must lose nothing across a real multi-turn chain"
        )

    def test_the_compressed_render_still_nets_positive_savings_across_the_whole_chain(self):
        history = self._mixed_realistic_history()
        full = _full_history_text(history)
        compressed = render_history(history)
        assert len(compressed) < len(full)

    def test_reconstruction_works_from_a_shared_stateful_delta_engine_too(self):
        """Proves the decompression path works whether the caller passes
        a fresh engine or reuses one across calls (DeltaEngine's own
        compress_intent_delta/apply_structural_delta never depend on its
        internal store_delta state, so either usage is equally real and
        correct)."""
        history = self._mixed_realistic_history()
        engine = DeltaEngine()
        ground_truth = _full_history_text(history)
        reconstructed = reconstruct_full_history_text(history, delta_engine=engine)
        assert _parse_turn_lines(reconstructed) == _parse_turn_lines(ground_truth)

    def test_individual_turn_states_recoverable_after_compressed_chain(self):
        """A finer-grained proof than whole-text equality: walk the same
        chain and confirm each individual turn's real tool_result is
        exactly recoverable via apply_structural_delta(), not just that
        the final joined string happens to match."""
        from rct_control_plane.autonomous_loop import _turn_state

        history = self._mixed_realistic_history()
        engine = DeltaEngine()
        prior_state = _turn_state(history[0])
        for step in history[1:]:
            current_state = _turn_state(step)
            compression = engine.compress_intent_delta(prior_state, current_state)
            reconstructed_state = engine.apply_structural_delta(prior_state, compression["ops"])
            assert reconstructed_state == current_state, f"iteration {step.iteration} lost information"
            prior_state = current_state


class TestDecideNextActionRealPromptWiring:
    """Confirms the exact real call chain end-to-end at the
    decide_next_action() level (not just via AutonomousLoop.run()),
    using its own pre-existing injectable llm_provider parameter."""

    def test_decide_next_action_embeds_the_real_compressed_history_in_its_prompt(self):
        step1 = LoopStep(iteration=1, tool_name="big_tool", tool_args={"rev": 0},
                          tool_result=_big_payload("payment", 0), llm_reasoning="r1")
        step2 = LoopStep(iteration=2, tool_name="big_tool", tool_args={"rev": 1},
                          tool_result=_big_payload("payment", 1), llm_reasoning="r2")
        provider = _CapturingProvider([json.dumps({"action": "finish", "reasoning": "done", "final_answer": "ok"})])

        asyncio.run(decide_next_action(
            goal="refine the plan", history=[step1, step2], available_tools=[], llm_provider=provider,
        ))

        assert len(provider.captured_prompts) == 1
        prompt = provider.captured_prompts[0]
        assert render_history([step1, step2]) in prompt
        assert "[delta vs iteration 1]" in prompt

    def test_decide_next_action_with_empty_history_is_unchanged(self):
        """Zero-Delete proof: the very first call of any run (history=[])
        renders identically to before this change."""
        provider = _CapturingProvider([json.dumps({"action": "finish", "reasoning": "done", "final_answer": "ok"})])
        asyncio.run(decide_next_action(
            goal="do something", history=[], available_tools=[], llm_provider=provider,
        ))
        assert "(no actions taken yet)" in provider.captured_prompts[0]

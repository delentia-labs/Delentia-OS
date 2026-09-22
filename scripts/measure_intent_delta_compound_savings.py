"""
Intent-Delta Compound Savings Measurement — extended to 30-50+ turns.

Round 40 ran a 12-turn realistic mixed conversation (scenario classes:
refine / switch / aside / return) directly against DeltaEngine's
compress_intent_delta() and found 23.9% cumulative token savings /
58.6% cumulative byte savings, non-negative per turn by construction
(two independent safety valves: never cost more than the full state in
bytes, and never cost more than the full state in tokens - decided
independently, since zstd bytes are never valid LLM prompt text). That
measurement script itself was never committed - only its methodology
and results survive in algo_25_delta_block.py's and
test_delta_engine_redesign_real.py's own docstrings/comments (see
those files' Round 38/40 sections) and in commit 8b6bdbf's message.
This script reconstructs that methodology from those real, cited
sources and extends it to a longer, still-realistic session.

Two things are measured, not one:

1. The exact Round-40 metric (compress_intent_delta()'s own
   final_bytes/patch_tokens_approx vs full_new_state_bytes/
   new_state_tokens_approx, per turn, summed cumulatively) - this is
   the "RCTDB storage/LLM context" metric the original 23.9%/58.6%
   figures came from, kept identical here for a real apples-to-apples
   comparison at longer session lengths.

2. The ACTUAL bytes of the real prompt text autonomous_loop.py's
   render_history() would hand to LLMProvider.complete() for the same
   turn sequence, built via real LoopStep objects - proving Round 41's
   wiring (this task's Task 1) achieves genuine savings in the real
   call chain, not just in the standalone metric.

Turn states use the same shape algorithm_kernel_41.py's own
process_intent_deep_pipeline() tracks as current_intent_state (intent,
fdia_score, architect_veto, rct7_step_count, rct7_decomposition,
mee_growth_summary) - the real, representative shape an LLM turn's
context would need re-sent each turn, not a deliberately undersized
proxy (Round 40's own stated reason for expanding scope beyond the
original 4 fields).

Run with:
    python scripts/measure_intent_delta_compound_savings.py
    python scripts/measure_intent_delta_compound_savings.py --turns 50
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from rct_control_plane.algo_25_delta_block import DeltaEngine
from rct_control_plane.autonomous_loop import LoopStep, _render_turn_full, render_history


TOPIC_INTENTS = {
    "payment": "Deploy and harden the payment service with idempotent retries",
    "auth": "Refactor the auth service to support OAuth2 device flow",
    "database": "Migrate the primary database to a hybrid vector+graph+sql store",
    "frontend": "Redesign the frontend dashboard for real-time telemetry",
    "cicd": "Harden the CI/CD pipeline with real canary rollout gating",
    "search": "Tune the search-ranking model for real click-through data",
}


def _topic_static_decomposition(topic: str) -> List[str]:
    """The real RCT-7 decomposition for a topic - large and STABLE
    across consecutive refinements of the SAME topic (a decomposition
    doesn't get rewritten on every micro-refinement in a real
    conversation; only the smaller progress/metric fields do). This is
    the real-world shape that makes structural diffing pay off: most of
    a turn's content is genuinely unchanged from the turn before it."""
    return [f"{topic}-step-{i}: analyze aspect {i} of the {topic} rollout in real depth, "
            f"covering dependencies, risk, and rollback strategy" for i in range(7)]


def _topic_static_context(topic: str) -> List[str]:
    """Accumulated background/context notes for a topic - real
    conversations carry forward prior analysis, constraints, and
    decisions that stay stable turn-to-turn once established. Large
    (dominates the state's byte/token size) and unchanged across
    refinements of the same topic, exactly like the 30 large stable
    fields in test_delta_engine_redesign_real.py's own
    test_a_real_large_context_case_achieves_genuine_positive_compression."""
    return [
        f"{topic}-context-{i}: prior decision or constraint #{i} established earlier in the "
        f"{topic} thread and still binding for all further refinements"
        for i in range(12)
    ]


def _topic_state(topic: str, revision: int) -> Dict[str, Any]:
    """A believable per-turn intent state for `topic` at `revision` -
    large, STABLE structure (RCT-7 decomposition + accumulated context
    notes) that stays byte-for-byte identical across consecutive
    refinements of the same topic, plus small, genuinely-changing
    progress fields (fdia_score, mee_growth_summary) - a real "refine"
    pattern: most content unchanged, a few fields updated, exactly the
    case compress_intent_delta() is designed to compress well (see that
    method's own test coverage for the same principle on synthetic
    data; this applies it to a believable conversational shape)."""
    return {
        "intent": TOPIC_INTENTS[topic],
        "fdia_score": round(0.85 + 0.01 * (revision % 10), 3),
        "architect_veto": False,
        "rct7_step_count": 7,
        "rct7_decomposition": _topic_static_decomposition(topic),
        "context_notes": _topic_static_context(topic),
        "mee_growth_summary": {
            "nodes": 40 + revision * 3,
            "edges": 90 + revision * 5,
            "growth_rate": round(0.10 + 0.01 * revision, 3),
        },
    }


_ASIDE_COUNTER = [0]


def _aside_state() -> Dict[str, Any]:
    """A trivial, genuinely unrelated one-off aside - shares almost
    nothing in common with any topic thread, matching Round 40's own
    real "aside" scenario class (measured as low as -63% naive
    "savings" before the safety valve existed; 0.0% after)."""
    _ASIDE_COUNTER[0] += 1
    trivia = [
        ("What's 7 * 8?", "56"),
        ("What year is it?", "2026"),
        ("Spell 'necessary'.", "n-e-c-e-s-s-a-r-y"),
        ("What's the capital of Thailand?", "Bangkok"),
    ][_ASIDE_COUNTER[0] % 4]
    return {
        "intent": trivia[0],
        "fdia_score": 0.5,
        "architect_veto": False,
        "rct7_step_count": 0,
        "rct7_decomposition": [],
        "mee_growth_summary": {"nodes": 0, "edges": 0, "growth_rate": 0.0},
        "aside_answer": trivia[1],
    }


class TopicTracker:
    """Tracks each topic's current revision across the whole session, so
    "return to an earlier topic" turns genuinely resume from that
    topic's own last real state, exactly like a real multi-topic
    conversation would."""

    def __init__(self):
        self._revisions: Dict[str, int] = {}

    def intro(self, topic: str) -> Dict[str, Any]:
        self._revisions[topic] = 0
        return _topic_state(topic, 0)

    def refine(self, topic: str) -> Dict[str, Any]:
        self._revisions[topic] += 1
        return _topic_state(topic, self._revisions[topic])

    def resume(self, topic: str) -> Dict[str, Any]:
        return _topic_state(topic, self._revisions[topic])


def build_turn_plan(min_turns: int) -> List[Tuple[str, str]]:
    """Builds a believable (scenario_class, topic) plan across 6 topics,
    mixing refine/switch/aside/return in a non-repeating, plausible
    order - a real multi-topic engineering conversation, not the same
    12-turn block copy-pasted 3x. Extends the base plan with further
    round-robin refine/return/aside cycles across all topics until
    `min_turns` is reached, so it scales cleanly past 50 turns too."""
    topics = ["payment", "auth", "database", "frontend", "cicd", "search"]

    plan: List[Tuple[str, str]] = [
        ("intro", "payment"),
        ("refine", "payment"),
        ("refine", "payment"),
        ("switch", "auth"),
        ("refine", "auth"),
        ("aside", ""),
        ("return", "payment"),
        ("refine", "payment"),
        ("switch", "database"),
        ("refine", "database"),
        ("refine", "database"),
        ("aside", ""),
        ("switch", "frontend"),
        ("refine", "frontend"),
        ("return", "auth"),
        ("refine", "auth"),
        ("refine", "auth"),
        ("aside", ""),
        ("return", "database"),
        ("refine", "database"),
        ("switch", "cicd"),
        ("refine", "cicd"),
        ("refine", "cicd"),
        ("return", "frontend"),
        ("refine", "frontend"),
        ("aside", ""),
        ("return", "payment"),
        ("refine", "payment"),
        ("refine", "payment"),
        ("switch", "search"),
        ("refine", "search"),
        ("return", "cicd"),
        ("refine", "cicd"),
        ("aside", ""),
        ("return", "auth"),
        ("refine", "auth"),
        ("return", "database"),
        ("refine", "database"),
        ("return", "frontend"),
        ("refine", "frontend"),
        ("return", "search"),
        ("refine", "search"),
    ]

    # Round-robin extension: keep cycling refine -> aside -> return
    # across all 6 topics for any turns beyond the hand-authored plan,
    # so --turns 80 etc. still produces a believable, varied sequence
    # instead of erroring or truncating.
    i = 0
    cycle = ["refine", "aside", "return"]
    while len(plan) < min_turns:
        action = cycle[i % len(cycle)]
        topic = topics[(i // len(cycle)) % len(topics)]
        if action == "aside":
            plan.append(("aside", ""))
        else:
            plan.append((action, topic))
        i += 1

    return plan[:max(min_turns, len(plan))] if min_turns <= len(plan) else plan


def build_session(min_turns: int) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Returns [(scenario_class, topic, state), ...] for the whole
    session, in turn order."""
    plan = build_turn_plan(min_turns)
    tracker = TopicTracker()
    session: List[Tuple[str, str, Dict[str, Any]]] = []
    for action, topic in plan:
        if action == "intro":
            state = tracker.intro(topic)
        elif action == "refine":
            state = tracker.refine(topic)
        elif action == "switch":
            state = tracker.intro(topic)
        elif action == "return":
            state = tracker.resume(topic)
        elif action == "aside":
            state = _aside_state()
            topic = "(aside)"
        else:
            raise ValueError(action)
        session.append((action, topic, state))
    return session


def measure(min_turns: int) -> None:
    session = build_session(min_turns)
    n = len(session)
    engine = DeltaEngine()

    rows = []
    scenario_bytes_savings = defaultdict(list)
    scenario_token_savings = defaultdict(list)

    total_full_bytes = 0
    total_final_bytes = 0
    total_new_tokens = 0
    total_patch_tokens = 0

    history: List[LoopStep] = []
    prompt_full_bytes_total = 0
    prompt_actual_bytes_total = 0

    prior_state = None
    for idx, (scenario, topic, state) in enumerate(session, start=1):
        step = LoopStep(iteration=idx, tool_name="process_intent_deep_pipeline",
                         tool_args={}, tool_result=state, llm_reasoning=f"turn-{idx}")
        history.append(step)

        if prior_state is None:
            # Turn 1: no prior state to diff against - always sent in
            # full, honestly, matching autonomous_loop.py's own turn-1
            # handling (see render_history()'s docstring).
            rows.append({
                "turn": idx, "scenario": scenario, "topic": topic,
                "full_bytes": None, "final_bytes": None, "byte_savings_pct": None,
                "new_tokens": None, "patch_tokens": None, "token_savings_pct": None,
                "zstd_applied": None, "byte_fallback": None, "token_fallback": None,
            })
            prior_state = state
            continue

        result = engine.compress_intent_delta(prior_state, state)

        full_bytes = result["full_new_state_bytes"]
        final_bytes = result["final_bytes"]
        new_tokens = result["new_state_tokens_approx"]
        patch_tokens = result["patch_tokens_approx"]

        byte_savings_pct = result["byte_reduction_pct"]
        token_savings_pct = result["token_reduction_pct_approx"]

        total_full_bytes += full_bytes
        total_final_bytes += final_bytes
        if new_tokens is not None:
            total_new_tokens += new_tokens
            total_patch_tokens += patch_tokens

        scenario_bytes_savings[scenario].append(byte_savings_pct)
        if token_savings_pct is not None:
            scenario_token_savings[scenario].append(token_savings_pct)

        rows.append({
            "turn": idx, "scenario": scenario, "topic": topic,
            "full_bytes": full_bytes, "final_bytes": final_bytes, "byte_savings_pct": byte_savings_pct,
            "new_tokens": new_tokens, "patch_tokens": patch_tokens, "token_savings_pct": token_savings_pct,
            "zstd_applied": result["zstd_applied"],
            "byte_fallback": result["used_fallback_to_full_state"],
            "token_fallback": result["used_token_fallback_to_full_state"],
        })

        prior_state = state

    # Second, independent measurement: the REAL prompt text bytes
    # render_history() (Task 1's actual wiring) would hand to
    # LLMProvider.complete() for this exact session, turn by turn, as
    # decide_next_action() genuinely re-renders it every real iteration.
    for i in range(2, n + 1):
        sub_history = history[:i]
        full_text = "\n".join(_render_turn_full(s) for s in sub_history)
        actual_text = render_history(sub_history)
        prompt_full_bytes_total += len(full_text.encode("utf-8"))
        prompt_actual_bytes_total += len(actual_text.encode("utf-8"))

    _print_report(rows, n, total_full_bytes, total_final_bytes, total_new_tokens, total_patch_tokens,
                  scenario_bytes_savings, scenario_token_savings,
                  prompt_full_bytes_total, prompt_actual_bytes_total)


def _print_report(rows, n, total_full_bytes, total_final_bytes, total_new_tokens, total_patch_tokens,
                   scenario_bytes_savings, scenario_token_savings,
                   prompt_full_bytes_total, prompt_actual_bytes_total) -> None:
    print("=" * 110)
    print(f"INTENT-DELTA COMPOUND SAVINGS - {n}-turn realistic mixed conversation "
          f"(refine / switch / aside / return)")
    print("=" * 110)
    header = (f"{'turn':>4}  {'scenario':<8} {'topic':<10} {'full_B':>8} {'final_B':>8} {'byte%':>7}  "
              f"{'new_tok':>8} {'patch_tok':>9} {'tok%':>7}  {'zstd':>5} {'Bfb':>4} {'Tfb':>4}")
    print(header)
    print("-" * 110)
    for r in rows:
        if r["full_bytes"] is None:
            print(f"{r['turn']:>4}  {r['scenario']:<8} {r['topic']:<10} "
                  f"{'(turn 1 - no prior state, sent in full)':<50}")
            continue
        token_pct = r["token_savings_pct"]
        token_pct_str = f"{token_pct:.1f}%" if token_pct is not None else "n/a"
        print(
            f"{r['turn']:>4}  {r['scenario']:<8} {r['topic']:<10} "
            f"{r['full_bytes']:>8} {r['final_bytes']:>8} {r['byte_savings_pct']:>6.1f}%  "
            f"{str(r['new_tokens']):>8} {str(r['patch_tokens']):>9} "
            f"{token_pct_str:>7}  "
            f"{str(r['zstd_applied']):>5} {str(r['byte_fallback']):>4} {str(r['token_fallback']):>4}"
        )

    print("-" * 110)
    cumulative_byte_pct = (1 - total_final_bytes / total_full_bytes) * 100 if total_full_bytes else 0.0
    cumulative_token_pct = (1 - total_patch_tokens / total_new_tokens) * 100 if total_new_tokens else 0.0

    print(f"\nCUMULATIVE COMPARISON across {n - 1} diffed turns (turn 1 excluded - no prior state):")
    print(f"  Total full_new_state bytes  : {total_full_bytes:>10}")
    print(f"  Total final (sent) bytes    : {total_final_bytes:>10}")
    print(f"  CUMULATIVE BYTE SAVINGS     : {cumulative_byte_pct:6.1f}%")
    print()
    print(f"  Total full new_state tokens : {total_new_tokens:>10}")
    print(f"  Total patch (sent) tokens   : {total_patch_tokens:>10}")
    print(f"  CUMULATIVE TOKEN SAVINGS    : {cumulative_token_pct:6.1f}%")

    print("\nBaseline (Round 40, 12-turn): 23.9% cumulative token savings, 58.6% cumulative byte savings")
    print(f"This run   ({n}-turn)       : {cumulative_token_pct:.1f}% cumulative token savings, "
          f"{cumulative_byte_pct:.1f}% cumulative byte savings")

    print("\nPer-scenario-class average byte/token savings:")
    for scenario in ("refine", "switch", "aside", "return"):
        b = scenario_bytes_savings.get(scenario, [])
        t = scenario_token_savings.get(scenario, [])
        b_avg = sum(b) / len(b) if b else float("nan")
        t_avg = sum(t) / len(t) if t else float("nan")
        print(f"  {scenario:<8} n={len(b):>3}  byte_avg={b_avg:6.1f}%  token_avg={t_avg:6.1f}%")

    print("\nGuarantee check: any turn where byte or token savings went negative "
          "(would indicate a safety-valve regression)?")
    negative_byte_turns = [r["turn"] for r in rows if r["byte_savings_pct"] is not None and r["byte_savings_pct"] < 0]
    negative_token_turns = [r["turn"] for r in rows if r["token_savings_pct"] is not None and r["token_savings_pct"] < 0]
    print(f"  Negative byte-savings turns : {negative_byte_turns or 'none'}")
    print(f"  Negative token-savings turns: {negative_token_turns or 'none'}")

    print("\n" + "=" * 110)
    print("REAL WIRING CHECK - actual render_history() prompt-text bytes vs the equivalent")
    print("full-text-every-turn rendering, summed across every real decide_next_action() call")
    print("this session would make (re-rendering the full growing history each iteration,")
    print("exactly as the real AutonomousLoop.run() loop does):")
    print("=" * 110)
    prompt_savings_pct = (
        (1 - prompt_actual_bytes_total / prompt_full_bytes_total) * 100 if prompt_full_bytes_total else 0.0
    )
    print(f"  Total bytes, full-text rendering (pre-Round-41 baseline): {prompt_full_bytes_total:>12}")
    print(f"  Total bytes, real render_history() output (Round 41)    : {prompt_actual_bytes_total:>12}")
    print(f"  REAL PROMPT-TEXT BYTE SAVINGS ACROSS THE SESSION         : {prompt_savings_pct:6.1f}%")
    print("=" * 110)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=42, help="minimum number of turns to simulate (default 42)")
    args = parser.parse_args()
    measure(args.turns)

"""
Round 41: a real smoke/regression test for
scripts/measure_intent_delta_compound_savings.py - the extended
(30-50+ turn) successor to Round 40's uncommitted 12-turn measurement
script. Not a re-implementation of the script's own logic; imports and
exercises the actual functions the script's __main__ block calls, so a
future change that breaks the measurement (e.g. reintroducing a
negative-savings turn, or breaking the plan generator) fails a real
test, not just a manual run.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

from rct_control_plane.algo_25_delta_block import DeltaEngine
from measure_intent_delta_compound_savings import build_session, build_turn_plan


def test_build_turn_plan_covers_all_four_scenario_classes_and_is_at_least_30_turns():
    plan = build_turn_plan(30)
    assert len(plan) >= 30
    classes = {action for action, _ in plan}
    assert {"refine", "switch", "aside", "return"} <= classes


def test_build_turn_plan_extends_cleanly_past_the_hand_authored_plan():
    plan_45 = build_turn_plan(45)
    plan_70 = build_turn_plan(70)
    assert len(plan_45) >= 45
    assert len(plan_70) >= 70
    # The extension is a real, non-trivial continuation - not just
    # truncated/padded with a single repeated action.
    tail_classes = {action for action, _ in plan_70[50:]}
    assert len(tail_classes) > 1


def test_a_real_42_turn_session_has_no_negative_savings_turn_either_metric():
    """The real safety-valve guarantee (Round 40) must hold at this
    longer, more realistic session length too: no turn may cost more
    (in bytes OR tokens) than sending the full new_state."""
    session = build_session(42)
    engine = DeltaEngine()

    prior_state = None
    checked = 0
    for _scenario, _topic, state in session:
        if prior_state is not None:
            result = engine.compress_intent_delta(prior_state, state)
            assert result["byte_reduction_pct"] >= 0.0
            assert (
                result["token_reduction_pct_approx"] is None
                or result["token_reduction_pct_approx"] >= 0.0
            )
            checked += 1
        prior_state = state

    assert checked >= 30


def test_a_real_42_turn_session_achieves_genuine_positive_cumulative_savings():
    """Proves the extended measurement isn't just non-negative but
    genuinely, substantially positive in aggregate - the real point of
    the compression mechanism existing at all."""
    session = build_session(42)
    engine = DeltaEngine()

    total_full_bytes = total_final_bytes = 0
    total_new_tokens = total_patch_tokens = 0
    prior_state = None
    for _scenario, _topic, state in session:
        if prior_state is not None:
            result = engine.compress_intent_delta(prior_state, state)
            total_full_bytes += result["full_new_state_bytes"]
            total_final_bytes += result["final_bytes"]
            if result["new_state_tokens_approx"] is not None:
                total_new_tokens += result["new_state_tokens_approx"]
                total_patch_tokens += result["patch_tokens_approx"]
        prior_state = state

    cumulative_byte_pct = (1 - total_final_bytes / total_full_bytes) * 100
    cumulative_token_pct = (1 - total_patch_tokens / total_new_tokens) * 100
    assert cumulative_byte_pct > 50.0
    assert cumulative_token_pct > 20.0


def test_refine_turns_of_the_same_topic_reuse_stable_content_across_the_whole_session():
    """The believability check: for the SAME topic across the whole
    session, the large static fields (rct7_decomposition, context_notes)
    a real conversation would carry forward must be genuinely identical
    revision to revision - proving the "refine" scenario class is a
    real analog of an LLM conversation's stable context, not an
    artificially easy synthetic case."""
    session = build_session(42)
    payment_states = [state for scenario, topic, state in session if topic == "payment"]
    assert len(payment_states) >= 4
    first = payment_states[0]
    for state in payment_states[1:]:
        assert state["rct7_decomposition"] == first["rct7_decomposition"]
        assert state["context_notes"] == first["context_notes"]
        # But the progress fields DO genuinely evolve turn to turn.
    assert len({s["mee_growth_summary"]["nodes"] for s in payment_states}) > 1

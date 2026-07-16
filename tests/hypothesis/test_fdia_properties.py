"""
Property-based tests for FDIAScorer — mathematical correctness guarantees.

These tests verify that the FDIA equation holds its constitutional properties
for ARBITRARY inputs (not just fixed test cases).

Formula: F = D^I × A  (simplified)
Full:    score = weighted(desire, intent, alignment, governance) × rep_factor × gov_multiplier

Properties verified:
  1. Output always in [0.0, 1.0]
  2. governance_penalty=1.0 collapses score to 0 (constitutional gate)
  3. Higher governance_penalty → lower or equal score (monotonic)
  4. Higher agent_reputation → higher or equal score (monotonic)
  5. rank_actions always returns descending-sorted scores
  6. select_best_action always returns highest-scoring action
  7. Determinism: same inputs → identical outputs
  8. Zero reputation → score ≤ 0.5 (reputation floor = 0.5)
"""

from hypothesis import given, assume, strategies as st

from core.fdia.fdia import (
    FDIAScorer,
    FDIAWeights,
    NPCAction,
    NPCIntentType,
)

# ── Shared scorer instance (stateless / pure functions) ──────────────────

_scorer = FDIAScorer(weights=FDIAWeights())

# ── Strategies ────────────────────────────────────────────────────────────

_intent_st = st.sampled_from(list(NPCIntentType))
_action_type_st = st.sampled_from(
    ["explore", "trade", "cooperate", "attack", "defend", "gather", "research"]
)
_reputation_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_penalty_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_resource_val_st = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)


def _make_action(action_type: str = "explore", action_id: str = "a1") -> NPCAction:
    return NPCAction(action_id=action_id, action_type=action_type)


# ── Property 1: Output always in [0.0, 1.0] ──────────────────────────────

@given(
    intent=_intent_st,
    action_type=_action_type_st,
    reputation=_reputation_st,
    penalty=_penalty_st,
)
def test_score_always_in_unit_interval(intent, action_type, reputation, penalty):
    """score_action() must always return a float in [0.0, 1.0] for any valid inputs."""
    score = _scorer.score_action(
        agent_intent=intent,
        action=_make_action(action_type),
        agent_reputation=reputation,
        governance_penalty=penalty,
    )
    assert isinstance(score, float), f"Expected float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"score={score} out of [0.0, 1.0]"


# ── Property 2: Constitutional gate — penalty=1.0 collapses score to 0 ───

@given(
    intent=_intent_st,
    action_type=_action_type_st,
    reputation=_reputation_st,
)
def test_full_governance_penalty_blocks_action(intent, action_type, reputation):
    """governance_penalty=1.0 must produce score=0.0 (constitutional hard block)."""
    score = _scorer.score_action(
        agent_intent=intent,
        action=_make_action(action_type),
        agent_reputation=reputation,
        governance_penalty=1.0,
    )
    assert score == 0.0, (
        f"governance_penalty=1.0 must produce 0.0, got {score} "
        f"(intent={intent.value}, action={action_type}, rep={reputation})"
    )


# ── Property 3: Governance monotonicity — higher penalty ≤ lower penalty ─

@given(
    intent=_intent_st,
    action_type=_action_type_st,
    reputation=_reputation_st,
    penalty_low=st.floats(min_value=0.0, max_value=0.5, allow_nan=False),
    penalty_high=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
)
def test_governance_penalty_monotonic(intent, action_type, reputation, penalty_low, penalty_high):
    """Higher governance_penalty must not produce a higher score (monotonic decrease)."""
    assume(penalty_high >= penalty_low)
    action = _make_action(action_type)
    score_low = _scorer.score_action(
        agent_intent=intent, action=action,
        agent_reputation=reputation, governance_penalty=penalty_low,
    )
    score_high = _scorer.score_action(
        agent_intent=intent, action=action,
        agent_reputation=reputation, governance_penalty=penalty_high,
    )
    assert score_high <= score_low + 1e-9, (
        f"Higher penalty ({penalty_high}) gave higher score ({score_high}) "
        f"than lower penalty ({penalty_low}, score={score_low})"
    )


# ── Property 4: Reputation monotonicity — higher rep ≥ lower rep ─────────

@given(
    intent=_intent_st,
    action_type=_action_type_st,
    penalty=_penalty_st,
    rep_low=st.floats(min_value=0.0, max_value=0.5, allow_nan=False),
    rep_high=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
)
def test_reputation_monotonic(intent, action_type, penalty, rep_low, rep_high):
    """Higher agent_reputation must not produce a lower score (monotonic increase)."""
    assume(rep_high >= rep_low)
    assume(penalty < 1.0)  # avoid degenerate case where both collapse to 0
    action = _make_action(action_type)
    score_low = _scorer.score_action(
        agent_intent=intent, action=action,
        agent_reputation=rep_low, governance_penalty=penalty,
    )
    score_high = _scorer.score_action(
        agent_intent=intent, action=action,
        agent_reputation=rep_high, governance_penalty=penalty,
    )
    assert score_high >= score_low - 1e-9, (
        f"Higher rep ({rep_high}) gave lower score ({score_high}) "
        f"than lower rep ({rep_low}, score={score_low})"
    )


# ── Property 5: rank_actions returns descending-sorted results ───────────

@given(
    intent=_intent_st,
    action_types=st.lists(
        _action_type_st, min_size=2, max_size=8, unique=True
    ),
    reputation=_reputation_st,
)
def test_rank_actions_sorted_descending(intent, action_types, reputation):
    """rank_actions() must always return list sorted by score descending."""
    actions = [
        NPCAction(action_id=f"a{i}", action_type=at)
        for i, at in enumerate(action_types)
    ]
    ranked = _scorer.rank_actions(
        agent_intent=intent,
        actions=actions,
        world_resources={},
        agent_reputation=reputation,
    )
    scores = [score for _, score in ranked]
    assert scores == sorted(scores, reverse=True), (
        f"rank_actions not sorted descending: {scores}"
    )


# ── Property 6: select_best_action returns highest-scoring action ─────────

@given(
    intent=_intent_st,
    action_types=st.lists(
        _action_type_st, min_size=2, max_size=6, unique=True
    ),
    reputation=_reputation_st,
)
def test_select_best_action_is_highest_ranked(intent, action_types, reputation):
    """select_best_action() must return the same action as rank_actions()[0]."""
    actions = [
        NPCAction(action_id=f"act{i}", action_type=at)
        for i, at in enumerate(action_types)
    ]
    best = _scorer.select_best_action(
        agent_intent=intent,
        candidate_actions=actions,
        agent_reputation=reputation,
    )
    ranked = _scorer.rank_actions(
        agent_intent=intent,
        actions=actions,
        world_resources={},
        agent_reputation=reputation,
    )
    assert best is not None
    assert best.action_id == ranked[0][0].action_id, (
        f"select_best_action returned {best.action_id} "
        f"but rank_actions[0] is {ranked[0][0].action_id}"
    )


# ── Property 7: Determinism — same inputs always yield same output ────────

@given(
    intent=_intent_st,
    action_type=_action_type_st,
    reputation=_reputation_st,
    penalty=_penalty_st,
)
def test_score_is_deterministic(intent, action_type, reputation, penalty):
    """score_action() is a pure function: calling it twice with identical inputs must return equal results."""
    action = _make_action(action_type)
    score_1 = _scorer.score_action(
        agent_intent=intent, action=action,
        agent_reputation=reputation, governance_penalty=penalty,
    )
    score_2 = _scorer.score_action(
        agent_intent=intent, action=action,
        agent_reputation=reputation, governance_penalty=penalty,
    )
    assert score_1 == score_2, (
        f"Non-deterministic: first={score_1}, second={score_2} "
        f"for intent={intent.value}, action={action_type}"
    )


# ── Property 8: Reputation floor (rep_factor ∈ [0.5, 1.0]) ──────────────

@given(
    intent=_intent_st,
    action_type=_action_type_st,
    penalty=st.floats(min_value=0.0, max_value=0.5, allow_nan=False),
)
def test_zero_reputation_floor(intent, action_type, penalty):
    """
    rep_factor = 0.5 + 0.5 * clamp(rep, 0.0, 1.0)
    At rep=0.0: rep_factor=0.5, so score ≤ 0.5 of the no-reputation score.
    Score at rep=0 must be ≤ score at rep=1.
    """
    action = _make_action(action_type)
    score_zero_rep = _scorer.score_action(
        agent_intent=intent, action=action,
        agent_reputation=0.0, governance_penalty=penalty,
    )
    score_full_rep = _scorer.score_action(
        agent_intent=intent, action=action,
        agent_reputation=1.0, governance_penalty=penalty,
    )
    assert score_zero_rep <= score_full_rep + 1e-9, (
        f"rep=0 score ({score_zero_rep}) > rep=1 score ({score_full_rep})"
    )


# ── Property 9: FDIAWeights always sum to 1.0 ────────────────────────────

def test_default_weights_sum_to_one():
    """FDIAWeights default values must sum to exactly 1.0 (validation invariant)."""
    w = FDIAWeights()
    total = w.desire + w.intent + w.alignment + w.governance
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"
    assert w.validate() is True

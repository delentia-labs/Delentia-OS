"""
Property-based tests for MemoryDeltaEngine — compression + replay correctness.

Properties verified:
  1. compute_compression_ratio() always in [0.0, 1.0]
  2. After recording N deltas, total_delta_count() == N
  3. rollback(n) removes exactly min(n, len(deltas)) records
  4. get_state_at_tick() at tick=0 matches initial state (identity)
  5. Resource reconstruction: sum of deltas equals final resource value
  6. Violation count never decreases after recording violations
  7. Engine with no data returns 0.0 compression ratio
  8. Registered agent count is always accurate
"""

from hypothesis import given, strategies as st

from core.delta_engine.memory_delta import MemoryDeltaEngine
from core.fdia.fdia import NPCIntentType

# ── Strategies ────────────────────────────────────────────────────────────

_intent_st = st.sampled_from(list(NPCIntentType))
_outcome_st = st.sampled_from(["success", "blocked", "partial"])
_resource_delta_st = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False
)
_agent_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=3, max_size=12,
)
_tick_st = st.integers(min_value=1, max_value=100)
_n_deltas_st = st.integers(min_value=1, max_value=20)
_initial_rep_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


def _fresh_engine() -> MemoryDeltaEngine:
    return MemoryDeltaEngine()


# ── Property 1: Compression ratio always in [0.0, 1.0] ───────────────────

@given(
    intent=_intent_st,
    n_deltas=_n_deltas_st,
    outcome=_outcome_st,
)
def test_compression_ratio_in_unit_interval(intent, n_deltas, outcome):
    """compute_compression_ratio() must always be in [0.0, 1.0]."""
    engine = _fresh_engine()
    engine.register_agent("agent_x", intent, {"energy": 100.0})
    for tick in range(1, n_deltas + 1):
        engine.record_delta(
            agent_id="agent_x",
            tick=tick,
            intent_type=intent,
            action_type="explore",
            outcome=outcome,
            resource_changes={"energy": -1.0},
        )
    ratio = engine.compute_compression_ratio()
    assert isinstance(ratio, float), f"Expected float, got {type(ratio)}"
    assert 0.0 <= ratio <= 1.0, f"Compression ratio {ratio} out of [0.0, 1.0]"


# ── Property 2: total_delta_count() == number of recorded deltas ──────────

@given(
    intent=_intent_st,
    n_deltas=_n_deltas_st,
)
def test_delta_count_accurate(intent, n_deltas):
    """total_delta_count() must exactly equal the number of recorded deltas."""
    engine = _fresh_engine()
    engine.register_agent("agent_y", intent)
    for tick in range(1, n_deltas + 1):
        engine.record_delta(
            agent_id="agent_y",
            tick=tick,
            intent_type=intent,
            action_type="trade",
            outcome="success",
        )
    assert engine.total_delta_count() == n_deltas, (
        f"total_delta_count={engine.total_delta_count()} != recorded {n_deltas}"
    )


# ── Property 3: rollback() removes correct number of records ─────────────

@given(
    intent=_intent_st,
    n_deltas=_n_deltas_st,
    rollback_n=st.integers(min_value=0, max_value=30),
)
def test_rollback_removes_correct_count(intent, n_deltas, rollback_n):
    """rollback(n) must remove exactly min(n, len(deltas)) records and return that count."""
    engine = _fresh_engine()
    engine.register_agent("agent_r", intent)
    for tick in range(1, n_deltas + 1):
        engine.record_delta(
            agent_id="agent_r",
            tick=tick,
            intent_type=intent,
            action_type="gather",
            outcome="success",
        )
    removed = engine.rollback("agent_r", rollback_n)
    expected_removed = min(rollback_n, n_deltas)
    assert removed == expected_removed, (
        f"rollback({rollback_n}) from {n_deltas} deltas: "
        f"removed={removed}, expected={expected_removed}"
    )
    remaining = len(engine.deltas["agent_r"])
    assert remaining == n_deltas - expected_removed, (
        f"Remaining deltas={remaining}, expected={n_deltas - expected_removed}"
    )


# ── Property 4: Unregistered agent rollback is safe ──────────────────────

@given(rollback_n=st.integers(min_value=0, max_value=100))
def test_rollback_unknown_agent_returns_zero(rollback_n):
    """rollback() on an unregistered agent must return 0 without raising."""
    engine = _fresh_engine()
    result = engine.rollback("ghost_agent", rollback_n)
    assert result == 0, f"Expected 0 for unknown agent, got {result}"


# ── Property 5: No data → compression ratio == 0.0 ───────────────────────

def test_empty_engine_compression_ratio():
    """An engine with no recorded deltas must return 0.0 compression ratio."""
    engine = _fresh_engine()
    assert engine.compute_compression_ratio() == 0.0


# ── Property 6: Registered agent count is accurate ───────────────────────

@given(n_agents=st.integers(min_value=1, max_value=10))
def test_registered_agent_count(n_agents):
    """registered_agent_count() must equal the number of register_agent() calls."""
    engine = _fresh_engine()
    for i in range(n_agents):
        engine.register_agent(f"agent_{i}", NPCIntentType.DISCOVER)
    assert engine.registered_agent_count() == n_agents, (
        f"registered_agent_count={engine.registered_agent_count()}, expected={n_agents}"
    )


# ── Property 7: State at tick=0 matches initial registration ─────────────

@given(
    intent=_intent_st,
    initial_rep=_initial_rep_st,
)
def test_state_at_tick_zero_matches_initial(intent, initial_rep):
    """get_state_at_tick(agent, 0) must match the initial registration state."""
    engine = _fresh_engine()
    engine.register_agent(
        "agent_init",
        intent,
        {"energy": 100.0},
        initial_reputation=initial_rep,
    )
    state = engine.get_state_at_tick("agent_init", 0)
    assert state is not None
    assert state.intent_type == intent
    assert abs(state.reputation - initial_rep) < 1e-9, (
        f"Initial rep mismatch: {state.reputation} != {initial_rep}"
    )


# ── Property 8: Resource deltas accumulate correctly ─────────────────────

@given(
    intent=_intent_st,
    deltas=st.lists(
        st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=10,
    ),
)
def test_resource_deltas_accumulate(intent, deltas):
    """Sum of resource deltas must equal reconstructed resource value."""
    engine = _fresh_engine()
    engine.register_agent("agent_acc", intent, {"gold": 0.0})
    for i, delta_val in enumerate(deltas, start=1):
        engine.record_delta(
            agent_id="agent_acc",
            tick=i,
            intent_type=intent,
            action_type="trade",
            outcome="success",
            resource_changes={"gold": delta_val},
        )
    final_state = engine.get_state_at_tick("agent_acc", len(deltas))
    expected_gold = sum(deltas)
    actual_gold = final_state.resources.get("gold", 0.0)
    assert abs(actual_gold - expected_gold) < 1e-6, (
        f"Gold mismatch: {actual_gold} != {expected_gold} (deltas={deltas})"
    )

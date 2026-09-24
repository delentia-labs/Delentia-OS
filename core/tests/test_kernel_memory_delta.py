"""
Round 43 item 5: real coverage for core/kernel/memory_delta.py, previously
untested (0 test files existed for it) despite being real, reachable code -
rct_control_plane/cli.py's `rct timeline` command imports MemoryDeltaEngine
from this exact module (not core/delta_engine/memory_delta.py, a
differently-located, separate file). All methods here are pure/deterministic
(no I/O, no randomness) so these tests need no mocking.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from core.kernel.memory_delta import MemoryDeltaEngine, MemoryDelta, AgentMemoryState
from core.kernel.fdia import NPCIntentType


class TestRegisterAgent:
    def test_register_creates_baseline_and_empty_deltas(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.ACCUMULATE, {"gold": 100.0}, 0.8)
        assert engine.registered_agent_count() == 1
        assert engine.deltas["a1"] == []
        baseline = engine.baseline_states["a1"]
        assert baseline.resources == {"gold": 100.0}
        assert baseline.reputation == 0.8

    def test_register_defaults_resources_and_reputation(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        baseline = engine.baseline_states["a1"]
        assert baseline.resources == {}
        assert baseline.reputation == 1.0

    def test_register_seeds_a_tick_zero_checkpoint(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        assert 0 in engine._checkpoints["a1"]


class TestRecordDelta:
    def test_record_delta_requires_prior_registration(self):
        engine = MemoryDeltaEngine()
        with pytest.raises(KeyError):
            engine.record_delta("ghost", 1, NPCIntentType.NEUTRAL, "idle", "success")

    def test_record_delta_appends_in_order(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.ACCUMULATE)
        engine.record_delta("a1", 1, NPCIntentType.ACCUMULATE, "trade", "success")
        engine.record_delta("a1", 2, NPCIntentType.ACCUMULATE, "collect", "success")
        assert [d.tick for d in engine.deltas["a1"]] == [1, 2]
        assert engine.total_delta_count() == 2

    def test_record_delta_defaults_optional_fields(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        engine.record_delta("a1", 1, NPCIntentType.NEUTRAL, "idle", "success")
        delta = engine.deltas["a1"][0]
        assert delta.resources_delta == {}
        assert delta.relationship_change == {}
        assert delta.governance_violation is False
        assert delta.changes == {}

    def test_record_delta_creates_checkpoint_at_interval(self):
        engine = MemoryDeltaEngine()
        engine.checkpoint_interval = 3
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        for tick in range(1, 4):
            engine.record_delta("a1", tick, NPCIntentType.NEUTRAL, "idle", "success")
        # 3rd record hits the interval -> a real checkpoint at tick 3
        assert 3 in engine._checkpoints["a1"]


class TestStateReconstruction:
    def _engine_with_history(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.ACCUMULATE, {"gold": 100.0}, initial_reputation=0.5)
        engine.record_delta("a1", 1, NPCIntentType.ACCUMULATE, "trade", "success",
                             resource_changes={"gold": 10.0})
        engine.record_delta("a1", 2, NPCIntentType.ACCUMULATE, "collect", "blocked",
                             governance_violation=True)
        engine.record_delta("a1", 3, NPCIntentType.ACCUMULATE, "trade", "success",
                             resource_changes={"gold": 5.0},
                             relationship_changes={"a2": 0.3})
        return engine

    def test_state_at_tick_zero_is_baseline(self):
        engine = self._engine_with_history()
        state = engine.get_state_at_tick("a1", 0)
        assert state.resources == {"gold": 100.0}
        assert state.reputation == 0.5

    def test_state_replays_resource_changes_cumulatively(self):
        engine = self._engine_with_history()
        state = engine.get_state_at_tick("a1", 3)
        assert state.resources["gold"] == 115.0

    def test_blocked_governance_violation_penalizes_reputation_and_counts(self):
        engine = self._engine_with_history()
        state = engine.get_state_at_tick("a1", 2)
        assert state.violation_count == 1
        # success at tick1 (+0.01) then blocked+violation at tick2 (-0.05)
        assert state.reputation == pytest.approx(0.5 + 0.01 - 0.05)

    def test_state_replays_relationship_changes(self):
        engine = self._engine_with_history()
        state = engine.get_state_at_tick("a1", 3)
        assert state.relationships["a2"] == pytest.approx(0.3)

    def test_state_stops_at_target_tick_not_beyond(self):
        engine = self._engine_with_history()
        state = engine.get_state_at_tick("a1", 1)
        assert state.resources["gold"] == 110.0
        assert state.violation_count == 0

    def test_replay_to_tick_is_an_alias_of_get_state_at_tick(self):
        engine = self._engine_with_history()
        a = engine.get_state_at_tick("a1", 2)
        b = engine.replay_to_tick("a1", 2)
        assert a.to_dict() == b.to_dict()

    def test_state_for_unregistered_agent_is_none(self):
        engine = MemoryDeltaEngine()
        assert engine.get_state_at_tick("ghost", 5) is None

    def test_reconstruction_uses_nearest_checkpoint_not_full_replay(self):
        # Real, meaningful behavior this test proves: with a checkpoint at
        # tick 3, querying tick 5 must NOT re-walk ticks 1-3 from baseline -
        # it should resume from the tick-3 checkpoint. Verified indirectly:
        # corrupting deltas before the checkpoint must not change the result.
        engine = MemoryDeltaEngine()
        engine.checkpoint_interval = 3
        engine.register_agent("a1", NPCIntentType.ACCUMULATE, {"gold": 0.0})
        for tick in range(1, 6):
            engine.record_delta("a1", tick, NPCIntentType.ACCUMULATE, "trade", "success",
                                 resource_changes={"gold": 1.0})
        assert 3 in engine._checkpoints["a1"]
        state_before = engine.get_state_at_tick("a1", 5)
        # Sabotage a pre-checkpoint delta - if reconstruction replayed from
        # baseline instead of the checkpoint, this would change the result.
        engine.deltas["a1"][0].resources_delta = {"gold": 999.0}
        state_after = engine.get_state_at_tick("a1", 5)
        assert state_after.resources["gold"] == state_before.resources["gold"] == 5.0


class TestRollback:
    def test_rollback_removes_last_n_deltas(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        for tick in range(1, 6):
            engine.record_delta("a1", tick, NPCIntentType.NEUTRAL, "idle", "success")
        removed = engine.rollback("a1", 2)
        assert removed == 2
        assert [d.tick for d in engine.deltas["a1"]] == [1, 2, 3]

    def test_rollback_clamps_to_available_deltas(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        engine.record_delta("a1", 1, NPCIntentType.NEUTRAL, "idle", "success")
        removed = engine.rollback("a1", 99)
        assert removed == 1
        assert engine.deltas["a1"] == []

    def test_rollback_on_unregistered_agent_is_a_real_noop(self):
        engine = MemoryDeltaEngine()
        assert engine.rollback("ghost", 3) == 0

    def test_rollback_invalidates_checkpoints_past_the_new_last_tick(self):
        engine = MemoryDeltaEngine()
        engine.checkpoint_interval = 2
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        for tick in range(1, 5):
            engine.record_delta("a1", tick, NPCIntentType.NEUTRAL, "idle", "success")
        assert 2 in engine._checkpoints["a1"] and 4 in engine._checkpoints["a1"]
        engine.rollback("a1", 3)  # last remaining delta is tick=1
        assert 2 not in engine._checkpoints["a1"]
        assert 4 not in engine._checkpoints["a1"]


class TestQueryHelpers:
    def test_get_recent_actions_returns_last_n_in_order(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        for i, action in enumerate(["a", "b", "c", "d"], start=1):
            engine.record_delta("a1", i, NPCIntentType.NEUTRAL, action, "success")
        assert engine.get_recent_actions("a1", n=2) == ["c", "d"]

    def test_get_recent_actions_for_unknown_agent_is_empty(self):
        engine = MemoryDeltaEngine()
        assert engine.get_recent_actions("ghost") == []

    def test_get_relationship_history_filters_by_other_id(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        engine.record_delta("a1", 1, NPCIntentType.NEUTRAL, "trade", "success",
                             relationship_changes={"a2": 0.2})
        engine.record_delta("a1", 2, NPCIntentType.NEUTRAL, "trade", "success",
                             relationship_changes={"a3": -0.1})
        engine.record_delta("a1", 3, NPCIntentType.NEUTRAL, "trade", "success",
                             relationship_changes={"a2": 0.1})
        history = engine.get_relationship_history("a1", "a2")
        assert history == [(1, 0.2), (3, 0.1)]

    def test_get_violation_count_only_counts_flagged_deltas(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        engine.record_delta("a1", 1, NPCIntentType.NEUTRAL, "idle", "blocked",
                             governance_violation=True)
        engine.record_delta("a1", 2, NPCIntentType.NEUTRAL, "idle", "success")
        engine.record_delta("a1", 3, NPCIntentType.NEUTRAL, "idle", "blocked",
                             governance_violation=True)
        assert engine.get_violation_count("a1") == 2


class TestCompressionRatio:
    def test_zero_before_any_recording(self):
        engine = MemoryDeltaEngine()
        assert engine.compute_compression_ratio() == 0.0

    def test_positive_ratio_after_recording_small_deltas(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        engine.record_delta("a1", 1, NPCIntentType.NEUTRAL, "idle", "success")
        ratio = engine.compute_compression_ratio()
        assert 0.0 < ratio <= 1.0

    def test_ratio_stays_within_0_and_1(self):
        engine = MemoryDeltaEngine()
        engine.register_agent("a1", NPCIntentType.NEUTRAL)
        # A huge changes payload could in principle exceed the naive
        # per-tick estimate - the real code clamps to [0, 1] regardless.
        engine.record_delta("a1", 1, NPCIntentType.NEUTRAL, "idle", "success",
                             extra_changes={"huge": "x" * 5000})
        assert 0.0 <= engine.compute_compression_ratio() <= 1.0


class TestToDictSerialization:
    def test_memory_delta_to_dict_rounds_and_sorts(self):
        delta = MemoryDelta(
            agent_id="a1", tick=1, intent_type=NPCIntentType.ACCUMULATE,
            action_type="trade", outcome="success",
            relationship_change={"b": 0.123456789, "a": 0.1},
            resources_delta={"wood": 1.0, "gold": 2.0},
        )
        d = delta.to_dict()
        assert d["intent_type"] == "ACCUMULATE"
        assert list(d["relationship_change"].keys()) == ["a", "b"]
        assert d["relationship_change"]["b"] == 0.123457
        assert list(d["resources_delta"].keys()) == ["gold", "wood"]

    def test_agent_memory_state_to_dict_reports_action_history_length_not_list(self):
        state = AgentMemoryState(
            agent_id="a1", tick=5, intent_type=NPCIntentType.NEUTRAL,
            action_history=["idle", "trade", "idle"],
        )
        d = state.to_dict()
        assert d["action_history_len"] == 3
        assert "action_history" not in d

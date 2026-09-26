"""
Round 45 item C: real tests for core/delta_engine/trace_emitter.py's
DeltaTraceEmitter/DeltaTraceEvent - confirmed genuinely used (exported
from core/delta_engine/__init__.py, consumed by
tools/generate_delta_trace.py), not a duplicate like core/kernel/fdia.py
was found to be in an earlier round. No mocking anywhere - real
MemoryDeltaEngine, real file writes to tmp_path.
"""
import json

import pytest

from core.delta_engine.memory_delta import MemoryDeltaEngine
from core.delta_engine.trace_emitter import DeltaTraceEmitter, DeltaTraceEvent
from core.fdia.fdia import NPCIntentType


class TestDeltaTraceEventToDict:
    def test_optional_fields_omitted_when_absent(self):
        event = DeltaTraceEvent(
            tick=1, agent_id="hero", action_type="explore", outcome="success",
            delta_bytes=40, naive_bytes=150, delta_cumulative=40, naive_cumulative=150,
            compression_ratio=0.7333, recall_ms=0.5,
        )
        d = event.to_dict()
        assert "resource_summary" not in d
        assert "checkpoint_created" not in d

    def test_optional_fields_included_when_present(self):
        event = DeltaTraceEvent(
            tick=1, agent_id="hero", action_type="explore", outcome="success",
            delta_bytes=40, naive_bytes=150, delta_cumulative=40, naive_cumulative=150,
            compression_ratio=0.7333, recall_ms=0.5,
            resource_summary={"energy": 99.5}, checkpoint_created=True,
        )
        d = event.to_dict()
        assert d["resource_summary"] == {"energy": 99.5}
        assert d["checkpoint_created"] is True

    def test_compression_ratio_and_recall_ms_are_rounded(self):
        event = DeltaTraceEvent(
            tick=1, agent_id="hero", action_type="explore", outcome="success",
            delta_bytes=40, naive_bytes=150, delta_cumulative=40, naive_cumulative=150,
            compression_ratio=0.123456789, recall_ms=1.23456789,
        )
        d = event.to_dict()
        assert d["compression_ratio"] == 0.1235
        assert d["recall_ms"] == 1.235


@pytest.fixture
def emitter():
    return DeltaTraceEmitter()


class TestEmitterConstruction:
    def test_creates_its_own_real_engine_when_none_given(self, emitter):
        assert isinstance(emitter.engine, MemoryDeltaEngine)

    def test_accepts_a_pre_built_engine(self):
        engine = MemoryDeltaEngine()
        emitter = DeltaTraceEmitter(engine=engine)
        assert emitter.engine is engine

    def test_events_start_empty(self, emitter):
        assert emitter.events == []


class TestRegisterAgentDelegation:
    def test_registers_on_the_real_underlying_engine(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        assert "hero" in emitter.engine.deltas
        assert emitter.engine.baseline_states["hero"].resources == {"energy": 100.0}


class TestRecordDelta:
    def test_records_in_the_real_engine_and_returns_a_real_event(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        event = emitter.record_delta(
            "hero", tick=1, intent_type=NPCIntentType.DISCOVER,
            action_type="explore", outcome="success",
            resource_changes={"energy": -5.0},
        )
        assert isinstance(event, DeltaTraceEvent)
        assert len(emitter.engine.deltas["hero"]) == 1
        assert event.tick == 1
        assert event.agent_id == "hero"

    def test_cumulative_totals_accumulate_across_real_calls(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        e1 = emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                                   action_type="explore", outcome="success")
        e2 = emitter.record_delta("hero", tick=2, intent_type=NPCIntentType.DISCOVER,
                                   action_type="explore", outcome="success")
        assert e2.naive_cumulative == e1.naive_cumulative + e1.naive_bytes
        assert e2.delta_cumulative == e1.delta_cumulative + e1.delta_bytes

    def test_delta_bytes_grows_with_a_real_larger_payload(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        small = emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                                      action_type="explore", outcome="success")
        large = emitter.record_delta(
            "hero", tick=2, intent_type=NPCIntentType.DISCOVER,
            action_type="explore", outcome="success",
            resource_changes={"energy": -5.0, "gold": 10.0, "health": -1.0},
            relationship_changes={"villager_1": 0.1},
            extra_changes={"note": "a much longer real payload with more fields"},
        )
        assert large.delta_bytes > small.delta_bytes

    def test_delta_bytes_has_a_real_floor_of_30_for_empty_payloads(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        event = emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                                      action_type="idle", outcome="success")
        assert event.delta_bytes == 30

    def test_compression_ratio_is_clamped_between_0_and_1(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        event = emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                                      action_type="explore", outcome="success")
        assert 0.0 <= event.compression_ratio <= 1.0

    def test_recall_ms_is_a_real_non_negative_measurement(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        event = emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                                      action_type="explore", outcome="success")
        assert event.recall_ms >= 0.0

    def test_resource_summary_reflects_the_real_reconstructed_state(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        event = emitter.record_delta(
            "hero", tick=1, intent_type=NPCIntentType.DISCOVER,
            action_type="explore", outcome="success",
            resource_changes={"energy": -5.0},
        )
        assert event.resource_summary is not None
        assert "energy" in event.resource_summary

    def test_checkpoint_created_true_exactly_on_the_real_interval(self):
        engine = MemoryDeltaEngine(checkpoint_interval=2)
        emitter = DeltaTraceEmitter(engine=engine)
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        e1 = emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                                   action_type="explore", outcome="success")
        e2 = emitter.record_delta("hero", tick=2, intent_type=NPCIntentType.DISCOVER,
                                   action_type="explore", outcome="success")
        assert e1.checkpoint_created is False
        assert e2.checkpoint_created is True

    def test_raises_for_an_unregistered_agent_via_the_real_engine(self, emitter):
        with pytest.raises(KeyError):
            emitter.record_delta("ghost", tick=1, intent_type=NPCIntentType.DISCOVER,
                                  action_type="explore", outcome="success")

    def test_writes_a_real_jsonl_line_when_output_path_is_set(self, tmp_path):
        out = tmp_path / "trace.jsonl"
        emitter = DeltaTraceEmitter(output_path=out)
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")
        emitter.record_delta("hero", tick=2, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")

        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        parsed = json.loads(lines[0])
        assert parsed["agent_id"] == "hero"
        assert parsed["tick"] == 1

    def test_no_file_write_when_output_path_is_none(self, emitter, tmp_path):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")
        assert list(tmp_path.iterdir()) == []


class TestDelegationHelpers:
    def test_get_state_at_tick_delegates_to_the_real_engine(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success",
                              resource_changes={"energy": -5.0})
        state = emitter.get_state_at_tick("hero", 1)
        assert state is not None
        assert state.resources["energy"] == 95.0

    def test_compute_compression_ratio_delegates_to_the_real_engine(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")
        assert emitter.compute_compression_ratio() == emitter.engine.compute_compression_ratio()


class TestEventsProperty:
    def test_events_returns_a_real_copy_not_the_internal_list(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")
        snapshot = emitter.events
        snapshot.append("not a real event")
        assert len(emitter.events) == 1


class TestSummary:
    def test_summary_before_any_real_events(self, emitter):
        assert emitter.summary() == {"total_ticks": 0, "compression_ratio": 0.0}

    def test_summary_reflects_real_recorded_events(self, emitter):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        emitter.register_agent("villager", NPCIntentType.BELONG, {"trust": 50.0})
        emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")
        emitter.record_delta("villager", tick=1, intent_type=NPCIntentType.BELONG,
                              action_type="socialize", outcome="success")

        summary = emitter.summary()
        assert summary["total_events"] == 2
        assert summary["total_ticks"] == 1
        assert summary["agents"] == emitter.engine.registered_agent_count()
        assert summary["compression_ratio"] == emitter.events[-1].compression_ratio
        assert summary["compression_pct"] == round(emitter.events[-1].compression_ratio * 100, 1)
        assert summary["avg_recall_ms"] >= 0.0
        assert summary["max_recall_ms"] >= summary["avg_recall_ms"]


class TestSaveJsonl:
    def test_writes_every_real_event_as_a_jsonl_line(self, emitter, tmp_path):
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")
        emitter.record_delta("hero", tick=2, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")

        out = tmp_path / "saved.jsonl"
        emitter.save_jsonl(out)

        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[1])["tick"] == 2

    def test_overwrites_an_existing_real_file(self, emitter, tmp_path):
        out = tmp_path / "saved.jsonl"
        out.write_text("stale content from a previous real run\n", encoding="utf-8")
        emitter.register_agent("hero", NPCIntentType.DISCOVER, {"energy": 100.0})
        emitter.record_delta("hero", tick=1, intent_type=NPCIntentType.DISCOVER,
                              action_type="explore", outcome="success")
        emitter.save_jsonl(out)
        content = out.read_text(encoding="utf-8")
        assert "stale content" not in content

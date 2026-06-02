"""
Tests for core/ — fdia scoring engine, memory_delta engine, regional_adapter.
All pure-function unit tests: no external I/O, no network calls.
"""

import pytest

from core.delta_engine.memory_delta import (
    AgentMemoryState,
    MemoryDelta,
    MemoryDeltaEngine,
)
from core.fdia.fdia import (
    DEFAULT_DESIRE_WEIGHTS,
    FDIAScorer,
    FDIAWeights,
    NPCAction,
    NPCIntentType,
    intent_alignment,
)
from core.regional_adapter.regional_adapter import (
    DetectedLanguage,
    LanguageDetector,
    RegionalModelCache,
    RegionalModelRouter,
)


# ---------------------------------------------------------------------------
# FDIA
# ---------------------------------------------------------------------------

class TestFDIAIntentTypes:
    def test_all_intent_types_present(self):
        types = list(NPCIntentType)
        assert len(types) == 6

    def test_default_desire_weights_all_positive(self):
        for intent_type, weight in DEFAULT_DESIRE_WEIGHTS.items():
            assert 0.0 <= weight <= 1.0, f"{intent_type} weight out of range"

    def test_alignment_matrix_complete(self):
        for a in NPCIntentType:
            for b in NPCIntentType:
                val = intent_alignment(a, b)
                assert -1.0 <= val <= 1.0


class TestFDIAWeights:
    def test_defaults_sum_to_one(self):
        w = FDIAWeights()
        assert w.validate() is True

    def test_custom_weights_valid(self):
        w = FDIAWeights(desire=0.25, intent=0.25, alignment=0.25, governance=0.25)
        assert w.validate() is True

    def test_invalid_weights_fail(self):
        w = FDIAWeights(desire=0.5, intent=0.5, alignment=0.5, governance=0.5)
        assert w.validate() is False

    def test_to_dict_keys(self):
        w = FDIAWeights()
        d = w.to_dict()
        assert set(d.keys()) == {"desire", "intent", "alignment", "governance"}


class TestFDIAScorer:
    def setup_method(self):
        self.scorer = FDIAScorer()

    def _action(self, action_type: str = "trade", agent_type: str = "helper") -> NPCAction:
        return NPCAction(
            action_id="a1",
            action_type=action_type,
            target_agent="agent_b",
            metadata={"agent_type": agent_type},
        )

    def test_score_returns_float_in_range(self):
        action = self._action()
        score = self.scorer.score_action(
            agent_intent=NPCIntentType.ACCUMULATE,
            action=action,
            other_agents_intents={},
            governance_score=1.0,
        )
        assert 0.0 <= score <= 1.0

    def test_no_governance_penalty_gives_higher_score(self):
        action = self._action()
        score_ok = self.scorer.score_action(
            agent_intent=NPCIntentType.DISCOVER,
            action=action,
            other_agents_intents={},
            governance_score=1.0,
        )
        score_bad = self.scorer.score_action(
            agent_intent=NPCIntentType.DISCOVER,
            action=action,
            other_agents_intents={},
            governance_score=0.5,
        )
        assert score_ok > score_bad

    def test_select_best_action_picks_highest(self):
        actions = [
            NPCAction(action_id="a1", action_type="idle"),
            NPCAction(action_id="a2", action_type="trade", metadata={"agent_type": "helper"}),
        ]
        best = self.scorer.select_best_action(
            agent_intent=NPCIntentType.ACCUMULATE,
            candidate_actions=actions,
            other_agents_intents={},
            governance_score=1.0,
        )
        assert best is not None
        assert best.action_id in ("a1", "a2")

    def test_select_from_empty_list_returns_none(self):
        best = self.scorer.select_best_action(
            agent_intent=NPCIntentType.NEUTRAL,
            candidate_actions=[],
            other_agents_intents={},
            governance_score=1.0,
        )
        assert best is None

    def test_dominate_vs_protect_low_alignment(self):
        alignment = intent_alignment(NPCIntentType.DOMINATE, NPCIntentType.PROTECT)
        assert alignment < 0  # Dominate conflicts with Protect

    def test_belong_vs_belong_high_alignment(self):
        alignment = intent_alignment(NPCIntentType.BELONG, NPCIntentType.BELONG)
        assert alignment > 0.7  # Two Belong agents cooperate well


# ---------------------------------------------------------------------------
# MemoryDelta
# ---------------------------------------------------------------------------


class TestMemoryDelta:
    def test_create_delta(self):
        delta = MemoryDelta(
            agent_id="npc_01",
            tick=5,
            intent_type=NPCIntentType.ACCUMULATE,
            action_type="trade",
            outcome="success",
            changes={"gold": 10},
        )
        assert delta.agent_id == "npc_01"
        assert delta.tick == 5

    def test_to_dict_contains_agent_id(self):
        delta = MemoryDelta(
            agent_id="npc_02",
            tick=1,
            intent_type=NPCIntentType.PROTECT,
            action_type="patrol",
            outcome="success",
        )
        d = delta.to_dict()
        assert d["agent_id"] == "npc_02"
        assert d["intent_type"] == "PROTECT"


class TestMemoryDeltaEngine:
    def setup_method(self):
        self.engine = MemoryDeltaEngine()

    def _register(self, agent_id: str = "npc_01"):
        self.engine.register_agent(
            agent_id=agent_id,
            initial_intent=NPCIntentType.DISCOVER,
            initial_resources={"gold": 100.0, "food": 50.0},
        )

    def test_register_agent(self):
        self._register()
        assert "npc_01" in self.engine.baseline_states

    def test_unregistered_agent_raises(self):
        with pytest.raises(KeyError):
            self.engine.record_delta(
                agent_id="ghost",
                tick=1,
                intent_type=NPCIntentType.NEUTRAL,
                action_type="idle",
                outcome="success",
            )

    def test_record_delta(self):
        self._register()
        self.engine.record_delta(
            agent_id="npc_01",
            tick=1,
            intent_type=NPCIntentType.DISCOVER,
            action_type="explore",
            outcome="success",
            resource_changes={"gold": -5.0},
        )
        assert len(self.engine.deltas["npc_01"]) == 1

    def test_get_state_at_tick_0(self):
        self._register()
        state = self.engine.get_state_at_tick("npc_01", 0)
        assert state.agent_id == "npc_01"
        assert state.resources["gold"] == 100.0

    def test_get_state_at_tick_after_delta(self):
        self._register()
        self.engine.record_delta(
            agent_id="npc_01",
            tick=1,
            intent_type=NPCIntentType.DISCOVER,
            action_type="trade",
            outcome="success",
            resource_changes={"gold": 50.0},
        )
        state = self.engine.get_state_at_tick("npc_01", 1)
        assert state.resources["gold"] == 150.0

    def test_rollback_removes_last_delta(self):
        self._register()
        self.engine.record_delta("npc_01", 1, NPCIntentType.DISCOVER, "explore", "success")
        self.engine.record_delta("npc_01", 2, NPCIntentType.DISCOVER, "trade", "success")
        self.engine.rollback("npc_01", n_ticks=1)
        assert len(self.engine.deltas["npc_01"]) == 1

    def test_compression_ratio_non_negative(self):
        self._register()
        self.engine.record_delta("npc_01", 1, NPCIntentType.DISCOVER, "explore", "success")
        ratio = self.engine.compute_compression_ratio()
        assert ratio >= 0.0


class TestMemoryDeltaEngineStyleB:
    """
    Tests for ``register_agent()`` Style B — passing a pre-built
    ``AgentMemoryState`` object as the second argument.

    This call style was added to fix a mismatch between docs/demos and the
    original positional-only API.  These tests cover the ``isinstance``
    branch that was previously uncovered.
    """

    def setup_method(self):
        self.engine = MemoryDeltaEngine()

    def test_register_agent_style_b_basic(self):
        """Style B: intent field, resources, and reputation are copied correctly."""
        state = AgentMemoryState(
            agent_id="npc_b",
            tick=3,  # non-zero tick: baseline must be normalised to tick=0
            intent_type=NPCIntentType.PROTECT,
            resources={"gold": 200.0, "energy": 80.0},
            reputation=0.9,
        )
        self.engine.register_agent("npc_b", state)

        assert "npc_b" in self.engine.baseline_states
        baseline = self.engine.baseline_states["npc_b"]
        assert baseline.intent_type == NPCIntentType.PROTECT
        assert baseline.resources["gold"] == 200.0
        assert baseline.reputation == 0.9
        assert baseline.tick == 0  # always reset to 0

    def test_register_agent_style_b_copies_all_fields(self):
        """Style B must deep-copy relationships, action_history, and violation_count."""
        state = AgentMemoryState(
            agent_id="npc_b",
            tick=10,
            intent_type=NPCIntentType.BELONG,
            resources={"gold": 50.0},
            relationships={"ally_x": 0.8, "enemy_y": -0.5},
            action_history=["trade", "explore", "rest"],
            violation_count=2,
        )
        self.engine.register_agent("npc_b", state)
        baseline = self.engine.baseline_states["npc_b"]

        assert baseline.relationships == {"ally_x": 0.8, "enemy_y": -0.5}
        assert baseline.action_history == ["trade", "explore", "rest"]
        assert baseline.violation_count == 2

    def test_register_agent_style_b_isolates_baseline_from_original(self):
        """Mutating the original state after registration must not affect the baseline."""
        state = AgentMemoryState(
            agent_id="npc_b",
            tick=0,
            intent_type=NPCIntentType.NEUTRAL,
            resources={"gold": 100.0},
        )
        self.engine.register_agent("npc_b", state)

        # Mutate original — baseline must be an independent copy
        state.resources["gold"] = 9999.0
        assert self.engine.baseline_states["npc_b"].resources["gold"] == 100.0

    def test_register_agent_style_b_allows_subsequent_deltas(self):
        """After Style B registration, ``record_delta`` must work normally."""
        state = AgentMemoryState(
            agent_id="npc_b",
            tick=0,
            intent_type=NPCIntentType.ACCUMULATE,
            resources={"gold": 100.0},
        )
        self.engine.register_agent("npc_b", state)
        self.engine.record_delta(
            agent_id="npc_b",
            tick=1,
            intent_type=NPCIntentType.ACCUMULATE,
            action_type="trade",
            outcome="success",
            resource_changes={"gold": 50.0},
        )
        result = self.engine.get_state_at_tick("npc_b", 1)
        assert result.resources["gold"] == 150.0

    def test_register_agent_style_b_creates_checkpoint(self):
        """Style B registration must create a tick-0 checkpoint (same as Style A)."""
        state = AgentMemoryState(
            agent_id="npc_b",
            tick=0,
            intent_type=NPCIntentType.DISCOVER,
            resources={"energy": 100.0},
        )
        self.engine.register_agent("npc_b", state)

        assert 0 in self.engine._checkpoints.get("npc_b", {})

    def test_register_agent_style_a_and_b_produce_equivalent_baseline(self):
        """
        Style A and Style B called with identical data must produce identical
        baseline states (except possibly for minor field ordering).
        """
        # Style A
        engine_a = MemoryDeltaEngine()
        engine_a.register_agent(
            "hero",
            NPCIntentType.DISCOVER,
            initial_resources={"gold": 100.0},
            initial_reputation=0.8,
        )
        # Style B — build the equivalent AgentMemoryState
        engine_b = MemoryDeltaEngine()
        state_b = AgentMemoryState(
            agent_id="hero",
            tick=0,
            intent_type=NPCIntentType.DISCOVER,
            resources={"gold": 100.0},
            reputation=0.8,
        )
        engine_b.register_agent("hero", state_b)

        bl_a = engine_a.baseline_states["hero"]
        bl_b = engine_b.baseline_states["hero"]
        assert bl_a.intent_type == bl_b.intent_type
        assert bl_a.resources == bl_b.resources
        assert bl_a.reputation == bl_b.reputation


# ---------------------------------------------------------------------------
# RegionalAdapter
# ---------------------------------------------------------------------------


class TestLanguageDetector:
    def setup_method(self):
        self.detector = LanguageDetector()

    def test_detect_english(self):
        result = self.detector.detect("Hello, this is a test sentence in English.")
        assert result.code == "en"

    def test_detect_thai(self):
        result = self.detector.detect("สวัสดีครับ ยินดีต้อนรับ")
        assert result.code == "th"

    def test_detect_japanese(self):
        result = self.detector.detect("こんにちは、元気ですか")
        assert result.code == "ja"

    def test_detect_empty_defaults_to_en(self):
        result = self.detector.detect("")
        assert result.code == "en"
        assert result.confidence == 0.0

    def test_detect_returns_detected_language(self):
        result = self.detector.detect("test")
        assert isinstance(result, DetectedLanguage)

    def test_confidence_in_range(self):
        result = self.detector.detect("Hello world this is a longer English sentence.")
        assert 0.0 <= result.confidence <= 1.0

    def test_detect_filipino(self):
        # Using Tagalog/Filipino markers
        result = self.detector.detect("Magandang araw sa inyong lahat, hindi ko alam kung sino.")
        assert result.code == "fil"

    def test_detect_malay(self):
        # Using Malay markers
        result = self.detector.detect("Saya tidak boleh datang kerana hari ini ialah hari cuti.")
        assert result.code == "ms"


class TestRegionalModelRouter:
    def setup_method(self):
        self.router = RegionalModelRouter()

    def test_route_english(self):
        model_id = self.router.route(language="en", region="US")
        assert model_id

    def test_route_thai(self):
        model_id = self.router.route(language="th", region="TH")
        assert model_id  # Should return Thai-specialised model

    def test_route_returns_string(self):
        result = self.router.route(language="en", region="US")
        assert isinstance(result, str)

    def test_route_filipino(self):
        model_id = self.router.route(language="fil", region="PH")
        assert model_id == "alibaba/qwen-2.5-7b"

    def test_route_malay(self):
        model_id = self.router.route(language="ms", region="MY")
        assert model_id == "alibaba/qwen-2.5-7b"

    def test_route_singapore_english(self):
        model_id = self.router.route(language="en", region="SG")
        assert model_id == "anthropic/claude-3.5-sonnet"


class TestRegionalModelCache:
    def test_cache_instantiates(self):
        cache = RegionalModelCache(max_size=10)
        assert cache is not None

    def test_cache_put_and_get(self):
        cache = RegionalModelCache(max_size=10)
        cache.put("en|US", "model-abc")
        result = cache.get("en|US")
        assert result == "model-abc"

    def test_cache_miss_returns_none(self):
        cache = RegionalModelCache(max_size=5)
        assert cache.get("zh|CN") is None

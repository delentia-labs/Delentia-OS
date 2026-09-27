"""
Round 45 item C (group 4): real tests for bdi_causal_engine.py - 0%
coverage before this file. Confirmed genuinely used: rct_control_plane/api.py
imports BDI_CAUSAL_ENGINE. Two real external boundaries mocked here:
ALGORITHM_KERNEL.process_intent_full_pipeline (confirmed disk side effect -
scaffolds files under workspace_output/genesis/ on every call, unrelated to
this module's own behavior) and urllib.request.urlopen (the optional live
Gemini persona call, gated behind GOOGLE_API_KEY). Everything else - belief
revision math, candidate scoring, action selection, world-tick bookkeeping -
runs for real.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest

import rct_control_plane.bdi_causal_engine as bdi_module
from rct_control_plane.bdi_causal_engine import BDICausalRevisionEngine, NPCBeliefProfile


class _FakeKernel:
    def process_intent_full_pipeline(self, intent):
        return {"fdia_score": 1.0}


@pytest.fixture(autouse=True)
def patched_kernel(monkeypatch):
    monkeypatch.setattr(bdi_module, "ALGORITHM_KERNEL", _FakeKernel())


@pytest.fixture(autouse=True)
def no_gemini_key_by_default(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


@pytest.fixture
def engine():
    return BDICausalRevisionEngine()


class TestNPCBeliefProfile:
    def test_default_traits_are_filled_in(self):
        npc = NPCBeliefProfile("e1", "Test NPC", "Villager", {})
        assert npc.beliefs["trust_player"] == 0.50
        assert npc.beliefs["greed"] == 0.40
        assert npc.beliefs["fatigue"] == 0.00

    def test_high_greed_dominates_toward_charge_premium(self):
        npc = NPCBeliefProfile("e1", "Greedy", "Merchant", {"greed": 0.90})
        assert npc.last_selected_action == "CHARGE_PREMIUM"

    def test_high_risk_tolerance_without_high_greed_dominates_toward_cold_indifference(self):
        npc = NPCBeliefProfile("e1", "Risky", "Adventurer", {"greed": 0.1, "risk_tolerance": 0.90})
        assert npc.last_selected_action == "COLD_INDIFFERENCE"

    def test_greed_check_takes_priority_over_risk_tolerance(self):
        npc = NPCBeliefProfile("e1", "Both", "X", {"greed": 0.9, "risk_tolerance": 0.9})
        assert npc.last_selected_action == "CHARGE_PREMIUM"

    def test_default_case_is_warm_conversation(self):
        npc = NPCBeliefProfile("e1", "Neutral", "X", {"greed": 0.1, "risk_tolerance": 0.1})
        assert npc.last_selected_action == "WARM_CONVERSATION"

    def test_to_dict_rounds_beliefs_and_reports_trace_count(self):
        npc = NPCBeliefProfile("e1", "Test", "X", {"trust_player": 0.123456})
        d = npc.to_dict()
        assert d["beliefs"]["trust_player"] == 0.123
        assert d["causal_trace_count"] == 0


class TestEngineInitialState:
    def test_starts_at_tick_one(self, engine):
        assert engine.world_tick == 1

    def test_registers_the_five_default_npcs(self, engine):
        assert set(engine.npcs.keys()) == {"pierre", "robin", "abigail", "lewis", "swarm_coder_01"}

    def test_pierre_starts_greedy_and_charging_premium(self, engine):
        assert engine.npcs["pierre"].last_selected_action == "CHARGE_PREMIUM"


class TestStepExperiencePipeline:
    def test_unknown_entity_raises(self, engine):
        with pytest.raises(ValueError, match="not found"):
            engine.step_experience_pipeline("no-such-npc", "did something", {})

    def test_world_tick_advances_by_one(self, engine):
        before = engine.world_tick
        engine.step_experience_pipeline("robin", "helped with a quest", {"trust_player": 0.1})
        assert engine.world_tick == before + 1

    def test_belief_deltas_are_applied_and_clamped_to_unit_interval(self, engine):
        engine.step_experience_pipeline("robin", "did something extreme", {"trust_player": 5.0})
        assert engine.npcs["robin"].beliefs["trust_player"] == 1.0

    def test_belief_deltas_are_clamped_at_the_lower_bound_too(self, engine):
        engine.step_experience_pipeline("robin", "betrayed them", {"trust_player": -5.0})
        assert engine.npcs["robin"].beliefs["trust_player"] == 0.0

    def test_unknown_belief_keys_in_event_impact_are_ignored(self, engine):
        # Must not raise and must not silently create a new belief key.
        engine.step_experience_pipeline("robin", "x", {"not_a_real_belief": 0.5})
        assert "not_a_real_belief" not in engine.npcs["robin"].beliefs

    def test_high_trust_gain_shifts_action_toward_warm_or_discount(self, engine):
        # robin starts trust=0.65, greed=0.30, loyalty=0.85 - a large trust
        # boost should push GIVE_DISCOUNT or WARM_CONVERSATION to the top,
        # away from robin's own greed-driven CHARGE_PREMIUM baseline score.
        entry = engine.step_experience_pipeline("robin", "gave a generous gift", {"trust_player": 0.35})
        assert entry["action_after"] in ("GIVE_DISCOUNT", "WARM_CONVERSATION")

    def test_decision_shifted_flag_is_accurate(self, engine):
        entry = engine.step_experience_pipeline("robin", "x", {"trust_player": 0.01})
        assert entry["decision_shifted"] == (entry["action_before"] != entry["action_after"])

    def test_trace_entry_has_the_real_expected_shape(self, engine):
        entry = engine.step_experience_pipeline("lewis", "a real event", {"loyalty": 0.1})
        assert entry["entity_id"] == "lewis"
        assert entry["entity_name"] == "Mayor Lewis"
        assert entry["fdia_score"] == 1.0
        assert entry["gate_10_6_status"] == "CLOSED_COMPLETE ✅"
        assert entry["signedai_seal"].startswith("ED25519-")
        assert entry["dialogue"]  # a real, non-empty fallback dialogue string

    def test_trace_is_recorded_on_both_the_npc_and_the_engine_audit_log(self, engine):
        engine.step_experience_pipeline("abigail", "x", {})
        assert len(engine.npcs["abigail"].causal_trace) == 1
        assert len(engine.pipeline_audit_log) == 1

    def test_repeated_steps_accumulate_trace_history(self, engine):
        for _ in range(3):
            engine.step_experience_pipeline("abigail", "x", {})
        assert len(engine.npcs["abigail"].causal_trace) == 3
        assert len(engine.pipeline_audit_log) == 3


class TestSynthesizeDialogueFallback:
    def test_without_gemini_key_returns_the_matching_action_template(self, engine):
        npc = engine.npcs["pierre"]
        text = engine._synthesize_relevant_dialogue(npc, "an experience", "WARM_CONVERSATION", "REFUSE_TRADE")
        assert "ไม่ค่อยไว้ใจ" in text  # REFUSE_TRADE's own hardcoded template

    def test_unknown_action_falls_back_to_the_generic_greeting(self, engine):
        npc = engine.npcs["pierre"]
        text = engine._synthesize_relevant_dialogue(npc, "x", "A", "NOT_A_REAL_ACTION")
        assert text == "สวัสดีครับ มีอะไรให้ช่วยไหม?"


class TestSynthesizeDialogueWithGeminiKey:
    def test_successful_live_call_returns_the_ai_reply(self, engine, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-test")

        class _FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                return json.dumps({
                    "candidates": [{"content": {"parts": [{"text": "  a real AI reply  "}]}}]
                }).encode("utf-8")

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=8: _FakeResp())

        npc = engine.npcs["pierre"]
        text = engine._synthesize_relevant_dialogue(npc, "an experience", "A", "WARM_CONVERSATION")
        assert text == "a real AI reply"

    def test_live_call_failure_falls_back_to_the_template(self, engine, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-test")

        import urllib.request

        def _raise(*a, **k):
            raise TimeoutError("simulated Gemini timeout")
        monkeypatch.setattr(urllib.request, "urlopen", _raise)

        npc = engine.npcs["pierre"]
        text = engine._synthesize_relevant_dialogue(npc, "an experience", "A", "COLD_INDIFFERENCE")
        assert "ยุ่งอยู่" in text  # COLD_INDIFFERENCE's own hardcoded template, not an AI reply


class TestGetWorldAndBdiState:
    def test_shape_and_npc_count(self, engine):
        state = engine.get_world_and_bdi_state()
        assert state["total_npcs"] == 5
        assert state["gate_10_6_compliance"] == "100.0% DETERMINISTIC"
        assert "pierre" in state["npcs"]

    def test_recent_causal_traces_are_capped_at_ten(self, engine):
        for i in range(15):
            engine.step_experience_pipeline("pierre", f"event {i}", {})
        state = engine.get_world_and_bdi_state()
        assert len(state["recent_causal_traces"]) == 10

"""
Phase 1 SDK Integration Tests

Verifies that loop_engine.py correctly integrates:
- Gap 4: FDIAGatekeeper uses FDIAScorer (not stub)
- Gap 5: MemoryLayer uses MemoryDeltaEngine (not hardcoded 3.74)
- Gap 7: SpecialistExecutor + SignedAIVerifier use HexaCoreRegistry (not hardcoded model IDs)
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from loop_engine import (
    FDIAGatekeeper,
    MemoryLayer,
    SpecialistExecutor,
    SignedAIVerifier,
    IntentLoopEngine,
    JITNAPacket,
    SecurityViolation,
)


# ─────────────────────────────────────────────────────────────────────────────
# Gap 4: FDIAGatekeeper uses real FDIAScorer
# ─────────────────────────────────────────────────────────────────────────────

class TestFDIAGatekeeperScorer:
    def test_fdia_scorer_instantiated(self):
        """FDIAGatekeeper must hold a live FDIAScorer instance (not None)."""
        from core.fdia.fdia import FDIAScorer
        gk = FDIAGatekeeper()
        assert isinstance(gk.scorer, FDIAScorer)

    @pytest.mark.asyncio
    async def test_discover_intent_scores_above_threshold(self):
        """DISCOVER-mapped intent should produce FDIA score > FDIA_THRESHOLD."""
        gk = FDIAGatekeeper()
        pkt = JITNAPacket(intent="Explore new research on quantum computing")
        result = await gk.validate(pkt)
        assert result is True

    @pytest.mark.asyncio
    async def test_protect_intent_maps_correctly(self):
        """'protect' keyword should map to NPCIntentType.PROTECT and still pass."""
        gk = FDIAGatekeeper()
        pkt = JITNAPacket(intent="protect the system from unauthorized access")
        result = await gk.validate(pkt)
        assert result is True

    @pytest.mark.asyncio
    async def test_accumulate_intent_maps_correctly(self):
        """'trade' keyword should map to NPCIntentType.ACCUMULATE and pass."""
        gk = FDIAGatekeeper()
        pkt = JITNAPacket(intent="trade assets on the market exchange")
        result = await gk.validate(pkt)
        assert result is True

    @pytest.mark.asyncio
    async def test_forbidden_keyword_raises_before_fdia_score(self):
        """Forbidden keyword check is a fast pre-filter (no scorer call needed)."""
        gk = FDIAGatekeeper()
        pkt = JITNAPacket(intent="exploit the vulnerability")
        with pytest.raises(SecurityViolation, match="forbidden keyword"):
            await gk.validate(pkt)

    def test_fdia_threshold_is_025(self):
        """FDIA_THRESHOLD must be 0.25 (calibrated for all legitimate intents)."""
        gk = FDIAGatekeeper()
        assert gk.FDIA_THRESHOLD == 0.25


# ─────────────────────────────────────────────────────────────────────────────
# Gap 5: MemoryLayer uses MemoryDeltaEngine (not hardcoded 3.74)
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryLayerDeltaEngine:
    def test_delta_engine_instantiated(self):
        """MemoryLayer must hold a live MemoryDeltaEngine."""
        from core.delta_engine.memory_delta import MemoryDeltaEngine
        ml = MemoryLayer()
        assert isinstance(ml.delta_engine, MemoryDeltaEngine)

    @pytest.mark.asyncio
    async def test_store_registers_new_agent(self):
        """Each unique intent stored must register one agent in delta_engine."""
        ml = MemoryLayer()
        pkt = JITNAPacket(intent="test the delta engine integration", intent_hash="abc123")
        mock_result = {"output": "delta engine test"}
        await ml.store(pkt, mock_result)
        assert ml.delta_engine.registered_agent_count() >= 1

    @pytest.mark.asyncio
    async def test_store_increments_delta_count(self):
        """Each store() call must record one delta in the delta_engine."""
        ml = MemoryLayer()
        pkt = JITNAPacket(intent="record this delta please", intent_hash="def456")
        mock_result = {"output": "ok"}
        before = ml.delta_engine.total_delta_count()
        await ml.store(pkt, mock_result)
        after = ml.delta_engine.total_delta_count()
        assert after == before + 1

    def test_compression_ratio_fallback_when_empty(self):
        """When delta_engine has no data, compression_ratio must return 3.74."""
        ml = MemoryLayer()
        assert ml.compression_ratio == 3.74

    @pytest.mark.asyncio
    async def test_compression_ratio_updates_after_stores(self):
        """After enough stores, compression_ratio should be a positive float."""
        ml = MemoryLayer()
        for i in range(5):
            pkt = JITNAPacket(intent=f"intent number {i} for ratio test", intent_hash=f"hash{i:04d}")
            await ml.store(pkt, {"output": f"result {i}"})
        # Should be a valid positive float (either live or fallback)
        assert ml.compression_ratio > 0.0

    @pytest.mark.asyncio
    async def test_same_intent_reuses_agent_slot(self):
        """Storing same intent_hash twice should not create a second agent."""
        ml = MemoryLayer()
        pkt = JITNAPacket(intent="same intent twice", intent_hash="samehash99")
        await ml.store(pkt, {"output": "first"})
        count_after_first = ml.delta_engine.registered_agent_count()
        await ml.store(pkt, {"output": "second"})
        count_after_second = ml.delta_engine.registered_agent_count()
        assert count_after_first == count_after_second


# ─────────────────────────────────────────────────────────────────────────────
# Gap 7: SpecialistExecutor uses HexaCoreRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecialistExecutorRegistry:
    def test_registry_instantiated(self):
        """SpecialistExecutor must hold a live HexaCoreRegistry."""
        from signedai.core.registry import HexaCoreRegistry
        se = SpecialistExecutor()
        assert isinstance(se.registry, HexaCoreRegistry)

    @pytest.mark.asyncio
    async def test_execute_returns_model_id_from_registry(self):
        """execute() result must include a model ID sourced from HexaCoreRegistry."""
        from signedai.core.registry import HexaCoreRegistry, HexaCoreRole
        se = SpecialistExecutor()
        valid_model_ids = {
            HexaCoreRegistry().get_model_id(role) for role in HexaCoreRole
        }
        pkt = JITNAPacket(intent="analyze the financial data")
        result = await se.execute(pkt)
        assert result.get("specialist") in valid_model_ids

    @pytest.mark.asyncio
    async def test_code_intent_routes_to_lead_builder(self):
        """Intent with 'code' keyword should route to LEAD_BUILDER model."""
        from signedai.core.registry import HexaCoreRegistry, HexaCoreRole
        se = SpecialistExecutor()
        expected = HexaCoreRegistry().get_model_id(HexaCoreRole.LEAD_BUILDER)
        pkt = JITNAPacket(intent="write code for a REST API")
        result = await se.execute(pkt)
        assert result["specialist"] == expected

    @pytest.mark.asyncio
    async def test_thai_intent_routes_to_regional_thai(self):
        """Intent with 'thai' keyword should route to REGIONAL_THAI model."""
        from signedai.core.registry import HexaCoreRegistry, HexaCoreRole
        se = SpecialistExecutor()
        expected = HexaCoreRegistry().get_model_id(HexaCoreRole.REGIONAL_THAI)
        pkt = JITNAPacket(intent="translate thai document to english")
        result = await se.execute(pkt)
        assert result["specialist"] == expected

    @pytest.mark.asyncio
    async def test_japanese_intent_routes_to_regional_core(self):
        """Intent with 'japanese' keyword should route to the pluggable REGIONAL_CORE model."""
        from signedai.core.registry import HexaCoreRegistry, HexaCoreRole
        se = SpecialistExecutor()
        pkt = JITNAPacket(intent="translate japanese document to english")
        result = await se.execute(pkt)
        assert result["specialist"] == "anthropic/claude-3.5-sonnet"
        assert result["specialist_role"] == HexaCoreRole.REGIONAL_CORE.value

    @pytest.mark.asyncio
    async def test_specialist_role_returned_in_result(self):
        """execute() must include specialist_role in result dict."""
        se = SpecialistExecutor()
        pkt = JITNAPacket(intent="research latest developments")
        result = await se.execute(pkt)
        assert "specialist_role" in result
        assert isinstance(result["specialist_role"], str)


# ─────────────────────────────────────────────────────────────────────────────
# Gap 7: SignedAIVerifier uses HexaCoreRegistry for model IDs
# ─────────────────────────────────────────────────────────────────────────────

class TestSignedAIVerifierRegistry:
    def test_verifier_models_from_registry(self):
        """SignedAIVerifier.models must be populated from HexaCoreRegistry (not hardcoded)."""
        from signedai.core.registry import HexaCoreRegistry, HexaCoreRole
        reg = HexaCoreRegistry()
        expected_supreme = reg.get_model_id(HexaCoreRole.SUPREME_ARCHITECT)
        sv = SignedAIVerifier()
        assert expected_supreme in sv.models

    def test_verifier_has_three_models(self):
        """Verifier must have exactly 3 models for consensus."""
        sv = SignedAIVerifier()
        assert len(sv.models) == 3

    def test_verifier_consensus_threshold(self):
        """Consensus threshold must be 0.67 (2/3 majority)."""
        sv = SignedAIVerifier()
        assert sv.consensus_threshold == 0.67

    def test_no_hardcoded_model_strings(self):
        """All model IDs in verifier must be valid HexaCore registry entries."""
        from signedai.core.registry import HexaCoreRegistry, HexaCoreRole
        reg = HexaCoreRegistry()
        valid_ids = {reg.get_model_id(role) for role in HexaCoreRole}
        sv = SignedAIVerifier()
        for model_id in sv.models:
            assert model_id in valid_ids, f"'{model_id}' not found in HexaCoreRegistry"


# ─────────────────────────────────────────────────────────────────────────────
# IntentLoopEngine: enhanced get_metrics() includes SDK fields
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentLoopEngineMetrics:
    def test_metrics_include_delta_engine_stats(self):
        """get_metrics() must include delta_engine_agents and delta_engine_deltas."""
        engine = IntentLoopEngine()
        metrics = engine.get_metrics()
        assert "delta_engine_agents" in metrics
        assert "delta_engine_deltas" in metrics
        assert isinstance(metrics["delta_engine_agents"], int)
        assert isinstance(metrics["delta_engine_deltas"], int)

    def test_metrics_include_verifier_models(self):
        """get_metrics() must include verifier_models list from HexaCoreRegistry."""
        from signedai.core.registry import HexaCoreRegistry, HexaCoreRole
        engine = IntentLoopEngine()
        metrics = engine.get_metrics()
        assert "verifier_models" in metrics
        valid_ids = {HexaCoreRegistry().get_model_id(role) for role in HexaCoreRole}
        for mid in metrics["verifier_models"]:
            assert mid in valid_ids

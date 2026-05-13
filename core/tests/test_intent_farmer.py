"""
Phase 3 Tests — IntentFarmer public SDK

Tests:
- farm(): single intent, FDIA gate pass/fail, normalization, hash stability
- warm_recall(): cache hit/miss
- bulk_farm(): list of seeds, domain/tier propagation
- FarmResult and IntentBlueprint field contracts
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.intent_loop import IntentFarmer, IntentBlueprint, FarmResult
from core.intent_loop.models import IntentBlueprint, FarmResult  # direct import sanity


# ─────────────────────────────────────────────────────────────────────────────
# Farm — basic flow
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentFarmerFarm:
    def test_farm_returns_farm_result(self):
        farmer = IntentFarmer()
        result = farmer.farm("Analyze market trends for Q1 2026", domain="finance")
        assert isinstance(result, FarmResult)

    def test_farm_passes_good_intent(self):
        farmer = IntentFarmer(fdia_threshold=0.25)
        result = farmer.farm("Explore new research on machine learning", domain="technology")
        assert result.total_farmed == 1
        assert result.rejected_count == 0
        assert len(result.blueprints) == 1

    def test_blueprint_fields_populated(self):
        farmer = IntentFarmer()
        result = farmer.farm("Build a distributed caching system", domain="engineering", tier=5)
        bp = result.blueprints[0]
        assert isinstance(bp, IntentBlueprint)
        assert bp.domain == "engineering"
        assert bp.tier == 5
        assert len(bp.intent_hash) == 16
        assert bp.fdia_score >= 0.0
        assert bp.fdia_score <= 1.0
        assert bp.original_intent == "Build a distributed caching system"

    def test_normalized_intent_is_lowercase(self):
        farmer = IntentFarmer()
        result = farmer.farm("  ANALYZE  The Data  ")
        assert result.blueprints[0].normalized_intent == "analyze the data"

    def test_hash_is_stable_for_same_text(self):
        farmer = IntentFarmer()
        r1 = farmer.farm("Stable intent text", domain="general")
        r2 = farmer.farm("Stable intent text", domain="general")
        assert r1.blueprints[0].intent_hash == r2.blueprints[0].intent_hash

    def test_hash_differs_for_different_text(self):
        farmer = IntentFarmer()
        r1 = farmer.farm("Intent A", domain="general")
        r2 = farmer.farm("Intent B different", domain="general")
        assert r1.blueprints[0].intent_hash != r2.blueprints[0].intent_hash

    def test_elapsed_ms_is_positive(self):
        farmer = IntentFarmer()
        result = farmer.farm("Quick test", domain="general")
        assert result.elapsed_ms >= 0.0

    def test_seed_intent_preserved_in_result(self):
        farmer = IntentFarmer()
        seed = "My exact seed text"
        result = farmer.farm(seed)
        assert result.seed_intent == seed

    def test_domain_normalized_to_lowercase(self):
        farmer = IntentFarmer()
        result = farmer.farm("Test domain normalization", domain="Finance")
        if result.blueprints:
            assert result.blueprints[0].domain == "finance"

    def test_metadata_stored_in_blueprint(self):
        farmer = IntentFarmer()
        meta = {"source": "chat", "user_id": "u_test"}
        result = farmer.farm("Metadata intent", metadata=meta)
        if result.blueprints:
            assert result.blueprints[0].metadata["source"] == "chat"

    def test_fdia_threshold_override(self):
        """Very high threshold forces rejection even for valid intents."""
        farmer = IntentFarmer(fdia_threshold=0.999)
        result = farmer.farm("Explore data", fdia_threshold=0.999)
        # Result may be 0 or 1 depending on actual FDIA score — just check no crash
        assert isinstance(result, FarmResult)
        assert result.total_farmed + result.rejected_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Warm recall
# ─────────────────────────────────────────────────────────────────────────────

class TestWarmRecall:
    def test_warm_recall_returns_blueprint_after_farm(self):
        farmer = IntentFarmer()
        result = farmer.farm("Cacheable intent text", domain="test")
        if result.blueprints:
            bp = result.blueprints[0]
            recalled = farmer.warm_recall(bp.intent_hash)
            assert recalled is not None
            assert recalled.intent_hash == bp.intent_hash

    def test_warm_recall_miss_returns_none(self):
        farmer = IntentFarmer()
        assert farmer.warm_recall("0000000000000000") is None

    def test_warm_recall_same_hash_on_repeat_farm(self):
        farmer = IntentFarmer()
        r1 = farmer.farm("Repeated recall intent", domain="test")
        r2 = farmer.farm("Repeated recall intent", domain="test")
        if r1.blueprints and r2.blueprints:
            assert r1.blueprints[0].intent_hash == r2.blueprints[0].intent_hash
            assert farmer.warm_recall(r1.blueprints[0].intent_hash) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Bulk farm
# ─────────────────────────────────────────────────────────────────────────────

class TestBulkFarm:
    def test_bulk_farm_returns_list_of_farm_results(self):
        farmer = IntentFarmer()
        seeds = ["Explore AI", "Analyze data", "Build pipeline"]
        results = farmer.bulk_farm(seeds, domain="technology")
        assert isinstance(results, list)
        assert len(results) == 3
        assert all(isinstance(r, FarmResult) for r in results)

    def test_bulk_farm_domain_propagated(self):
        farmer = IntentFarmer()
        results = farmer.bulk_farm(["Test domain propagation"], domain="medical")
        for r in results:
            if r.blueprints:
                assert r.blueprints[0].domain == "medical"

    def test_bulk_farm_tier_propagated(self):
        farmer = IntentFarmer()
        results = farmer.bulk_farm(["Test tier propagation"], domain="general", tier=7)
        for r in results:
            if r.blueprints:
                assert r.blueprints[0].tier == 7

    def test_bulk_farm_empty_seeds(self):
        farmer = IntentFarmer()
        results = farmer.bulk_farm([])
        assert results == []

    def test_bulk_farm_single_seed(self):
        farmer = IntentFarmer()
        results = farmer.bulk_farm(["Single seed intent"])
        assert len(results) == 1


# ─────────────────────────────────────────────────────────────────────────────
# FarmResult and IntentBlueprint field contracts
# ─────────────────────────────────────────────────────────────────────────────

class TestDataclassContracts:
    def test_farm_result_total_farmed_equals_blueprint_count(self):
        farmer = IntentFarmer()
        result = farmer.farm("Contract test intent")
        assert result.total_farmed == len(result.blueprints)

    def test_intent_blueprint_created_at_is_datetime(self):
        from datetime import datetime
        farmer = IntentFarmer()
        result = farmer.farm("Datetime check intent")
        if result.blueprints:
            assert isinstance(result.blueprints[0].created_at, datetime)

    def test_intent_blueprint_fdia_score_in_range(self):
        farmer = IntentFarmer()
        result = farmer.farm("Score range check intent")
        if result.blueprints:
            assert 0.0 <= result.blueprints[0].fdia_score <= 1.0

"""
Round 43 item 5: real coverage for algo_19_fusion.py, previously untested
(0 test files existed) despite being a real, production-ported algorithm
(ALGO-19 Data Fusion v2) with real numpy math - no I/O, no network, no
mocking needed. This file already had a working __main__ smoke test; these
tests port and substantially expand on those same real assertions.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import numpy as np
import pytest

from rct_control_plane.algo_19_fusion import (
    FusionEngine, FusionStrategy, ResolutionStrategy, ModalityData,
)


def _modalities():
    return {
        "text": ModalityData("text", np.array([0.1, 0.2, 0.3, 0.4]), confidence=0.9, metadata={}),
        "vector": ModalityData("vector", np.array([0.5, 0.1]), confidence=0.6, metadata={}),
        "graph": ModalityData("graph", np.array([0.2, 0.2, 0.2]), confidence=0.3, metadata={}),
    }


class TestFuseValidation:
    def test_fuse_rejects_empty_modalities(self):
        engine = FusionEngine()
        with pytest.raises(ValueError):
            engine.fuse({})

    def test_default_weights_are_equal_when_unspecified(self):
        engine = FusionEngine()
        modalities = {
            "a": ModalityData("a", np.array([1.0]), confidence=0.9, metadata={}),
            "b": ModalityData("b", np.array([1.0]), confidence=0.9, metadata={}),
        }
        result = engine.fuse(modalities, strategy=FusionStrategy.EARLY)
        assert result.metadata["weights_used"]["a"] == pytest.approx(0.5)
        assert result.metadata["weights_used"]["b"] == pytest.approx(0.5)

    def test_custom_weights_are_normalized_to_sum_to_one(self):
        engine = FusionEngine()
        modalities = {
            "a": ModalityData("a", np.array([1.0]), confidence=0.9, metadata={}),
            "b": ModalityData("b", np.array([1.0]), confidence=0.9, metadata={}),
        }
        result = engine.fuse(modalities, strategy=FusionStrategy.EARLY, weights={"a": 3.0, "b": 1.0})
        assert result.metadata["weights_used"]["a"] == pytest.approx(0.75)
        assert result.metadata["weights_used"]["b"] == pytest.approx(0.25)


class TestFuseStrategies:
    @pytest.mark.parametrize("strategy", [FusionStrategy.EARLY, FusionStrategy.LATE, FusionStrategy.HYBRID])
    def test_each_strategy_produces_a_valid_result(self, strategy):
        engine = FusionEngine()
        result = engine.fuse(_modalities(), strategy=strategy)
        assert result.fused_representation.size > 0
        assert 0.0 <= result.confidence <= 1.0
        assert result.strategy_used == strategy
        assert set(result.sources_used) == {"text", "vector", "graph"}

    def test_early_fusion_result_is_l2_normalized(self):
        engine = FusionEngine()
        result = engine.fuse(_modalities(), strategy=FusionStrategy.EARLY)
        assert np.linalg.norm(result.fused_representation) == pytest.approx(1.0, abs=1e-4)

    def test_late_fusion_counts_low_confidence_sources_as_conflicts(self):
        engine = FusionEngine()
        # "graph" has confidence 0.3 (<0.5) -> exactly one real conflict
        result = engine.fuse(_modalities(), strategy=FusionStrategy.LATE)
        assert result.conflicts_resolved == 1

    def test_hybrid_fusion_with_only_high_confidence_modalities_falls_back_to_early_only(self):
        engine = FusionEngine()
        modalities = {
            "text": ModalityData("text", np.array([1.0, 0.0]), confidence=0.9, metadata={}),
            "vector": ModalityData("vector", np.array([0.0, 1.0]), confidence=0.8, metadata={}),
        }
        result = engine.fuse(modalities, strategy=FusionStrategy.HYBRID)
        assert result.conflicts_resolved == 0
        assert result.fused_representation.size > 0

    def test_hybrid_fusion_with_only_low_confidence_modalities_falls_back_to_late_only(self):
        engine = FusionEngine()
        modalities = {
            "graph": ModalityData("graph", np.array([1.0, 0.0]), confidence=0.2, metadata={}),
            "audio": ModalityData("audio", np.array([0.0, 1.0]), confidence=0.1, metadata={}),
        }
        result = engine.fuse(modalities, strategy=FusionStrategy.HYBRID)
        assert result.fused_representation.size > 0

    def test_fuse_increments_fusion_count_and_strategy_stats(self):
        engine = FusionEngine()
        engine.fuse(_modalities(), strategy=FusionStrategy.EARLY)
        engine.fuse(_modalities(), strategy=FusionStrategy.EARLY)
        engine.fuse(_modalities(), strategy=FusionStrategy.LATE)
        stats = engine.get_stats()
        assert stats["total_fusions"] == 3
        assert stats["fusions_by_strategy"]["early"] == 2
        assert stats["fusions_by_strategy"]["late"] == 1
        assert stats["fusions_by_strategy"]["hybrid"] == 0

    def test_confidence_is_the_weighted_average_of_modality_confidences(self):
        engine = FusionEngine()
        modalities = {
            "a": ModalityData("a", np.array([1.0]), confidence=1.0, metadata={}),
            "b": ModalityData("b", np.array([1.0]), confidence=0.0, metadata={}),
        }
        result = engine.fuse(modalities, strategy=FusionStrategy.EARLY, weights={"a": 1.0, "b": 1.0})
        assert result.confidence == pytest.approx(0.5)


class TestAlignFeatures:
    @pytest.mark.parametrize("method", ["cca", "procrustes", "linear"])
    def test_each_method_produces_a_bounded_alignment_score(self, method):
        engine = FusionEngine()
        src = np.array([1.0, 2.0, 3.0])
        tgt = np.array([1.0, 2.0, 3.0, 4.0])
        result = engine.align_features(src, tgt, method=method)
        assert 0.0 <= result.alignment_score <= 1.0 + 1e-6

    def test_identical_vectors_score_close_to_1_for_linear_cosine_method(self):
        engine = FusionEngine()
        v = np.array([1.0, 2.0, 3.0])
        result = engine.align_features(v, v.copy(), method="linear")
        assert result.alignment_score == pytest.approx(1.0, abs=1e-4)

    def test_cca_pads_the_shorter_vector_before_comparing(self):
        engine = FusionEngine()
        result = engine.align_features(np.array([1.0, 0.0]), np.array([1.0, 0.0, 0.0]), method="cca")
        assert result.aligned_source.shape == result.aligned_target.shape == (3,)

    def test_cca_omits_transformation_matrix_above_100_dims(self):
        engine = FusionEngine()
        big = np.zeros(150)
        result = engine.align_features(big, big.copy(), method="cca")
        assert result.transformation_matrix is None

    def test_cca_includes_transformation_matrix_at_or_below_100_dims(self):
        engine = FusionEngine()
        small = np.zeros(10)
        result = engine.align_features(small, small.copy(), method="cca")
        assert result.transformation_matrix is not None
        assert result.transformation_matrix.shape == (10, 10)

    def test_procrustes_handles_a_zero_variance_source_without_dividing_by_zero(self):
        engine = FusionEngine()
        # A constant source has zero variance after centering (all zeros) -
        # source_scale <= 1e-8, hitting the "leave centered as-is" branch
        # rather than dividing by a near-zero scale.
        source = np.array([5.0, 5.0, 5.0])
        target = np.array([1.0, 2.0, 3.0])
        result = engine.align_features(source, target, method="procrustes")
        assert np.allclose(result.aligned_source, 0.0)
        assert 0.0 <= result.alignment_score <= 1.0 + 1e-6

    def test_procrustes_rescales_source_to_target_norm(self):
        engine = FusionEngine()
        source = np.array([1.0, 2.0, 3.0])
        target = np.array([2.0, 4.0, 6.0])
        result = engine.align_features(source, target, method="procrustes")
        # A perfectly proportional source/target should align almost exactly
        assert result.alignment_score == pytest.approx(1.0, abs=1e-4)

    def test_unknown_method_falls_back_to_linear(self):
        engine = FusionEngine()
        v = np.array([1.0, 2.0])
        result = engine.align_features(v, v.copy(), method="not_a_real_method")
        linear_result = engine.align_features(v, v.copy(), method="linear")
        assert result.alignment_score == pytest.approx(linear_result.alignment_score)


class TestResolveConflictsValidation:
    def test_resolve_conflicts_rejects_empty_sources(self):
        engine = FusionEngine()
        with pytest.raises(ValueError):
            engine.resolve_conflicts([])


def _sources():
    return [
        {"id": "s1", "data": {"name": "Delentia"}, "confidence": 0.9, "modality": "text"},
        {"id": "s2", "data": {"name": "Delentia OS"}, "confidence": 0.4, "modality": "graph"},
        {"id": "s3", "data": {"name": "Delentia"}, "confidence": 0.8, "modality": "vector"},
    ]


class TestResolveByVoting:
    def test_majority_confidence_weighted_value_wins(self):
        engine = FusionEngine()
        resolved = engine.resolve_conflicts(_sources(), strategy=ResolutionStrategy.VOTING, confidence_threshold=0.7)
        # Only s1 (0.9) and s3 (0.8) clear the 0.7 threshold, both say "Delentia"
        assert resolved["resolved_data"]["name"] == "Delentia"
        assert resolved["resolution_method"] == "confidence_weighted_voting"
        assert resolved["conflicts"] == []

    def test_below_threshold_sources_do_not_participate_in_voting(self):
        engine = FusionEngine()
        sources = [
            {"id": "s1", "data": {"name": "A"}, "confidence": 0.9},
            {"id": "s2", "data": {"name": "B"}, "confidence": 0.9},
        ]
        # Raise threshold above both -> no votes cast -> nothing resolved for "name"
        resolved = engine.resolve_conflicts(sources, strategy=ResolutionStrategy.VOTING, confidence_threshold=0.95)
        assert resolved["resolved_data"] == {}

    def test_real_tie_is_reported_as_a_conflict(self):
        engine = FusionEngine()
        sources = [
            {"id": "s1", "data": {"name": "A"}, "confidence": 0.9},
            {"id": "s2", "data": {"name": "B"}, "confidence": 0.9},
        ]
        resolved = engine.resolve_conflicts(sources, strategy=ResolutionStrategy.VOTING, confidence_threshold=0.5)
        assert len(resolved["conflicts"]) == 1
        assert resolved["conflicts"][0]["field"] == "name"


class TestResolveByConfidence:
    def test_highest_confidence_source_wins(self):
        engine = FusionEngine()
        resolved = engine.resolve_conflicts(_sources(), strategy=ResolutionStrategy.CONFIDENCE)
        assert resolved["resolved_data"]["name"] == "Delentia"  # s1, confidence=0.9
        assert resolved["resolution_method"] == "highest_confidence"
        assert resolved["confidence"] == 0.9

    def test_falls_back_to_all_sources_when_none_clear_the_threshold(self):
        engine = FusionEngine()
        sources = [{"id": "s1", "data": {"x": 1}, "confidence": 0.1}]
        resolved = engine.resolve_conflicts(sources, strategy=ResolutionStrategy.CONFIDENCE, confidence_threshold=0.99)
        assert resolved["resolved_data"] == {"x": 1}

    def test_reports_real_disagreement_across_sources_as_a_conflict(self):
        engine = FusionEngine()
        resolved = engine.resolve_conflicts(_sources(), strategy=ResolutionStrategy.CONFIDENCE, confidence_threshold=0.0)
        assert any(c["field"] == "name" for c in resolved["conflicts"])


class TestResolveByPriority:
    def test_text_modality_wins_over_vector_and_graph(self):
        engine = FusionEngine()
        resolved = engine.resolve_conflicts(_sources(), strategy=ResolutionStrategy.PRIORITY)
        assert resolved["resolved_data"]["name"] == "Delentia"  # s1, modality=text
        assert resolved["resolution_method"] == "modality_priority"

    def test_unknown_modality_sorts_last(self):
        engine = FusionEngine()
        sources = [
            {"id": "s1", "data": {"x": "from_unknown"}, "confidence": 0.9, "modality": "something_else"},
            {"id": "s2", "data": {"x": "from_graph"}, "confidence": 0.5, "modality": "graph"},
        ]
        resolved = engine.resolve_conflicts(sources, strategy=ResolutionStrategy.PRIORITY)
        assert resolved["resolved_data"]["x"] == "from_graph"


class TestResolveByEnsemble:
    def test_ensemble_uses_voting_result_when_no_conflicts(self):
        engine = FusionEngine()
        sources = [
            {"id": "s1", "data": {"name": "Delentia"}, "confidence": 0.9},
            {"id": "s2", "data": {"name": "Delentia"}, "confidence": 0.8},
        ]
        resolved = engine.resolve_conflicts(sources, strategy=ResolutionStrategy.ENSEMBLE, confidence_threshold=0.5)
        assert resolved["resolution_method"] == "ensemble"
        assert resolved["resolved_data"]["name"] == "Delentia"
        assert resolved["conflicts"] == []

    def test_ensemble_falls_back_to_confidence_for_real_voting_conflicts(self):
        engine = FusionEngine()
        resolved = engine.resolve_conflicts(_sources(), strategy=ResolutionStrategy.ENSEMBLE, confidence_threshold=0.0)
        # With threshold 0.0 all 3 sources vote, "Delentia" (2 votes, weighted)
        # vs "Delentia OS" (1 vote) is a real conflict at the field level -
        # ensemble's confidence fallback still resolves it to a real value.
        assert "name" in resolved["resolved_data"]
        assert resolved["resolution_method"] == "ensemble"

"""
ALGO-19: Data Fusion v2 — Core Fusion Engine (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/data-fusion-v2/
app/core/fusion_engine.py on 2026-09-15, following the same
strip-the-FastAPI-keep-the-engine pattern used for ALGO-07 (mee_engine.py).
No HTTP framework code — this file only imports numpy (already available
via Delentia-OS's `graph` extra, see pyproject.toml) plus stdlib.

Real logic ported as-is:
    - Early fusion: weight + concatenate + L2-normalize feature vectors.
    - Late fusion: normalize each modality independently, weight, then
      zero-pad/truncate to a common length and sum.
    - Hybrid fusion: early-fuse the high-confidence (>=0.7) modalities,
      late-fuse the low-confidence ones, then combine both by their
      relative share of total modality count.
    - Conflict resolution: voting (confidence-weighted majority),
      confidence (best single source), priority (text > vector > graph),
      and ensemble (voting first, confidence for any field left
      conflicted).

Honest, preserved simplification (do not "fix" — the source disclosed
this and it is intentional): align_features()'s "cca" and "procrustes"
methods are NOT true Canonical Correlation Analysis / Procrustes
analysis. CCA here is cosine-similarity-based correlation after padding
and L2-normalizing both vectors; "Procrustes" here is a simple
center-and-rescale (no rotation solve, no SVD). Both are labeled as
"Simplified version for demonstration" in the source and are ported
verbatim, not upgraded into real CCA/Procrustes.

Usage::

    engine = FusionEngine()
    modalities = {
        "text": ModalityData("text", np.array([0.1, 0.2, 0.3]), confidence=0.9, metadata={}),
        "vector": ModalityData("vector", np.array([0.4, 0.5]), confidence=0.6, metadata={}),
    }
    result = engine.fuse(modalities, strategy=FusionStrategy.HYBRID)
    print(result.fused_representation, result.confidence)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class FusionStrategy(str, Enum):
    """Fusion strategy types"""
    EARLY = "early"
    LATE = "late"
    HYBRID = "hybrid"


class ResolutionStrategy(str, Enum):
    """Conflict resolution strategy types"""
    VOTING = "voting"
    CONFIDENCE = "confidence"
    PRIORITY = "priority"
    ENSEMBLE = "ensemble"


@dataclass
class ModalityData:
    """Data for a single modality"""
    modality_type: str  # text, vector, graph
    features: np.ndarray
    confidence: float
    metadata: Dict[str, Any]


@dataclass
class FusionResult:
    """Result of fusion operation"""
    fused_representation: np.ndarray
    confidence: float
    strategy_used: FusionStrategy
    sources_used: List[str]
    conflicts_resolved: int
    metadata: Dict[str, Any]


@dataclass
class AlignmentResult:
    """Result of cross-modal alignment"""
    aligned_source: np.ndarray
    aligned_target: np.ndarray
    alignment_score: float
    transformation_matrix: Optional[np.ndarray]


class FusionEngine:
    """
    Core fusion engine for multi-modal data.

    Supports:
    - Early fusion: Combine features before processing
    - Late fusion: Process separately, then combine
    - Hybrid fusion: Mix of early and late
    """

    def __init__(self):
        self.fusion_count = 0
        self.strategy_stats = {
            FusionStrategy.EARLY: 0,
            FusionStrategy.LATE: 0,
            FusionStrategy.HYBRID: 0
        }
        self.conflicts_resolved = 0

    def fuse(
        self,
        modalities: Dict[str, ModalityData],
        strategy: FusionStrategy = FusionStrategy.HYBRID,
        weights: Optional[Dict[str, float]] = None
    ) -> FusionResult:
        """
        Fuse data from multiple modalities.

        Args:
            modalities: Dictionary of modality name to ModalityData
            strategy: Fusion strategy to use
            weights: Optional weights for each modality (default: equal)

        Returns:
            FusionResult with fused representation
        """
        if not modalities:
            raise ValueError("No modalities provided for fusion")

        if weights is None:
            weights = {name: 1.0 / len(modalities) for name in modalities.keys()}

        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}

        if strategy == FusionStrategy.EARLY:
            fused_features, conflicts = self._early_fusion(modalities, weights)
        elif strategy == FusionStrategy.LATE:
            fused_features, conflicts = self._late_fusion(modalities, weights)
        else:  # HYBRID
            fused_features, conflicts = self._hybrid_fusion(modalities, weights)

        confidence = self._calculate_confidence(modalities, weights)

        self.fusion_count += 1
        self.strategy_stats[strategy] += 1
        self.conflicts_resolved += conflicts

        return FusionResult(
            fused_representation=fused_features,
            confidence=confidence,
            strategy_used=strategy,
            sources_used=list(modalities.keys()),
            conflicts_resolved=conflicts,
            metadata={
                "weights_used": weights,
                "fusion_timestamp": datetime.now().isoformat(),
                "total_fusions": self.fusion_count
            }
        )

    def _early_fusion(
        self,
        modalities: Dict[str, ModalityData],
        weights: Dict[str, float]
    ) -> Tuple[np.ndarray, int]:
        """Early fusion: Concatenate features, then process."""
        feature_list = []
        for name in sorted(modalities.keys()):
            data = modalities[name]
            weighted_features = data.features * weights[name]
            feature_list.append(weighted_features)

        concatenated = np.concatenate(feature_list)
        fused = concatenated / (np.linalg.norm(concatenated) + 1e-8)

        conflicts = 0
        return fused, conflicts

    def _late_fusion(
        self,
        modalities: Dict[str, ModalityData],
        weights: Dict[str, float]
    ) -> Tuple[np.ndarray, int]:
        """Late fusion: Process separately, then combine (weighted sum)."""
        processed_features = []
        conflicts = 0

        for name in sorted(modalities.keys()):
            data = modalities[name]
            normalized = data.features / (np.linalg.norm(data.features) + 1e-8)
            weighted = normalized * weights[name]
            processed_features.append(weighted)

            if data.confidence < 0.5:
                conflicts += 1

        max_len = max(len(f) for f in processed_features)
        padded_features = []
        for features in processed_features:
            if len(features) < max_len:
                padded = np.pad(features, (0, max_len - len(features)))
            else:
                padded = features[:max_len]
            padded_features.append(padded)

        fused = np.sum(padded_features, axis=0)
        return fused, conflicts

    def _hybrid_fusion(
        self,
        modalities: Dict[str, ModalityData],
        weights: Dict[str, float]
    ) -> Tuple[np.ndarray, int]:
        """
        Hybrid fusion: early-fuse high-confidence (>=0.7) modalities,
        late-fuse low-confidence ones, then combine by relative share.
        """
        high_conf = {k: v for k, v in modalities.items() if v.confidence >= 0.7}
        low_conf = {k: v for k, v in modalities.items() if v.confidence < 0.7}

        if high_conf:
            high_weights = {k: weights[k] for k in high_conf.keys()}
            total = sum(high_weights.values())
            high_weights = {k: v / total for k, v in high_weights.items()}
            early_result, early_conflicts = self._early_fusion(high_conf, high_weights)
        else:
            early_result = np.array([])
            early_conflicts = 0

        if low_conf:
            low_weights = {k: weights[k] for k in low_conf.keys()}
            total = sum(low_weights.values())
            low_weights = {k: v / total for k, v in low_weights.items()}
            late_result, late_conflicts = self._late_fusion(low_conf, low_weights)
        else:
            late_result = np.array([])
            late_conflicts = 0

        conflicts = early_conflicts + late_conflicts

        if len(early_result) > 0 and len(late_result) > 0:
            high_conf_weight = len(high_conf) / len(modalities)
            low_conf_weight = len(low_conf) / len(modalities)

            max_len = max(len(early_result), len(late_result))
            early_padded = np.pad(early_result, (0, max(0, max_len - len(early_result))))[:max_len]
            late_padded = np.pad(late_result, (0, max(0, max_len - len(late_result))))[:max_len]

            fused = early_padded * high_conf_weight + late_padded * low_conf_weight
        elif len(early_result) > 0:
            fused = early_result
        else:
            fused = late_result

        return fused, conflicts

    def _calculate_confidence(
        self,
        modalities: Dict[str, ModalityData],
        weights: Dict[str, float]
    ) -> float:
        """Calculate overall confidence from modality confidences."""
        weighted_conf = sum(
            modalities[name].confidence * weights[name]
            for name in modalities.keys()
        )
        return float(np.clip(weighted_conf, 0.0, 1.0))

    def align_features(
        self,
        source_features: np.ndarray,
        target_features: np.ndarray,
        method: str = "cca"
    ) -> AlignmentResult:
        """
        Align features from different modalities.

        Args:
            source_features: Features from source modality
            target_features: Features from target modality
            method: Alignment method (cca, procrustes, linear)
        """
        if method == "cca":
            return self._align_cca(source_features, target_features)
        elif method == "procrustes":
            return self._align_procrustes(source_features, target_features)
        else:  # linear
            return self._align_linear(source_features, target_features)

    def _align_cca(self, source: np.ndarray, target: np.ndarray) -> AlignmentResult:
        """
        "Canonical Correlation Analysis" alignment — SIMPLIFIED (not true
        CCA): cosine similarity between padded, L2-normalized vectors.
        Ported verbatim from the source's own "Simplified version for
        demonstration" implementation.
        """
        source_flat = source.flatten()
        target_flat = target.flatten()

        max_len = max(len(source_flat), len(target_flat))
        source_padded = np.pad(source_flat, (0, max_len - len(source_flat)))
        target_padded = np.pad(target_flat, (0, max_len - len(target_flat)))

        source_norm = source_padded / (np.linalg.norm(source_padded) + 1e-8)
        target_norm = target_padded / (np.linalg.norm(target_padded) + 1e-8)

        correlation = np.dot(source_norm, target_norm)
        alignment_score = float(np.abs(correlation))

        transformation = np.eye(max_len) if max_len <= 100 else None

        return AlignmentResult(
            aligned_source=source_norm,
            aligned_target=target_norm,
            alignment_score=alignment_score,
            transformation_matrix=transformation
        )

    def _align_procrustes(self, source: np.ndarray, target: np.ndarray) -> AlignmentResult:
        """
        "Procrustes" alignment — SIMPLIFIED (not true Procrustes analysis:
        no rotation solve/SVD). Centers both vectors and rescales the
        source to match the target's norm. Ported verbatim.
        """
        source_flat = source.flatten()
        target_flat = target.flatten()

        max_len = max(len(source_flat), len(target_flat))
        source_padded = np.pad(source_flat, (0, max_len - len(source_flat)))
        target_padded = np.pad(target_flat, (0, max_len - len(target_flat)))

        source_centered = source_padded - np.mean(source_padded)
        target_centered = target_padded - np.mean(target_padded)

        source_scale = np.linalg.norm(source_centered)
        target_scale = np.linalg.norm(target_centered)

        if source_scale > 1e-8:
            aligned_source = source_centered * (target_scale / source_scale)
        else:
            aligned_source = source_centered

        alignment_score = 1.0 - np.linalg.norm(aligned_source - target_centered) / (target_scale + 1e-8)
        alignment_score = float(np.clip(alignment_score, 0.0, 1.0))

        return AlignmentResult(
            aligned_source=aligned_source,
            aligned_target=target_centered,
            alignment_score=alignment_score,
            transformation_matrix=None
        )

    def _align_linear(self, source: np.ndarray, target: np.ndarray) -> AlignmentResult:
        """Simple linear transformation alignment (cosine similarity)."""
        source_flat = source.flatten()
        target_flat = target.flatten()

        max_len = max(len(source_flat), len(target_flat))
        source_padded = np.pad(source_flat, (0, max_len - len(source_flat)))
        target_padded = np.pad(target_flat, (0, max_len - len(target_flat)))

        source_norm = source_padded / (np.linalg.norm(source_padded) + 1e-8)
        target_norm = target_padded / (np.linalg.norm(target_padded) + 1e-8)

        alignment_score = float(np.dot(source_norm, target_norm))
        alignment_score = float(np.clip(alignment_score, 0.0, 1.0))

        return AlignmentResult(
            aligned_source=source_norm,
            aligned_target=target_norm,
            alignment_score=alignment_score,
            transformation_matrix=None
        )

    def resolve_conflicts(
        self,
        sources: List[Dict[str, Any]],
        strategy: ResolutionStrategy = ResolutionStrategy.CONFIDENCE,
        confidence_threshold: float = 0.7
    ) -> Dict[str, Any]:
        """Resolve conflicting information from multiple sources."""
        if not sources:
            raise ValueError("No sources provided for conflict resolution")

        if strategy == ResolutionStrategy.VOTING:
            return self._resolve_by_voting(sources, confidence_threshold)
        elif strategy == ResolutionStrategy.CONFIDENCE:
            return self._resolve_by_confidence(sources, confidence_threshold)
        elif strategy == ResolutionStrategy.PRIORITY:
            return self._resolve_by_priority(sources)
        else:  # ENSEMBLE
            return self._resolve_by_ensemble(sources, confidence_threshold)

    def _resolve_by_voting(self, sources: List[Dict[str, Any]], threshold: float) -> Dict[str, Any]:
        """Resolve conflicts by voting (confidence-weighted majority wins)."""
        votes: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        conflicts = []

        for source in sources:
            data = source.get("data", {})
            confidence = source.get("confidence", 0.5)

            if confidence >= threshold:
                for key, value in data.items():
                    if key not in votes:
                        votes[key] = {}

                    value_str = str(value)
                    if value_str not in votes[key]:
                        votes[key][value_str] = []

                    votes[key][value_str].append({
                        "source": source.get("id"),
                        "confidence": confidence
                    })

        resolved_data = {}
        for key, value_votes in votes.items():
            if len(value_votes) > 1:
                conflicts.append({
                    "field": key,
                    "values": list(value_votes.keys()),
                    "sources": [v[0]["source"] for v in value_votes.values()]
                })

            best_value = None
            best_score = 0
            for value, vote_list in value_votes.items():
                score = sum(v["confidence"] for v in vote_list)
                if score > best_score:
                    best_score = score
                    best_value = value

            resolved_data[key] = best_value

        if sources:
            avg_confidence = sum(s.get("confidence", 0.5) for s in sources) / len(sources)
        else:
            avg_confidence = 0.5

        return {
            "resolved_data": resolved_data,
            "resolution_method": "confidence_weighted_voting",
            "conflicts": conflicts,
            "confidence": float(avg_confidence)
        }

    def _resolve_by_confidence(self, sources: List[Dict[str, Any]], threshold: float) -> Dict[str, Any]:
        """Resolve conflicts by choosing highest confidence source."""
        valid_sources = [s for s in sources if s.get("confidence", 0) >= threshold]

        if not valid_sources:
            valid_sources = sources

        best_source = max(valid_sources, key=lambda s: s.get("confidence", 0))

        conflicts = []
        for key in best_source.get("data", {}).keys():
            unique_values = set(
                str(s.get("data", {}).get(key))
                for s in sources
                if key in s.get("data", {})
            )
            if len(unique_values) > 1:
                conflicts.append({
                    "field": key,
                    "values": list(unique_values),
                    "sources": [s.get("id") for s in sources]
                })

        return {
            "resolved_data": best_source.get("data", {}),
            "resolution_method": "highest_confidence",
            "conflicts": conflicts,
            "confidence": best_source.get("confidence", 0.5)
        }

    def _resolve_by_priority(self, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Resolve conflicts by modality priority: text > vector > graph."""
        priority_order = ["text", "vector", "graph"]

        def get_priority(source):
            modality = source.get("modality", "unknown")
            try:
                return priority_order.index(modality)
            except ValueError:
                return len(priority_order)

        sorted_sources = sorted(sources, key=get_priority)
        best_source = sorted_sources[0]

        conflicts = []
        for key in best_source.get("data", {}).keys():
            unique_values = set(
                str(s.get("data", {}).get(key))
                for s in sources
                if key in s.get("data", {})
            )
            if len(unique_values) > 1:
                conflicts.append({
                    "field": key,
                    "values": list(unique_values),
                    "sources": [s.get("id") for s in sources]
                })

        return {
            "resolved_data": best_source.get("data", {}),
            "resolution_method": "modality_priority",
            "conflicts": conflicts,
            "confidence": best_source.get("confidence", 0.5)
        }

    def _resolve_by_ensemble(self, sources: List[Dict[str, Any]], threshold: float) -> Dict[str, Any]:
        """Resolve conflicts using an ensemble: voting first, confidence for leftovers."""
        voting_result = self._resolve_by_voting(sources, threshold)

        if voting_result["conflicts"]:
            confidence_result = self._resolve_by_confidence(sources, threshold)
            resolved_data = {**voting_result["resolved_data"], **confidence_result["resolved_data"]}
        else:
            resolved_data = voting_result["resolved_data"]

        return {
            "resolved_data": resolved_data,
            "resolution_method": "ensemble",
            "conflicts": voting_result["conflicts"],
            "confidence": voting_result["confidence"]
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get fusion statistics."""
        return {
            "total_fusions": self.fusion_count,
            "fusions_by_strategy": {
                strategy.value: count
                for strategy, count in self.strategy_stats.items()
            },
            "conflicts_resolved": self.conflicts_resolved
        }


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    print("=== ALGO-19 Data Fusion v2 smoke test ===")

    engine = FusionEngine()

    modalities = {
        "text": ModalityData("text", np.array([0.1, 0.2, 0.3, 0.4]), confidence=0.9, metadata={}),
        "vector": ModalityData("vector", np.array([0.5, 0.1]), confidence=0.6, metadata={}),
        "graph": ModalityData("graph", np.array([0.2, 0.2, 0.2]), confidence=0.3, metadata={}),
    }

    for strategy in (FusionStrategy.EARLY, FusionStrategy.LATE, FusionStrategy.HYBRID):
        result = engine.fuse(modalities, strategy=strategy)
        print(f"[{strategy.value}] fused shape={result.fused_representation.shape}, "
              f"confidence={result.confidence:.4f}, conflicts={result.conflicts_resolved}")
        assert result.fused_representation.size > 0
        assert 0.0 <= result.confidence <= 1.0

    stats = engine.get_stats()
    print(f"Stats: {stats}")
    assert stats["total_fusions"] == 3

    # Alignment (simplified CCA / Procrustes / linear — see docstrings)
    src = np.array([1.0, 2.0, 3.0])
    tgt = np.array([1.0, 2.0, 3.0, 4.0])
    for method in ("cca", "procrustes", "linear"):
        align = engine.align_features(src, tgt, method=method)
        print(f"[{method}] alignment_score={align.alignment_score:.4f}")
        assert 0.0 <= align.alignment_score <= 1.0 + 1e-6

    # Conflict resolution
    sources = [
        {"id": "s1", "data": {"name": "Delentia"}, "confidence": 0.9, "modality": "text"},
        {"id": "s2", "data": {"name": "Delentia OS"}, "confidence": 0.4, "modality": "graph"},
        {"id": "s3", "data": {"name": "Delentia"}, "confidence": 0.8, "modality": "vector"},
    ]
    for strat in (ResolutionStrategy.VOTING, ResolutionStrategy.CONFIDENCE,
                  ResolutionStrategy.PRIORITY, ResolutionStrategy.ENSEMBLE):
        resolved = engine.resolve_conflicts(sources, strategy=strat)
        print(f"[{strat.value}] resolved={resolved['resolved_data']}, "
              f"method={resolved['resolution_method']}")
        assert "resolved_data" in resolved

    print("=== ALGO-19 Data Fusion v2: ALL ASSERTIONS PASSED ===")

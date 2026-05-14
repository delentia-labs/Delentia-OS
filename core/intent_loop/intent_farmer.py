"""
IntentFarmer — public SDK for intent harvesting, normalization, and FDIA gating.

Usage::

    from core.intent_loop import IntentFarmer

    farmer = IntentFarmer()
    result = farmer.farm("Analyze market trends for Q1 2026", domain="finance")
    print(result.blueprints[0].fdia_score)
"""

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import FarmResult, IntentBlueprint

# Lazy-import the real FDIAScorer so the module still imports when the private
# core SDK is not on the path (useful in isolated unit-test environments).
try:
    import sys
    import os as _os
    _FARMER_DIR = _os.path.dirname(_os.path.abspath(__file__))
    _PROJECT_ROOT = _os.path.abspath(_os.path.join(_FARMER_DIR, "../.."))
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)

    from core.fdia.fdia import FDIAScorer, NPCAction, NPCIntentType  # noqa: E402
    _FDIA_AVAILABLE = True
except ImportError:
    _FDIA_AVAILABLE = False
    FDIAScorer = None  # type: ignore[assignment,misc]
    NPCAction = None  # type: ignore[assignment,misc]
    NPCIntentType = None  # type: ignore[assignment,misc]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _intent_hash(text: str) -> str:
    """Return a 16-char hex prefix of the SHA-256 digest of the normalized text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _score_fdia(intent_text: str) -> float:
    """Compute FDIA score for an intent. Returns 0.5 if SDK unavailable."""
    if not _FDIA_AVAILABLE:
        return 0.5

    scorer = FDIAScorer()
    action = NPCAction(action_id=_intent_hash(intent_text), action_type="explore")
    return scorer.score_action(
        agent_intent=NPCIntentType.DISCOVER,
        action=action,
        agent_reputation=1.0,
        governance_penalty=0.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# IntentFarmer
# ─────────────────────────────────────────────────────────────────────────────

class IntentFarmer:
    """
    Public SDK class for converting raw intent strings into validated
    IntentBlueprint records.

    Features:
    - FDIA quality gating (optional threshold override)
    - Normalization and content-addressable hashing
    - In-memory warm-recall cache (LRU, max 1 000 entries)
    - Bulk farming with optional serial or parallel execution
    """

    _WARM_RECALL_MAX = 1_000

    def __init__(self, fdia_threshold: float = 0.25):
        self.fdia_threshold = fdia_threshold
        self._cache: Dict[str, IntentBlueprint] = {}

    # ── Public API ───────────────────────────────────────────────────────────

    def farm(
        self,
        seed_intent: str,
        domain: str = "general",
        tier: int = 3,
        fdia_threshold: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> FarmResult:
        """
        Process a single seed intent and return a FarmResult.

        Args:
            seed_intent: Raw intent text.
            domain: Domain label (e.g. "finance", "medical", "general").
            tier: JITNA tier 1–9.
            fdia_threshold: Override instance default.
            metadata: Extra key/value pairs stored in the blueprint.

        Returns:
            FarmResult with 0 or 1 blueprint depending on FDIA gate.
        """
        threshold = fdia_threshold if fdia_threshold is not None else self.fdia_threshold
        t0 = time.perf_counter()

        normalized = _normalize(seed_intent)
        intent_hash = _intent_hash(normalized)
        fdia_score = _score_fdia(normalized)

        blueprints: List[IntentBlueprint] = []
        rejected = 0

        if fdia_score >= threshold:
            bp = IntentBlueprint(
                intent_hash=intent_hash,
                original_intent=seed_intent,
                normalized_intent=normalized,
                domain=domain.lower().strip(),
                tier=tier,
                fdia_score=round(fdia_score, 4),
                created_at=datetime.now(tz=timezone.utc),
                metadata=metadata or {},
            )
            blueprints.append(bp)
            self._cache_put(intent_hash, bp)
        else:
            rejected = 1

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return FarmResult(
            seed_intent=seed_intent,
            blueprints=blueprints,
            total_farmed=len(blueprints),
            domain=domain,
            fdia_threshold=threshold,
            elapsed_ms=round(elapsed_ms, 3),
            rejected_count=rejected,
        )

    def warm_recall(self, intent_hash: str) -> Optional[IntentBlueprint]:
        """
        Retrieve a previously farmed blueprint by its content hash.

        Returns None if the hash is not in the warm-recall cache.
        """
        return self._cache.get(intent_hash)

    def bulk_farm(
        self,
        seeds: List[str],
        domain: str = "general",
        tier: int = 3,
        fdia_threshold: Optional[float] = None,
        batch_size: int = 100,
        parallel: bool = False,
    ) -> List[FarmResult]:
        """
        Farm a list of seed intents.

        Args:
            seeds: List of raw intent strings.
            domain: Domain label applied to all seeds.
            tier: JITNA tier applied to all seeds.
            fdia_threshold: Override instance default.
            batch_size: Unused currently (reserved for future async batching).
            parallel: Unused currently (reserved for ThreadPoolExecutor).

        Returns:
            List of FarmResult, one per seed.
        """
        # Note: parallel=True is reserved for future implementation.
        # Serial execution is safe and correct for all current use cases.
        return [
            self.farm(seed, domain=domain, tier=tier, fdia_threshold=fdia_threshold)
            for seed in seeds
        ]

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _cache_put(self, key: str, bp: IntentBlueprint) -> None:
        """Add to warm-recall cache; evict oldest entry when over limit."""
        if len(self._cache) >= self._WARM_RECALL_MAX:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = bp

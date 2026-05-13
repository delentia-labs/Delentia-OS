"""
IntentBlueprint and FarmResult data models for the IntentFarmer public SDK.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class IntentBlueprint:
    """
    A processed and validated intent record ready for downstream use.

    Created by IntentFarmer.farm() for each seed intent that passes the
    FDIA quality gate.
    """
    intent_hash: str          # 16-char SHA-256 prefix for display / dedup
    original_intent: str      # Raw text as supplied by the caller
    normalized_intent: str    # Lowercased, whitespace-collapsed version
    domain: str               # Detected or supplied domain label
    tier: int                 # JITNA tier 1–9 (default: supplied or 3)
    fdia_score: float         # FDIA quality score 0.0–1.0
    created_at: datetime      # UTC timestamp of farming
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FarmResult:
    """
    Aggregated result of a single IntentFarmer.farm() call.
    """
    seed_intent: str                   # The original seed text
    blueprints: List[IntentBlueprint]  # All blueprints produced
    total_farmed: int                  # Count of blueprints (len(blueprints))
    domain: str                        # Domain used for this batch
    fdia_threshold: float              # Minimum FDIA score enforced
    elapsed_ms: float                  # Wall-clock time in milliseconds
    rejected_count: int = 0            # Intents rejected by FDIA gate

"""
SignedAI Core Router — standalone public implementation

Routes analysis jobs to the appropriate consensus tier (S/4/6/8) based on
a scored risk assessment of the artifact being reviewed.

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

from typing import Dict, List

from .models import (
    AnalysisJob,
    RiskLevel,
    TierLevel,
)

# ---------------------------------------------------------------------------
# Tier metadata (kept inline to avoid circular imports)
# ---------------------------------------------------------------------------

_TIER_CONFIG: Dict[TierLevel, Dict] = {
    TierLevel.TIER_S: {
        "signers": 3,
        "required_votes": 2,
        "chairman_veto": False,
        "threshold": 0.667,
    },
    TierLevel.TIER_4: {
        "signers": 4,
        "required_votes": 3,
        "chairman_veto": True,
        "threshold": 0.75,
    },
    TierLevel.TIER_6: {
        "signers": 6,
        "required_votes": 4,
        "chairman_veto": True,
        "threshold": 0.667,
    },
    TierLevel.TIER_8: {
        "signers": 8,
        "required_votes": 6,
        "chairman_veto": True,
        "threshold": 0.75,
    },
}

_BASE_COST_PER_SIGNER_USD = 0.008  # approximate; overridden by registry estimate

_RISK_SCORE_FACTORS: List[str] = [
    "artifact_type",
    "content_sensitive",
    "domain_critical",
    "has_side_effects",
]


class TierRouter:
    """
    Routes an incoming :class:`AnalysisJob` to the appropriate SignedAI tier.

    Risk scoring (0–4 pts) → tier mapping:
      0   → TIER_S (spot-check, 3 signers)
      1–2 → TIER_4 (standard, 4 signers)
      3   → TIER_6 (elevated, 6 signers)
      4+  → TIER_8 (critical, 8 signers)
    """

    def route(self, job: AnalysisJob) -> AnalysisJob:
        """
        Inspect *job*, calculate risk, assign tier, return updated job.

        Modifies the job in-place and also returns it for convenience.
        """
        if job.risk_level is None:
            job.risk_level = self._calculate_risk_level(job)

        if job.tier is None or job.tier_auto_selected:
            job.tier = self._select_tier(job.risk_level)
            job.tier_auto_selected = True

        return job

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_risk_level(self, job: AnalysisJob) -> RiskLevel:
        """Return a :class:`RiskLevel` based on lightweight heuristics."""
        score = 0

        # Config / infra artifacts are inherently risky
        if job.artifact_type in ("config", "schema"):
            score += 1

        artifact_lower = (job.artifact_content or "").lower()

        # Names that suggest sensitive / identity-related logic
        sensitive_tokens = (
            "password", "secret", "token", "key", "auth",
            "credential", "private", "encrypt",
        )
        if any(tok in artifact_lower for tok in sensitive_tokens):
            score += 1

        # Domain context from JITNAPacket — infrastructure / critical systems
        critical_domains = (
            "production", "infra", "infrastructure", "database",
            "security", "critical", "payment", "blockchain",
        )
        domain_lower = (job.intent.D + job.intent.R).lower()
        if any(d in domain_lower for d in critical_domains):
            score += 1

        # Side-effect signals
        side_effect_tokens = ("exec", "deploy", "delete", "drop", "shutdown", "migration")
        if any(tok in artifact_lower for tok in side_effect_tokens):
            score += 1

        return {
            0: RiskLevel.LOW,
            1: RiskLevel.MEDIUM,
            2: RiskLevel.MEDIUM,
            3: RiskLevel.HIGH,
        }.get(score, RiskLevel.CRITICAL)

    def _select_tier(self, risk: RiskLevel) -> TierLevel:
        """Map a :class:`RiskLevel` to the corresponding :class:`TierLevel`."""
        return {
            RiskLevel.LOW: TierLevel.TIER_S,
            RiskLevel.MEDIUM: TierLevel.TIER_4,
            RiskLevel.HIGH: TierLevel.TIER_6,
            RiskLevel.CRITICAL: TierLevel.TIER_8,
        }[risk]

    def estimate_cost(self, tier: TierLevel) -> float:
        """Return an estimated USD cost for the given tier."""
        cfg = _TIER_CONFIG[tier]
        return cfg["signers"] * _BASE_COST_PER_SIGNER_USD


__all__ = ["TierRouter"]

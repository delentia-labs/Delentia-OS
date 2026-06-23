"""
RCT NPC Kernel — FDIA Scoring Engine (Plan 21)

FDIA = Faithfulness · Desire · Intent · Alignment

Decision formula (from RCT-NPC-System-Analysis-1.md):
    Score = (Desire ^ Intent) × Alignment × GovernanceFactor

Where:
    Desire      — how strongly the agent wants the outcome (0.0–1.0)
    Intent      — exponent expressing conviction/commitment (0.5–2.0)
    Alignment   — compatibility with other agents' intents (0.0–1.0)
    Governance  — compliance factor (0.5–1.0; <1.0 = penalised)

Weighted blend used for action selection:
    FDIAScore = (w_desire  × desire_score)
              + (w_intent  × intent_alignment_score)
              + (w_align   × other_alignment_score)
              + (w_gov     × governance_score)

Default weights (configurable):
    desire   = 0.40
    intent   = 0.30
    align    = 0.20
    govern   = 0.10

Layer: Core scoring (depends on world_state via type hints only, no imports)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum


# ---------------------------------------------------------------------------
# NPC Intent Types (distinct from control-plane IntentRole)
# ---------------------------------------------------------------------------

class NPCIntentType(str, Enum):
    """
    Primitive intent types for NPC agents.
    Each has a default desire weight representing base drive strength.
    """
    PROTECT   = "PROTECT"    # protect family/faction/territory
    ACCUMULATE = "ACCUMULATE"  # gather resources / wealth
    BELONG    = "BELONG"     # join groups, form alliances
    DISCOVER  = "DISCOVER"   # explore, learn, research
    DOMINATE  = "DOMINATE"   # control others, assert authority
    NEUTRAL   = "NEUTRAL"    # no strong drive; reactive


# Default desire strength per intent type (0.0–1.0)
DEFAULT_DESIRE_WEIGHTS: Dict[NPCIntentType, float] = {
    NPCIntentType.PROTECT:    0.75,
    NPCIntentType.ACCUMULATE: 0.80,
    NPCIntentType.BELONG:     0.65,
    NPCIntentType.DISCOVER:   0.55,
    NPCIntentType.DOMINATE:   0.90,
    NPCIntentType.NEUTRAL:    0.30,
}

# Alignment matrix: how compatible are two intent types? (-1.0 to +1.0)
# Positive = cooperative, Negative = competitive, 0 = neutral
INTENT_ALIGNMENT_MATRIX: Dict[NPCIntentType, Dict[NPCIntentType, float]] = {
    NPCIntentType.PROTECT: {
        NPCIntentType.PROTECT:    0.8,
        NPCIntentType.ACCUMULATE: 0.0,
        NPCIntentType.BELONG:     0.6,
        NPCIntentType.DISCOVER:   0.2,
        NPCIntentType.DOMINATE:  -0.7,
        NPCIntentType.NEUTRAL:    0.1,
    },
    NPCIntentType.ACCUMULATE: {
        NPCIntentType.PROTECT:    0.0,
        NPCIntentType.ACCUMULATE:-0.3,  # compete for same resources
        NPCIntentType.BELONG:     0.3,
        NPCIntentType.DISCOVER:   0.4,
        NPCIntentType.DOMINATE:  -0.5,
        NPCIntentType.NEUTRAL:    0.2,
    },
    NPCIntentType.BELONG: {
        NPCIntentType.PROTECT:    0.6,
        NPCIntentType.ACCUMULATE: 0.3,
        NPCIntentType.BELONG:     0.9,
        NPCIntentType.DISCOVER:   0.5,
        NPCIntentType.DOMINATE:  -0.4,
        NPCIntentType.NEUTRAL:    0.3,
    },
    NPCIntentType.DISCOVER: {
        NPCIntentType.PROTECT:    0.2,
        NPCIntentType.ACCUMULATE: 0.4,
        NPCIntentType.BELONG:     0.5,
        NPCIntentType.DISCOVER:   0.8,
        NPCIntentType.DOMINATE:  -0.1,
        NPCIntentType.NEUTRAL:    0.4,
    },
    NPCIntentType.DOMINATE: {
        NPCIntentType.PROTECT:   -0.7,
        NPCIntentType.ACCUMULATE:-0.5,
        NPCIntentType.BELONG:    -0.4,
        NPCIntentType.DISCOVER:  -0.1,
        NPCIntentType.DOMINATE:  -0.8,  # dominators conflict with each other
        NPCIntentType.NEUTRAL:    0.0,
    },
    NPCIntentType.NEUTRAL: {
        NPCIntentType.PROTECT:    0.1,
        NPCIntentType.ACCUMULATE: 0.2,
        NPCIntentType.BELONG:     0.3,
        NPCIntentType.DISCOVER:   0.4,
        NPCIntentType.DOMINATE:   0.0,
        NPCIntentType.NEUTRAL:    0.5,
    },
}


def intent_alignment(a: NPCIntentType, b: NPCIntentType) -> float:
    """
    Return alignment score between two intent types (-1.0 to +1.0).
    Pure function — no side effects.
    """
    return INTENT_ALIGNMENT_MATRIX.get(a, {}).get(b, 0.0)


# ---------------------------------------------------------------------------
# FDIA Weights
# ---------------------------------------------------------------------------

@dataclass
class FDIAWeights:
    """Configurable FDIA component weights (must sum to 1.0)."""
    desire:     float = 0.40
    intent:     float = 0.30
    alignment:  float = 0.20
    governance: float = 0.10

    def validate(self) -> bool:
        total = self.desire + self.intent + self.alignment + self.governance
        return abs(total - 1.0) < 1e-6

    def to_dict(self) -> Dict[str, float]:
        return {
            "desire": self.desire,
            "intent": self.intent,
            "alignment": self.alignment,
            "governance": self.governance,
        }


# ---------------------------------------------------------------------------
# Action descriptor (lightweight — avoids circular imports)
# ---------------------------------------------------------------------------

@dataclass
class NPCAction:
    """
    A candidate action an NPC agent can take during a tick.

    Attributes:
        action_id:    Unique identifier within this tick
        action_type:  Category: "trade", "attack", "cooperate", "explore", "idle"
        target_agent: Optional target agent ID
        resource_id:  Optional resource involved
        amount:       Quantity of resource (if applicable)
        metadata:     Extra context
    """
    action_id: str
    action_type: str
    target_agent: Optional[str] = None
    resource_id: Optional[str] = None
    amount: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "target_agent": self.target_agent,
            "resource_id": self.resource_id,
            "amount": round(self.amount, 6),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# FDIA Scorer
# ---------------------------------------------------------------------------

@dataclass
class FDIAScorer:
    """
    Computes a 0.0–1.0 score for a candidate action using the FDIA formula.

    All methods are PURE FUNCTIONS — no mutation, no randomness, no I/O.
    The same inputs always produce the same output (determinism guarantee).

    Usage:
        scorer = FDIAScorer()
        score = scorer.score_action(
            agent_intent=NPCIntentType.ACCUMULATE,
            action=action,
            world_resources={"gold": 100.0},
            agent_reputation=0.7,
            other_intents=[NPCIntentType.PROTECT, NPCIntentType.NEUTRAL],
            governance_penalty=0.0,
        )
    """
    weights: FDIAWeights = field(default_factory=FDIAWeights)

    # --- public API ---------------------------------------------------------

    def score_action(
        self,
        agent_intent: NPCIntentType,
        action: NPCAction,
        world_resources: Dict[str, float],
        agent_reputation: float = 1.0,
        other_intents: Optional[List[NPCIntentType]] = None,
        governance_penalty: float = 0.0,
    ) -> float:
        """
        Compute FDIA score for *action* given agent's intent and world context.

        Returns a float in [0.0, 1.0].
        """
        assert self.weights.validate(), "FDIAWeights must sum to 1.0"

        desire_score      = self._compute_desire(agent_intent, action, world_resources)
        intent_score      = self._compute_intent_compatibility(agent_intent, action)
        alignment_score   = self._compute_other_alignment(
            agent_intent, action, other_intents or []
        )
        governance_score  = self._compute_governance_score(governance_penalty)

        w = self.weights
        raw = (
            w.desire     * desire_score
            + w.intent   * intent_score
            + w.alignment * alignment_score
            + w.governance * governance_score
        )

        # Reputation multiplier ∈ [0.5, 1.0]
        rep_factor = 0.5 + 0.5 * max(0.0, min(1.0, agent_reputation))
        # Governance penalty acts as a hard multiplier on the final score so that
        # high penalties (close to 1.0) can suppress the score to near zero.
        gov_multiplier = max(0.0, 1.0 - governance_penalty)
        final = raw * rep_factor * gov_multiplier

        return max(0.0, min(1.0, final))

    # --- private helpers (all pure) ----------------------------------------

    def _compute_desire(
        self,
        intent: NPCIntentType,
        action: NPCAction,
        world_resources: Dict[str, float],
    ) -> float:
        """
        How strongly does this action satisfy the agent's desire?
        Maps intent type × action type → desire intensity.
        """
        base = DEFAULT_DESIRE_WEIGHTS.get(intent, 0.3)

        # Desire-action compatibility bonuses
        bonuses: Dict[str, Dict[str, float]] = {
            NPCIntentType.ACCUMULATE: {"trade": 0.3, "collect": 0.4, "idle": -0.3},
            NPCIntentType.PROTECT:    {"defend": 0.4, "patrol": 0.3, "idle": 0.1, "attack": -0.4},
            NPCIntentType.DOMINATE:   {"attack": 0.5, "tax": 0.4, "idle": -0.2},
            NPCIntentType.BELONG:     {"cooperate": 0.5, "trade": 0.2, "attack": -0.5},
            NPCIntentType.DISCOVER:   {"explore": 0.5, "research": 0.4, "idle": 0.0},
            NPCIntentType.NEUTRAL:    {},
        }
        bonus = bonuses.get(intent, {}).get(action.action_type, 0.0)

        # Resource availability modulator
        resource_factor = 1.0
        if action.resource_id and action.amount > 0:
            available = world_resources.get(action.resource_id, 0.0)
            if available <= 0:
                resource_factor = 0.1    # nothing available → low desire
            elif available < action.amount:
                resource_factor = available / action.amount

        score = (base + bonus) * resource_factor
        return max(0.0, min(1.0, score))

    def _compute_intent_compatibility(
        self,
        intent: NPCIntentType,
        action: NPCAction,
    ) -> float:
        """
        Is this action type compatible with the agent's fundamental intent?
        High if action directly expresses the intent, low if contradicts.
        """
        compat: Dict[str, Dict[str, float]] = {
            NPCIntentType.ACCUMULATE: {
                "trade": 0.8, "collect": 0.9, "explore": 0.5,
                "cooperate": 0.4, "idle": 0.2, "attack": 0.3, "defend": 0.2,
            },
            NPCIntentType.PROTECT: {
                "defend": 0.9, "patrol": 0.8, "cooperate": 0.6,
                "idle": 0.5, "trade": 0.3, "attack": 0.2, "collect": 0.3,
            },
            NPCIntentType.DOMINATE: {
                "attack": 0.9, "tax": 0.8, "trade": 0.5,
                "patrol": 0.6, "idle": 0.1, "cooperate": 0.2, "defend": 0.5,
            },
            NPCIntentType.BELONG: {
                "cooperate": 0.9, "trade": 0.7, "idle": 0.4,
                "defend": 0.5, "explore": 0.5, "attack": 0.1, "collect": 0.3,
            },
            NPCIntentType.DISCOVER: {
                "explore": 0.9, "research": 0.9, "trade": 0.5,
                "cooperate": 0.6, "idle": 0.3, "attack": 0.1, "defend": 0.2,
            },
            NPCIntentType.NEUTRAL: {
                "idle": 0.7, "trade": 0.5, "explore": 0.5,
                "cooperate": 0.5, "defend": 0.3, "attack": 0.2, "collect": 0.4,
            },
        }
        return compat.get(intent, {}).get(action.action_type, 0.4)

    def _compute_other_alignment(
        self,
        agent_intent: NPCIntentType,
        action: NPCAction,
        other_intents: List[NPCIntentType],
    ) -> float:
        """
        Average alignment of this action with the broader agent community.
        Positive = cooperative, negative = hostile (maps to 0–1).
        """
        if not other_intents:
            return 0.5  # neutral when alone

        # Actions targeting a specific agent have alignment with that agent's intent
        raw_scores = []
        for other in other_intents:
            raw = intent_alignment(agent_intent, other)  # -1 to +1
            # For hostile actions (attack), flip alignment with cooperative agents
            if action.action_type == "attack":
                raw = -raw  # attacking costs alignment
            raw_scores.append(raw)

        avg_raw = sum(raw_scores) / len(raw_scores)
        # Map -1..+1 to 0..1
        return max(0.0, min(1.0, (avg_raw + 1.0) / 2.0))

    def _compute_governance_score(self, penalty: float) -> float:
        """
        Governance compliance score.
        penalty=0.0 → full score 1.0
        penalty=1.0 → score 0.0 (fully penalised)
        """
        return max(0.0, 1.0 - max(0.0, min(1.0, penalty)))

    # --- bulk scoring -------------------------------------------------------

    def rank_actions(
        self,
        agent_intent: NPCIntentType,
        actions: List[NPCAction],
        world_resources: Dict[str, float],
        agent_reputation: float = 1.0,
        other_intents: Optional[List[NPCIntentType]] = None,
        governance_penalties: Optional[Dict[str, float]] = None,
    ) -> List[tuple]:
        """
        Score and rank all candidate actions.

        Returns:
            List of (action, score) sorted descending by score.
        """
        penalties = governance_penalties or {}
        scored = []
        for action in actions:
            penalty = penalties.get(action.action_id, 0.0)
            score = self.score_action(
                agent_intent=agent_intent,
                action=action,
                world_resources=world_resources,
                agent_reputation=agent_reputation,
                other_intents=other_intents,
                governance_penalty=penalty,
            )
            scored.append((action, score))
        # Deterministic sort: score descending, then action_id ascending for ties
        scored.sort(key=lambda x: (-x[1], x[0].action_id))
        return scored

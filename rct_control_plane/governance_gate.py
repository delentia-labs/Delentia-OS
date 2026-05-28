"""
GovernanceGate — Standalone Constitutional Governance Module

The GovernanceGate is the single authoritative entry-point for policy-level
governance decisions in the RCT Control Plane. It sits between the MEE
(Meta-Evolution Engine) and raw FDIA scores, applying:

  1. FDIA threshold enforcement — F < min_fdia → DENIED
  2. Action blocklist — explicit deny-list of action types
  3. Cooldown enforcement — prevent high-frequency bursts per agent
  4. CORD spike detection — anomalous FDIA score jumps → WARNING or DENIED
  5. Cumulative violation tracking — repeated violations escalate to SUSPENDED

Typical MEE integration::

    gate = GovernanceGate()
    verdict = gate.audit(agent_id="agent-001", action="trade", fdia_score=0.72)
    if not verdict.allowed:
        raise GovernanceError(verdict.reason)
    session.step(delta=0.08, governance_violation=not verdict.allowed)

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from rct_control_plane.cord_security import GovernanceViolationDetector

# ============================================================================
# Constants
# ============================================================================

GOVERNANCE_GATE_VERSION = "1.0"

# Default policy values
DEFAULT_MIN_FDIA: float = 0.30          # Minimum acceptable F score
DEFAULT_MAX_VIOLATIONS: int = 5         # Violations before SUSPENDED
DEFAULT_COOLDOWN_SECONDS: float = 1.0   # Minimum seconds between audits per agent
DEFAULT_SPIKE_BLOCKS: bool = False      # Whether CORD spike = DENIED (vs WARNING)


# ============================================================================
# Enums
# ============================================================================

class GovernanceOutcome(str, Enum):
    """Verdict outcome for a GovernanceGate audit."""
    ALLOWED = "allowed"           # Action passes all checks
    WARNING = "warning"           # Action allowed but flagged (soft violation)
    DENIED = "denied"             # Action blocked by policy
    SUSPENDED = "suspended"       # Agent suspended due to repeated violations


class PolicyFlag(str, Enum):
    """Flags set when a specific governance check triggers."""
    FDIA_BELOW_THRESHOLD = "fdia_below_threshold"
    ACTION_BLOCKED = "action_blocked"
    COOLDOWN_VIOLATION = "cooldown_violation"
    FDIA_SPIKE = "fdia_spike"
    METRIC_GAMING = "metric_gaming"
    AGENT_SUSPENDED = "agent_suspended"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class GovernancePolicy:
    """
    Configurable policy for a GovernanceGate instance.

    All fields have safe defaults matching the DEFAULT_* constants above.
    """
    #: Minimum acceptable FDIA F score. Actions with F < this are DENIED.
    min_fdia: float = DEFAULT_MIN_FDIA

    #: Set of action type strings that are always DENIED regardless of score.
    action_blocklist: Set[str] = field(default_factory=set)

    #: Maximum cumulative hard violations before the agent is SUSPENDED.
    max_violations_before_suspend: int = DEFAULT_MAX_VIOLATIONS

    #: Minimum seconds between audits for the same agent (rate limiting).
    cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS

    #: If True, a CORD spike finding (CORD-G001) causes DENIED; otherwise WARNING.
    spike_causes_deny: bool = DEFAULT_SPIKE_BLOCKS

    def with_blocklist(self, *actions: str) -> "GovernancePolicy":
        """Return a copy of this policy with additional blocked actions."""
        new = GovernancePolicy(
            min_fdia=self.min_fdia,
            action_blocklist=set(self.action_blocklist) | set(actions),
            max_violations_before_suspend=self.max_violations_before_suspend,
            cooldown_seconds=self.cooldown_seconds,
            spike_causes_deny=self.spike_causes_deny,
        )
        return new


@dataclass
class GovernanceVerdict:
    """
    Result of a GovernanceGate.audit() call.

    Attributes:
        outcome:       The decision: ALLOWED / WARNING / DENIED / SUSPENDED
        allowed:       True when outcome is ALLOWED or WARNING
        agent_id:      The agent that was audited
        action:        The action type that was audited
        fdia_score:    The FDIA F score at the time of audit
        reason:        Human-readable explanation of the decision
        policy_flags:  List of PolicyFlag values that triggered
    """
    outcome: GovernanceOutcome
    agent_id: str
    action: str
    fdia_score: float
    reason: str
    policy_flags: List[PolicyFlag] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        """True when the action is permitted (ALLOWED or WARNING)."""
        return self.outcome in (GovernanceOutcome.ALLOWED, GovernanceOutcome.WARNING)

    @property
    def is_hard_violation(self) -> bool:
        """True when the outcome is DENIED or SUSPENDED."""
        return self.outcome in (GovernanceOutcome.DENIED, GovernanceOutcome.SUSPENDED)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "allowed": self.allowed,
            "agent_id": self.agent_id,
            "action": self.action,
            "fdia_score": round(self.fdia_score, 6),
            "reason": self.reason,
            "policy_flags": [f.value for f in self.policy_flags],
        }


class GovernanceError(Exception):
    """Raised when a governance gate explicitly denies an action."""
    def __init__(self, verdict: GovernanceVerdict) -> None:
        self.verdict = verdict
        super().__init__(
            f"GovernanceGate DENIED: agent={verdict.agent_id} "
            f"action={verdict.action} fdia={verdict.fdia_score:.3f} "
            f"flags={[f.value for f in verdict.policy_flags]}"
        )


# ============================================================================
# Agent State (internal)
# ============================================================================

@dataclass
class _AgentState:
    """Per-agent runtime state tracked by the GovernanceGate."""
    violation_count: int = 0
    last_audit_time: float = 0.0
    suspended: bool = False


# ============================================================================
# GovernanceGate
# ============================================================================

class GovernanceGate:
    """
    Constitutional governance gate — single entry-point for all agent actions.

    GovernanceGate combines policy enforcement (FDIA thresholds, blocklists,
    cooldowns) with CORD's statistical anomaly detection (metric gaming /
    score spikes) into one auditable decision chain.

    Example::

        policy = GovernancePolicy(min_fdia=0.4, spike_causes_deny=True)
        gate = GovernanceGate(policy=policy)

        verdict = gate.audit("agent-001", "trade", fdia_score=0.82)
        assert verdict.allowed

        verdict = gate.audit("agent-001", "nuclear_strike", fdia_score=0.9)
        assert not verdict.allowed  # action_blocklist

    Thread safety: GovernanceGate is NOT thread-safe by design.
    Wrap in a lock if sharing across threads.
    """

    def __init__(self, policy: Optional[GovernancePolicy] = None) -> None:
        self._policy = policy or GovernancePolicy()
        self._spike_detector = GovernanceViolationDetector()
        self._agent_states: Dict[str, _AgentState] = {}

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def policy(self) -> GovernancePolicy:
        """The active governance policy."""
        return self._policy

    def audit(
        self,
        agent_id: str,
        action: str,
        fdia_score: float,
    ) -> GovernanceVerdict:
        """
        Evaluate whether an agent action is permitted under governance policy.

        Args:
            agent_id:   Unique agent identifier.
            action:     Action type string (e.g. "trade", "delete", "transfer").
            fdia_score: Computed FDIA F score for this step (0.0 – 1.0).

        Returns:
            GovernanceVerdict — always returned; raises GovernanceError only
            if you call ``audit_strict()``.
        """
        state = self._agent_states.setdefault(agent_id, _AgentState())
        flags: List[PolicyFlag] = []

        # 1. Suspension check
        if state.suspended:
            return GovernanceVerdict(
                outcome=GovernanceOutcome.SUSPENDED,
                agent_id=agent_id,
                action=action,
                fdia_score=fdia_score,
                reason=(
                    f"Agent '{agent_id}' is SUSPENDED after "
                    f"{state.violation_count} governance violations."
                ),
                policy_flags=[PolicyFlag.AGENT_SUSPENDED],
            )

        # 2. Cooldown check
        now = time.monotonic()
        elapsed = now - state.last_audit_time
        if state.last_audit_time > 0 and elapsed < self._policy.cooldown_seconds:
            flags.append(PolicyFlag.COOLDOWN_VIOLATION)

        state.last_audit_time = now

        # 3. Action blocklist check
        if action.lower() in {a.lower() for a in self._policy.action_blocklist}:
            flags.append(PolicyFlag.ACTION_BLOCKED)
            state.violation_count += 1
            self._check_suspend(state)
            return GovernanceVerdict(
                outcome=GovernanceOutcome.DENIED,
                agent_id=agent_id,
                action=action,
                fdia_score=fdia_score,
                reason=f"Action '{action}' is in the governance blocklist.",
                policy_flags=flags,
            )

        # 4. FDIA threshold check
        if fdia_score < self._policy.min_fdia:
            flags.append(PolicyFlag.FDIA_BELOW_THRESHOLD)
            state.violation_count += 1
            self._check_suspend(state)
            return GovernanceVerdict(
                outcome=GovernanceOutcome.DENIED,
                agent_id=agent_id,
                action=action,
                fdia_score=fdia_score,
                reason=(
                    f"FDIA score {fdia_score:.3f} is below policy minimum "
                    f"{self._policy.min_fdia:.3f}."
                ),
                policy_flags=flags,
            )

        # 5. CORD spike / metric-gaming check
        cord_findings = self._spike_detector.record(agent_id, fdia_score)
        spike_finding = next(
            (f for f in cord_findings if f.pattern_id == "CORD-G001"), None
        )
        gaming_finding = next(
            (f for f in cord_findings if f.pattern_id == "CORD-G002"), None
        )

        if gaming_finding:
            flags.append(PolicyFlag.METRIC_GAMING)
            state.violation_count += 1
            self._check_suspend(state)
            return GovernanceVerdict(
                outcome=GovernanceOutcome.DENIED,
                agent_id=agent_id,
                action=action,
                fdia_score=fdia_score,
                reason=gaming_finding.detail,
                policy_flags=flags,
            )

        if spike_finding:
            flags.append(PolicyFlag.FDIA_SPIKE)
            if self._policy.spike_causes_deny:
                state.violation_count += 1
                return GovernanceVerdict(
                    outcome=GovernanceOutcome.DENIED,
                    agent_id=agent_id,
                    action=action,
                    fdia_score=fdia_score,
                    reason=spike_finding.detail,
                    policy_flags=flags,
                )
            # Soft: allow with warning
            return GovernanceVerdict(
                outcome=GovernanceOutcome.WARNING,
                agent_id=agent_id,
                action=action,
                fdia_score=fdia_score,
                reason=f"FDIA spike detected (WARNING). {spike_finding.detail}",
                policy_flags=flags,
            )

        # 6. Cooldown violation — WARNING only (action not blocked)
        if PolicyFlag.COOLDOWN_VIOLATION in flags:
            return GovernanceVerdict(
                outcome=GovernanceOutcome.WARNING,
                agent_id=agent_id,
                action=action,
                fdia_score=fdia_score,
                reason=(
                    f"Cooldown violation: {elapsed:.3f}s elapsed, "
                    f"minimum is {self._policy.cooldown_seconds:.3f}s."
                ),
                policy_flags=flags,
            )

        # 7. All clear
        return GovernanceVerdict(
            outcome=GovernanceOutcome.ALLOWED,
            agent_id=agent_id,
            action=action,
            fdia_score=fdia_score,
            reason="All governance checks passed.",
            policy_flags=flags,
        )

    def audit_strict(
        self,
        agent_id: str,
        action: str,
        fdia_score: float,
    ) -> GovernanceVerdict:
        """
        Like ``audit()``, but raises GovernanceError when the verdict is DENIED
        or SUSPENDED. WARNING verdicts are returned normally.
        """
        verdict = self.audit(agent_id, action, fdia_score)
        if verdict.is_hard_violation:
            raise GovernanceError(verdict)
        return verdict

    def reset_agent(self, agent_id: str) -> None:
        """Clear all violation history and suspension state for an agent."""
        self._agent_states.pop(agent_id, None)
        self._spike_detector.reset_agent(agent_id)

    def get_violation_count(self, agent_id: str) -> int:
        """Return the cumulative violation count for an agent."""
        return self._agent_states.get(agent_id, _AgentState()).violation_count

    def is_suspended(self, agent_id: str) -> bool:
        """Return True if an agent is currently suspended."""
        return self._agent_states.get(agent_id, _AgentState()).suspended

    def lift_suspension(self, agent_id: str) -> None:
        """Manually lift a suspension (human override)."""
        state = self._agent_states.get(agent_id)
        if state:
            state.suspended = False
            state.violation_count = 0

    # ── Private helpers ────────────────────────────────────────────────────

    def _check_suspend(self, state: _AgentState) -> None:
        """Suspend the agent if violation threshold is exceeded."""
        if state.violation_count >= self._policy.max_violations_before_suspend:
            state.suspended = True

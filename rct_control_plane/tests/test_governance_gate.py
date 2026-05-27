"""
Tests for GovernanceGate — rct_control_plane/governance_gate.py

18 tests covering:
 - ALLOWED verdict (all checks pass)
 - DENIED: FDIA below threshold
 - DENIED: action blocklist
 - WARNING: FDIA spike (soft, non-blocking)
 - DENIED: FDIA spike with spike_causes_deny=True
 - WARNING: cooldown violation
 - DENIED: metric gaming (CORD-G002)
 - SUSPENDED: agent exceeds max violations
 - Reset agent clears state
 - audit_strict raises GovernanceError on DENIED
 - to_dict serialization
 - lift_suspension restores agent
 - GovernancePolicy.with_blocklist
 - Custom policy: higher min_fdia
 - Multiple agents independent
 - Violation count tracking
 - allowed property on GovernanceVerdict
 - PolicyFlag values present in flagged verdicts
"""

import time

import pytest

from rct_control_plane.governance_gate import (
    GovernanceError,
    GovernanceGate,
    GovernanceOutcome,
    GovernancePolicy,
    GovernanceVerdict,
    PolicyFlag,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_gate(
    min_fdia: float = 0.30,
    blocklist: set | None = None,
    max_violations: int = 5,
    cooldown: float = 0.0,
    spike_causes_deny: bool = False,
) -> GovernanceGate:
    policy = GovernancePolicy(
        min_fdia=min_fdia,
        action_blocklist=blocklist or set(),
        max_violations_before_suspend=max_violations,
        cooldown_seconds=cooldown,
        spike_causes_deny=spike_causes_deny,
    )
    return GovernanceGate(policy=policy)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ALLOWED verdict
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceGateAllowed:
    def test_normal_action_allowed(self):
        gate = make_gate()
        verdict = gate.audit("agent-1", "trade", fdia_score=0.75)
        assert verdict.outcome == GovernanceOutcome.ALLOWED
        assert verdict.allowed is True

    def test_allowed_verdict_has_correct_fields(self):
        gate = make_gate()
        verdict = gate.audit("agent-2", "cooperate", fdia_score=0.80)
        assert verdict.agent_id == "agent-2"
        assert verdict.action == "cooperate"
        assert verdict.fdia_score == 0.80
        assert verdict.allowed is True

    def test_allowed_verdict_has_no_policy_flags(self):
        gate = make_gate()
        verdict = gate.audit("agent-3", "discover", fdia_score=0.60)
        assert PolicyFlag.FDIA_BELOW_THRESHOLD not in verdict.policy_flags
        assert PolicyFlag.ACTION_BLOCKED not in verdict.policy_flags


# ─────────────────────────────────────────────────────────────────────────────
# 2. DENIED: FDIA below threshold
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceGateFDIAThreshold:
    def test_fdia_below_threshold_denied(self):
        gate = make_gate(min_fdia=0.40)
        verdict = gate.audit("agent-1", "trade", fdia_score=0.25)
        assert verdict.outcome == GovernanceOutcome.DENIED
        assert not verdict.allowed

    def test_fdia_below_threshold_flag_set(self):
        gate = make_gate(min_fdia=0.40)
        verdict = gate.audit("agent-1", "trade", fdia_score=0.25)
        assert PolicyFlag.FDIA_BELOW_THRESHOLD in verdict.policy_flags

    def test_fdia_exactly_at_threshold_allowed(self):
        gate = make_gate(min_fdia=0.40)
        verdict = gate.audit("agent-1", "trade", fdia_score=0.40)
        assert verdict.allowed is True

    def test_zero_fdia_denied(self):
        gate = make_gate(min_fdia=0.30)
        verdict = gate.audit("agent-1", "trade", fdia_score=0.0)
        assert verdict.outcome == GovernanceOutcome.DENIED


# ─────────────────────────────────────────────────────────────────────────────
# 3. DENIED: Action blocklist
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceGateBlocklist:
    def test_blocked_action_denied(self):
        gate = make_gate(blocklist={"nuclear_strike", "delete_all"})
        verdict = gate.audit("agent-1", "nuclear_strike", fdia_score=0.95)
        assert verdict.outcome == GovernanceOutcome.DENIED

    def test_blocked_action_flag_set(self):
        gate = make_gate(blocklist={"nuclear_strike"})
        verdict = gate.audit("agent-1", "nuclear_strike", fdia_score=0.95)
        assert PolicyFlag.ACTION_BLOCKED in verdict.policy_flags

    def test_case_insensitive_blocklist(self):
        gate = make_gate(blocklist={"DELETE_ALL"})
        verdict = gate.audit("agent-1", "delete_all", fdia_score=0.9)
        assert verdict.outcome == GovernanceOutcome.DENIED

    def test_non_blocked_action_allowed(self):
        gate = make_gate(blocklist={"nuclear_strike"})
        verdict = gate.audit("agent-1", "trade", fdia_score=0.75)
        assert verdict.allowed is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. WARNING: FDIA spike (soft, non-blocking by default)
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceGateFDIASpike:
    def _trigger_spike(self, gate: GovernanceGate, agent_id: str = "agent-spike") -> GovernanceVerdict:
        gate.audit(agent_id, "trade", fdia_score=0.40)   # baseline
        # Large jump of >0.35
        return gate.audit(agent_id, "trade", fdia_score=0.80)

    def test_spike_produces_warning_by_default(self):
        gate = make_gate()
        verdict = self._trigger_spike(gate)
        assert verdict.outcome == GovernanceOutcome.WARNING
        assert PolicyFlag.FDIA_SPIKE in verdict.policy_flags

    def test_spike_causes_deny_when_policy_set(self):
        gate = make_gate(spike_causes_deny=True)
        verdict = self._trigger_spike(gate)
        assert verdict.outcome == GovernanceOutcome.DENIED

    def test_warning_verdict_is_allowed(self):
        gate = make_gate()
        verdict = self._trigger_spike(gate)
        # WARNING is still allowed
        assert verdict.allowed is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. WARNING: Cooldown violation
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceGateCooldown:
    def test_rapid_calls_produce_warning(self):
        gate = make_gate(cooldown=60.0)   # 60-second cooldown
        gate.audit("agent-1", "trade", fdia_score=0.7)   # first call sets timer
        # Immediate second call — should trigger cooldown warning
        verdict = gate.audit("agent-1", "trade", fdia_score=0.7)
        assert verdict.outcome == GovernanceOutcome.WARNING
        assert PolicyFlag.COOLDOWN_VIOLATION in verdict.policy_flags

    def test_no_cooldown_on_first_call(self):
        gate = make_gate(cooldown=60.0)
        verdict = gate.audit("agent-1", "trade", fdia_score=0.7)
        # First call: no previous timestamp → no cooldown
        assert PolicyFlag.COOLDOWN_VIOLATION not in verdict.policy_flags


# ─────────────────────────────────────────────────────────────────────────────
# 6. SUSPENDED: Agent exceeds max violations
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceGateSuspension:
    def test_agent_suspended_after_max_violations(self):
        gate = make_gate(min_fdia=0.50, max_violations=3)
        for _ in range(3):
            gate.audit("agent-bad", "trade", fdia_score=0.10)  # below threshold → violation
        verdict = gate.audit("agent-bad", "trade", fdia_score=0.90)
        assert verdict.outcome == GovernanceOutcome.SUSPENDED
        assert gate.is_suspended("agent-bad")

    def test_suspended_agent_always_gets_suspended_outcome(self):
        gate = make_gate(min_fdia=0.50, max_violations=3)
        for _ in range(3):
            gate.audit("agent-bad", "trade", fdia_score=0.1)
        # Even with perfect FDIA
        verdict = gate.audit("agent-bad", "trade", fdia_score=1.0)
        assert verdict.outcome == GovernanceOutcome.SUSPENDED

    def test_lift_suspension_restores_agent(self):
        gate = make_gate(min_fdia=0.50, max_violations=3)
        for _ in range(3):
            gate.audit("agent-bad", "trade", fdia_score=0.1)
        gate.lift_suspension("agent-bad")
        assert not gate.is_suspended("agent-bad")
        verdict = gate.audit("agent-bad", "trade", fdia_score=0.8)
        assert verdict.allowed is True


# ─────────────────────────────────────────────────────────────────────────────
# 7. Reset and audit_strict
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceGateHelpers:
    def test_reset_agent_clears_violation_count(self):
        gate = make_gate(min_fdia=0.50)
        gate.audit("agent-1", "trade", fdia_score=0.10)
        assert gate.get_violation_count("agent-1") > 0
        gate.reset_agent("agent-1")
        assert gate.get_violation_count("agent-1") == 0

    def test_audit_strict_raises_on_denied(self):
        gate = make_gate(blocklist={"evil_action"})
        with pytest.raises(GovernanceError) as exc_info:
            gate.audit_strict("agent-1", "evil_action", fdia_score=0.9)
        assert exc_info.value.verdict.outcome == GovernanceOutcome.DENIED

    def test_audit_strict_returns_verdict_on_allowed(self):
        gate = make_gate()
        verdict = gate.audit_strict("agent-1", "trade", fdia_score=0.8)
        assert verdict.allowed is True

    def test_to_dict_serializable(self):
        gate = make_gate()
        verdict = gate.audit("agent-1", "trade", fdia_score=0.75)
        d = verdict.to_dict()
        assert "outcome" in d
        assert "allowed" in d
        assert d["fdia_score"] == pytest.approx(0.75, abs=1e-6)

    def test_policy_with_blocklist_extends_blocklist(self):
        base = GovernancePolicy(action_blocklist={"delete"})
        extended = base.with_blocklist("format", "nuke")
        assert "delete" in extended.action_blocklist
        assert "format" in extended.action_blocklist
        assert "nuke" in extended.action_blocklist

    def test_multiple_agents_independent(self):
        gate = make_gate(min_fdia=0.50, max_violations=2)
        gate.audit("agent-A", "trade", fdia_score=0.10)  # violation for A
        gate.audit("agent-A", "trade", fdia_score=0.10)  # 2nd violation → suspend A
        assert gate.is_suspended("agent-A")
        # B is independent
        assert not gate.is_suspended("agent-B")
        verdict_b = gate.audit("agent-B", "trade", fdia_score=0.80)
        assert verdict_b.allowed is True

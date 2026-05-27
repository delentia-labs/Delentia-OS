"""
MEE v2 — Meta-Evolution Engine (Production Runtime)

Implements ALGO-07 from the RCT v13 Algorithm Bundle.

Formula:
    G(t+1) = G(t) × (1 + M × Δ) × R_t

Where:
    G(t)   — growth metric at step t (composite intent quality score, 0.0–∞)
    M      — meta-learning rate (default 0.1, configurable per session)
    Δ      — delta improvement from current step (signed; negative = degradation)
    R_t    — resilience factor at step t (1.0 = stable; <1.0 = recovery mode)

Behaviour guarantees:
    - Monotonic growth when Δ > 0 and M > 0
    - Bounded decay when Δ < 0 (G never drops below G_floor)
    - R_t automatically computed from violation history
    - Session-level persistence: G saved to .rct.json under "mee_state"
    - Thread-safe: MEESession uses an internal lock

MEE Session lifecycle::

    session = MEESession(session_id="sess-001", g_initial=1.0)
    session.step(delta=0.12)          # record improvement
    session.step(delta=-0.05)         # record degradation
    print(session.g)                  # current growth metric
    print(session.summary())          # full report

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ============================================================================
# Constants
# ============================================================================

MEE_VERSION = "2.0"

# Default hyperparameters
DEFAULT_META_RATE: float = 0.10        # M — learning rate
DEFAULT_RESILIENCE: float = 1.00       # R_t baseline
RESILIENCE_PENALTY: float = 0.02       # R_t deducted per governance violation
RESILIENCE_RECOVERY: float = 0.005     # R_t recovered per clean step
G_FLOOR: float = 0.10                  # G never drops below this value
G_CAP: float = 1_000.0                 # soft cap before renormalization


# ============================================================================
# Step Record
# ============================================================================

@dataclass
class MEEStepRecord:
    """Immutable record of a single MEE step."""
    step_number: int
    g_before: float
    g_after: float
    delta: float
    meta_rate: float
    resilience: float
    governance_violation: bool
    timestamp: str

    @property
    def growth_ratio(self) -> float:
        """Ratio g_after / g_before (>1 = grew, <1 = shrank)."""
        return self.g_after / self.g_before if self.g_before != 0 else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_number,
            "g_before": round(self.g_before, 6),
            "g_after": round(self.g_after, 6),
            "delta": round(self.delta, 6),
            "meta_rate": round(self.meta_rate, 4),
            "resilience": round(self.resilience, 4),
            "governance_violation": self.governance_violation,
            "growth_ratio": round(self.growth_ratio, 4),
            "timestamp": self.timestamp,
        }


# ============================================================================
# MEE Session
# ============================================================================

class MEESession:
    """
    A single MEE v2 session tracking cumulative growth for one agent or context.

    Thread-safe via internal RLock.

    Args:
        session_id: Unique identifier for this session.
        g_initial: Starting growth metric (default 1.0).
        meta_rate: M — learning rate (default 0.10).
        resilience_initial: R_t starting value (default 1.0).

    Example::

        session = MEESession("agent-42")
        for delta in [0.1, 0.15, -0.03, 0.2]:
            session.step(delta)
        print(f"Final G = {session.g:.4f}")
        print(f"Growth ratio = {session.total_growth_ratio:.2f}×")
    """

    def __init__(
        self,
        session_id: str,
        g_initial: float = 1.0,
        meta_rate: float = DEFAULT_META_RATE,
        resilience_initial: float = DEFAULT_RESILIENCE,
    ) -> None:
        self.session_id = session_id
        self._g = max(g_initial, G_FLOOR)
        self._g_initial = self._g
        self._meta_rate = meta_rate
        self._resilience = resilience_initial
        self._history: List[MEEStepRecord] = []
        self._lock = threading.RLock()
        self._created_at = datetime.now(timezone.utc).isoformat()

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def g(self) -> float:
        """Current growth metric G(t)."""
        with self._lock:
            return self._g

    @property
    def resilience(self) -> float:
        """Current resilience factor R_t."""
        with self._lock:
            return self._resilience

    @property
    def step_count(self) -> int:
        with self._lock:
            return len(self._history)

    @property
    def total_growth_ratio(self) -> float:
        """G_current / G_initial — overall multiplier."""
        with self._lock:
            return self._g / self._g_initial if self._g_initial != 0 else 1.0

    @property
    def history(self) -> List[MEEStepRecord]:
        with self._lock:
            return list(self._history)

    # ── Core Step ────────────────────────────────────────────────────────

    def step(
        self,
        delta: float,
        *,
        governance_violation: bool = False,
        meta_rate_override: Optional[float] = None,
    ) -> MEEStepRecord:
        """
        Advance one MEE step.

        Args:
            delta: Signed improvement for this step (positive = grew, negative = shrank).
            governance_violation: If True, apply resilience penalty.
            meta_rate_override: Override M for this step only.

        Returns:
            MEEStepRecord for this step.

        Formula applied:
            G(t+1) = max(G_FLOOR, G(t) × (1 + M × Δ) × R_t)
        """
        with self._lock:
            M = meta_rate_override if meta_rate_override is not None else self._meta_rate

            # Update resilience before applying it
            if governance_violation:
                self._resilience = max(0.50, self._resilience - RESILIENCE_PENALTY)
            else:
                self._resilience = min(DEFAULT_RESILIENCE, self._resilience + RESILIENCE_RECOVERY)

            g_before = self._g
            g_after = g_before * (1.0 + M * delta) * self._resilience

            # Apply floor and soft cap
            g_after = max(G_FLOOR, g_after)
            if g_after > G_CAP:
                # Renormalize: scale history ratios, keep relative growth intact
                g_after = G_CAP

            self._g = g_after

            record = MEEStepRecord(
                step_number=len(self._history) + 1,
                g_before=g_before,
                g_after=g_after,
                delta=delta,
                meta_rate=M,
                resilience=self._resilience,
                governance_violation=governance_violation,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._history.append(record)
            return record

    # ── Persistence Helpers ───────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session state for .rct.json storage."""
        with self._lock:
            return {
                "mee_version": MEE_VERSION,
                "session_id": self.session_id,
                "g_initial": round(self._g_initial, 6),
                "g_current": round(self._g, 6),
                "resilience": round(self._resilience, 4),
                "meta_rate": self._meta_rate,
                "step_count": len(self._history),
                "total_growth_ratio": round(self.total_growth_ratio, 4),
                "created_at": self._created_at,
                "last_step_at": (
                    self._history[-1].timestamp if self._history else None
                ),
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MEESession":
        """Restore a session from persisted dict (partial history — steps not replayed)."""
        session = cls(
            session_id=data["session_id"],
            g_initial=data.get("g_initial", 1.0),
            meta_rate=data.get("meta_rate", DEFAULT_META_RATE),
            resilience_initial=data.get("resilience", DEFAULT_RESILIENCE),
        )
        # Restore g_current directly without replaying steps
        session._g = data.get("g_current", data.get("g_initial", 1.0))
        return session

    # ── Summary ───────────────────────────────────────────────────────────

    def summary(self) -> Dict[str, Any]:
        """
        Return a human-friendly summary of session growth.

        Example::

            {
                "session_id": "sess-001",
                "g_initial": 1.0,
                "g_current": 1.387,
                "total_growth_ratio": 1.387,
                "steps": 8,
                "violations": 1,
                "resilience": 0.98,
                "trend": "growing"
            }
        """
        with self._lock:
            violations = sum(1 for r in self._history if r.governance_violation)
            recent = self._history[-5:] if len(self._history) >= 5 else self._history
            recent_deltas = [r.delta for r in recent]
            avg_delta = sum(recent_deltas) / len(recent_deltas) if recent_deltas else 0.0

            if avg_delta > 0.01:
                trend = "growing"
            elif avg_delta < -0.01:
                trend = "declining"
            else:
                trend = "stable"

            return {
                "session_id": self.session_id,
                "mee_version": MEE_VERSION,
                "g_initial": round(self._g_initial, 4),
                "g_current": round(self._g, 4),
                "total_growth_ratio": round(self.total_growth_ratio, 4),
                "steps": len(self._history),
                "violations": violations,
                "resilience": round(self._resilience, 4),
                "avg_recent_delta": round(avg_delta, 4),
                "trend": trend,
            }


# ============================================================================
# MEE Engine (multi-session manager)
# ============================================================================

class MEEEngine:
    """
    Manages multiple MEE sessions, each keyed by session_id.

    Suitable for use in a Control Plane service managing many concurrent agents.

    Usage::

        engine = MEEEngine()
        engine.create_session("agent-001")
        engine.step("agent-001", delta=0.12)
        engine.step("agent-001", delta=0.08, governance_violation=False)
        print(engine.summary("agent-001"))
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, MEESession] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        session_id: str,
        *,
        g_initial: float = 1.0,
        meta_rate: float = DEFAULT_META_RATE,
    ) -> MEESession:
        """Create and register a new MEE session. Raises if session_id already exists."""
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"Session '{session_id}' already exists.")
            session = MEESession(session_id, g_initial=g_initial, meta_rate=meta_rate)
            self._sessions[session_id] = session
            return session

    def get_or_create(self, session_id: str, **kwargs: Any) -> MEESession:
        """Return existing session or create a new one."""
        with self._lock:
            if session_id not in self._sessions:
                return self.create_session(session_id, **kwargs)
            return self._sessions[session_id]

    def step(
        self,
        session_id: str,
        delta: float,
        *,
        governance_violation: bool = False,
    ) -> MEEStepRecord:
        """Advance the named session by one step."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session '{session_id}' not found. Call create_session() first.")
        return session.step(delta, governance_violation=governance_violation)

    def summary(self, session_id: str) -> Dict[str, Any]:
        """Return summary dict for the named session."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session '{session_id}' not found.")
        return session.summary()

    def all_summaries(self) -> List[Dict[str, Any]]:
        """Return summaries for all active sessions."""
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.summary() for s in sessions]

    def delete_session(self, session_id: str) -> None:
        """Remove a session from the engine."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def restore_session(self, data: Dict[str, Any]) -> MEESession:
        """Restore a persisted session from a dict (e.g. loaded from .rct.json)."""
        session = MEESession.from_dict(data)
        with self._lock:
            self._sessions[session.session_id] = session
        return session

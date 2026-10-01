"""
MEE growth for the agent runtime (Round 51): the part of "the more it is used,
the smarter, faster and cheaper it gets" that can be measured.

Before this module the loop fed MEE a fixed +1 / 0 / -0.5 / -1 by stopped
reason, kept the growth session only in memory (so G restarted at 1.0 with
every process), and never learned whether a reused skill actually helped.
Here:

  * episode_delta()  turns one episode into a graded growth signal in [-1, 1]:
    verified success is worth 0.5, plus up to 0.2 for how well the answer
    matches the intent, plus up to 0.3 for being cheaper/faster than this
    namespace's own earlier verified runs of the same goal. A verified
    success is always > 0 (it can be slower than before and still be a
    success); anything unverified is never > 0, so it can never become a
    skill (skill_library's gate is delta > 0 and no violation).
  * GrowthLedger     persists one MEE session per namespace in RCTDB, so G
    survives restarts and belongs to a user/agent, and keeps the counters the
    Desk shows.
  * efficiency_baseline() reads that namespace's earlier verified runs of the
    same goal from experiment_runs.

MEE's formula is unchanged: G(t+1) = G(t) x (1 + M x delta) x R_t.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rct_control_plane.mee_engine import MEESession

BASE_VERIFIED = 0.5
ALIGNMENT_MAX = 0.2
EFFICIENCY_MAX = 0.3
MIN_BASELINE_RUNS = 1

_OTHER_OUTCOMES = {
    # (delta, governance_violation)
    "fdia_blocked": (-1.0, True),
    "pending_approval": (0.0, False),
    "guard_blocked": (0.0, False),
    "residency_blocked": (0.0, False),      # the policy refused the call: neither growth nor an agent violation
    "notary_unavailable": (0.0, False),
}
_INCOMPLETE = (-0.5, False)


@dataclass
class Baseline:
    runs: int
    iterations: Optional[float]
    cost_usd: Optional[float]
    duration_s: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {"runs": self.runs, "iterations": self.iterations, "cost_usd": self.cost_usd, "duration_s": self.duration_s}


def efficiency_baseline(prior_runs: List[Dict[str, Any]]) -> Baseline:
    """Medians over earlier *verified* runs (finished and aligned) of the same
    goal. Unverified runs are not a standard to beat."""
    verified = [r.get("metrics") or {} for r in prior_runs]
    verified = [m for m in verified if m.get("finished") == 1 and m.get("aligned_with_intent") == 1]

    def median(key: str) -> Optional[float]:
        values = [m[key] for m in verified if isinstance(m.get(key), (int, float))]
        return float(statistics.median(values)) if values else None

    return Baseline(len(verified), median("iterations"), median("cost_usd"), median("duration_s"))


def _relative_gain(previous: Optional[float], current: Optional[float]) -> Optional[float]:
    """+1 = used nothing, 0 = same as before, -1 = at least twice as much."""
    if previous is None or current is None or previous <= 0:
        return None
    return max(-1.0, min(1.0, (previous - current) / previous))


def episode_delta(
    *,
    stopped_reason: str,
    verification: Dict[str, Any],
    iterations: int,
    cost_usd: Optional[float],
    duration_s: float,
    baseline: Baseline,
    threshold: float,
) -> Dict[str, Any]:
    """Returns {"delta", "governance_violation", "parts"}; every part is a
    measured number, so the Desk can show why G moved."""
    verified = (
        stopped_reason == "llm_finished"
        and bool(verification.get("applicable"))
        and bool(verification.get("aligned_with_intent"))
    )
    if not verified:
        if stopped_reason == "llm_finished":
            delta, violation = _INCOMPLETE          # finished, but the answer misses the goal
        else:
            delta, violation = _OTHER_OUTCOMES.get(stopped_reason, _INCOMPLETE)
        return {"delta": delta, "governance_violation": violation, "parts": {"verified": False, "stopped_reason": stopped_reason}}

    similarity = float(verification.get("similarity_score") or 0.0)
    alignment = ALIGNMENT_MAX * max(0.0, min(1.0, (similarity - threshold) / max(1e-9, 1.0 - threshold)))

    gains = {}
    if baseline.runs >= MIN_BASELINE_RUNS:
        gains = {
            "iterations": _relative_gain(baseline.iterations, float(iterations)),
            "cost": _relative_gain(baseline.cost_usd, cost_usd),
            "duration": _relative_gain(baseline.duration_s, duration_s),
        }
    measured = [g for g in gains.values() if g is not None]
    efficiency = EFFICIENCY_MAX * (sum(measured) / len(measured)) if measured else 0.0

    delta = max(0.05, BASE_VERIFIED + alignment + efficiency)  # a verified success always grows
    return {
        "delta": round(min(1.0, delta), 4),
        "governance_violation": False,
        "parts": {
            "verified": True, "base": BASE_VERIFIED, "alignment": round(alignment, 4),
            "efficiency": round(efficiency, 4), "gains": {k: (None if v is None else round(v, 4)) for k, v in gains.items()},
            "baseline": baseline.to_dict(),
        },
    }


class GrowthLedger:
    """One persisted MEE session per namespace (a user or agent identity)."""

    STATE_NAMESPACE = "mee_growth"

    def __init__(self, persistence: Any, namespace: str) -> None:
        self._persistence = persistence
        self.namespace = namespace
        self.episodes = 0
        self.verified_episodes = 0
        self.session = self._load()

    def _load(self) -> MEESession:
        row = None
        try:
            row = self._persistence.get_state(namespace=self.STATE_NAMESPACE, key=self.namespace)
        except Exception:
            row = None
        if row and isinstance(row.get("value"), dict):
            value = row["value"]
            self.episodes = int(value.get("episodes", 0))
            self.verified_episodes = int(value.get("verified_episodes", 0))
            try:
                return MEESession.from_dict(value["session"])
            except Exception:
                pass
        return MEESession(session_id=f"governed-loop:{self.namespace}")

    def record(self, signal: Dict[str, Any]) -> Any:
        step = self.session.step(signal["delta"], governance_violation=signal["governance_violation"])
        self.episodes += 1
        if signal["parts"].get("verified"):
            self.verified_episodes += 1
        self._save()
        return step

    def _save(self) -> None:
        try:
            self._persistence.save_state(
                state_id=f"{self.STATE_NAMESPACE}:{self.namespace}", namespace=self.STATE_NAMESPACE, key=self.namespace,
                value={"session": self.session.to_dict(), "episodes": self.episodes, "verified_episodes": self.verified_episodes},
            )
        except Exception:
            pass    # growth bookkeeping must never change an episode's outcome

    def summary(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace, "G": round(self.session.g, 4), "resilience": round(self.session.resilience, 4),
            "growth_ratio": round(self.session.total_growth_ratio, 4), "episodes": self.episodes,
            "verified_episodes": self.verified_episodes,
        }

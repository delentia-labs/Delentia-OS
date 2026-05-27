"""
Helix-TTD — Topological Trend Drift Detector

Monitors an 8-dimensional system state vector for topology drift in the
RCT OS runtime.  When drift velocity exceeds the alert threshold, the system
has entered an unstable operating region and downstream governors should apply
rate-limiting or trigger a governance review.

8D State Vector (HelixStateVector):
    [0] fdia          — FDIA constitutional alignment score        [0, 1]
    [1] cord_score    — CORD injection-resistance score             [0, 1]
    [2] mee_g         — MEE governance ratio                        [0, 1]
    [3] violation_rate — recent policy violation rate               [0, 1]
    [4] entropy       — agent communication entropy                 [0, 8]
    [5] latency_norm  — normalized response latency                 [0, 1]
    [6] throughput_norm — normalized request throughput             [0, 1]
    [7] governance_ratio — active governors / total agents ratio    [0, 1]

Drift velocity = Euclidean distance between consecutive state vectors,
normalized by the vector dimension (8) to give a per-dimension average.

Alert threshold: drift_velocity > DRIFT_VELOCITY_ALERT (default 0.15)

HELIX_TTD_VERSION = "1.0"
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

HELIX_TTD_VERSION = "1.0"

# 8 dimensions of the state vector
HELIX_STATE_DIM = 8
HELIX_DIM_NAMES = [
    "fdia",
    "cord_score",
    "mee_g",
    "violation_rate",
    "entropy",
    "latency_norm",
    "throughput_norm",
    "governance_ratio",
]

# Drift thresholds
DRIFT_VELOCITY_ALERT = 0.15      # per-dimension average Euclidean step
DRIFT_VELOCITY_CRITICAL = 0.35   # immediate escalation

# Rolling window defaults
DEFAULT_HISTORY_SIZE = 50         # max state vectors in HelixHistory


# ============================================================
# State Vector
# ============================================================

@dataclass
class HelixStateVector:
    """
    An 8D snapshot of the RCT OS runtime health metrics.

    All values should be normalised to [0, 1] except ``entropy`` which spans [0, 8].
    The ``recorded_at`` timestamp is set automatically on creation.
    """
    fdia: float
    cord_score: float
    mee_g: float
    violation_rate: float
    entropy: float
    latency_norm: float
    throughput_norm: float
    governance_ratio: float
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> List[str]:
        """Return a list of validation errors; empty list means OK."""
        errors: List[str] = []
        unit_fields = [
            ("fdia", self.fdia),
            ("cord_score", self.cord_score),
            ("mee_g", self.mee_g),
            ("violation_rate", self.violation_rate),
            ("latency_norm", self.latency_norm),
            ("throughput_norm", self.throughput_norm),
            ("governance_ratio", self.governance_ratio),
        ]
        for name, val in unit_fields:
            if not (0.0 <= val <= 1.0):
                errors.append(f"'{name}' must be in [0, 1]; got {val}")
        if not (0.0 <= self.entropy <= 8.0):
            errors.append(f"'entropy' must be in [0, 8]; got {self.entropy}")
        return errors

    def as_tuple(self) -> Tuple[float, ...]:
        """Return the 8-dimensional numeric values as a tuple."""
        return (
            self.fdia,
            self.cord_score,
            self.mee_g,
            self.violation_rate,
            self.entropy / 8.0,   # normalise to [0, 1] for distance calc
            self.latency_norm,
            self.throughput_norm,
            self.governance_ratio,
        )

    def to_dict(self) -> dict:
        return {
            "fdia": self.fdia,
            "cord_score": self.cord_score,
            "mee_g": self.mee_g,
            "violation_rate": self.violation_rate,
            "entropy": self.entropy,
            "latency_norm": self.latency_norm,
            "throughput_norm": self.throughput_norm,
            "governance_ratio": self.governance_ratio,
            "recorded_at": self.recorded_at,
        }


# ============================================================
# Drift calculation
# ============================================================

def euclidean_distance(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    """Euclidean distance between two equal-length tuples."""
    if len(a) != len(b):
        raise ValueError(f"Dimension mismatch: {len(a)} vs {len(b)}")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def drift_velocity(v1: HelixStateVector, v2: HelixStateVector) -> float:
    """
    Compute the normalised per-dimension drift between two consecutive states.

    Returns Euclidean distance / sqrt(HELIX_STATE_DIM) so that:
      - A single dimension jumping by 1.0 produces velocity ≈ 0.354
      - All dimensions jumping 0.15 simultaneously produces velocity ≈ 0.15

    This keeps the alert threshold scale-invariant to state dimension count.
    """
    d = euclidean_distance(v1.as_tuple(), v2.as_tuple())
    return d / math.sqrt(HELIX_STATE_DIM)


# ============================================================
# Drift alert
# ============================================================

@dataclass
class DriftAlert:
    """
    Alert raised when drift velocity exceeds a threshold.

    Attributes:
        severity:  'warning' (>= ALERT) or 'critical' (>= CRITICAL)
        velocity:  measured drift velocity
        threshold: the threshold that was exceeded
        from_state: the previous state vector
        to_state:   the current state vector
        detected_at: ISO-8601 timestamp
    """
    severity: str
    velocity: float
    threshold: float
    from_state: HelixStateVector
    to_state: HelixStateVector
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "velocity": round(self.velocity, 6),
            "threshold": self.threshold,
            "detected_at": self.detected_at,
            "from_state": self.from_state.to_dict(),
            "to_state": self.to_state.to_dict(),
        }


# ============================================================
# TopologicalDriftDetector
# ============================================================

class TopologicalDriftDetector:
    """
    Detects topological drift in the Helix state space.

    Call ``observe(state)`` on each new state snapshot.
    The detector keeps the previous state and computes drift velocity.
    Raises DriftAlert when ``drift_velocity > DRIFT_VELOCITY_ALERT``.

    Args:
        alert_threshold:    drift_velocity above this → 'warning' alert
        critical_threshold: drift_velocity above this → 'critical' alert
    """

    def __init__(
        self,
        alert_threshold: float = DRIFT_VELOCITY_ALERT,
        critical_threshold: float = DRIFT_VELOCITY_CRITICAL,
    ) -> None:
        self._alert_threshold = alert_threshold
        self._critical_threshold = critical_threshold
        self._previous: Optional[HelixStateVector] = None
        self._alert_count: int = 0

    @property
    def alert_count(self) -> int:
        """Total number of alerts raised since creation."""
        return self._alert_count

    def observe(self, state: HelixStateVector) -> Optional[DriftAlert]:
        """
        Record a new state snapshot.

        Returns:
            DriftAlert if drift velocity exceeds the alert threshold,
            otherwise None.

        Raises:
            ValueError: if the state vector fails validation.
        """
        errors = state.validate()
        if errors:
            raise ValueError(f"Invalid HelixStateVector: {errors}")

        if self._previous is None:
            self._previous = state
            return None

        v = drift_velocity(self._previous, state)
        prev = self._previous
        self._previous = state

        if v >= self._critical_threshold:
            self._alert_count += 1
            return DriftAlert(
                severity="critical",
                velocity=v,
                threshold=self._critical_threshold,
                from_state=prev,
                to_state=state,
            )
        elif v >= self._alert_threshold:
            self._alert_count += 1
            return DriftAlert(
                severity="warning",
                velocity=v,
                threshold=self._alert_threshold,
                from_state=prev,
                to_state=state,
            )
        return None

    def reset(self) -> None:
        """Clear state and alert counter."""
        self._previous = None
        self._alert_count = 0


# ============================================================
# HelixHistory — rolling window
# ============================================================

class HelixHistory:
    """
    Rolling window of HelixStateVectors with drift analytics.

    Args:
        max_size: maximum number of state vectors to retain
    """

    def __init__(self, max_size: int = DEFAULT_HISTORY_SIZE) -> None:
        self._window: deque[HelixStateVector] = deque(maxlen=max_size)
        self._detector = TopologicalDriftDetector()
        self._alerts: List[DriftAlert] = []

    def push(self, state: HelixStateVector) -> Optional[DriftAlert]:
        """Add a state vector; return DriftAlert if drift was detected."""
        alert = self._detector.observe(state)
        self._window.append(state)
        if alert:
            self._alerts.append(alert)
        return alert

    @property
    def states(self) -> List[HelixStateVector]:
        return list(self._window)

    @property
    def alerts(self) -> List[DriftAlert]:
        return list(self._alerts)

    @property
    def alert_count(self) -> int:
        return len(self._alerts)

    def mean_vector(self) -> Optional[HelixStateVector]:
        """
        Return a HelixStateVector whose fields are the per-dimension means.
        Returns None if the history is empty.
        """
        if not self._window:
            return None
        n = len(self._window)
        sums = [0.0] * HELIX_STATE_DIM
        for sv in self._window:
            for i, v in enumerate(sv.as_tuple()):
                sums[i] += v
        # as_tuple() normalises entropy; un-normalise for storage
        means = [s / n for s in sums]
        return HelixStateVector(
            fdia=means[0],
            cord_score=means[1],
            mee_g=means[2],
            violation_rate=means[3],
            entropy=means[4] * 8.0,  # un-normalise
            latency_norm=means[5],
            throughput_norm=means[6],
            governance_ratio=means[7],
        )

    def clear(self) -> None:
        """Clear all history and alerts."""
        self._window.clear()
        self._alerts.clear()
        self._detector.reset()

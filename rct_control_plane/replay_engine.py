"""
Replay Engine — RCT OS Definition Paper §1.7

Provides deterministic replay and verification of Control Plane executions.
Every execution is hash-checkpointed so that replays can be verified against
the original run for auditability, debugging, and compliance.

Core Concepts
─────────────
1. **Execution Hash**: SHA-256 over (intent, graph, transitions) ensuring
   content-addressable identification of an execution path.
2. **Checkpoint**: Snapshot of a ControlPlaneState at a specific version/phase,
   stored with its execution hash.
3. **ReplayResult**: Outcome of replaying an execution against expected hash.
4. **ReplayEngine**: Orchestrates recording, checkpointing, and replay
   verification across the execution lifecycle.

Usage
─────
    from rct_control_plane.replay_engine import ReplayEngine, compute_execution_hash

    engine = ReplayEngine()

    # Record a checkpoint during execution
    engine.record(state)

    # Verify replay
    result = engine.verify(state, expected_hash)
    assert result.matches
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .control_plane_state import ControlPlaneState, ControlPlanePhase


# ============================================================
# Execution Hash
# ============================================================

def compute_execution_hash(state: ControlPlaneState) -> str:
    """
    Compute a deterministic SHA-256 hash for the given state.

    The hash covers:
        - intent_id
        - phase (current)
        - version
        - intent_snapshot (serialised)
        - graph_snapshot (serialised)
        - transition history (from/to/actor/reason for each)

    Returns:
        64-character hex-encoded SHA-256 hash.
    """
    parts: List[str] = [
        f"intent_id:{state.intent_id}",
        f"phase:{state.phase.value}",
        f"version:{state.version}",
    ]

    # Intent snapshot
    if state.intent_snapshot is not None:
        try:
            intent_data = state.intent_snapshot.model_dump()
            parts.append(f"intent:{json.dumps(intent_data, sort_keys=True, default=str)}")
        except Exception:
            parts.append(f"intent:{str(state.intent_snapshot)}")
    else:
        parts.append("intent:null")

    # Graph snapshot
    if state.graph_snapshot is not None:
        try:
            graph_data = state.graph_snapshot.to_dict()
            parts.append(f"graph:{json.dumps(graph_data, sort_keys=True, default=str)}")
        except Exception:
            parts.append(f"graph:{str(state.graph_snapshot)}")
    else:
        parts.append("graph:null")

    # Transitions — captures the full execution path
    for t in state.transitions:
        parts.append(
            f"transition:{t.from_phase.value}->{t.to_phase.value}"
            f"|actor:{t.actor}|reason:{t.reason or ''}"
        )

    content = "\n".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ============================================================
# Checkpoint
# ============================================================

@dataclass
class Checkpoint:
    """A snapshot of a ControlPlaneState at a given point in time."""

    state_id: str
    intent_id: str
    phase: str
    version: int
    execution_hash: str
    recorded_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "intent_id": self.intent_id,
            "phase": self.phase,
            "version": self.version,
            "execution_hash": self.execution_hash,
            "recorded_at": self.recorded_at,
            "metadata": self.metadata,
        }


# ============================================================
# Replay Result
# ============================================================

@dataclass
class ReplayResult:
    """Outcome of a replay verification."""

    matches: bool
    expected_hash: str
    actual_hash: str
    state_id: str = ""
    intent_id: str = ""
    phase: str = ""
    verified_at: str = field(default_factory=lambda: datetime.now().isoformat())
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matches": self.matches,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "state_id": self.state_id,
            "intent_id": self.intent_id,
            "phase": self.phase,
            "verified_at": self.verified_at,
            "details": self.details,
        }


# ============================================================
# Replay Engine
# ============================================================

class ReplayEngine:
    """
    Deterministic replay and verification engine.

    Maintains a history of checkpoints so that any execution can be
    replayed and verified against its recorded hash.
    """

    def __init__(self) -> None:
        self._checkpoints: Dict[str, List[Checkpoint]] = {}  # state_id → checkpoints
        self._hash_index: Dict[str, str] = {}  # execution_hash → state_id

    # ----------------------------------------------------------
    # Recording
    # ----------------------------------------------------------

    def record(self, state: ControlPlaneState, metadata: Optional[Dict[str, Any]] = None) -> Checkpoint:
        """
        Record a checkpoint for the given state.

        Args:
            state: The current ControlPlaneState to checkpoint.
            metadata: Optional metadata to attach.

        Returns:
            The created Checkpoint.
        """
        exec_hash = compute_execution_hash(state)

        checkpoint = Checkpoint(
            state_id=state.state_id,
            intent_id=state.intent_id,
            phase=state.phase.value,
            version=state.version,
            execution_hash=exec_hash,
            metadata=metadata or {},
        )

        self._checkpoints.setdefault(state.state_id, []).append(checkpoint)
        self._hash_index[exec_hash] = state.state_id

        return checkpoint

    # ----------------------------------------------------------
    # Verification
    # ----------------------------------------------------------

    def verify(self, state: ControlPlaneState, expected_hash: str) -> ReplayResult:
        """
        Verify that the current state matches the expected execution hash.

        Args:
            state: The ControlPlaneState to verify.
            expected_hash: The expected SHA-256 hash.

        Returns:
            ReplayResult indicating match/mismatch.
        """
        actual_hash = compute_execution_hash(state)
        matches = actual_hash == expected_hash

        return ReplayResult(
            matches=matches,
            expected_hash=expected_hash,
            actual_hash=actual_hash,
            state_id=state.state_id,
            intent_id=state.intent_id,
            phase=state.phase.value,
            details="Hash matches — replay verified." if matches else "Hash mismatch — replay diverged.",
        )

    # ----------------------------------------------------------
    # Queries
    # ----------------------------------------------------------

    def get_checkpoints(self, state_id: str) -> List[Checkpoint]:
        """Return all checkpoints for a given state_id, ordered chronologically."""
        return list(self._checkpoints.get(state_id, []))

    def get_latest_checkpoint(self, state_id: str) -> Optional[Checkpoint]:
        """Return the most recent checkpoint for a state_id, or None."""
        cps = self._checkpoints.get(state_id, [])
        return cps[-1] if cps else None

    def lookup_by_hash(self, execution_hash: str) -> Optional[str]:
        """Return the state_id associated with an execution hash, or None."""
        return self._hash_index.get(execution_hash)

    def get_checkpoint_count(self) -> int:
        """Return total number of checkpoints across all states."""
        return sum(len(cps) for cps in self._checkpoints.values())

    def get_state_ids(self) -> List[str]:
        """Return all state_ids that have checkpoints."""
        return list(self._checkpoints.keys())

    # ----------------------------------------------------------
    # Replay chain verification
    # ----------------------------------------------------------

    def verify_chain(self, state_id: str) -> List[ReplayResult]:
        """
        Verify that all recorded checkpoints for a state_id form a
        consistent, non-duplicated progression (versions increase,
        hashes differ between checkpoints).

        Returns:
            List of ReplayResult, one per consecutive checkpoint pair.
        """
        cps = self.get_checkpoints(state_id)
        results: List[ReplayResult] = []

        for i in range(1, len(cps)):
            prev, curr = cps[i - 1], cps[i]
            version_ok = curr.version > prev.version
            hash_differs = curr.execution_hash != prev.execution_hash

            results.append(
                ReplayResult(
                    matches=version_ok and hash_differs,
                    expected_hash=prev.execution_hash,
                    actual_hash=curr.execution_hash,
                    state_id=state_id,
                    intent_id=curr.intent_id,
                    phase=curr.phase,
                    details=(
                        f"v{prev.version}→v{curr.version}: "
                        + ("chain consistent" if (version_ok and hash_differs) else "chain broken")
                    ),
                )
            )

        return results

    # ----------------------------------------------------------
    # Serialization
    # ----------------------------------------------------------

    def export_checkpoints(self) -> Dict[str, Any]:
        """Export all checkpoints as a serializable dictionary."""
        return {
            sid: [cp.to_dict() for cp in cps]
            for sid, cps in self._checkpoints.items()
        }

    def clear(self) -> None:
        """Clear all recorded checkpoints."""
        self._checkpoints.clear()
        self._hash_index.clear()

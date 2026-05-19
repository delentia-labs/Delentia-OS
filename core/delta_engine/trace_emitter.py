"""
RCT Delta Engine — Trace Emitter

Wraps MemoryDeltaEngine to emit structured JSONL trace events for every
recorded delta. These events power the Delta Compression Visualizer on
rctlabs.co and the generate_delta_trace.py CLI tool.

Each emitted event contains:
  tick               — simulation tick number
  agent_id           — which agent changed
  action_type        — what the agent did
  outcome            — success / blocked / partial
  delta_bytes        — bytes used by this delta record
  naive_bytes        — bytes that naive (full-snapshot) storage would use
  delta_cumulative   — total bytes stored so far (delta method)
  naive_cumulative   — total bytes stored so far (naive method)
  compression_ratio  — 1 - (delta_cumulative / naive_cumulative)  ≈ 0.74
  recall_ms          — time to reconstruct agent state at this tick (ms)

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.delta_engine.memory_delta import (
    AgentMemoryState,
    MemoryDeltaEngine,
)
from core.fdia.fdia import NPCIntentType


# ---------------------------------------------------------------------------
# Trace Event
# ---------------------------------------------------------------------------

@dataclass
class DeltaTraceEvent:
    """Single structured event emitted by DeltaTraceEmitter."""
    tick: int
    agent_id: str
    action_type: str
    outcome: str
    # Per-delta byte estimates
    delta_bytes: int
    naive_bytes: int
    # Running totals across all agents
    delta_cumulative: int
    naive_cumulative: int
    # Derived metrics
    compression_ratio: float          # 1 - delta_cumulative/naive_cumulative
    recall_ms: float                  # state reconstruction time
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Optional extra
    resource_summary: Optional[Dict[str, float]] = None
    checkpoint_created: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "tick": self.tick,
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "outcome": self.outcome,
            "delta_bytes": self.delta_bytes,
            "naive_bytes": self.naive_bytes,
            "delta_cumulative": self.delta_cumulative,
            "naive_cumulative": self.naive_cumulative,
            "compression_ratio": round(self.compression_ratio, 4),
            "recall_ms": round(self.recall_ms, 3),
            "timestamp": self.timestamp,
        }
        if self.resource_summary:
            d["resource_summary"] = self.resource_summary
        if self.checkpoint_created:
            d["checkpoint_created"] = True
        return d


# ---------------------------------------------------------------------------
# DeltaTraceEmitter
# ---------------------------------------------------------------------------

class DeltaTraceEmitter:
    """
    Drop-in wrapper around MemoryDeltaEngine that also emits trace events.

    Usage:
        from core.delta_engine import DeltaTraceEmitter, MemoryDeltaEngine
        engine = MemoryDeltaEngine()
        emitter = DeltaTraceEmitter(engine, output_path=Path("trace.jsonl"))
        emitter.register_agent("hero", NPCIntentType.DISCOVER)
        emitter.record_delta("hero", tick=1, ...)
        events = emitter.events  # list of DeltaTraceEvent
    """

    def __init__(
        self,
        engine: Optional[MemoryDeltaEngine] = None,
        output_path: Optional[Path] = None,
        naive_bytes_per_state: int = 200,
    ) -> None:
        self.engine = engine or MemoryDeltaEngine()
        self.output_path = output_path
        self.naive_bytes_per_state = naive_bytes_per_state
        self._events: List[DeltaTraceEvent] = []
        self._naive_cumulative: int = 0
        self._delta_cumulative: int = 0

    # ── delegate registration ──────────────────────────────────────────────

    def register_agent(
        self,
        agent_id: str,
        initial_intent: "NPCIntentType | AgentMemoryState",
        initial_resources: Optional[Dict[str, float]] = None,
        initial_reputation: float = 1.0,
    ) -> None:
        self.engine.register_agent(
            agent_id, initial_intent, initial_resources, initial_reputation
        )

    # ── instrumented delta recording ──────────────────────────────────────

    def record_delta(
        self,
        agent_id: str,
        tick: int,
        intent_type: NPCIntentType,
        action_type: str,
        outcome: str,
        resource_changes: Optional[Dict[str, float]] = None,
        relationship_changes: Optional[Dict[str, float]] = None,
        governance_violation: bool = False,
        extra_changes: Optional[Dict[str, Any]] = None,
    ) -> DeltaTraceEvent:
        """Record delta in engine AND emit a trace event. Returns the event."""
        # ── Record in engine ──
        self.engine.record_delta(
            agent_id=agent_id,
            tick=tick,
            intent_type=intent_type,
            action_type=action_type,
            outcome=outcome,
            resource_changes=resource_changes,
            relationship_changes=relationship_changes,
            governance_violation=governance_violation,
            extra_changes=extra_changes,
        )

        # ── Estimate sizes ──
        naive_bytes = self.naive_bytes_per_state
        # Delta size approximation (JSON of changed fields only)
        delta_payload: Dict[str, Any] = {}
        if resource_changes:
            delta_payload["res"] = resource_changes
        if relationship_changes:
            delta_payload["rel"] = relationship_changes
        if extra_changes:
            delta_payload["extra"] = extra_changes
        delta_bytes = max(30, len(json.dumps(delta_payload, separators=(",", ":"))))

        self._naive_cumulative += naive_bytes
        self._delta_cumulative += delta_bytes
        compression_ratio = 1.0 - (self._delta_cumulative / self._naive_cumulative)

        # ── Measure warm recall ──
        t0 = time.perf_counter()
        state = self.engine.get_state_at_tick(agent_id, tick)
        recall_ms = (time.perf_counter() - t0) * 1000

        # ── Check if checkpoint was created ──
        agent_deltas = self.engine.deltas.get(agent_id, [])
        checkpoint_created = (
            len(agent_deltas) > 0
            and len(agent_deltas) % self.engine.checkpoint_interval == 0
        )

        # ── Build event ──
        resource_summary: Optional[Dict[str, float]] = None
        if state and state.resources:
            resource_summary = {k: round(v, 2) for k, v in state.resources.items()}

        event = DeltaTraceEvent(
            tick=tick,
            agent_id=agent_id,
            action_type=action_type,
            outcome=outcome,
            delta_bytes=delta_bytes,
            naive_bytes=naive_bytes,
            delta_cumulative=self._delta_cumulative,
            naive_cumulative=self._naive_cumulative,
            compression_ratio=max(0.0, min(1.0, compression_ratio)),
            recall_ms=recall_ms,
            resource_summary=resource_summary,
            checkpoint_created=checkpoint_created,
        )
        self._events.append(event)

        # ── Write to file ──
        if self.output_path:
            with self.output_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

        return event

    # ── delegation helpers ─────────────────────────────────────────────────

    def get_state_at_tick(self, agent_id: str, tick: int) -> Optional[AgentMemoryState]:
        return self.engine.get_state_at_tick(agent_id, tick)

    def compute_compression_ratio(self) -> float:
        return self.engine.compute_compression_ratio()

    # ── event access ──────────────────────────────────────────────────────

    @property
    def events(self) -> List[DeltaTraceEvent]:
        return list(self._events)

    def summary(self) -> Dict[str, Any]:
        """Return a compression summary dict."""
        if not self._events:
            return {"total_ticks": 0, "compression_ratio": 0.0}
        last = self._events[-1]
        return {
            "total_events": len(self._events),
            "total_ticks": last.tick,
            "agents": self.engine.registered_agent_count(),
            "naive_cumulative_kb": round(self._naive_cumulative / 1024, 2),
            "delta_cumulative_kb": round(self._delta_cumulative / 1024, 2),
            "compression_ratio": round(last.compression_ratio, 4),
            "compression_pct": round(last.compression_ratio * 100, 1),
            "avg_recall_ms": round(
                sum(e.recall_ms for e in self._events) / len(self._events), 3
            ),
            "max_recall_ms": round(max(e.recall_ms for e in self._events), 3),
        }

    def save_jsonl(self, path: Path) -> None:
        """Flush all events to a JSONL file."""
        with path.open("w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        print(f"✓  Trace saved: {path} ({len(self._events)} events)")

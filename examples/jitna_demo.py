"""
JITNA End-to-End Demo
=====================
Just In Time Nodal Assembly — all three protocol layers in action.

Run this script from the delentia-os root:

    python examples/jitna_demo.py

It demonstrates:
  Layer 1 — JITNA Protocol (RFC-001 v2.0): wire-format packet + validator
  Layer 2 — JITNA Language (6-field I/D/Δ/A/R/M): structured intent expression
  Layer 3 — JITNA Intake (loop_engine.py): user-facing ingestion + LoopMetrics
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1 — JITNA PROTOCOL  (rct_control_plane/jitna_protocol.py)
# ─────────────────────────────────────────────────────────────────────────────

def demo_layer1_protocol() -> None:
    """Demonstrate RFC-001 wire-format packet creation and validation."""

    print("\n" + "=" * 60)
    print("LAYER 1 — JITNA PROTOCOL (RFC-001 v2.0)")
    print("=" * 60)

    try:
        from rct_control_plane.jitna_protocol import (
            JITNAPacket,
            JITNAValidator,
            JITNAMessageType,
            JITNAStatus,
        )

        packet = JITNAPacket(
            packet_id=str(uuid.uuid4()),
            source_agent_id="demo-orchestrator",
            target_agent_id="specialist-analyst",
            message_type=JITNAMessageType.TASK_REQUEST,
            payload={
                "objective": "Detect anomalies in Q1 2026 trading data",
                "action": "analyze",
                "target_tool": "anomaly-detector",
            },
            timestamp=datetime.now().isoformat(),
            schema_version="2.0",
            priority=3,
            correlation_id=str(uuid.uuid4()),
            signature="",  # Ed25519 would be set in production
            metadata={"env": "demo"},
            status=JITNAStatus.PENDING,
        )

        validator = JITNAValidator()
        result = validator.validate(packet)

        print(f"  Packet ID    : {packet.packet_id}")
        print(f"  Source Agent : {packet.source_agent_id}")
        print(f"  Target Agent : {packet.target_agent_id}")
        print(f"  Action       : {packet.payload['action']}")
        print(f"  Validated    : {result}")
        print(f"  Schema Ver.  : {packet.schema_version}")

    except ImportError:
        # Protocol module requires full ecosystem — show structure only
        packet_id = str(uuid.uuid4())
        print(f"  [Protocol module not loaded — showing packet schema]")
        print(f"  Packet ID    : {packet_id}")
        print(f"  Source       : demo-orchestrator → specialist-analyst")
        print(f"  Action       : analyze (priority 3)")
        print(f"  Schema Ver.  : 2.0")
        print(f"  Security     : Ed25519 signature (The 9 Codex)")
        print(f"  Ref          : docs/architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md")


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2 — JITNA LANGUAGE  (6-field I / D / Δ / A / R / M)
# ─────────────────────────────────────────────────────────────────────────────

def demo_layer2_language() -> None:
    """Demonstrate the 6-field JITNA Language schema."""

    print("\n" + "=" * 60)
    print("LAYER 2 — JITNA LANGUAGE (6-field template)")
    print("=" * 60)

    # ---------------------------------------------------------
    # Example 1: Software engineering intent
    # ---------------------------------------------------------
    print("\n  [Example 1] — Software Refactoring Intent:")
    eng_intent: dict[str, str] = {
        "I": "Refactor authentication module to clean architecture",
        "D": "Current impl: 800-line monolith with mixed concerns, 0 unit tests",
        "Δ": "Separate domain logic from infra; no breaking API changes",
        "A": "Apply Hexagonal Architecture + dependency inversion pattern",
        "R": "Previous refactor failed — interface contracts were missing",
        "M": "All existing tests pass; cyclomatic complexity < 10 per function",
    }
    _print_jitna_fields(eng_intent)

    # ---------------------------------------------------------
    # Example 2: Data analysis intent
    # ---------------------------------------------------------
    print("\n  [Example 2] — Data Analysis Intent:")
    data_intent: dict[str, str] = {
        "I": "Identify anomalies in Q1 2026 trading dataset",
        "D": "5M rows, tick data; 3% missing values; timezone: UTC+7",
        "Δ": "Surface top-20 anomaly events with confidence > 0.85",
        "A": "Isolation Forest + DBSCAN ensemble, weighted by volume spikes",
        "R": "Previous IQR method: 60% false positives on illiquid hours",
        "M": "Threshold 0.85 confirmed by domain expert 2026-03-10",
    }
    _print_jitna_fields(data_intent)

    # ---------------------------------------------------------
    # Example 3: AI coordination intent (multi-agent)
    # ---------------------------------------------------------
    print("\n  [Example 3] — Multi-Agent Coordination Intent:")
    coord_intent: dict[str, str] = {
        "I": "Verify the refactored auth module using SignedAI consensus",
        "D": "SHA-256: abc123; 6 models available (Tier-6, 67% quorum required)",
        "Δ": "Consensus result: PASS or REVISE with annotation",
        "A": "Route to SignedAI Tier-6; each model scores independently",
        "R": "Single model rejected in last round — requires fresh consensus",
        "M": "Agreement threshold ≥ 4/6 models; latency budget 30 s",
    }
    _print_jitna_fields(coord_intent)

    print(
        "\n  Key: I=Intent  D=Data  Δ=Delta  A=Approach  R=Reflection  M=Memory"
    )


def _print_jitna_fields(fields: dict[str, str]) -> None:
    labels = {"I": "Intent", "D": "Data", "Δ": "Delta", "A": "Approach", "R": "Reflection", "M": "Memory"}
    for key, value in fields.items():
        label = labels.get(key, key)
        print(f"    {key} ({label:>10}): {value}")


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3 — JITNA INTAKE  (microservices/intent-loop/loop_engine.py)
# ─────────────────────────────────────────────────────────────────────────────

def demo_layer3_intake() -> None:
    """Demonstrate the user-facing IntentLoopEngine + LoopMetrics."""

    print("\n" + "=" * 60)
    print("LAYER 3 — JITNA INTAKE (IntentLoopEngine)")
    print("=" * 60)

    # Import from intake module (adjust sys.path for demo execution)
    import importlib.util
    import os

    intake_path = os.path.join(
        os.path.dirname(__file__), "..", "microservices", "intent-loop", "loop_engine.py"
    )
    spec = importlib.util.spec_from_file_location("loop_engine", intake_path)
    if spec is None or spec.loader is None:
        print("  [loop_engine.py not found — showing Layer 3 schema only]")
        _demo_layer3_schema_only()
        return

    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        print(f"  [Could not load loop_engine.py: {exc}]")
        _demo_layer3_schema_only()
        return

    JITNAPacket = mod.JITNAPacket
    IntentLoopEngine = mod.IntentLoopEngine
    LoopMetrics = mod.LoopMetrics

    # ---------------------------------------------------------
    # LoopMetrics — tracking engine performance
    # ---------------------------------------------------------
    print("\n  [LoopMetrics — runtime statistics]")
    metrics = LoopMetrics(
        total_processed=42,
        cache_hits=35,
        cache_misses=7,
        avg_latency_ms=18.4,
        error_count=1,
    )
    print(f"    Total processed   : {metrics.total_processed}")
    print(f"    Cache hits        : {metrics.cache_hits}")
    print(f"    Cache misses      : {metrics.cache_misses}")
    print(f"    Cache hit rate    : {metrics.cache_hit_rate:.1%}")
    print(f"    Avg latency       : {metrics.avg_latency_ms:.1f} ms")
    print(f"    Error count       : {metrics.error_count}")

    # ---------------------------------------------------------
    # JITNAPacket — user-facing intake
    # ---------------------------------------------------------
    print("\n  [JITNAPacket — user-facing intake packet]")
    packet = JITNAPacket(
        intent="Analyze Q1 2026 trading data for anomalies",
        context={
            "dataset": "q1_ticks.parquet",
            "rows": 5_000_000,
            "threshold": 0.85,
        },
    )
    print(f"    Intent      : {packet.intent}")
    print(f"    Context     : {packet.context}")
    print(f"    Hash        : {packet.compute_hash()}")

    # ---------------------------------------------------------
    # IntentLoopEngine — submit + evolve
    # ---------------------------------------------------------
    print("\n  [IntentLoopEngine — process intent]")
    engine = IntentLoopEngine()

    t0 = time.perf_counter()
    result = engine.process(packet)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    print(f"    State       : {result.state.value if hasattr(result.state, 'value') else result.state}")
    print(f"    Latency     : {elapsed_ms:.2f} ms")
    print(f"    Cache hit   : {result.cache_hit}")
    print(f"    Verified    : {result.verification_passed}")

    if result.error:
        print(f"    Error       : {result.error}")
    else:
        print(f"    Output keys : {list(result.output.keys()) if result.output else 'none'}")


def _demo_layer3_schema_only() -> None:
    print("""
  Layer 3 — JITNA Intake schema:

  class JITNAPacket:
      intent: str                  # user intent string
      context: dict                # supporting context
      compute_hash() -> str        # SHA-256 of intent + context

  class LoopMetrics:
      total_processed: int
      cache_hits: int
      cache_misses: int
      avg_latency_ms: float
      error_count: int
      last_updated: datetime
      cache_hit_rate: float        # property

  class IntentLoopEngine:
      process(packet) -> IntentResult
    """)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         JITNA — Just In Time Nodal Assembly                 ║")
    print("║         End-to-End Protocol Demo  (RFC-001 v2.0)            ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    demo_layer1_protocol()
    demo_layer2_language()
    demo_layer3_intake()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print()
    print("  Docs:    docs/concepts/jitna.md")
    print("  RFC:     docs/architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md")
    print("  Tests:   tests/security/test_api_security.py")
    print("           microservices/intent-loop/tests/test_intent_loop.py")
    print()


if __name__ == "__main__":
    main()

# Intent Loop

**The 7-state pipeline that processes every user intent from receipt to commitment.**

---

## The 7-State Pipeline

```
RECEIVED → VALIDATED → MEMORY_CHECK → COMPUTING
         → VERIFYING → COMMITTING   → COMPLETED
                                     ↓
                               (or REJECTED at any gate)
```

### State Transitions

| State | What Happens | Gate |
|-------|-------------|------|
| **RECEIVED** | JITNAPacket arrives at control plane | — |
| **VALIDATED** | FDIA score computed: `F = D^I × A` | Score < threshold → REJECTED |
| **MEMORY_CHECK** | Delta Engine queried for similar past intents | Cache hit → skip COMPUTING |
| **COMPUTING** | Multi-step DSL graph executed | Error → REJECTED |
| **VERIFYING** | SignedAI consensus across N models | Consensus < threshold → REJECTED |
| **COMMITTING** | ED25519-signed result written to RCTDB | Write failure → REJECTED |
| **COMPLETED** | Result returned + delta stored in memory | — |

---

## Performance Characteristics

| Path | Latency | When |
|------|---------|------|
| **Cold Start** | 3–5 seconds | Full computation + SignedAI consensus |
| **Warm Recall** | <50ms | Memory hit (semantic similarity > 0.95) |
| **Cost Trend** | → $0 | As memory fills with past intents |

!!! tip "Memory Cache Effect"
    Once an intent pattern appears in the Delta Engine, subsequent calls with >95% semantic similarity skip COMPUTING and VERIFYING entirely — jumping straight from MEMORY_CHECK to COMPLETED. This is why cost decreases as the system learns.

---

## IntentState Usage

```python
from rct_control_plane.intent_schema import IntentObject, IntentState

intent = IntentObject(
    intent_text="Deploy authentication service to staging",
    domain="backend-engineering",
    architect_constraint="No production database changes",
    requirements="All tests pass, <500ms p99 response time",
)

# Compile through the loop
from rct_control_plane.intent_compiler import IntentCompiler

compiler = IntentCompiler()
result = compiler.compile(intent)

print(f"State: {result.state}")            # → IntentState.COMPLETED
print(f"Duration: {result.duration_ms}ms")
print(f"From cache: {result.cache_hit}")
```

---

## Observability

Every state transition is emitted as a structured log event:

```json
{
  "intent_id": "int_abc123",
  "tick": 1714230000,
  "from_state": "VALIDATED",
  "to_state": "MEMORY_CHECK",
  "fdia_score": 0.847,
  "cache_hit": false,
  "duration_ms": 12
}
```

Events are collected by `rct_control_plane/observability.py` and can be streamed to any OTEL-compatible backend.

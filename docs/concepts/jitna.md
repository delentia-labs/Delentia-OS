# JITNA — Just In Time Nodal Assembly

**"The HTTP of Agentic AI"**

JITNA is the open communication protocol of the RCT Ecosystem. It defines how AI agents discover each other, negotiate tasks, execute work, and verify results — without any permanent agent hierarchy or pre-configured workflows.

The name captures the core design principle:

| Letter | Word | Meaning |
|--------|------|---------|
| **J** | Just | เพียงแค่ |
| **I** | In | ใน |
| **T** | Time | เวลา / ทันเวลา |
| **N** | Nodal | ของโหนด / node-based |
| **A** | Assembly | การประกอบ / การรวมตัว |

Agents are **assembled into working groups just in time** based on the intent of the current task, then dissolved when the task completes.

---

## The Three-Layer Architecture

JITNA is not a single class or file. It is a three-layer system where each layer has a distinct role:

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1 — JITNA PROTOCOL (RFC-001 v2.0)                        │
│  Technical name: "Just-In-Time Network Actuation"               │
│  Role: Wire format for AI-to-AI communication                   │
│  File: rct_control_plane/jitna_protocol.py                      │
│  Structure: header + intent + payload + validation              │
│  Security: Ed25519 signatures, The 9 Codex                      │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2 — JITNA LANGUAGE (6-field templates)                   │
│  Role: Structured intent communication format                   │
│  Fields: I / D / Δ / A / R / M                                  │
│  Used for: prompts, memory tagging, vault metadata, RCTDB        │
│  Templates: 50+ workflow templates available                    │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3 — JITNA INTAKE (user-facing)                           │
│  Role: Simplified front-door for user intent                    │
│  File: microservices/intent-loop/loop_engine.py                 │
│  Structure: intent (str) + context (dict) + compute_hash()      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Layer 2: The 6-Field Language

The JITNA Language provides a canonical 6-field schema for structuring any intent:

| Field | Name | Description |
|-------|------|-------------|
| **I** | Intent | เป้าหมายหลัก — what the agent ultimately wants to achieve |
| **D** | Data | ข้อมูล/ความเป็นจริง — facts and context currently available |
| **Δ** | Delta | ช่องว่าง — the gap or desired change between current and goal state |
| **A** | Approach | แนวทาง — the algorithm or strategy to apply |
| **R** | Reflection | บทเรียน — lessons learned, feedback, or post-execution review |
| **M** | Memory | สิ่งที่ต้องจำ — long-term context to persist across sessions |

### Example: Software Engineering Intent

```python
intent = {
    "I": "Refactor the authentication module to clean architecture",
    "D": "Current implementation is 800-line monolith with mixed concerns",
    "Δ": "Separate domain logic from infrastructure — no API breaking changes",
    "A": "Apply Hexagonal Architecture pattern with dependency inversion",
    "R": "Previous refactor attempt failed due to missing interface contracts",
    "M": "All existing tests must pass; cyclomatic complexity must drop below 10",
}
```

### Example: Data Analysis Intent

```python
intent = {
    "I": "Identify anomalies in the trading dataset for Q1 2026",
    "D": "5M rows of tick data; 3% missing values; timezone normalized to UTC+7",
    "Δ": "Surface top-20 anomaly events with confidence scores above 0.85",
    "A": "Isolation Forest + DBSCAN ensemble; weighted by volume spike detection",
    "R": "Previous IQR method produced 60% false positives on illiquid hours",
    "M": "Model threshold 0.85 confirmed by domain expert on 2026-03-10",
}
```

!!! note "SignedAI Semantic Layer vs JITNA Language"
    The `JITNAPacket` in `signedai/core/models.py` uses a different field mapping
    (D=Domain, A=Assumptions, R=Requirements, M=Metrics). That is the **SignedAI
    Semantic Layer** — a verification-focused variant used inside the consensus
    engine. The canonical JITNA Language fields (D=Data, A=Approach, R=Reflection,
    M=Memory) are the primary schema for prompts, memory, and vault tagging.

---

## Layer 1: The Protocol (RFC-001 v2.0)

Every JITNA communication uses a standardized packet:

```python
# From rct_control_plane/jitna_protocol.py
@dataclass
class JITNAPacket:
    packet_id: str           # UUID v4
    source_agent_id: str     # Sender identity
    target_agent_id: str     # Receiver identity
    message_type: str        # JITNAMessageType enum
    payload: Dict            # Intent content
    timestamp: str           # ISO 8601
    schema_version: str      # "2.0"
    priority: int            # 1–5 (1 = highest)
    correlation_id: str      # For chaining packets
    signature: str           # Ed25519 (RFC 8032)
    metadata: Dict
    status: str              # JITNAStatus enum
```

The full specification is in [RFC-001](../architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md).

---

## The Negotiation Pattern

JITNA agents do not blindly execute instructions — they **negotiate**:

```
Agent A: PROPOSE  → "I need you to analyze this dataset"
Agent B: COUNTER  → "I can do it, but I need the schema first"
Agent A: ACCEPT   → "Here is the schema" [attaches schema]
Agent B: ACCEPT   → "Executing analysis"
Agent B: COMPLETE → "Analysis complete" [attaches results + signature]
```

Or when an agent cannot fulfill the request:

```
Agent A: PROPOSE  → "Translate this medical document to Thai"
Agent B: REJECT   → "Not qualified for medical translation"
Agent A: PROPOSE  → [redirects to Agent C, a medical specialist]
```

---

## JITNA vs Tool-Calling APIs

| Dimension | Tool-Calling APIs | JITNA Protocol |
|-----------|-------------------|----------------|
| Communication model | Request → Response | PROPOSE → COUNTER → ACCEPT/REJECT |
| Agent autonomy | None (tools are passive) | Full (agents can negotiate and refuse) |
| Verification | None built-in | Ed25519 signed packets |
| Replay support | Not supported | SHA-256 checkpoint chain |
| Multi-agent consensus | Not supported | SignedAI integration (Tier S/4/6/8) |
| Discovery | Hardcoded list | Dynamic registry with capability matching |
| Standardization | Vendor-specific | Open RFC (Apache 2.0) |

---

## Integration with the RCT Ecosystem

```
User Intent
    │
    ▼
FDIA Validation (F = D^I × A)   ← Validates intent quality
    │
    ▼
Agent Assembly (JITNA Layer 1)  ← Routes to correct agent set
    │
    ▼
Negotiation (PROPOSE/COUNTER)   ← Agents agree on approach
    │
    ▼
Execution (Layer 3 Intake)      ← Specialist processes the task
    │
    ▼
SignedAI Verification           ← Multi-model consensus
    │
    ▼
RCTDB Commit                    ← Permanent audit trail
    │
    ▼
Output
```

### JITNA + FDIA
Every packet's `intent` field is scored by the FDIA equation (`F = D^I × A`). If the score falls below threshold, the transaction is blocked before any agent begins work.

### JITNA + SignedAI
For high-criticality tasks, JITNA routes through SignedAI consensus. Multiple models independently process the task and must reach agreement (Tier 4: 75%, Tier 6: 67%, Tier 8: 75%) before the result is committed.

### JITNA + RCTDB
Every completed JITNA transaction is committed to RCTDB — the 8-dimensional universal memory schema. Any transaction can be replayed from any point. The Delta Engine compresses stored state by 74%.

---

## Security: The 9 Codex

All JITNA implementations enforce **The 9 Codex** — nine constitutional security rules:

1. Never execute commands that modify system security settings
2. Always validate digital signatures before execution
3. Respect resource constraints and limits
4. Log all operations for audit trail
5. Never expose sensitive data in responses
6. Validate all input parameters for safety
7. Implement graceful failure modes
8. Enforce time-based expiration of commands
9. Maintain principle of least privilege

### Security Levels

| Level | Name | Operations |
|-------|------|------------|
| 1 | SAFE | Read-only, no system changes |
| 2 | RESTRICTED | Limited changes, sandboxed |
| 3 | MODERATE | Standard operations, monitored |
| 4 | ELEVATED | Administrative, enhanced logging |
| 5 | CRITICAL | System-critical, multi-factor auth |

---

## Key Files

| File | Layer | Purpose |
|------|-------|---------|
| `rct_control_plane/jitna_protocol.py` | 1 — Protocol | `JITNAPacket`, `JITNAValidator`, `JITNANormalizer`, `JITNAProtocolRegistry` |
| `signedai/core/models.py` | 1 — Semantic | `JITNAPacket` for SignedAI verification context (different field semantics) |
| `microservices/intent-loop/loop_engine.py` | 3 — Intake | User-facing `JITNAPacket`, `LoopMetrics`, `IntentLoopEngine` |

---

## Further Reading

- [RFC-001: Open JITNA Protocol Specification](../architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md)
- [SignedAI Consensus](signedai.md) — verification layer using JITNA packets
- [Intent Loop](intent-loop.md) — Layer 3 intake and the evolutionary intelligence loop
- [FDIA Engine](fdia.md) — intent scoring that gates every JITNA transaction

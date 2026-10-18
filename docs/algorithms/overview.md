# Open-Core Architecture & Public Reference Overview

**RCT Platform / Delentia OS** provides an intent-centric constitutional AI SDK built on a 9-Tier architecture. The ecosystem is organized around a clear **Open-Core Architecture Boundary**: the **Public Open-Source Core (Apache 2.0)** and the **Private Enterprise Full Engine**.

!!! tip "Open-Core Design Philosophy"
    The Public Core SDK ships reference implementations for intent scoring, the SignedAI jury runner, memory compression, and 5 reference microservices. High-value enterprise orchestration and proprietary execution clusters are smart-masked within the Private Enterprise Engine.

---

## Architecture Topology & Boundaries

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        🌐 PUBLIC CORE (Apache 2.0 Open Source SDK)                     │
│  • FDIA Scorer Engine (core/fdia/fdia.py)                                               │
│  • JITNA Protocol RFC-001 Reference (rct_control_plane/)                              │
│  • SignedAI jury runner (signedai/)                                                     │
│  • Delta Engine Memory State Diffing (core/delta_engine/)                              │
│  • Regional Language Adapter (core/regional_adapter/)                                  │
│                                                                                        │
│  5 Production Reference Microservices (Integration Examples):                          │
│   1. [analysearch-intent] — Intent Analysis & Search Service                           │
│   2. [crystallizer]       — Context Compression & Memory State Service                 │
│   3. [gateway-api]        — Public API Gateway Interface                               │
│   4. [intent-loop]        — FDIA Control Loop Engine Service                           │
│   5. [vector-search]      — Basic Vector Embedding Search Service                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼ (Commercial Moat Boundary)
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     🔒 PRIVATE ENTERPRISE ENGINE (Smart Masked Clusters)               │
│ A separate, private codebase. It is not part of this repository and not offered today: │
│ no hosted service, no price, no customers, and no figure about it is quoted here.      │
│ Only this repository's own CI test count is quoted (docs/testing/TESTING_CANONICAL.md).  │
└────────────────────────────────────────────────────────────────────────────────────────┘

!!! note "On the private codebase"
    `Delentia-Private-OS` is a separate private codebase that this repository does not
    contain and cannot audit, so nothing about it is claimed here. The Public Core's own
    numbers are reproducible by anyone who clones this repository and runs the test suite,
    and that is the standard this page holds itself to for everything it presents as "public."
```

---

## Public Core Components

### 1. FDIA Scorer Engine
The mathematical core of intent grounding. Every action is scored before execution.

$$F = D^I \times A$$

- **F (Future/Fulfillment):** Execution confidence output score.
- **D (Data):** Data quality score ($0.0 - 1.0$).
- **I (Intent):** Intent precision exponent ($I \ge 1.0$).
- **A (Architect):** Human-in-the-loop gate. When $A=0$, $F=0$ and the gate refuses (on every path that applies it).

### 2. JITNA Protocol (RFC-001)
Canonical reference for intent packet transport ($I, D, \Delta, A, R, M$).

### 3. SignedAI Consensus
A jury runner: independent models vote agree, disagree or abstain, the tier sets the number of agreeing votes required, and the verdict is a SHA-256 digest that can be signed with Ed25519. Tested with scripted voters only.

### 4. 5 Reference Microservices
Shipped in `microservices/` with 142 dedicated integration tests:
- `analysearch-intent`: Intent classification and entity parsing.
- `crystallizer`: Memory state compaction.
- `gateway-api`: Standard REST/GraphQL gateway.
- `intent-loop`: FDIA scoring control loop.
- `vector-search`: Basic vector search backend.

---

## Proof of Scale & Enterprise Metrics

!!! note "Scope of this section"
    The figures below describe `Delentia-Private-OS`'s enterprise runtime — a separate,
    non-public codebase. They are self-reported and not independently verifiable from
    this repository. For an independently reproducible number, use the Public Core's own
    verified test count (this repo's own `docs/testing/TESTING_CANONICAL.md`) instead.

- **Test suite:** the public repository's CI count is the only count quoted (see `docs/testing/TESTING_CANONICAL.md`). An earlier private count of 4,849 was withdrawn: it cannot be verified.
- **Hallucination Protection:** no hallucination rate is claimed (the earlier "0.3%" was withdrawn); the SignedAI jury runner exists but has been tested with scripted voters only — internal methodology, see `docs/benchmark/hallucination-methodology.md` for the full protocol and its own disclosed limitations (simulated consensus in the public reproduction, non-public evaluation dataset, no independent review yet).
- **Memory Compression:** Delta Engine's measured saving is 39% (20 ticks) to 90% (500 ticks) against storing a full snapshot every tick — run `python scripts/measure_delta_engine_real.py` yourself to verify. The older 91.5% was a formula estimate and is withdrawn.

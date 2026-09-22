# Open-Core Architecture & Public Reference Overview

**RCT Platform / Delentia OS** provides an intent-centric constitutional AI SDK built on a 9-Tier architecture. The ecosystem is organized around a clear **Open-Core Architecture Boundary**: the **Public Open-Source Core (Apache 2.0)** and the **Private Enterprise Full Engine**.

!!! tip "Open-Core Design Philosophy"
    The Public Core SDK ships complete reference implementations for intent scoring, multi-LLM consensus, memory compression, and 5 production reference microservices. High-value enterprise orchestration and proprietary execution clusters are smart-masked within the Private Enterprise Engine.

---

## Architecture Topology & Boundaries

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        🌐 PUBLIC CORE (Apache 2.0 Open Source SDK)                     │
│  • FDIA Scorer Engine (core/fdia/fdia.py)                                               │
│  • JITNA Protocol RFC-001 Reference (rct_control_plane/)                              │
│  • SignedAI Multi-LLM Consensus Layer (signedai/core/)                                 │
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
│  • Cluster 1: [Delta Intent Engine Cluster]        ──▶ 15 Microservices / 10 Algorithms   │
│  • Cluster 2: [Logic & Safety Guard Cluster]      ──▶ 20 Microservices / 15 Algorithms   │
│  • Cluster 3: [Optimized Nodal Assembler Cluster]  ──▶ 27 Microservices / 16 Algorithms   │
│                                                                                        │
│  Proof of Scale & Complexity Metrics (self-reported enterprise snapshot,                │
│  not independently verified — see note below):                                          │
│   - 4,849 enterprise test cases (private runtime, separate from the public              │
│     SDK's own verified suite — see the Public Core's own test count instead             │
│     for an independently reproducible number)                                           │
│   - <0.3% hallucination rate target (internal methodology; see                          │
│     docs/benchmark/hallucination-methodology.md for the full protocol and               │
│     its own disclosed limitations)                                                      │
│   - Crash-rate and VRAM-optimization figures for this private tier are not              │
│     yet published with a reproducible methodology and are omitted here                  │
│     pending one — see CLAIM_REGISTRY.md §2 for what "not yet qualified"                 │
│     means in practice                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────┘

!!! warning "On the Enterprise metrics above"
    These describe `Delentia-Private-OS`'s runtime, a separate private codebase this
    document does not have access to audit. They are reproduced here as self-reported
    context, not as claims this repository can verify. The Public Core's own numbers
    (this repo, this SDK) are independently reproducible by anyone who clones it and
    runs the test suite themselves — that is the standard this page holds itself to for
    everything it presents as "public."
```

---

## Public Core Components

### 1. FDIA Scorer Engine
The mathematical core of intent grounding. Every action is scored before execution.

$$F = D^I \times A$$

- **F (Future/Fulfillment):** Execution confidence output score.
- **D (Data):** Data quality score ($0.0 - 1.0$).
- **I (Intent):** Intent precision exponent ($I \ge 1.0$).
- **A (Architect):** Human-in-the-loop gate. When $A=0$, output is constitutionally blocked.

### 2. JITNA Protocol (RFC-001)
Canonical reference for intent packet transport ($I, D, \Delta, A, R, M$).

### 3. SignedAI Consensus
Jury-based multi-LLM consensus voting ($\ge 75\%$ consensus threshold, variance $\le \pm 0.20$) with SHA-256 cryptographic attestation.

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

- **Enterprise Test Suite:** 4,849 property-based and integration test cases across Python 3.10–3.12 (self-reported, private runtime — see note above).
- **Hallucination Protection:** Target $<0.3\%$ hallucination rate via SignedAI multi-model consensus — internal methodology, see `docs/benchmark/hallucination-methodology.md` for the full protocol and its own disclosed limitations (simulated consensus in the public reproduction, non-public evaluation dataset, no independent review yet).
- **Memory Compression:** Delta Engine's public, independently reproducible measurement is 91.5% (design floor ≥74%) — run `python scripts/benchmark_fdia_delta.py --json` yourself to verify.

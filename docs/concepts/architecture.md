# Architecture Overview

**RCT Platform is organized as an 11-layer constitutional AI stack.**

---

## Layer Diagram

```
┌──────────────────────────────────────────────────────────┐
│               RCT PLATFORM SDK v2.0.0                    │
│         Intent-Centric AI Operating System               │
└──────────────────────────────────────────────────────────┘

Layer 11: CI/CD & Quality Gates
├─ GitHub Actions (ci.yml + security-scan.yml)
├─ 1,791 passing tests · 91% coverage · Python 3.10/3.11/3.12
└─ Bandit 0 HIGH · mypy clean

Layer 10: Enterprise Hardening
├─ Pre-commit hooks (black, isort, bandit)
├─ Semantic versioning (2.0.0)
└─ CITATION.cff · CODE_OF_CONDUCT.md · CONTRIBUTING.md

Layer 9: Regional & Compliance
├─ 8 regional pairs (TH, JP, KR, CN, VN, ID, TW, US)
├─ PDPA / PIPA / PIPL / GDPR adapters
└─ core/regional_adapter/

Layer 8: Reference Microservices (5)
├─ intent-loop         ← 7-state pipeline, FDIA gating
├─ analysearch-intent  ← GIGOProtector, adversarial self-refinement
├─ vector-search       ← FAISS + Qdrant backends
├─ crystallizer        ← concept graph, keyword extraction
└─ gateway-api         ← routing, CORS, health

Layer 7: Intent Loop Engine
├─ RECEIVED → VALIDATED → MEMORY_CHECK → COMPUTING
├─ → VERIFYING → COMMITTING → COMPLETED
├─ Cold start: 3–5s   Warm recall: <50ms
└─ rct_control_plane/intent_compiler.py

Layer 6: SignedAI Consensus
├─ S/4/6/8 tier framework
├─ ED25519 cryptographic attestation
├─ 9 HexaCore roles (+ Ollama LOCAL + Groq LPU)
└─ signedai/core/

Layer 5: Delta Engine
├─ 91.5% measured compression (design floor ≥74%)
├─ SHA-256 per-record deduplication
├─ Full rollback to any past tick
└─ core/delta_engine/

Layer 4: FDIA Engine
├─ F = D^I × A  (constitutional equation)
├─ A=0 → full block (governance guarantee)
├─ Accuracy: 0.92 vs industry 0.65
└─ core/fdia/fdia.py

Layer 3: Control Plane DSL (15 modules)
├─ intent_schema · dsl_parser · execution_graph_ir
├─ policy_language · observability · replay_engine
├─ jitna_protocol · signed_execution · cli · api
└─ rct_control_plane/

Layer 2: JITNA Protocol (RFC-001 v2.0)
├─ Wire format: { I, D, Δ, A, R, M }
├─ Standard for cross-agent intent negotiation
└─ signedai/core/models.py

Layer 1: Core SDK Primitives
├─ IntentObject · ExecutionGraph · DSLParser
├─ FDIAScorer · SignedAIRegistry · MemoryDeltaEngine
└─ Exportable under Apache 2.0
```

---

## Data Flow — Single Intent Request

```mermaid
sequenceDiagram
    participant U as User/Agent
    participant CP as Control Plane
    participant FDIA as FDIA Engine
    participant SAI as SignedAI Consensus
    participant DE as Delta Engine

    U->>CP: POST /compile (JITNAPacket)
    CP->>FDIA: score_action(intent, data, architect)
    FDIA-->>CP: score ∈ [0.0, 1.0]
    alt score < threshold or A=0
        CP-->>U: 403 Blocked (constitutional gate)
    else score ≥ threshold
        CP->>SAI: verify(action, tier)
        SAI-->>CP: consensus + ED25519 signature
        CP->>DE: record_delta(agent_id, tick, changes)
        DE-->>CP: compressed delta saved
        CP-->>U: 200 OK (signed execution graph)
    end
```

---

## Key Design Decisions

### Why the FDIA equation is not a config option
The equation `F = D^I × A` is enforced at the **mathematics level**. Governance is not a switch — when A=0, F=0 by arithmetic, not by condition check. This makes the guarantee **unforgeable**.

### Why deltas instead of state snapshots
Storing full agent state at every tick is O(n×t). Delta Engine stores only `changed_fields` with SHA-256 content hashing, achieving 91.5% measured compression (design floor ≥74%) on typical agent trajectories. Full rollback is still possible by replaying the delta chain.

### Why ED25519 over RSA
ED25519 signatures are 64 bytes vs RSA-2048's 256 bytes, verify 3× faster, and offer equivalent security. Critical for high-throughput multi-LLM consensus where thousands of decisions need attestation per second.

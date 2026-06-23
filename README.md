# Delentia OS — Intent-Centric AI Operating System

[![CI](https://github.com/delentia-labs/Delentia-OS/actions/workflows/ci.yml/badge.svg)](https://github.com/delentia-labs/Delentia-OS/actions/workflows/ci.yml)
[![Security](https://github.com/delentia-labs/Delentia-OS/actions/workflows/security-scan.yml/badge.svg)](https://github.com/delentia-labs/Delentia-OS/actions/workflows/security-scan.yml)
[![codecov](https://codecov.io/gh/delentia-labs/Delentia-OS/graph/badge.svg?token=IE08MVKA6C)](https://app.codecov.io/gh/delentia-labs/Delentia-OS)
[![Version](https://img.shields.io/badge/version-2.2.6-blue)](CHANGELOG.md)
[![PyPI](https://img.shields.io/badge/PyPI-v2.2.6-gold)](https://pypi.org/project/delentia-os/)
[![npm](https://img.shields.io/badge/npm-%40delentia%2Fdelentia--os-cb3837?logo=npm)](https://www.npmjs.com/package/@delentia/delentia-os)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Docs](https://img.shields.io/badge/docs-rctlabs.github.io-blue?logo=readthedocs&logoColor=white)](https://delentia-labs.github.io/Delentia-OS/)
[![Status](https://img.shields.io/badge/status-STABLE%20SDK-brightgreen)](CHANGELOG.md)
[![Website](https://img.shields.io/badge/website-delentia.com-brightgreen)](https://delentia.com)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/delentia-labs/Delentia-OS/blob/main/notebooks/rct_playground.ipynb)
[![Open in Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/delentia-labs/Delentia-OS/main?filepath=notebooks%2Frct_playground.ipynb)
[![Open in Codespaces](https://img.shields.io/badge/Open%20in-Codespaces-181717?logo=github&logoColor=white)](https://codespaces.new/delentia-labs/Delentia-OS)

## Intent-Centric AI Operating System — Constitutional Architecture

> **RCT** = **Reverse Component Thinking** — decompose any system into its smallest verifiable parts, then rebuild with constitutional guarantees.

---

## What is RCT?

**Delentia OS** is the open SDK layer of the RCT Ecosystem — the world's first **Intent-Centric AI Operating System** with constitutional architecture. Think of it as **"Linux for AI Agents."** It provides:

- **Auditability** — every decision traces back to a signed evidence chain
- **Governance** — multi-tier consensus prevents unilateral AI action  
- **Interpretability** — the FDIA equation makes intent and confidence explicit
- **Regional awareness** — built-in adapters for ASEAN, JP, KR, CN contexts

The full ecosystem runs in production at [delentia.com](https://delentia.com).  
This SDK exposes the core components under Apache 2.0.

🌐 **Website:** [delentia.com](https://delentia.com) · 🔗 **GitHub:** [github.com/delentia-labs](https://github.com/delentia-labs)

---

## Start Here in 5 Minutes

If you're arriving from social media or seeing RCT Platform for the first time, use this path:

1. **Try the offline demo** — run `python examples/quickdemo.py` or open `notebooks/rct_playground.ipynb`
2. **Verify the claims** — see [`docs/testing/TESTING_CANONICAL.md`](docs/testing/TESTING_CANONICAL.md) for the current authoritative test and coverage checkpoint
3. **Understand the scope boundary** — compare the open SDK surface vs enterprise-only surface in the table below
4. **Check release readiness** — see [`docs/release/RELEASE_READINESS_CHECKLIST.md`](docs/release/RELEASE_READINESS_CHECKLIST.md)
5. **Find support channels** — see [`docs/community/GITHUB_UI_LAUNCH_CHECKLIST.md`](docs/community/GITHUB_UI_LAUNCH_CHECKLIST.md) for Discussions, milestones, About, Topics, and profile setup

---

## What's Included in This SDK

| Component | In This SDK (Apache 2.0) | Enterprise Only (Proprietary) |
|-----------|--------------------------|-------------------------------|
| FDIA Scorer + equation engine | ✅ `core/fdia/fdia.py` | — |
| SignedAI multi-LLM consensus | ✅ `signedai/core/` | — |
| HexaCoreRole registry (10 roles v2.3) | ✅ `signedai/core/registry.py` | — |
| Delta Engine (91.5% measured compression, design floor ≥74%) | ✅ `core/delta_engine/` | — |
| Regional Language Adapter | ✅ `core/regional_adapter/` | — |
| RCT Control Plane DSL (22 modules) | ✅ `rct_control_plane/` | — |
| JITNA Protocol v3 (Intake + Negotiation) | ✅ `rct_control_plane/jitna_protocol_v3.py` | — |
| TOON Formatter (ALGO-42 compression engine) | ✅ `rct_control_plane/toon_formatter.py` | — |
| CORD Security Engine (100 injection patterns) | ✅ `rct_control_plane/cord_security.py` | — |
| ZK-FDIA (Zero-Knowledge Pedersen proofs) | ✅ `rct_control_plane/zk_fdia.py` | — |
| Helix-TTD (Topological drift detector) | ✅ `rct_control_plane/helix_ttd.py` | — |
| PaymentEngine (Metered billing & trust gates) | ✅ `rct_control_plane/payment_engine.py` | — |
| NodeNetwork (2/3 supermajority consensus) | ✅ `rct_control_plane/node_network.py` | — |
| Groq LPU Adapter (Llama 3.3 integration) | ✅ `signedai/core/groq_adapter.py` | — |
| PostgresPersistence (Layer 5/6 DB bridge) | ✅ `rct_control_plane/persistence_pg.py` | — |
| rct-edge (TypeScript Edge Package) | ✅ `sdk-typescript/packages/rct-edge/` | — |
| fdia-wasm (TypeScript WebAssembly Package) | ✅ `sdk-typescript/packages/fdia-wasm/` | — |
| 5 Reference Microservices | ✅ `microservices/` (297 passing tests) | — |
| CLI (`rct` entry point) | ✅ editable install or built wheel | — |
| Genome / Creator Profile API | ❌ 501 stub (`genome_api.py`) | ✅ Full implementation |
| Full Production Microservice Stack | ❌ | ✅ 62 microservices |
| Enterprise Dashboard | ❌ | ✅ |
| Docker Compose + full infra | ❌ | ✅ |
| 8-level test pyramid (4,849 tests) | ❌ | ✅ private |

> **Stable SDK** means: API is stable, CI enforces 90% coverage floor, packages published on PyPI + npm.  
> **Enterprise** means: runs at [delentia.com](https://delentia.com) — contact for licensing.

---

## Products

| Product | Description | Link |
|---------|-------------|------|
| 🤖 **Delentia Platform** | Core intent-centric AI platform — full ecosystem access | [delentia.com/products/delentia-platform](https://delentia.com/en/products/delentia-platform) |
| 🎨 **Delentia AI** | AI-powered creative studio — intent-driven content generation | [delentia.com/products/delentia-ai](https://delentia.com/en/products/delentia-ai) |
| ✍️ **SignedAI** | Cryptographic verification layer — ED25519 signed AI outputs | [delentia.com/products/signed-ai](https://delentia.com/en/products/signed-ai) |

> All three products run on the same RCT OS constitutional core. SignedAI powers hallucination prevention via multi-LLM consensus + ED25519 attestation.

---

## The FDIA Equation

$$F = D^I \times A$$

| Symbol | Meaning |
|--------|---------|
| **F** | **Future** — the desired output the AI must deliver |
| **D** | Data quality — accuracy and completeness of inputs (0.0–1.0) |
| **I** | Intent precision — clarity of intent acts as an **exponent** (higher = amplifies result) |
| **A** | **Architect** — Human-in-the-loop approval gate (0.0–1.0) |

> **When Intent is high (I→2), even moderate Data quality produces excellent results.**  
> **When A = 0, all output is blocked** — Constitutional AI guarantee. The system never acts without human approval.

Accuracy: **0.92** (industry baseline: ~0.65). Implemented in [`core/fdia/fdia.py`](core/fdia/fdia.py).

---

## Key Numbers

| Metric | Value |
|--------|-------|
| **Public SDK validation** | See [`docs/testing/TESTING_CANONICAL.md`](docs/testing/TESTING_CANONICAL.md) for the current verified checkpoint |
| **Algorithms** | 41 (Tier 1–9, reference implementations) |
| **LLM Models** | 10 HexaCore roles (3 Western + 3 Eastern + 1 Regional + 1 Thai + 1 Local + 1 LPU) — v2.3 |
| **Hallucination Rate** | 0.3% (vs industry 12–15%) — 97% reduction via SignedAI |
| **Memory Compression** | 91.5% measured (design floor ≥74%) via Delta Engine (stores state diffs, not full state) |
| **Intent Recall Speed** | Cold start 3–5s → Warm recall <50ms (Intent Loop) |
| **Uptime SLA** | 99.98% |
| **Languages** | 8 regional pairs (JP, KR, CN, TW, TH, VN, ID, US) |
| **Universal Adapters** | 13 (Home Assistant, Terraform, n8n, Obsidian, Playwright, ...) |
| **FDIA Accuracy** | 0.92 (industry baseline: ~0.65) |

For the current single source of truth, see [`docs/testing/TESTING_CANONICAL.md`](docs/testing/TESTING_CANONICAL.md).

---

## Architecture

```text
┌──────────────────────────────────────────────────────────┐
│               RCT PLATFORM SDK v2.0.0                    │
│         Intent-Centric AI Operating System               │
└──────────────────────────────────────────────────────────┘

Layer 11: CI/CD & Quality Gates
├─ GitHub Actions (ci.yml + security-scan.yml)
├─ 1,791 passing tests · 90% coverage floor · Python 3.10/3.11/3.12
└─ E2E integration tests (no Docker required)

Layer 10: Enterprise Hardening
├─ Security (JWT RS256, RBAC, ABAC, Rate Limiting)
├─ Validation (SQL Injection 3-layer, Pydantic v2, XSS)
└─ Resilience (Circuit Breaker, Retry policies)

Layer 9: Control Plane
├─ JITNA Wire Schema (JITNAPacket: I, D, Δ, A, R, M)
├─ TOON Formatter (ALGO-42 compression, 40-50% token savings)
├─ Ed25519 Signed Execution (RFC 8032)
├─ Replay Engine (SHA-256 checkpoints)
└─ rct_control_plane: 15-module DSL + intent schema

Layer 8: Regional Language (8 markets)
├─ LanguageDetector (EN, TH, JA, KO, ZH, VI, ID)
└─ RegionalModelRouter (LRU cache, 4-level resolution)

Layer 7: Universal Adapters (13 integrations)
└─ Home Assistant · Terraform · n8n · Obsidian · Playwright · ...

Layer 6: JITNA Protocol (RFC-001 v2.0)
└─ AI-to-AI intent wire format + task negotiation

Layer 5: SignedAI — Multi-LLM Consensus
├─ TIER_S (1) · TIER_4 (4) · TIER_6 (6) · TIER_8 (8 + veto)
└─ Hallucination rate: 0.3% vs industry 12–15%

Layer 4: RCTDB v2.0 — 8-Dimensional Universal Memory
└─ Registry Zone · Vault Zone · Governance Zone

Layer 3: 41 Production Algorithms (Tier 1–9)
Layer 2: OS Primitives (6 Kernel RFCs)
Layer 1: 7 Genome System + Cognitive Kernel

SDK Modules: signedai/ · core/ · rct_control_plane/
             5 reference microservices
```

> **Enterprise layer** (62 microservices, proprietary) runs in production at [delentia.com](https://delentia.com).

---

## Quick Install (No API Keys Required)

```bash
# 1. Clone & install
git clone https://github.com/delentia-labs/delentia-os.git
cd delentia-os
pip install -e .

# 2. Validate the CLI surface without API keys
rct version
rct start --ui-test

# 3. Create a local .env template for real runs
rct init
rct doctor

# 4. Run the 5-minute offline demo — zero API keys needed
python examples/quickdemo.py

# 5. Run the FDIA benchmark (target: 0.92 accuracy)
python benchmark/fdia_benchmark.py --verbose

# 6. Try the CLI
rct compile 'Protect resources from hostile agents'
rct governance
rct timeline
```

**Expected output (quickdemo.py):**
```
✅  Best action: act_001 (cooperate) — highest FDIA score
Consensus: PASSED ✅ (threshold: 4/6)
Final decision: EXECUTE — all 7 gates cleared, FDIA ≥ threshold, intent signed
Memory compression ratio: 5.0× (baseline + 4 deltas vs 5 full-state copies)
```

**Expected output (fdia_benchmark.py):**
```
RCT FDIA Score       : 0.9167
Industry Baseline    : 0.6500
Delta vs Baseline    : +0.2667 (+41.0%)
✅  Benchmark PASSED
```

## Quick Start (With API Keys)

```bash
# 1. Generate a local .env template
rct init
# Edit .env with your API keys

# 2. Run tests
python -m pytest microservices/ -q

# 3. Try the SignedAI demo
python examples/signed_ai_demo.py

# 4. Try the Hexa-Core demo
python examples/hexa_core_demo.py
```

**Expected output (signed_ai_demo.py):**
```
ALL IMPORTS OK
Tier 6: 6 signers, required=4
Consensus: True, confidence=75.00%
Supreme Architect: anthropic/claude-opus-4.6
```

## Verify This Repository Quickly

Use these paths when you need evidence, not marketing copy:

- **Current test and coverage checkpoint** — [`docs/testing/TESTING_CANONICAL.md`](docs/testing/TESTING_CANONICAL.md)
- **Release gate checklist** — [`docs/release/RELEASE_READINESS_CHECKLIST.md`](docs/release/RELEASE_READINESS_CHECKLIST.md)
- **Public export and provenance policy** — [`docs/release/PUBLIC_RELEASE_PROVENANCE.md`](docs/release/PUBLIC_RELEASE_PROVENANCE.md)
- **GitHub UI launch tasks** — [`docs/community/GITHUB_UI_LAUNCH_CHECKLIST.md`](docs/community/GITHUB_UI_LAUNCH_CHECKLIST.md)

---

## Core Components

### FDIA Engine (`core/fdia/fdia.py`)

The FDIA Scorer evaluates candidate NPC/agent actions using a weighted constitutional formula. All methods are pure functions — deterministic, no side effects.

```python
from core.fdia.fdia import FDIAScorer, FDIAWeights, NPCAction, NPCIntentType

scorer = FDIAScorer(weights=FDIAWeights())
score = scorer.score_action(
    agent_intent=NPCIntentType.DISCOVER,
    action=NPCAction(action_id="a1", action_type="explore"),
    world_resources={"knowledge": 50.0},
    agent_reputation=0.85,
    other_intents=[NPCIntentType.PROTECT],
    governance_penalty=0.0,
)
print(f"FDIA score: {score:.4f}")  # deterministic float in [0.0, 1.0]
```

### SignedAI Consensus (`signedai/core/`)

Multi-tier verification framework for AI decisions. Routes to the appropriate tier based on risk level.

```python
from signedai.core.registry import SignedAITier, RiskLevel, SignedAIRegistry
from signedai.core.router import TierRouter

# Tier selection by risk level
tier_config = SignedAIRegistry.get_tier_by_risk(RiskLevel.HIGH)
print(f"High-risk → {tier_config.tier.value}: {len(tier_config.signers)} signers")

# Consensus calculation
result = SignedAIRegistry.calculate_consensus(
    tier=SignedAITier.TIER_6,
    votes_for=4,
    votes_against=2,
)
print(f"Consensus: {result.consensus_reached}, confidence={result.confidence:.2%}")

# Cost estimation
total_cost, breakdown = SignedAIRegistry.estimate_tier_cost(
    SignedAITier.TIER_6, input_tokens=10_000, output_tokens=5_000
)
print(f"TIER_6 cost: ${total_cost:.4f}")
```

**SignedAI Tier Reference:**

| Tier | Signers | Geopolitical Balance | Required Votes | Use Case |
|------|---------|---------------------|----------------|----------|
| TIER_S | 1 | — | 1 | Chat, low-risk queries |
| TIER_4 | 4 | 2 West + 2 East | 3 (75%) | Code review, API design |
| TIER_6 | 6 | 3 West + 3 East | 4 (67%) | Production releases, DB migrations |
| TIER_8 | 6 + chairman veto | 3W + 3E + override | 6 (75%) | Critical infrastructure, crisis |

### Delta Engine (`core/delta_engine/memory_delta.py`)

Stores agent memory as compressed delta sequences — only what changed, not full state.

| Property | Value |
|----------|-------|
| **Compression** | 91.5% measured (design floor ≥74%) — stores DIFF, not full state |
| **Deduplication** | SHA-256 content hash per record |
| **Rollback** | Replay any agent to any past tick via delta chain |

```python
from core.delta_engine.memory_delta import (
    MemoryDeltaEngine, AgentMemoryState, NPCIntentType
)

engine = MemoryDeltaEngine()
engine.register_agent("agent-1", AgentMemoryState(
    agent_id="agent-1", tick=0,
    intent_type=NPCIntentType.ACCUMULATE,
    resources={"gold": 100.0},
))
engine.record_delta(
    agent_id="agent-1", tick=5,
    intent_type=NPCIntentType.ACCUMULATE,
    action_type="trade", outcome="success",
    resource_changes={"gold": 10.0},
)
state = engine.get_state_at_tick("agent-1", tick=5)
print(f"Gold at tick 5: {state.resources['gold']}")
print(f"Compression: {engine.compute_compression_ratio():.1%}")
```

### Intent Loop Engine

Every user intent passes through a 7-state pipeline:

```
RECEIVED → VALIDATED (FDIA) → MEMORY_CHECK → COMPUTING
         → VERIFYING (SignedAI) → COMMITTING (RCTDB) → COMPLETED
```

| Property | Value |
|----------|-------|
| **Cold Start** | 3–5 seconds (full computation + SignedAI consensus) |
| **Warm Recall** | <50ms (memory hit, semantic similarity > 0.95) |
| **Cost Trend** | Decreases as memory fills — approaches $0 for repeated intents |

### JITNA Protocol (RFC-001 v2.0)

> **Just In Time Nodal Assembly** — agents are assembled into working groups just in time based on intent, then dissolved when the task completes.

Full documentation: [docs/concepts/jitna.md](docs/concepts/jitna.md) | [RFC-001 Specification](docs/architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md)

JITNA is a three-layer system:
- **Layer 1 — Protocol** (`rct_control_plane/jitna_protocol.py`): RFC-001 wire format, Ed25519 signed packets, The 9 Codex
- **Layer 2 — Language** (6-field I/D/Δ/A/R/M templates): 50+ workflow templates for structured intent expression
- **Layer 3 — Intake** (`microservices/intent-loop/loop_engine.py`): user-facing JITNAPacket + LoopMetrics

```python
from signedai.core.models import JITNAPacket

# SignedAI Semantic Layer — verification-focused variant
# (D=Domain, A=Assumptions, R=Requirements, M=Metrics)
packet = JITNAPacket(
    I="Refactor authentication module",
    D="Backend engineering",
    **{"Δ": "Adopt clean architecture pattern"},
    A="No breaking changes to public API",
    R="Test coverage must remain > 90%",
    M="All existing tests pass, cyclomatic complexity < 10",
)
```

The canonical 6-field JITNA Language schema uses I=Intent, D=**Data**, Δ=Delta, A=**Approach**, R=**Reflection**, M=**Memory** — the SignedAI variant above uses different field semantics for verification context. See [docs/concepts/jitna.md](docs/concepts/jitna.md) for the full disambiguation.

### Regional Adapter (`core/regional_adapter/regional_adapter.py`)

Context adaptation for multi-region deployments:

| Region | Languages | Compliance |
|--------|-----------|------------|
| Thailand | TH, EN | PDPA |
| Japan | JA, EN | — |
| South Korea | KO, EN | PIPA |
| China | ZH, EN | PIPL |
| Vietnam | VI, EN | — |
| Indonesia | ID, EN | — |
| Taiwan | ZH-TW, EN | — |
| US/Global | EN | GDPR-ready |

### rct_control_plane

15-module DSL + intent schema for composing multi-step agent pipelines:

```python
from rct_control_plane import IntentObject, ExecutionGraph, DSLParser

parser = DSLParser()
graph = parser.parse(dsl_text)
print(f"Nodes: {len(graph.nodes)}, Edges: {len(graph.edges)}")
```

Available modules: `intent_schema` · `dsl_parser` · `execution_graph_ir` · `intent_compiler` · `policy_language` · `observability` · `control_plane_state` · `jitna_protocol` · `signed_execution` · `replay_engine` · `default_policies` · `cli` · `api` · `middleware` · `rich_formatter` · `plan_engine` · `architect_policy_loader` · `approval_gateway` · `otel_adapter`

### Enterprise CLI Commands (v1.1.0)

```bash
# Lifecycle
rct plan "Refactor auth module"         # Terraform-style simulation — cost, risk, model roster
rct apply "Deploy payment service"       # compile → evaluate → execute
rct apply -f examples/pipeline.yaml     # Run JITNA pipeline file

# Memory
rct memory history                       # AI decision timeline with SHA-256 audit chain
rct memory rollback 3                    # Roll back 3 ticks

# Policy Governance
rct policy add -f config/architect_policy.yaml   # Load policy rules from YAML
rct policy list                          # List active rules
rct policy test "Migrate database"       # Dry-run policy evaluation
rct approve --pending                    # Interactive approval queue

# Monitoring
rct serve                                # Start API server (GET /metrics for Prometheus)
```

### TypeScript SDK (`sdk-typescript/`)

```typescript
import { computeFDIA, RCTClient, selectSignedAITier } from './src/index';

// FDIA formula
const score = computeFDIA(0.85, 0.90, 1.0);  // F = D^I × A

// REST client
const client = new RCTClient('http://localhost:8000');
const result = await client.compile({ natural_language: 'Deploy service' });

// Governance tier selection
const tier = selectSignedAITier('enterprise', 'high');
```

### GitHub Action

```yaml
- uses: delentia-labs/delentia-os/github-action@v1.1.0
  with:
    intent: "Deploy to production"
    rct_api_url: ${{ secrets.RCT_API_URL }}
    user_tier: enterprise
    min_governance_score: "0.8"
    fail_on_reject: "true"
```

### Analysearch Intent (`microservices/analysearch-intent/`)

Multi-disciplinary deep analysis engine with adversarial self-refinement:

| Mode | Pipeline | Use Case |
|------|----------|----------|
| `quick` | Single-pass lookup | Fast factual queries |
| `standard` | Analysis + research synthesis | Standard decisions |
| `deep` | Mirror Mode (3 passes) | Critical analysis |
| `mirror` | PROPOSE → COUNTER → REFINE loop | Adversarial self-challenge |

Key capabilities:
- **GIGO Protection** — Entropy-based input validation; garbage in = rejected before any LLM call
- **Golden Keyword Crystallization** — ALGO-41 extracts the 3–5 decisive keywords from any query
- **Cross-Disciplinary Synthesis** — Connects insights across unrelated domains automatically
- **Intent Conservation** — Original intent preserved and checked through every refinement pass

### HexaCore Registry (`signedai/core/registry.py`)

10 purpose-specific AI roles with full geopolitical balance (v2.3):

| Role | Model | Country | Specialty |
|------|-------|---------|----------|
| SUPREME_ARCHITECT | claude-opus-4.6 | US | Architecture, reasoning, final decisions |
| LEAD_BUILDER | kimi-k2.5 | CN | Complex coding, visual analysis |
| JUNIOR_BUILDER | minimax-m2.1 | CN | Routine coding, unit tests |
| SPECIALIST | gemini-3-flash | US | Finance, health, multimodal, speed |
| LIBRARIAN | grok-4.1-fast | US | Long context (2M tokens), RAG, science |
| HUMANIZER | deepseek-v3.2 | CN | Natural language, creative, translation |
| **REGIONAL_CORE** | **pluggable (e.g. typhoon-v2, HyperCLOVA, Rakuten AI)** | **VARIOUS** | **Pluggable regional LLM, cultural & legal compliance** |
| **REGIONAL_THAI** | **typhoon-v2-70b** | **TH** | **Legacy Thai NLP specialist (maps to REGIONAL_CORE)** |
| **OLLAMA_ADAPTER** | **ollama (local)** | **LOCAL** | **Local LLM fallback supporting the 1+4 Pillar Architecture (Executor, Router, Guardian, Scribe) for air-gapped inference** |
| **GROQ_ADAPTER** | **llama-3.3-70b-versatile** | **LPU** | **Ultra-fast LPU inference, 128k ctx** |

```python
from signedai.core.registry import HexaCoreRegistry, HexaCoreRole

# All 10 roles
for role, model in HexaCoreRegistry.MODELS.items():
    print(f"{role.value}: {model.id} ({model.country})")

# Geopolitical balance
balance = HexaCoreRegistry.get_geopolitical_balance()
# → {'US': 3, 'CN': 3, 'TH': 1, 'REGION': 1}

# Pluggable regional specialist
regional = HexaCoreRegistry.get_model(HexaCoreRole.REGIONAL_CORE)
print(regional.specialties)  # ['Regional NLP', 'Local culture', 'Local legal', ...]

# Dynamic model resolution based on request context (e.g. Vietnam)
model_id = HexaCoreRegistry.get_model_id(
    HexaCoreRole.REGIONAL_CORE,
    context_lang="vi",
    context_region="VN"
)
# → 'alibaba/qwen-2.5-7b' (or any custom registered model)
```

---

## Microservices

Five reference microservices demonstrating production patterns:

| Service | Port | Description |
|---------|------|-------------|
| `intent-loop` | 8001 | Core FDIA execution loop |
| `analysearch-intent` | 8002 | Semantic search + intent analysis |
| `vector-search` | 8003 | Vector similarity search over RCTDB |
| `crystallizer` | 8004 | Output crystallization + fact verification |
| `gateway-api` | 8000 | Unified entry point + rate limiting |

Each service includes a `Dockerfile` and follows the OpenAPI contract in `contracts/openapi.yaml`.

---

## Benchmark Results

Reproducible benchmarks are in [`benchmark/`](benchmark/).

Run against your own setup:
```bash
python benchmark/run_benchmark.py --config benchmark/default_config.json
```

See [benchmark/README.md](benchmark/README.md) for methodology.

---

## API Contract

Full OpenAPI 3.1.0 specification: [`contracts/openapi.yaml`](contracts/openapi.yaml)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health |
| `/metrics` | GET | Prometheus metrics |
| `/v1/kernel/execute` | POST | Execute RCT Kernel with intent |
| `/v1/rctdb/query` | POST | Query RCTDB knowledge vault |

---

## Enterprise Platform — v1.1.0 (Current SDK) · v5.5.0 (Private)

> **Note:** This section records the enterprise platform history. The public SDK versioning starts at `v1.0.0-alpha`. See [CHANGELOG.md](CHANGELOG.md) for SDK release notes.

✅ **1,791 Passed · 0 Failed** — Full delentia-os SDK test suite (Phase A–D v2.0.0)  
✅ **Plan Engine** — `rct plan` Terraform-style pre-execution simulation  
✅ **Policy Governance** — `rct policy` + `approval_gateway.py` omni-channel human approval  
✅ **OTel + Prometheus + Grafana** — `GET /metrics` scrape endpoint + monitoring stack  
✅ **TypeScript SDK** — `sdk-typescript/`: fdia, jitna, signedai, client modules  
✅ **GitHub Action** — `rct-policy-gate` for CI/CD governance enforcement  

Previous milestone:  
✅ **4,849 Passed · 16 Skipped · 0 Failed · 0 Errors** — Complete private enterprise test suite (all 62 microservices)  

Full SDK changelog → [CHANGELOG.md](CHANGELOG.md)

---

## Whitepapers

- [Foundation (01)](docs/whitepapers/01_foundation/) — The FDIA equation, Hexagonal Core architecture, constitutional AI theory
- [Architecture (02)](docs/whitepapers/02_architecture/) — JITNA Protocol, SignedAI tier system, production deployment patterns

---

## Project Structure

```
delentia-os/
├─ core/                        # Core algorithms + AI engine
│  ├─ fdia/fdia.py              # FDIA Scorer (NPCIntentType, FDIAWeights)
│  ├─ delta_engine/             # Memory Delta Engine (74% compression)
│  └─ regional_adapter/         # 8-market language routing
├─ signedai/                    # SignedAI consensus framework
│  └─ core/
│     ├─ registry.py            # HexaCoreRegistry (7 models) + SignedAIRegistry
│     ├─ router.py              # TierRouter (risk → tier selection)
│     └─ models.py              # JITNAPacket, AnalysisJob
├─ rct_control_plane/           # 19-module DSL + intent schema + enterprise platform
│  ├─ plan_engine.py            # PlanEngine — Terraform-style pre-execution simulation
│  ├─ architect_policy_loader.py # PolicyRule YAML loader
│  ├─ approval_gateway.py       # Omni-channel human approval (SHA-256 tokens)
│  └─ otel_adapter.py           # OpenTelemetry bridge for FDIA metrics
├─ sdk-typescript/              # TypeScript SDK (fdia, jitna, signedai, client)
├─ github-action/               # rct-policy-gate GitHub Action (Node 20)
├─ microservices/               # 5 reference microservices
│  ├─ intent-loop/              # Core FDIA execution loop (port 8001)
│  ├─ analysearch-intent/       # Deep analysis + Mirror Mode (port 8002)
│  ├─ vector-search/            # RCTDB semantic search (port 8003)
│  ├─ crystallizer/             # Output crystallization (port 8004)
│  └─ gateway-api/              # Unified entry + rate limiting (port 8000)
├─ config/                      # Configuration files
│  ├─ architect_policy.yaml     # 6 constitutional policy rules
│  ├─ prometheus.yml            # Prometheus scrape config
│  └─ grafana-datasources.yml   # Grafana auto-provision
├─ docker-compose.monitoring.yml # Prometheus + Grafana + OTel Collector stack
├─ examples/                    # Working code demos + pipeline.yaml
├─ contracts/openapi.yaml       # OpenAPI 3.1.0 spec
└─ docs/                        # Architecture docs + whitepapers
   └─ assets/grafana-dashboard.json  # Pre-built Control Plane dashboard
```

---

## Built With

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white)

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- 🐛 [Report Bugs](https://github.com/delentia-labs/delentia-os/issues)
- 💡 [Suggest Features](https://github.com/delentia-labs/delentia-os/discussions)
- 📖 Improve docs
- 🧪 Add tests
- 🔌 Build adapters for new integrations

---

## Security

For vulnerability reports, see [SECURITY.md](SECURITY.md).  
Do **not** open public issues for security findings.

---

## 👤 About the Author

**Ittirit Saengow (อิทธิฤทธิ์ แซ่โง้ว)**  
*Architect & Sole Creator of RCT Platform and the RCT Ecosystem*

> *"I'm a solo developer from Klong Toei, Bangkok. I believe AI governance should be a mathematical guarantee — not a setting you can turn off."*

### Origin Story

In June 2025, I started asking a question no one had answered clearly: **Why does AI safety depend on configuration files instead of math?**

On August 11, 2025 — a personal turning point — I wrote the first version of the FDIA equation on paper:

```
F = D^I × A
```

The insight: when `A = 0`, the output `F = 0` **by the properties of multiplication** — no code path can bypass it. That's a constitutional guarantee, not a setting.

Over the next 10 months, working alone from a room in **Klong Toei, Bangkok**, I built that equation into:
- A 11-layer constitutional AI operating system
- 41 production algorithms (Tier 1–9)
- The JITNA Protocol (RFC-001) — an open standard for AI-to-AI communication
- SignedAI: multi-LLM consensus with ED25519 cryptographic attestation
- **1,287 passing tests**, 92% coverage, with 0 skips
- A 450+ page whitepaper documenting every decision

This is not a research paper. It runs in production at [delentia.com](https://delentia.com).

| | |
|---|---|
| **GitHub** | [@ittirit-delentia](https://github.com/ittirit-delentia) |
| **Email** | ittirit720@gmail.com |
| **Org** | founder@delentia.com |
| **Website** | [delentia.com](https://delentia.com) |
| **LinkedIn** | [linkedin.com/in/ittirit-saengow](https://www.linkedin.com/in/ittirit-saengow/) |
| **X / Twitter** | [@ittirit_rct](https://x.com/ittirit_rct) |
| **Reddit** | [u/WindLate5307](https://www.reddit.com/user/WindLate5307/) |
| **BIO** | [ittiritsaengow.link](https://ittiritsaengow.link) |
| **Docs** | [rctlabs.github.io/delentia-os](https://delentia-labs.github.io/delentia-os/) |
| **Location** | Klong Toei, Bangkok, Thailand 🇹🇭 |
| **Started** | June 2025 |
| **Turning Point** | August 11, 2025 |

### Timeline

| Period | Milestone |
|--------|-----------|
| Jun 2025 | First FDIA equation written |
| Aug 11, 2025 | Commitment to build RCT OS |
| Oct 2025 | JITNA Protocol RFC-001 drafted |
| Dec 2025 | Foundation whitepaper (~100 pages) |
| Jan 2026 | 41 algorithms complete, 4,849 enterprise tests |
| Feb 2026 | 3,053 Python files, Level 4 Virtuoso stress test |
| Apr 2026 | Public SDK — 723 tests, 89%+ coverage, Apache 2.0 release |
| May 2026 | Enterprise CLI Design System — Unicode block wordmark, FDIA formula card, boot animation, PyPI v1.0.4b0 live |
| June 2026 (current) | Enterprise Platform v1.1.0 — Plan/Apply/Memory/Policy/Approve CLI, TypeScript SDK, GitHub Action, OTel + Prometheus + Grafana, 800 tests 0 failed |

> See [ROADMAP.md](ROADMAP.md) for what comes next.

---

## The Delentia Ecosystem

Delentia OS is the open-source core. The full ecosystem extends across:

| Repository | Purpose | Status |
|---|---|---|
| [Delentia-OS](https://github.com/delentia-labs/Delentia-OS) | Core SDK — JITNA v3, FDIA, HexaCore, IntentKernel | ✅ Apache 2.0 |
| [Delentia-OS-Gui](https://github.com/delentia-labs/Delentia-OS-Gui) | Tauri desktop app — Delentia Desk (Win/Mac/Linux) | ✅ Apache 2.0 |
| [Delentia-AI-SLM](https://github.com/delentia-labs/Delentia-AI-SLM) | SLM fine-tuning factory — Llama 3.1 8B + QLoRA | ✅ Apache 2.0 |
| [Delentia-Ecosystem](https://github.com/delentia-labs/Delentia-Ecosystem) | Plugin registry — LINE, Slack, skill manifests | ✅ Apache 2.0 |
| [Delentia-Infra-Public](https://github.com/delentia-labs/Delentia-Infra-Public) | Community deployment — Docker, K8s, Helm, Terraform | ✅ Apache 2.0 |
| [Delentia-Infra-Enterprise](https://github.com/delentia-labs/Delentia-Infra-Enterprise) | Enterprise HA — EKS/GKE, Vault, PDPA/GDPR compliance | 🔒 Proprietary |
| [Delentia-Private-OS](https://github.com/delentia-labs/Delentia-Private-OS) | Enterprise platform — 62 microservices, 4,849 tests | 🔒 Proprietary |
| [Delentia-Website](https://github.com/delentia-labs/Delentia-Website) | Marketing + docs site — Next.js, Vercel | 🔒 Proprietary |

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

Copyright 2026 Ittirit Saengow (อิทธิฤทธิ์ แซ่โง้ว) — Delentia Labs  
Made with ❤️ from Bangkok, Thailand 🇹🇭


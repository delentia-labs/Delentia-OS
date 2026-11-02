# SDK modules and components (reference)

> **Moved from the README on 2026-11-01.** The README is now a short entrance; this is the detail that used to sit in it, with the text unchanged except where a line starts with **[corrected 2026-11-01]** or **[context 2026-11-01]**. Anything here that is older than the code is history, not a description of today: the status of each capability is in [Release levels](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/release/RELEASE_LEVELS.md) and the current test checkpoint is in [Testing](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/testing/TESTING_CANONICAL.md).

## What's Included in This SDK

| Component | In This SDK (Apache 2.0) | Enterprise Only (Proprietary) |
|-----------|--------------------------|-------------------------------|
| FDIA Scorer + equation engine | ✅ `core/fdia/fdia.py` | — |
| SignedAI jury runner (independent votes, signed verdict; scripted-voter tests only) | ✅ `signedai/` | — |
| `HexaCoreRegistry`: a table of example model roles used by the jury arithmetic (no fixed roster runs) | ✅ `signedai/core/registry.py` | — |
| Delta Engine (memory deltas: ~39% smaller after 20 ticks, ~90% after 500, measured in bytes; see Round 52; **[context 2026-11-01]** plain snapshot + zstd compresses as well, so this is a property of the format, not a claim of being better) | ✅ `core/delta_engine/` | — |
| Regional Language Adapter | ✅ `core/regional_adapter/` | — |
| RCT Control Plane DSL (22 modules) | ✅ `rct_control_plane/` | — |
| JITNA Protocol v3 (Intake + Negotiation) | ✅ `rct_control_plane/jitna_protocol_v3.py` | — |
| TOON Formatter (ALGO-42 compression engine) — **[corrected 2026-11-01]** the agent does not use it: measured on the runtime's own payloads it used about 15% MORE tokens than compact JSON (Round 54); the file stays on disk | ✅ `rct_control_plane/toon_formatter.py` | — |
| CORD Security Engine (100 injection patterns) | ✅ `rct_control_plane/cord_security.py` | — |
| ZK-FDIA: a hash commitment to an FDIA score (hides D, I, A; **not** a zero-knowledge proof, the verifier cannot check that the sealed F follows from them) | ✅ `rct_control_plane/zk_fdia.py` | — |
| Helix-TTD (Topological drift detector) | ✅ `rct_control_plane/helix_ttd.py` | — |
| PaymentEngine (Metered billing & trust gates) | ✅ `rct_control_plane/payment_engine.py` | — |
| NodeNetwork (2/3 supermajority consensus) | ✅ `rct_control_plane/node_network.py` | — |
| Groq LPU Adapter (Llama 3.3 integration) | ✅ `signedai/core/groq_adapter.py` | — |
| PostgresPersistence (Layer 5/6 DB bridge) | ✅ `rct_control_plane/persistence_pg.py` | — |
| rct-edge (TypeScript Edge Package) | ✅ `sdk-typescript/packages/rct-edge/` | — |
| fdia-wasm (TypeScript WebAssembly Package) | ✅ `sdk-typescript/packages/fdia-wasm/` | — |
| 5 Reference Microservices | ✅ `microservices/` (297 passing tests) | — |
| CLI (`delentia` entry point) | ✅ editable install or built wheel | — |
| Genome / Creator Profile API | ❌ 501 stub (`genome_api.py`) | ✅ Full implementation |
| Full Production Microservice Stack | ❌ | ✅ private |
| Enterprise Dashboard | ❌ | ✅ |
| Docker Compose + full infra | ❌ | ✅ |
| Private test suite (count not published) | ❌ | ✅ private |

> **Status: experimental.** The SDK surface is versioned and the full suite is **9,069 passed, 46 skipped, 0 failed** (CI, 2026-10-30, see [TESTING_CANONICAL](../testing/TESTING_CANONICAL.md)), CI enforces a 72% coverage floor (`--cov-fail-under=72`; Codecov separately targets 90% with tolerance), packages published on PyPI + npm. A passing suite is evidence about the code, not about how well a model uses it: no capable hosted model has driven the agent yet (see the table above).  
> **Enterprise** (not in this repository) means a separate proprietary layer; this repository does not offer it as a running service — contact for licensing or a design-partner conversation.

---

## Products

| Product | Description | Link |
|---------|-------------|------|
| 🤖 **Delentia OS** (this repository) | The agent runtime: loop, tools, memory, skills, approvals, audit log | [Quick start](https://github.com/delentia-labs/Delentia-OS#readme) |
| 🛡️ **Delentia Guard** | A policy filter that sits in front of any MCP server and checks each tool call (npm `delentia-guard`) | [delentia-mcp](https://github.com/delentia-labs/delentia-mcp) |
| 🔌 **Delentia MCP connector** | Six advisory tools hosted on Cloudflare Workers, reached through a stdio bridge (npm `delentia-mcp`) | [delentia-mcp](https://github.com/delentia-labs/delentia-mcp) |

> SignedAI is the optional jury runner: models you name vote independently and the verdict is signed with Ed25519. It has been tested with scripted voters only and has not been shown to reduce hallucination.

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
| **Compression** | 39% (20 ticks) to 90% (500 ticks) measured in bytes — stores DIFF, not full state; the gain grows with history length, and plain zstd over full snapshots does as well or better |
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

> **[context 2026-11-01]** This 7-state pipeline is the older **intent-loop reference microservice** (`microservices/intent-loop`), which simulates execution and verification (its `/health` says so). It is not the agent runtime's cycle. The runtime's cycle is the eight steps in the README (GUARD, THINK, ROUTE, ACT, COMPRESS, VERIFY, RECORD, LEARN), implemented in `rct_control_plane/governed_autonomous_loop.py`; the five pillars of the Intent Loop are reported per episode by `rct_control_plane/intent_loop.py`. The two are different abstractions and one is not a stage of the other.

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

Full documentation: [docs/concepts/jitna.md](../concepts/jitna.md) | [RFC-001 Specification](../architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md)

JITNA is a three-layer system:
- **Layer 1 — Protocol** (`rct_control_plane/jitna_protocol.py`): RFC-001 wire format, Ed25519 signed packets, The 9 Codex
- **Layer 2 — Language** (6-field I/D/Δ/A/R/M): a parser and formatter for the text form (`rct_control_plane/jitna_file.py`, Round 52) and the `.jitna` signed file; no template library ships in this repository, and earlier text that cited "50+ workflow templates" is withdrawn
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

The canonical 6-field JITNA Language schema uses I=Intent, D=**Data**, Δ=Delta, A=**Approach**, R=**Reflection**, M=**Memory** — the SignedAI variant above uses different field semantics for verification context. See [docs/concepts/jitna.md](../concepts/jitna.md) for the full disambiguation.

#### The `.jitna` file (Round 52)

A JITNA packet can be written as a signed file and sent over any network or medium; the receiver needs only the sender's public key. The 6-field language is plain text:

```text
I: Refactor the authentication module
D: 800-line monolith, no tests
Δ: separate domain logic from infrastructure
A: hexagonal architecture
M: all tests must pass
```

```bash
delentia jitna keygen --out ~/.delentia/keys/jitna.pem        # prints the public key to publish
delentia jitna pack --language intent.txt --source planner --target worker --key ~/.delentia/keys/jitna.pem -o task.jitna
delentia jitna verify task.jitna --trust <sender public key>   # exit 0 valid+trusted, 3 valid but not trusted, 1 invalid
delentia jitna unpack task.jitna --trust <sender public key>   # prints the language, only from a file that verifies
```

Each packet carries its own Ed25519 signature, and the file carries a **seal** over the whole body. The seal matters because a packet's own hash leaves `priority`, `correlation_id`, `metadata` and `status` outside what is signed. "Valid" (nothing changed after signing) and "trusted" (you pinned the signer's key) are reported separately: anyone can generate a key and sign anything. A `.jitna` file is signed, not encrypted. Receivers can also `POST /v1/jitna/verify`. Code: `rct_control_plane/jitna_file.py`.

---

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

> **Historical, not currently runnable (noted 2026-09-24, version note updated 2026-09-25):** this block
> describes v1.1.0's command surface; the current public CLI (`delentia`)
> does not have `plan`, `apply`, `memory`, `policy`, or `approve`
> commands - confirmed against `delentia --help`'s real, current command
> list (`adapter, audit, build, chat, compile, doctor, evaluate,
> governance, init, list, logs, metrics, replay, reset, serve, start,
> status, timeline, version`). `plan_engine.py` and `approval_gateway.py`
> are real modules with real logic (see "Available modules" above), just
> not wired to any CLI command today. Also: `rct` here means the CLI's
> old name - the real, current command is `delentia` (`pyproject.toml`'s
> `delentia = "rct_control_plane.cli:main"`). The `rct serve` line's own
> `(GET /metrics for Prometheus)` sub-claim is also fabricated - see the
> API Contract table's own correction below; no route in this repo has
> ever exposed `/metrics`, in v1.1.0 or since.

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

---

### HexaCoreRegistry: a table of example model roles (`signedai/core/registry.py`)

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

# All example roles in the table
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

### SignedAI jury (`signedai/runner.py`, `delentia jury`)

Several different models vote on a proposal and the verdict is signed. Give each tier role an endpoint in a JSON file (a key is never in the file; `credential_env` names a variable), then:

```bash
delentia jury run --config jury.json --tier tier_4 --question "Is this migration safe?" --proposal-file plan.md --sign-key jury-key.pem --out verdict.json
delentia jury verify verdict.json --pubkey <hex>
```

What it guarantees: members are asked independently and at the same time; a reply that is not a clear vote, a timeout, an error or a member the sovereignty policy forbids is an abstention (it never counts as agreement and cannot lift the ratio); a jury whose answering members are one model is not a consensus (opt out with `--allow-shared-model`, recorded in the verdict); in tier 8 the chairman can veto but cannot force a pass; the verdict carries a SHA-256 digest and an optional Ed25519 signature that `verify` re-checks together with the vote counts and the tier rules. What it does not do yet: the governed loop does not call it by itself, and no multi-vendor vote has been run with real keys.

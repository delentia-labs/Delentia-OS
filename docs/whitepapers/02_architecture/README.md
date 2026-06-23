# 🏗️ RCT Ecosystem — Architecture Whitepaper

<!-- @architecture-anchor -->
<!-- @ssot-anchor: architecture-canonical -->
<!-- See: docs/HEXA_CORE_SIGNEDAI_ARCHITECTURE.md for full implementation reference -->

**Technical Architecture Reference — Hexa-Core AI Orchestration System**

---

## 📋 Document Information

| Property | Details |
|----------|---------|
| **Document** | Architecture Whitepaper v2.1.3 |
| **Directory** | `/whitepapers/02_architecture/` |
| **Status** | ✅ PRODUCTION — Updated February 25, 2026 |
| **Source** | `docs/HEXA_CORE_SIGNEDAI_ARCHITECTURE.md` · `delentia_os/config/` |
| **Target Audience** | Solution Architects, System Designers, Technical Leads |
| **Maintainer** | Ittirit Saengow (The Architect) |
| **Classification** | PUBLIC / TECHNICAL |
| **Classification** | Apache 2.0 |

---

## 1. System Overview

The **RCT Ecosystem** is a Constitutional AI Operating System built on a **Hexa-Core multi-model orchestration** layer. Rather than relying on a single AI model, it routes every task to the most cost-optimal, capability-matched model from a curated set of six, then optionally verifies the result through a tiered **SignedAI** consensus protocol.

```
User Request
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│              ModelRouter  (TaskIntent → HexaCoreRole)        │
│                                                              │
│  CODING_COMPLEX  ──▶ LEAD_BUILDER     (Kimi K2.5)          │
│  CODING_SIMPLE   ──▶ JUNIOR_BUILDER   (MiniMax M2.1)        │
│  FINANCE/HEALTH  ──▶ SPECIALIST       (Gemini 3 Flash)      │
│  RAG/SCIENCE     ──▶ LIBRARIAN        (Grok 4.1 Fast)       │
│  CHAT/TRANSLATE  ──▶ HUMANIZER        (DeepSeek V3.2)       │
│  ARCHITECTURE    ──▶ SUPREME_ARCH     (Claude Opus 4.6)     │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌───────────────────────────────────────────────┐
│        SignedAI Consensus  (optional)          │
│  Tier S → 1 signer  |  Tier 4 → 4 signers    │
│  Tier 6 → 6 signers |  Tier 8 → 8 signers    │
└───────────────────────────────────────────────┘
     │
     ▼
  Verified Response  ✅
```

---

## 2. Hexa-Core Model Registry

Six AI models, each with a distinct role. **Geopolitical balance:** 3 US + 3 CN.

| Role | Model ID | Provider | Country | Input $/1M | Output $/1M | Context |
|------|----------|----------|---------|-----------|------------|---------|
| `SUPREME_ARCHITECT` | `anthropic/claude-opus-4.6` | Anthropic | 🇺🇸 US | $5.00 | $25.00 | 1 M |
| `LEAD_BUILDER` | `moonshotai/kimi-k2.5` | Moonshot AI | 🇨🇳 CN | $0.45 | $2.25 | 1 M |
| `JUNIOR_BUILDER` | `minimax/minimax-m2.1` | MiniMax | 🇨🇳 CN | $0.27 | $0.95 | 200 K |
| `SPECIALIST` | `google/gemini-3-flash` | Google | 🇺🇸 US | $0.50 | $3.00 | 1 M |
| `LIBRARIAN` | `x-ai/grok-4.1-fast` | xAI | 🇺🇸 US | $0.20 | $0.50 | **2 M** |
| `HUMANIZER` | `deepseek/deepseek-v3.2` | DeepSeek | 🇨🇳 CN | $0.25 | $0.38 | 200 K |

**Implementation:** `delentia_os/config/hexa_core_registry.py` (317 lines, Pydantic v2)  
**Key methods:** `get_model()`, `get_cheapest_coder()`, `get_longest_context()`, `estimate_cost()`, `get_geopolitical_balance()`

### Role Specifications

**Supreme Architect — Claude Opus 4.6**  
Highest reasoning capability. Reserved for `ARCHITECTURE` and `CRITICAL` intents only (Tier 8 tasks). At $5/$25 per million tokens it is 18× more expensive than the cheapest slot — delegates all routine work downward.

**Lead Builder — Kimi K2.5**  
Programming Rank #1 (tied with Opus), visual coding specialist, OSWorld benchmark leader. Handles `CODING_COMPLEX`, `CODING_REVIEW`, `BENCHMARK`. 10× cheaper than Opus for code generation.

**Junior Builder — MiniMax M2.1**  
Programming Rank #2. Handles `CODING_SIMPLE` and `CODING_TESTS`. At $0.27/$0.95, it is the cheapest code-capable model — **53% cheaper than Kimi** for unit test generation.

**Specialist — Gemini 3 Flash**  
Finance Rank #1, Health Rank #1. Handles `FINANCE`, `HEALTH`. Multimodal. Google direct key available for latency/cost optimization.

**Librarian — Grok 4.1 Fast**  
Science Rank #1. **2 M token context window** — the longest available. Handles `RAG_RETRIEVAL`, `SUMMARIZATION`, `SCIENCE`. Cheapest per-token overall ($0.20/$0.50).

**Humanizer — DeepSeek V3.2**  
Roleplay Rank #1. Handles `CHAT`, `TRANSLATION`, `CREATIVE`. Powers user-facing interactions and Tier-S (single-signer) consensus — fastest response chain.

---

## 3. Smart Task Routing

**Implementation:** `delentia_os/config/model_router.py` (269 lines)  
**Entry point:** `ModelRouter.route_task(intent: TaskIntent) → (model_id, HexaCoreRole)`

### Complete Routing Table

| TaskIntent | → Model | → HexaCoreRole | Key Context |
|-----------|---------|----------------|-------------|
| `CODING_COMPLEX` | Kimi K2.5 | `LEAD_BUILDER` | PRODUCTION |
| `CODING_SIMPLE` | MiniMax M2.1 | `JUNIOR_BUILDER` | PRODUCTION |
| `CODING_REVIEW` | Kimi K2.5 | `LEAD_BUILDER` | PRODUCTION |
| `CODING_TESTS` | MiniMax M2.1 | `JUNIOR_BUILDER` | **DEVELOPMENT** |
| `FINANCE` | Gemini 3 Flash | `SPECIALIST` | PRODUCTION |
| `HEALTH` | Gemini 3 Flash | `SPECIALIST` | PRODUCTION |
| `SCIENCE` | Grok 4.1 Fast | `LIBRARIAN` | PRODUCTION |
| `RAG_RETRIEVAL` | Grok 4.1 Fast | `LIBRARIAN` | PRODUCTION |
| `SUMMARIZATION` | Grok 4.1 Fast | `LIBRARIAN` | PRODUCTION |
| `CHAT` | DeepSeek V3.2 | `HUMANIZER` | PRODUCTION |
| `TRANSLATION` | DeepSeek V3.2 | `HUMANIZER` | PRODUCTION |
| `CREATIVE` | DeepSeek V3.2 | `HUMANIZER` | PRODUCTION |
| `ARCHITECTURE` | Claude Opus 4.6 | `SUPREME_ARCHITECT` | PRODUCTION |
| `BENCHMARK` | Kimi K2.5 | `LEAD_BUILDER` | **BENCHMARK** |
| `CRITICAL` | Claude Opus 4.6 | `SUPREME_ARCHITECT` | PRODUCTION |

### Cost Comparison (10K input + 5K output tokens)

| Task | Model | Cost |
|------|-------|------|
| Simple test generation | MiniMax M2.1 | $0.0075 |
| Complex code | Kimi K2.5 | $0.016 |
| Financial analysis | Gemini 3 Flash | $0.020 |
| RAG pipeline | Grok 4.1 Fast | $0.0045 |
| Architecture review | Claude Opus 4.6 | $0.175 |

**Aggregate savings: 40–60%** by delegating non-critical tasks away from premium models.

---

## 4. SignedAI Consensus — 4-Tier Protocol

**Implementation:** `delentia_os/config/signed_ai_tiers.py` (307 lines)  
**Purpose:** Multi-model consensus prevents hallucinations (0.3% vs 12–15% industry average)

### Tier Specifications

| Tier | Signers | Required Votes | Chairman Veto | Geo Balance | Cost | Use Case |
|------|---------|---------------|---------------|-------------|------|----------|
| **S** | 1 (DeepSeek) | 1/1 (100%) | ❌ | N/A | 1× | Chat, low-risk |
| **4** | 4 (2 West + 2 East) | 3/4 (75%) | ❌ | ✅ | 4× | Code review, API design |
| **6** | 6 (3 West + 3 East) | 4/6 (67%) | ❌ | ✅ | 6× | Production releases, DB migrations |
| **8** | 8 (Tier-6 + Chairman + Reasoner) | 6/8 (75%) | ✅ (Opus) | ✅ | 8× | Architecture changes, legal decisions |

### Tier 6 Composition (Production — Geopolitical Parity)

```
West (US) ×3              East (CN) ×3
──────────────────────    ─────────────────────────
claude-3.5-sonnet         moonshotai/kimi-k2.5
google/gemini-3-flash     minimax/minimax-m2.1
x-ai/grok-4.1-fast        deepseek/deepseek-v3.2
```

### Consensus Calculation

`consensus_reached = True` when `votes_for >= required_votes`  
In Tier 8: if Chairman (Claude Opus) votes `false`, result is `false` regardless of count.

```python
# Example — Tier 6 production consensus
result = SignedAIRegistry.calculate_consensus(
    tier=SignedAITier.TIER_6,
    votes_for=5,
    votes_against=1
)
# → consensus_reached=True, confidence=83.3%
```

**Tier suggestion logic** (in `ModelRouter.suggest_tier()`):
- `CRITICAL`, `ARCHITECTURE` → Tier 8
- `CODING_REVIEW` → Tier 6
- `FINANCE`, `HEALTH` → Tier 4
- All others → Tier S

---

## 5. Vault-Key Strategy — 6-Key Security Architecture

**Implementation:** `delentia_os/config/key_manager.py` (235 lines)  
**Purpose:** Separate API keys per operational context to contain blast radius, enable cost tracking per pipeline, and support emergency key rotation without system downtime.

| KeyContext | Environment Variable | Usage |
|-----------|---------------------|-------|
| `PRODUCTION` | `RCT_CORE_BRAIN_KEY` | User-facing Hexa-Core operations |
| `SECURITY` | `RCT_SIGNED_AI_SEC_KEY` | Tier 4/6/8 consensus verification |
| `BENCHMARK` | `RCT_BENCHMARK_LAB_KEY` | Terminal Bench, OSWorld runs (limit: $20/run) |
| `FARMING` | `RCT_FARMER_GEN_KEY` | Intent farming, bulk data generation |
| `DEVELOPMENT` | `RCT_DEV_SANDBOX_KEY` | Local testing, unit test runs (limit: $5/month) |
| `GOOGLE_DIRECT` | `GOOGLE_API_KEY` | Direct Gemini 3 Flash (free tier, lower latency) |

**Fallback chain:** specific key → `RCT_DEV_SANDBOX_KEY` → `RCT_CORE_BRAIN_KEY` → `ValueError`  
**Key validation:** prefix matches provider-specific format AND length ≥ 20  
**Key masking:** shows first 8 + last 4 chars in debug logs

---

## 6. JITNA Protocol (RFC-001)

> "The HTTP of Agentic AI" — an open standard for AI-to-AI communication

**Specification:** `docs/architecture/RFC-001-OPEN-JITNA-PROTOCOL-SPECIFICATION.md`

JITNA (Just-In-Time Neural Architecture) defines a stateless request-response protocol enabling autonomous AI agents to:
- Discover capabilities of other agents
- Delegate subtasks across agent boundaries
- Aggregate partial results with provenance tracking
- Propagate SignedAI attestations end-to-end

The protocol is intentionally model-agnostic — any model registered in `HexaCoreRegistry` can act as a JITNA endpoint.

---

## 7. 7-Genome System

Each Genome is a specialized behavioral layer with its own identity, memory space, and invocation path:

| # | Genome | Role | Key Capability |
|---|--------|------|---------------|
| 1 | **Architect** | Creator intelligence | System design, meta-decisions |
| 2 | **ARTENT** | Creation engine | Artifact generation |
| 3 | **JITNA** | Protocol layer | Inter-agent routing |
| 4 | **Codex** | Knowledge vault | Long-term memory, RCTDB access |
| 5 | **SignedAI** | Verification layer | Multi-model consensus |
| 6 | **Vault-1010** | Memory architecture | 8D schema operations |
| 7 | **RCT-7** | Continuous improvement | Self-reflection, performance tuning |

---

## 8. Core Module Structure

```
delentia_os/
└── config/
    ├── __init__.py              # Public API exports
    ├── hexa_core_registry.py    # 6-model registry (317 lines, Pydantic v2)
    ├── signed_ai_tiers.py       # 4-tier consensus (307 lines)
    ├── model_router.py          # Task routing (269 lines, openai client)
    └── key_manager.py           # 6-key vault (235 lines)

rct_benchmark/                   # Plan 18+19: Benchmark Execution Engine
├── __init__.py                  # v1.3.0, Plan 19 public exports
├── config.py                    # BenchmarkConfig (Hexa-Core model IDs)
├── model_adapter.py             # Unified Hexa-Core routing adapter
├── openrouter_client.py         # OpenRouter async HTTP client  
├── benchmark_memory.py          # Error-Driven Learning memory (Plan 19)
├── benchmark_control_plane.py   # HexaCoreBenchmarkController (Plan 19)
└── simulation_runner.py         # Iterative improvement loop (Plan 19)

dashboard/                       # Plan 20: War Room Dashboard
├── app.py                       # Streamlit main UI (780 lines)
├── log_parser.py                # Live JSONL/JSON benchmark log parser
├── metrics_calculator.py        # Accuracy, trend, cost analytics
└── sota_data.py                 # Global leaderboard (SOTA Feb 2026)

core/kernel/                     # Plans 21-24: NPC Simulation Kernel
├── __init__.py                  # Public exports (7 modules)
├── simulation.py                # Master 8-phase tick engine (471 lines)
├── fdia.py                      # FDIA Scoring Engine F=(D^I)×A (392 lines)
├── conflict_resolution.py      # Deterministic arbitration (270 lines)
├── governance.py               # Constitutional enforcement layer (324 lines)
├── memory_delta.py             # Temporal delta compression (313 lines)
├── npc_agent.py                # Intent-driven NPC agent (307 lines)
├── world_state.py              # Shared simulation environment (242 lines)
└── llm_agent.py                # LLM-enhanced NPC, heuristic mode (198 lines)

use_cases/rct_npc_system/        # Plans 22-24: NPC Application Layer
├── run_simulation.py           # CLI: --agents/--ticks/--seed/--scenario (150 lines)
├── metrics.py                  # Gini/Shannon/top10/compliance (162 lines)
├── behavior_analyzer.py        # Power-law/wealth-regime/intent (166 lines)
├── scenarios/                  # 6 pre-built research scenarios
│   ├── trade_economy.py        # 30 agents, 200 ticks, 50% ACCUMULATE
│   ├── faction_politics.py     # 20 agents, 300 ticks, 40% DOMINATE
│   ├── resource_scarcity.py    # 50 agents, 500 ticks, scarce resources
│   ├── supply_chain_network.py # 40 agents, 400 ticks, ore chain
│   ├── pandemic_dynamics.py    # 60 agents, 500 ticks, 40% PROTECT
│   └── civil_conflict.py       # 45 agents, 600 ticks, 40% DOMINATE
└── results/                    # Pre-generated result archive (SHA256 proof)
```

All modules use **Pydantic v2** for schema validation. The `openai` client is configured with `base_url="https://openrouter.ai/api/v1"` for unified multi-provider access.

**Plan 19 — Hexa-Core Benchmark Orchestration:** The `benchmark_control_plane.py` implements the 6-step `observe→analyze→plan→execute→verify→learn` loop. Every task failure feeds `BenchmarkMemory` (JSON-backed), injecting lessons into future planning prompts.

**Plan 20 — RCT War Room Dashboard:** Run `streamlit run dashboard/app.py` for a real-time monitoring UI showing live accuracy vs SOTA, leaderboard ranking, cost comparison, and go/no-go submission readiness.

**Plans 21–24 — NPC Simulation Kernel:** The `core/kernel/` modules implement an 8-phase deterministic tick engine. Each tick: agents OBSERVE world state → EVAL intents → FDIA SCORE actions → DETECT conflicts → ARBITRATE → GOVERNANCE veto/sanction → EXECUTE → MEMORY UPDATE. The entire pipeline is seeded deterministic: same `SimulationConfig.seed` always produces the same `SimulationResult.sha256_hash`. Validated across 10 repeat runs in `test_determinism.py`.

---

## 9. Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/unit/config/` (4 files) | **111** | ✅ PASS |
| `tests/benchmark_tests/` (5 files) | **80** | ✅ PASS |
| `tests/test_dashboard.py` (Plan 20) | **33** | ✅ PASS |
| `tests/kernel/` (Plans 21-24, 15 files) | **265** | ✅ PASS |
| `tests/benchmark/` + `tests/integration/` (Plans 21-24) | **108** | ✅ PASS |
| **Total runnable** | **597/597** | **✅ 100%** |

Run all runnable: `python3 -m pytest tests/unit/config/ tests/benchmark_tests/ tests/test_dashboard.py tests/kernel/ tests/benchmark/ -v`

> 📚 See [`../../docs/testing/TESTING_CANONICAL.md`](../../docs/testing/TESTING_CANONICAL.md) for full test inventory and Hypothesis profile breakdown.

---

## 10. Cross-References

- 🔑 **Key setup guide:** `docs/HEXA_CORE_SIGNEDAI_ARCHITECTURE.md` §Quick Start
- 💾 **Database layer:** [`../03_database/README.md`](../03_database/README.md)
- 📖 **Complete system:** [`../01_foundation/RCT_ECOSYSTEM_WHITEPAPER_COMPLETE_2026.md`](../01_foundation/RCT_ECOSYSTEM_WHITEPAPER_COMPLETE_2026.md)
- 🧪 **Testing guide:** [`../../docs/testing/TESTING_CANONICAL.md`](../../docs/testing/TESTING_CANONICAL.md)
- 📊 **Registry:** [`../WHITEPAPER_REGISTRY.json`](../WHITEPAPER_REGISTRY.json)

---

## 📄 Document Metadata

| Property | Value |
|----------|-------|
| **Created** | February 16, 2026 (placeholder) |
| **Last Substantive Update** | February 25, 2026 |
| **Version** | 2.1.3 |
| **Maintainer** | Ittirit Saengow — Chief Architect |
| **Next Review** | March 24, 2026 |

---

**© 2026 Ittirit Saengow. Licensed under Apache 2.0.**

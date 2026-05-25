## RCT Platform — Public Roadmap

> Last updated: June 2026
> Current version: **v1.1.0 (Stable)**  
> Maintained by: Ittirit Saengow — [rctlabs.co](https://rctlabs.co)

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Shipped |
| 🔄 | In progress |
| 📋 | Planned — confirmed |
| 💡 | Considering — not confirmed |

---

## v1.1.0 — Enterprise Platform ✅ (June 2026)

**Goal: Full enterprise-grade CLI, OTel observability, TypeScript SDK, and GitHub Action.**

> Released: June 2026 · 800 tests · 0 failures · commit `9afecb8`

### Phase 1 — CLI Lifecycle (rct plan / apply / memory) ✅
- ✅ `rct plan "<intent>"` — Terraform-style pre-execution simulation (PlanEngine)
- ✅ `rct apply [-f pipeline.yaml]` — compile → evaluate → execute with JITNA YAML support
- ✅ `rct memory history` — AI decision timeline with SHA-256 audit chain
- ✅ `rct memory rollback <n>` — Roll back N ticks (control plane or NPC delta engine)
- ✅ `examples/pipeline.yaml` — JITNA 6-field packet reference example

### Phase 2 — Policy Governance (policy-as-code + A-gate) ✅
- ✅ `rct policy add -f config/architect_policy.yaml` — load policies from YAML
- ✅ `rct policy list` — list active policy rules with priority/action
- ✅ `rct policy remove <id>` — remove a policy by ID or name
- ✅ `rct policy test "<intent>"` — dry-run evaluate against all policies
- ✅ `rct approve --pending` — interactive omni-channel approval queue
- ✅ `approval_gateway.py` — SHA-256 approval tokens, Slack/Teams/webhook dispatch
- ✅ `architect_policy_loader.py` — load `PolicyRule` objects from YAML policy files
- ✅ `config/architect_policy.yaml` — reference policy file with 6 constitutional rules

### Phase 3 — Observability (OTel + Prometheus + Grafana) ✅
- ✅ `otel_adapter.py` — OpenTelemetry bridge for FDIA metrics as OTel spans
- ✅ `GET /metrics` — Prometheus scrape endpoint (Prometheus exposition format)
- ✅ `docker-compose.monitoring.yml` — Prometheus + Grafana + OTel Collector stack
- ✅ `docs/assets/grafana-dashboard.json` — pre-built RCT Control Plane dashboard
- ✅ `config/prometheus.yml` — Prometheus scrape config for rct-platform
- ✅ `config/grafana-datasources.yml` — auto-provision Grafana datasource

### Phase 4 — TypeScript SDK ✅
- ✅ `sdk-typescript/src/fdia.ts` — `computeFDIA(d, i, a)` → F=D^I×A formula
- ✅ `sdk-typescript/src/jitna.ts` — JITNA 6-field packet type + `constructJITNA()`
- ✅ `sdk-typescript/src/signedai.ts` — `selectSignedAITier(tier, risk)` → HexaCore roles
- ✅ `sdk-typescript/src/client.ts` — `RCTClient` REST wrapper (compile, evaluate, metrics)
- ✅ `sdk-typescript/src/index.ts` — clean barrel export

### Phase 5 — GitHub Action ✅
- ✅ `github-action/action.yml` — `rct-policy-gate` action definition
- ✅ `github-action/src/index.ts` — compile + evaluate + gate logic (Node 20)
- ✅ Inputs: `intent`, `rct_api_url`, `user_tier`, `min_governance_score`, `fail_on_reject`
- ✅ Outputs: `decision`, `governance_score`, `risk_profile`, `triggered_rules`

### Phase 6 — RCT Desktop 💡 (Post v1.0.0)
- 💡 Tauri + Next.js desktop app with live `rct start` dashboard
- 💡 System tray agent with per-intent notifications
- 💡 Scheduled intent queue and approval inbox

---

## v1.0.5b0 — CLI Polish & Customization 📋 (June 2026)

**Goal: Add aesthetic refinements, drop shadows, animation switches, and custom config thresholds.**

- 📋 CLI version badge refinement: rounded pill-box border format
- 📋 CLI wordmark drop shadow: offset color duplicate row under standard and wide banners
- 📋 CLI animation switch: `--no-animation` flag to bypass letter-by-letter reveal in slow TTY environments
- 📋 CLI Configuration: `rct.config.json` support to define custom terminal width threshold tier overrides
- 📋 Verify Windows Terminal / Linux TTY specific ASCII compatibility across diverse SSH clients

---

## v1.0.4b0 — Beta Preview ✅ (May 2026)

**Goal: harden the public CLI and first-run experience before PyPI release.**

- ✅ Shared package version source across CLI, API, and release metadata
- ✅ `rct doctor` environment diagnostics
- ✅ `rct start --ui-test` for zero-key first-run validation
- ✅ `rct status --live` runtime dashboard with health-endpoint fallback
- ✅ `rct logs --follow` live log streaming
- ✅ `rct init` fallback template for wheel and clean-room installs
- ✅ Focused CLI coverage for first-run onboarding paths

---

## v1.0.2a0 — Public Alpha ✅ (April 2026)

**Public release of the RCT Platform open SDK.**

- ✅ FDIA Scorer (`core/fdia/`) — `F = D^I × A` constitutional equation
- ✅ SignedAI Registry (`signedai/`) — HexaCore 7-model registry + TIER_S/4/6/8 consensus
- ✅ Delta Engine (`core/delta_engine/`) — state compression + warm recall
- ✅ JITNA Protocol RFC-001 (`rct_control_plane/jitna_protocol.py`)
- ✅ Regional Language Adapter — 8 ASEAN language pairs
- ✅ RCT Control Plane DSL — 15 modules, `rct` CLI entry point
- ✅ 5 reference microservices (intent-loop, analysearch, vector-search, crystallizer, gateway-api)
- ✅ 1,287 passed, 0 skipped, 92% coverage, Bandit 0 HIGH
- ✅ CI/CD: GitHub Actions (ci.yml + security-scan.yml)
- ✅ MkDocs documentation site
- ✅ Whitepaper: 450+ pages, bilingual (EN + TH)
- ✅ CITATION.cff for academic attribution
- ✅ .devcontainer for GitHub Codespaces

---

## v1.0.3a0 — Playground Release 📋 (May 2026)

**Goal: zero-friction first experience — no clone, no install.**

- ✅ `notebooks/rct_playground.ipynb` — runnable Colab notebook (FDIA + SignedAI + Delta demos)
- ✅ `benchmark/run_benchmark.py` — unified benchmark runner CLI
- ✅ Binder / Colab / Codespaces quick-launch badges in README
- ✅ Hypothesis property-based tests — mathematical correctness guarantees for FDIA, Delta Engine, SignedAI
- 📋 `docs/benchmark/hallucination-methodology.md` improvement — 100-prompt public dataset
- 📋 Enable GitHub Discussions in the GitHub UI — Q&A, RFC Discussion, Show & Tell categories
- 📋 API stability guarantees documented for `core/fdia`, `signedai/core`, `core/delta_engine`

---

## v1.0.0 Stable — PyPI Release 📋 (Q3 2026)

**Goal: `pip install rct-platform` works from PyPI.**

- 📋 Publish to PyPI as `rct-platform==1.0.0`
- 📋 Semantic versioning stability guarantee — no breaking changes without major version bump
- 📋 Full API reference documentation (`docs/api/`)
- 📋 Type stubs (`py.typed` marker + complete `__init__.pyi`)
- 📋 Pre-built wheels for Python 3.10 / 3.11 / 3.12
- 📋 GitHub Release with signed artifacts
- 📋 External reproduction of hallucination benchmark (community-verified)
- 📋 Create GitHub Milestones for roadmap items and link them from `ROADMAP.md`

---

## v1.1.0 — Observability + Integrations 📋 (Q4 2026)

**Goal: production-ready observability and first third-party integrations.**

- 📋 Prometheus `/metrics` endpoint (live in `rct serve`)
- 📋 Grafana dashboard template (`docs/assets/grafana-dashboard.json`)
- 📋 `docker-compose.monitoring.yml` — Prometheus + Grafana local stack
- 📋 OpenTelemetry trace exporter for distributed tracing
- 📋 n8n integration adapter (from Universal Adapter collection)
- 📋 Home Assistant integration adapter
- 📋 Obsidian plugin (knowledge graph ↔ JITNA intent tagging)
- 📋 JITNA Protocol v2.1 draft — bidirectional agent negotiation

---

## v1.2.0 — ASEAN Expansion 💡 (2027)

**Goal: first-class multi-language support and ASEAN regulatory alignment.**

- 💡 VN, ID, MY language adapters (expand from 8 → 11 pairs)
- 💡 PDPA (Thailand) compliance module with audit evidence export
- 💡 PIPL (China) adapter for E3 model slot
- 💡 ASEAN AI Governance checklist alignment
- 💡 RCT Platform certification program (community-driven)
- 💡 JITNA Protocol RFC-002 — cross-platform agent identity standard

---

## What We Are NOT Planning

To set clear expectations:

| Out of Scope | Reason |
|---|---|
| Full production microservice stack (62 services) | Enterprise tier — [contact rctlabs.co](https://rctlabs.co) |
| Genome / Creator Profile API | Enterprise proprietary |
| Full inference engine | Hardware / cost constraints outside OSS scope |
| Hosted API / SaaS | Runs at rctlabs.co — enterprise licensing |

---

## How to Influence the Roadmap

- 💬 Open a [GitHub Discussion](https://github.com/rctlabs/rct-platform/discussions) with your use case once Discussions are enabled in the GitHub UI
- 🐛 File an [issue](https://github.com/rctlabs/rct-platform/issues) for bugs or missing features
- 🗳️ Upvote existing issues — high-engagement items move up the priority list
- 📧 Enterprise timeline requests: founder@rctlabs.co

---

> This roadmap reflects current intent, not a binding commitment.  
> Timelines may shift. GitHub Milestones and Discussions require explicit GitHub UI configuration before they become visible to users.

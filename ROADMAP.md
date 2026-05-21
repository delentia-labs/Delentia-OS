## RCT Platform — Public Roadmap

> Last updated: May 20, 2026  
> Current version: **v1.0.4b0 (Beta Preview)**  
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

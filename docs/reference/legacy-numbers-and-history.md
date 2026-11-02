# Earlier README content: numbers, layers, install variants, structure and timeline

> **Moved from the README on 2026-11-01.** The README is now a short entrance; this is the detail that used to sit in it, with the text unchanged except where a line starts with **[corrected 2026-11-01]** or **[context 2026-11-01]**. Anything here that is older than the code is history, not a description of today: the status of each capability is in [Release levels](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/release/RELEASE_LEVELS.md) and the current test checkpoint is in [Testing](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/testing/TESTING_CANONICAL.md).

**Read this page as history.** It keeps what the README once said so that nothing is lost; several figures and blocks below come from the older SDK (before the agent runtime) and were measured under conditions other than the runtime's. The notes marked [corrected] or [context] say where.

---

## Install & Run (5-10 minutes, fully local, no API keys)

**Linux / macOS / WSL2:**
```bash
curl -fsSL https://raw.githubusercontent.com/delentia-labs/delentia-os/main/install.sh | bash
```

**Windows PowerShell:**
```powershell
iex (irm https://raw.githubusercontent.com/delentia-labs/delentia-os/main/install.ps1)
```

Or, if you just want the CLI without cloning the repo:
```bash
pip install delentia-os
```

Either way, then:
```bash
delentia doctor     # real preflight check - tells you exactly what's missing
delentia init        # creates a local .env from the template
delentia chat        # start the terminal chat UI
```

For a fully local, zero-cloud setup (nothing leaves your machine, no account, no API key): [install Ollama](https://ollama.com/download), run `ollama pull llama3.1`, and `delentia` talks to it at `http://127.0.0.1:11434` by default.

Both installer scripts only create a project-local virtualenv - no sudo, no elevation, no system-wide changes. Read them before running them if you'd rather not pipe-to-shell: [`install.sh`](https://github.com/delentia-labs/Delentia-OS/blob/main/install.sh), [`install.ps1`](https://github.com/delentia-labs/Delentia-OS/blob/main/install.ps1).

## Start Here in 5 Minutes (verify the claims yourself)

If you're arriving from social media or seeing RCT Platform for the first time and want to check our work rather than take our word for it, use this path:

1. **Try the offline demo** - run `python examples/quickdemo.py` or open `notebooks/rct_playground.ipynb`
2. **Verify the claims** - see [`docs/testing/TESTING_CANONICAL.md`](../testing/TESTING_CANONICAL.md) for the current authoritative test and coverage checkpoint
3. **Understand the scope boundary** - compare the open SDK surface vs enterprise-only surface in the table below
4. **Check release readiness** - see [`docs/release/RELEASE_READINESS_CHECKLIST.md`](../release/RELEASE_READINESS_CHECKLIST.md)
5. **Find support channels** - see [`docs/community/GITHUB_UI_LAUNCH_CHECKLIST.md`](../community/GITHUB_UI_LAUNCH_CHECKLIST.md) for Discussions, milestones, About, Topics, and profile setup

---

---

## Key Numbers

> [!NOTE]  
> **Disclaimer on Metrics:** The metrics below (such as hallucination rate, compression, and accuracy) represent synthetic measurements gathered under controlled testing environments (using local properties suites and mock benchmarks). They are not live SLAs and may vary under real enterprise traffic.

| Metric | Value |
|--------|-------|
| **Public SDK validation** | See [`docs/testing/TESTING_CANONICAL.md`](../testing/TESTING_CANONICAL.md) for the current verified checkpoint |
| **Algorithms** | 41 (Tier 1–9, reference implementations) |
| **LLM Models** | You choose: a local model (Ollama), any model on OpenRouter, or any OpenAI-compatible endpoint. No fixed roster |
| **Hallucination Rate** | Not currently claimed. The earlier 0.3% figure was withdrawn 2026-09-28 because it could not be reproduced (see `docs/benchmark/hallucination-methodology.md`) |
| **Memory Compression** | stores state diffs, not full state: 39% (20 ticks) to 90% (500 ticks) smaller than a full snapshot per tick, measured in bytes (`scripts/measure_delta_engine_real.py`). The earlier 91.5% was a formula estimate, not a measurement |
| **Intent Recall Speed** | Cold start 3–5s -> Warm recall <50ms (synthetic benchmark) — **[context 2026-11-01]** measured on the older intent-loop reference service, which simulates execution; it is not a latency of the agent runtime |
| **Uptime SLA** | N/A (Experimental Hobby Platform, no enterprise SLA guaranteed) |
| **Languages** | 8 regional pairs (JP, KR, CN, TW, TH, VN, ID, US) |
| **Universal Adapters** | 13 (Home Assistant, Terraform, n8n, Obsidian, Playwright, ...) — **[context 2026-11-01]** not re-checked in the README audit of that date |
| **FDIA Accuracy** | **[context 2026-11-01]** the 'Baseline 0.65' below is a number the author chose, not a measured industry figure. 0.9167 rank accuracy (11 of 12 hand-written cases; classification accuracy on the same set is 0.5833, 7 of 12). Tiny set: treat as a smoke test, not a benchmark. Baseline 0.65 is a design reference. |

For the current single source of truth, see [`docs/testing/TESTING_CANONICAL.md`](../testing/TESTING_CANONICAL.md).

---

## Architecture

```text
┌──────────────────────────────────────────────────────────┐
│               DELENTIA OS SDK                            │
│         Intent-Centric AI Operating System               │
└──────────────────────────────────────────────────────────┘

Layer 11: CI/CD & Quality Gates
├─ GitHub Actions (ci.yml + security-scan.yml)
├─ See docs/testing/TESTING_CANONICAL.md for the current, live test/coverage checkpoint (this number moves every round - do not hardcode it in two places that can drift apart, see Round 44's own audit) · Python 3.10/3.11/3.12
└─ E2E integration tests (no Docker required)

Layer 10: Enterprise Hardening
├─ Security (JWT RS256, RBAC, ABAC, Rate Limiting)   <- [context 2026-11-01] a design list: JWT RS256 is not wired into the runtime; rate limiting and token-based roles are (see runtime-features)
├─ Validation (SQL Injection 3-layer, Pydantic v2, XSS)
└─ Resilience (Circuit Breaker, Retry policies)

Layer 9: Control Plane
├─ JITNA Wire Schema (JITNAPacket: I, D, Δ, A, R, M)
├─ TOON Formatter (ALGO-42 compression, 40-50% token savings)   <- [corrected 2026-11-01] measured about 15% MORE tokens than compact JSON on the runtime's payloads; not used by the agent
├─ Ed25519 Signed Execution (RFC 8032)
├─ Replay Engine (SHA-256 checkpoints)
└─ rct_control_plane: 15-module DSL + intent schema

Layer 8: Regional Language + data residency (routing and call-time enforcement)
├─ LanguageDetector (EN, TH, JA, KO, ZH, VI, ID)
└─ RegionalModelRouter (LRU cache, 4-level resolution)

Layer 7: Universal Adapters (13 integrations)
└─ Home Assistant · Terraform · n8n · Obsidian · Playwright · ...

Layer 6: JITNA Protocol (RFC-001 v2.0)
└─ AI-to-AI intent wire format + task negotiation

Layer 5: SignedAI — optional jury of independent models
├─ TIER_S (1) · TIER_4 (4) · TIER_6 (6) · TIER_8 (8 + veto)
└─ Hallucination rate: not measured (earlier 0.3% claim withdrawn, see docs/benchmark)

Layer 4: RCTDB v2.0 — 8-Dimensional Universal Memory
└─ Registry Zone · Vault Zone · Governance Zone

Layer 3: 41 Algorithms (Tier 1–9)
Layer 2: OS Primitives (6 Kernel RFCs)
Layer 1: 7 Genome System + Cognitive Kernel

SDK Modules: signedai/ · core/ · rct_control_plane/
             5 reference microservices
```

---

## Quick Install (No API Keys Required)

```bash
# 1. Clone & install
git clone https://github.com/delentia-labs/delentia-os.git
cd delentia-os
pip install -e .

# 1b. (Only if you want to run the test suite) install the full dependency set.
#     `pip install -e .` is enough for the CLI and demos, but tests import torch,
#     numpy, opencv, faiss and others that pyproject.toml lists as optional extras.
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q --no-header   # needs internet + Ollama for ~40 network-dependent tests

# 2. Validate the CLI surface without API keys
delentia version
delentia start --ui-test

# 3. Create a local .env template for real runs
delentia init
delentia doctor

# 4. Run the 5-minute offline demo — zero API keys needed
python examples/quickdemo.py

# 5. Run the FDIA benchmark (target: 0.92 accuracy)
python benchmark/fdia_benchmark.py --verbose

# 6. Try the CLI
delentia compile 'Protect resources from hostile agents'
delentia governance
delentia timeline
```

**[corrected 2026-11-01] The two 'expected output' blocks below are from an older version of these scripts; run them to see what they print today. `quickdemo.py` is an offline tour with simulated votes, not the agent runtime (for that, see the README's two-minute demo).**

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
Industry Baseline    : 0.6500   (now printed as 'Design reference (not measured)')
Delta vs Baseline    : +0.2667 (+41.0%)
✅  Benchmark PASSED
```

## Quick Start (With API Keys)

```bash
# 1. Generate a local .env template
delentia init
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

- **Property-based safety verification** - Audit the FDIA safety gate natively by running the Hypothesis properties suite:
  ```bash
  pytest tests/hypothesis/test_fdia_properties.py -v
  ```
- **The whole system against a scripted model (Round 52)** - 15 cases, 76 checks: guard, a real tool call, warm recall, signed approvals, memory, model failures, budget, data residency, delegation, three subagents in three OS processes and git worktrees, a forged subagent answer, audit tampering and the `.jitna` handoff. The model is a real HTTP endpoint that follows a script, so a result is about the system, not about a model:
  ```bash
  python scripts/full_pipeline_cases.py            # add --no-subagents for the 30-second version
  python scripts/real_model_tool_probe.py qwen2.5:7b   # the other question: is this MODEL good enough to drive it?
  ```
- **Current test and coverage checkpoint** - [`docs/testing/TESTING_CANONICAL.md`](../testing/TESTING_CANONICAL.md)
- **Release gate checklist** - [`docs/release/RELEASE_READINESS_CHECKLIST.md`](../release/RELEASE_READINESS_CHECKLIST.md)
- **Public export and provenance policy** - [`docs/release/PUBLIC_RELEASE_PROVENANCE.md`](../release/PUBLIC_RELEASE_PROVENANCE.md)
- **GitHub UI launch tasks** - [`docs/community/GITHUB_UI_LAUNCH_CHECKLIST.md`](../community/GITHUB_UI_LAUNCH_CHECKLIST.md)

---

## Microservices

Five reference microservices demonstrating production patterns:

| Service | Port | Description |
|---------|------|-------------|
| `intent-loop` | 8001 | Core FDIA execution loop |
| `analysearch-intent` | 8020 | Semantic search + intent analysis |
| `vector-search` | 8016 | Vector similarity search over RCTDB |
| `crystallizer` | 8004 | Output crystallization + fact verification |
| `gateway-api` | 8000 | Unified entry point + rate limiting |

Each service includes a `Dockerfile` and follows the OpenAPI contract in `contracts/openapi.yaml`. All 5 build, run, and report `healthy` under `docker compose up --build` (verified for real 2026-09-25, see `microservices/docker-compose.yml`'s own port mapping, which these match).

---

## Benchmark Results

Reproducible benchmarks are in [`benchmark/`](https://github.com/delentia-labs/Delentia-OS/tree/main/benchmark/).

Run against your own setup:
```bash
python benchmark/run_benchmark.py --config benchmark/default_config.json
```

See [benchmark/README.md](https://github.com/delentia-labs/Delentia-OS/blob/main/benchmark/README.md) for methodology.

---

## API Contract

Full OpenAPI 3.1.0 specification: [`contracts/openapi.yaml`](https://github.com/delentia-labs/Delentia-OS/blob/main/contracts/openapi.yaml)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health |
| `/v1/kernel/execute` | POST | Execute RCT Kernel with intent |
| `/v1/rctdb/query` | POST | Query RCTDB knowledge vault |

> **Corrected 2026-09-24/25:** `GET /metrics` for Prometheus does not exist in this repo's real routes (`rct_control_plane/api.py`, `microservices/*/gateway_main.py`/`main.py`) - confirmed via grep, no route registers that path. This same fabricated claim was found and fixed twice already this session in `docs/architecture/observability.md` and `docs/getting-started/cli-reference.md`; this was the third occurrence, in this README. `config/prometheus.yml` exists as a scrape-target config file, but nothing in this repo currently exposes a `/metrics` endpoint for it to scrape.

---

## Earlier SDK milestones (historical)

> **Note:** This section records earlier milestones and is kept for history. Current versions are on [PyPI](https://pypi.org/project/delentia-os/) and in [CHANGELOG.md](https://github.com/delentia-labs/Delentia-OS/blob/main/CHANGELOG.md); the status of each capability is in [RELEASE_LEVELS](../release/RELEASE_LEVELS.md).

✅ **9,069 Passed** (public CI, 2026-10-30; see TESTING_CANONICAL.md for the checkpoint and caveats) — Full delentia-os test suite  
✅ **Plan Engine** — `plan_engine.py` real Terraform-style pre-execution simulation logic *(corrected 2026-09-24: not currently wired to any real CLI command - `plan` isn't in `delentia --help`'s command list; the module itself is real)*  
✅ **Policy Governance** — `approval_gateway.py` real omni-channel human approval logic, plus the real `delentia governance` command (shows governance violations from the audit log) *(corrected 2026-09-24: `rct policy` doesn't exist as a command; `approval_gateway.py` isn't currently wired to any CLI command either)*  
✅ **TypeScript SDK** — `sdk-typescript/`: fdia, jitna, signedai, client modules  

Previous milestone:  
Private enterprise test suite: count not published (not independently verifiable from this repository)  

Full SDK changelog → [CHANGELOG.md](https://github.com/delentia-labs/Delentia-OS/blob/main/CHANGELOG.md)

---

---

## Project Structure

```
delentia-os/
├─ core/                        # Core algorithms + AI engine
│  ├─ fdia/fdia.py              # FDIA Scorer (NPCIntentType, FDIAWeights)
│  ├─ delta_engine/             # Delta-Memory (39-90% in measured bytes on a synthetic simulation, grows with run length)
│  └─ regional_adapter/         # regional routing + sovereignty policy (data residency)
├─ signedai/                    # SignedAI consensus framework
│  └─ core/
│     ├─ registry.py            # HexaCoreRegistry (table of example roles) + SignedAIRegistry
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
│  ├─ analysearch-intent/       # Deep analysis + Mirror Mode (port 8020)
│  ├─ vector-search/            # RCTDB semantic search (port 8016)
│  ├─ crystallizer/             # Output crystallization (port 8004)
│  └─ gateway-api/              # Unified entry + rate limiting (port 8000)
├─ config/                      # Configuration files
│  ├─ architect_policy.yaml     # 6 constitutional policy rules
│  ├─ prometheus.yml            # Prometheus scrape config
│  └─ grafana-datasources.yml   # Grafana auto-provision
├─ docker-compose.monitoring.yml # Prometheus + Grafana + OTel Collector stack
├─ examples/                    # Working code demos + pipeline.yaml
├─ contracts/openapi.yaml       # OpenAPI 3.1.0 spec
├─ apps/gui/                    # Desktop GUI, Next.js + Tauri (was Delentia-OS-Gui)
├─ plugins/adapters/            # Adapter SDK, manifest schema and registry (was Delentia-Ecosystem)
├─ deploy/                      # Docker, Kubernetes, Helm, Terraform (was Delentia-Infra-Public)
└─ docs/                        # Architecture docs + whitepaper/ (3.0) + whitepapers/ (historical)
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

### Timeline

| Period | Milestone |
|--------|-----------|
| 28 Jun 2025 | Start of the work, including the FDIA Equation and RCT 7 Thinking (creator's account) |
| 11 Aug 2025 | A personal turning point and commitment to carry the work through |
| Oct 2025 | JITNA Protocol RFC-001 drafted |
| Dec 2025 | Foundation whitepaper (~100 pages) |
| Jan 2026 | 41 algorithms complete |
| Feb 2026 | 3,053 Python files, Level 4 Virtuoso stress test |
| Apr 2026 | Public SDK — 723 tests, 89%+ coverage, Apache 2.0 release |
| May 2026 | Enterprise CLI Design System — Unicode block wordmark, FDIA formula card, boot animation, PyPI v1.0.4b0 live |
| June 2026 | Enterprise Platform v1.1.0 — Plan/Apply/Memory/Policy/Approve CLI, TypeScript SDK, GitHub Action, OTel + Prometheus + Grafana, 800 tests 0 failed |
| Sep 2026 (current) | Round 41-44 engineering pass — CI fully green (was red ~4 weeks), all 41/41 algorithms confirmed real, GovernedAutonomousLoop wires FDIA/JITNA/RCT-7/Delta into the agent loop for the first time, DAG-workflow-YAML + Skill Library re-application shipped, all 5 reference microservices verified via real `docker compose up`, dozens of fabricated numbers found and corrected across docs/CLI/README - see [CHANGELOG.md](https://github.com/delentia-labs/Delentia-OS/blob/main/CHANGELOG.md) for the itemized commit history |

> See [ROADMAP.md](https://github.com/delentia-labs/Delentia-OS/blob/main/ROADMAP.md) for what comes next.

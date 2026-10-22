# Delentia OS — an experimental, self-hosted AI agent runtime

[![CI](https://github.com/delentia-labs/Delentia-OS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/delentia-labs/Delentia-OS/actions/workflows/ci.yml)
[![Security](https://github.com/delentia-labs/Delentia-OS/actions/workflows/security-scan.yml/badge.svg)](https://github.com/delentia-labs/Delentia-OS/actions/workflows/security-scan.yml)
[![codecov](https://codecov.io/gh/delentia-labs/Delentia-OS/graph/badge.svg?token=IE08MVKA6C)](https://app.codecov.io/gh/delentia-labs/Delentia-OS)
[![Version](https://img.shields.io/badge/version-2.3.1-blue)](CHANGELOG.md)
[![PyPI](https://img.shields.io/pypi/v/delentia-os?label=PyPI)](https://pypi.org/project/delentia-os/)
[![npm](https://img.shields.io/badge/npm-%40delentia%2Fdelentia--os-cb3837?logo=npm)](https://www.npmjs.com/package/@delentia/delentia-os)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Docs](https://img.shields.io/badge/docs-delentia--labs.github.io-blue?logo=readthedocs&logoColor=white)](https://delentia-labs.github.io/Delentia-OS/)
[![Status](https://img.shields.io/badge/status-experimental-orange)](CHANGELOG.md)
[![Website](https://img.shields.io/badge/website-delentia.com-brightgreen)](https://delentia.com)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/delentia-labs/Delentia-OS/blob/main/notebooks/rct_playground.ipynb)
[![Open in Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/delentia-labs/Delentia-OS/main?filepath=notebooks%2Frct_playground.ipynb)
[![Open in Codespaces](https://img.shields.io/badge/Open%20in-Codespaces-181717?logo=github&logoColor=white)](https://codespaces.new/delentia-labs/Delentia-OS)

Delentia OS is an open-source, intent-centric AI agent runtime. It contains its own agent loop, tools, memory, skills, scheduling and subagents. Operators choose a model and manage installation on an existing operating system. The design connects RCT-7 workflow structure, FDIA/owner-policy controls, and recorded feedback.

**Status: experimental.** Public code, scripted mechanism demos and supervised operation are distinct from capable-model evaluation and an external pilot. Read the [release levels](docs/release/RELEASE_LEVELS.md) before choosing a deployment scope.

Current public information: [ภาษาไทย](docs/public/CURRENT_PUBLIC_INFORMATION_TH.md) · [English](docs/public/CURRENT_PUBLIC_INFORMATION_EN.md). These pages separate creator-confirmed definitions, implementation evidence and open questions.

## Start with the scripted demo

No model or API key is needed for this path. Use Python 3.10 or newer in a virtual environment. To inspect this checkout, install from source:

```bash
python -m venv .venv
source .venv/bin/activate                   # Windows: .venv\Scripts\activate
python -m pip install -e .
delentia version
delentia demo init
delentia demo run compare --scripted
delentia demo run edit --scripted
delentia demo status
```

The edit case must report `pending_approval` before changing the demo fixture. Replace `ACTUAL_APPROVAL_ID` below with the ID printed by that run:

```bash
delentia demo approve ACTUAL_APPROVAL_ID --scripted
delentia demo status
```

`--scripted` replaces only the model with a fixed program. Files, tools, the gate, Ed25519 approval checks and the signed audit chain use the implementation. This demonstrates a mechanism; it does not measure a language model's ability. The demo key is on the same machine for convenience and does not establish deployment assurance.

See the [Thai quickstart](docs/demo/QUICKSTART_TH.md), [English quickstart](docs/demo/QUICKSTART_EN.md) and [sample output](docs/demo/SAMPLE_OUTPUT.md). Record the source commit, package version, environment and every failed attempt when reproducing a run. A published package may differ from the checkout; `pip install delentia-os` installs a package, not proof of this commit's behaviour.

## Using a real model

Run `delentia setup` and `delentia model show`, then use the demo commands without `--scripted`. A local Ollama model or an OpenAI-compatible endpoint can be configured. A hosted provider may receive prompts and tool results and may incur costs. Keep credentials out of committed files and recordings; use the credential environment variable required by the selected provider.

Review [W02 pilot instructions](docs/demo/PILOT_ONE_WORKFLOW_TH.md) and the [research protocol](research/PROTOCOL.md) before a paid run. Development smoke tests, model capability screening, comparative evaluation and pilot gates answer different questions. A scripted pass does not satisfy a capable-model gate. Installation and model downloads need network access; self-hosting alone does not imply offline operation.

The optional [shell installer](install.sh) and [PowerShell installer](install.ps1) are available for review. Read them before executing them.

## RCT-7 and the eight-step cycle

**RCT-7 means Reverse Component Thinking:** Observe → Analyze → Deconstruct → Reverse reasoning → Identify core intent → Reconstruct → Compare with intent.

The creator's requirements include explicit knowns and unknowns, goal-dependent components, a backward chain from the desired result, clarification when intent is unresolved, a plan visible before the artifact, and a pause to ask the user when the result does not match intent. Existing planning representations and outcome checks implement part of this design. They do not establish full fidelity to these requirements. See the [requirements and implementation map](docs/concepts/rct-7-thinking.md).

The **Constitutional Cycle** describes the episode lifecycle:

**GUARD → THINK → ROUTE → ACT → COMPRESS → VERIFY → RECORD → LEARN**

These are functional stages: tool calls may repeat, compression happens during execution, and logging occurs throughout. Guarded or pending episodes can stop before completion. RCT planning participates in THINK and outcome comparison in VERIFY. A plan placed in a model prompt is not evidence that a user saw it. An experimental [explicit acceptance-contract path](docs/concepts/intent-contracts.md) adds plan visibility and durable mismatch clarification for its documented CLI/API scope; the default path and full RCT fidelity remain separate work.

LEARN includes runtime memory, selected reusable skills and feedback. It does not automatically fine-tune the main LLM's weights. Recording an episode, extracting a skill, retrieving it and demonstrating causal benefit are separate observations.

## FDIA Equation

**FDIA Equation has no approved expanded name.**

$$F = (D^I) \times A$$

| Variable | Creator's conceptual meaning | Computational interpretation to inspect |
|---|---|---|
| F | Future: the actual outcome | An assessment score, not a calibrated probability of correctness or safety |
| D | Data, experience, conditions and constraints | Evidence/clarity estimates that vary by path |
| I | Intent: clarity, depth and persistence | Precision/strictness proxies; not every conceptual dimension is measured |
| A | Architect: the responsible human designer | Policy-derived authority and signed approval under declared trust assumptions |

Separate the concept, numeric estimators and execution controls. In the raw equation, increasing I lowers the score when 0 < D < 1, leaves D^I unchanged at D = 1, and increases it when D > 1. For D > 0, I = 0 gives D^0 = 1; a helper returning zero for I ≤ 0 adds a domain rule. The helpers do not all share a single range.

A = 0 produces zero in the defined numeric domain. Preventing a protected effect additionally requires the execution path to enforce its decision. A passing score cannot replace a required signature or override a forbidden path. See [FDIA concepts and mapping](docs/concepts/fdia.md) and [gate properties](research/GATE_PROPERTIES.md).

## What the evidence supports

| Evidence | Scope and limitation |
|---|---|
| Public CI checkpoint | [Testing canonical](docs/testing/TESTING_CANONICAL.md) reports 7,820 passed, 43 skipped and 1 xfailed at `3dbed0d`, 18 October 2026. This is a historical checkpoint, not a new run on every reader's checkout. |
| Scripted mechanism demos and workflow rehearsals | Exercise files, gates, signatures, audit and deterministic oracles with a scripted model. See [master workflows](research/MASTER_WORKFLOWS.md). |
| Small local-model probes | Report successes and failures for their particular model/tasks. They do not establish capable-model readiness for the workflows. |
| Delta measurements | See [claim registry](docs/distribution/CLAIM_REGISTRY.md) for dated synthetic byte measurements and comparison with generic compression. No universal savings figure is claimed here. |
| Comparative value and deployment assurance | Capable-model results, causal ablations, outside reproduction and deployment-specific recovery/witness checks remain separate work. |

No hallucination rate, RCT accuracy percentage, weight-level safety guarantee, universal latency or whole-system safety certification is claimed. A signed, hash-chained record is not tamper-proof merely because it is signed. ZK-FDIA is a hash commitment: its verifier does not prove the sealed score equals the equation.

## Repository map

| Path | Purpose |
|---|---|
| [rct_control_plane/](rct_control_plane/) | Agent loop, policy, approvals, API, CLI, memory and feedback |
| [core/](core/) | FDIA NPC action scorer, memory deltas and regional adapters |
| [signedai/](signedai/) | Optional jury runner and signed verdicts |
| [microservices/](microservices/) | Five reference services; their Docker files are separate from a validated production deployment |
| [sdk-typescript/](sdk-typescript/) | TypeScript SDK and edge packages |
| [apps/gui/](apps/gui/) | Desktop GUI sources |
| [plugins/adapters/](plugins/adapters/) | Adapter SDK and registry |
| [deploy/](deploy/) | Public deployment examples |
| [research/](research/) | Protocol, task generators, independent oracles and runners |

The runtime includes 41 algorithm implementations; direct execution, advice, record-only and untriggered roles must be distinguished in a run. Algorithm count and architecture labels do not measure user utility. A separate proprietary service layer is outside this repository.

SignedAI can be requested by the governed loop's conditional jury hook when policy and configuration require it. Wiring and scripted votes do not establish a real multi-vendor result or a reduction in hallucinations.

Regional routing and residency checks have declared coverage and limitations; they are not legal compliance certification. Read the relevant implementation and [Whitepaper 3.0](docs/whitepaper/DELENTIA_WHITEPAPER_3.0_EN.md) before relying on a feature.

## Development and checks

Use the repository's existing instructions and CI for the component you develop. The complete suite requires optional dependencies and external services (including Ollama and PostgreSQL for relevant integration cases); a minimal editable install does not prepare the whole CI workflow.

For the model-free demo and representative checks, install the test tools in your virtual environment:

```bash
python -m pip install pytest pytest-asyncio hypothesis
python examples/quickdemo.py
python -m pytest core/tests/test_core.py signedai/tests/test_signedai.py tests/hypothesis/test_fdia_properties.py -q
python -m pytest rct_control_plane/tests/test_demo_scripted_round79_real.py -q
```

For the control-plane API:

```bash
python -m uvicorn rct_control_plane.api:app --host 127.0.0.1 --port 8000
```

`GET /health` checks basic service health. `GET /health/detailed` reports subsystem limitations; finance can be degraded when the separate service module is absent. Use a functional request as well as health checks to validate your intended workflow. The OpenAPI contract is in [contracts/openapi.yaml](contracts/openapi.yaml); inspect the running API schema for its actual routes.

The NPC scorer example remains in [FDIA concepts](docs/concepts/fdia.md). Its weighted action-ranking semantics differ from the governed loop's numeric authority gate. Historical CLI examples and release milestones are retained in [CHANGELOG.md](CHANGELOG.md), rather than presented as current runnable commands.

## Origin and creator

Ittirit Saengow (อิทธิฤทธิ์ แซ่โง้ว), who describes himself as a thinker and the creator of Delentia, identifies **28 June 2025** as the start of the project, including FDIA Equation and RCT 7 Thinking, on paper and in conversations with ordinary AI chat. FDIA began with the question **“What is the future?”** and his framework for how data, intent and human action shape outcomes. **11 August 2025** marks a separate personal turning point and commitment.

This is the creator's account of the origin; publication metadata and independent evidence of priority are different matters. It is not a claim of worldwide novelty or an empirical law that predicts every future event.

## Read more and contribute

- [Current public information — Thai](docs/public/CURRENT_PUBLIC_INFORMATION_TH.md) and [English](docs/public/CURRENT_PUBLIC_INFORMATION_EN.md)
- [Release levels](docs/release/RELEASE_LEVELS.md), [readiness snapshot](docs/release/READINESS_SNAPSHOT.md) and [release checklist](docs/release/RELEASE_READINESS_CHECKLIST.md)
- [Whitepaper 3.0 — English](docs/whitepaper/DELENTIA_WHITEPAPER_3.0_EN.md) and [Thai](docs/whitepaper/DELENTIA_WHITEPAPER_3.0_TH.md); earlier papers in [the historical collection](docs/whitepapers/README.md)
- [Contributing](CONTRIBUTING.md), [Issues](https://github.com/delentia-labs/Delentia-OS/issues) and [Discussions](https://github.com/delentia-labs/Delentia-OS/discussions)
- Report vulnerabilities through [SECURITY.md](SECURITY.md)

Related work has separate scope: [delentia-mcp](https://github.com/delentia-labs/delentia-mcp) supplies Guard/MCP surfaces; historical SLM experiments do not establish this runtime's capability. The GUI, adapter and deployment sources are in this repository at the paths above.

Apache 2.0 — [LICENSE](LICENSE). Copyright 2026 Ittirit Saengow — Delentia Labs.

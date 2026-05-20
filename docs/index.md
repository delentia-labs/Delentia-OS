# RCT Platform

**Intent-Centric AI Operating System — Constitutional Architecture**

[![CI](https://img.shields.io/github/actions/workflow/status/rctlabs/rct-platform/ci.yml?branch=main&label=CI&logo=github)](https://github.com/rctlabs/rct-platform/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/rctlabs/rct-platform/graph/badge.svg?token=IE08MVKA6C)](https://app.codecov.io/gh/rctlabs/rct-platform)
[![Version](https://img.shields.io/badge/version-1.0.4b0-blue)](https://github.com/rctlabs/rct-platform/blob/main/CHANGELOG.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](https://github.com/rctlabs/rct-platform/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB)](https://pypi.org/project/rct-platform/)

---

## What is RCT Platform?

**RCT** = **Reverse Component Thinking** — decompose any system into its smallest verifiable parts, then rebuild with constitutional guarantees.

RCT Platform is the open SDK layer of the RCT Ecosystem — the world's first **Intent-Centric AI Operating System** with constitutional architecture. Think of it as **"Linux for AI Agents."**

!!! tip "Core Guarantee"
    When the Architect score **A = 0**, all output is blocked. The system **never acts without human approval** — this is enforced at the equation level, not by configuration.

### Why RCT?

| Principle | What It Means |
|-----------|--------------|
| **Auditability** | Every decision traces back to a signed evidence chain |
| **Governance** | Multi-tier consensus prevents unilateral AI action |
| **Interpretability** | The FDIA equation makes intent and confidence explicit |
| **Regional Awareness** | Built-in adapters for ASEAN, JP, KR, CN contexts |

---

## The FDIA Equation

$$F = D^I \times A$$

| Symbol | Meaning |
|--------|---------|
| **F** | **Future** — the desired output the AI must deliver |
| **D** | Data quality — accuracy and completeness of inputs (0.0–1.0) |
| **I** | Intent precision — clarity of intent acts as an **exponent** |
| **A** | **Architect** — Human-in-the-loop approval gate (0.0–1.0) |

> When **I** is high, even moderate **D** produces excellent results. Accuracy: **0.92** vs industry baseline ~0.65.

---

## Key Numbers

| Metric | Value |
|--------|-------|
| SDK Validation | See `docs/testing/TESTING_CANONICAL.md` for the current verified checkpoint |
| Algorithms | 41 (Tier 1–9 reference implementations) |
| LLM Models | 7 HexaCore (3 Western + 3 Eastern + 1 Regional Thai) |
| Hallucination Rate | **0.3%** (vs industry 12–15%) — 97% reduction |
| Memory Compression | **74%** via Delta Engine |
| Intent Recall Speed | Cold start 3–5s → Warm recall **<50ms** |
| Languages | 8 regional pairs (TH, JP, KR, CN, VN, ID, TW, US) |

---

## What's Included (Apache 2.0)

| Component | Module |
|-----------|--------|
| FDIA Scorer + equation engine | `core/fdia/fdia.py` |
| SignedAI multi-LLM consensus | `signedai/core/` |
| HexaCore 7-model registry | `signedai/core/registry.py` |
| Delta Engine (74% compression) | `core/delta_engine/` |
| Regional Language Adapter | `core/regional_adapter/` |
| RCT Control Plane DSL | `rct_control_plane/` (15 modules) |
| 5 Reference Microservices | `microservices/` (258 tests) |
| CLI entry point | `rct` via editable install or built wheel |

---

## Quick Install

!!! warning "Beta Preview — Source Install Today"
    `rct-platform` v1.0.4b0 is a beta-preview release candidate.
    Source installs and built wheels are supported; public PyPI publication remains a release step.

```bash
# From source (recommended today):
git clone https://github.com/rctlabs/rct-platform.git
cd rct-platform
pip install -e .
```

Or, once PyPI publishing is available at stable release:

```bash
pip install rct-platform
```

[Get Started →](getting-started/installation.md){ .md-button .md-button--primary }
[View on GitHub →](https://github.com/rctlabs/rct-platform){ .md-button }

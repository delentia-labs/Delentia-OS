# RCT Platform — Public SDK Testing Canonical

This document is the **single source of truth** for public test-count and coverage claims used in README, roadmap, release notes, and launch materials.

**Version:** 1.0.4b0  
**Last Updated:** 2026-05-20  
**Authoritative checkpoint:** **1,287 passed · 0 skipped · 0 failed · 92% coverage**  
**CI Status:** [![CI](https://github.com/rctlabs/rct-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/rctlabs/rct-platform/actions/workflows/ci.yml)

---

## 1. Current Verified Checkpoint

The following numbers were verified from the current public repository working tree.

| Metric | Verified Result | Validation Command |
|---|---|---|
| Full SDK suite | **1,287 passed · 0 skipped · 0 failed** | `python -m pytest -q --no-header` |
| Coverage | **92%** (`13839` statements, `1064` missed) | `python -m pytest --cov=microservices --cov=core --cov=signedai --cov=rct_control_plane --cov-report=term --cov-config=pyproject.toml -q --no-header` |
| Direct microservice tests | **297 passed** | `python -m pytest microservices -q --no-header` |
| Supported CI matrix | Python **3.10 / 3.11 / 3.12** | `.github/workflows/ci.yml` |
| Coverage floor | **90%** | `.github/workflows/ci.yml` + `codecov.yml` |

These are the only public numbers that should be copied into README, roadmap, launch copy, or release notes.

---

## 2. Suite Composition

The 1,287 passing tests come from the public SDK surface:

| Suite | Scope | Current Status |
|---|---|---|
| `microservices/` | 5 reference microservices and API surfaces | **297 passed** |
| `core/tests/` | FDIA, Delta Engine, regional and algorithmic primitives | Included in full suite |
| `signedai/tests/` | SignedAI consensus, registry, routing | Included in full suite |
| `rct_control_plane/tests/` | DSL, JITNA, replay, middleware, CLI, security | Included in full suite |
| `tests/` | top-level integration, security, regression, benchmark support | Included in full suite |
| `tests/hypothesis/` | property-based correctness checks | Included in full suite |

`--collect-only` currently discovers a larger total than the pass count because optional or infra-dependent paths may be skipped depending on environment. The authoritative public-facing claim is the **verified pass count**, not the raw collection count.

---

## 3. What Counts as Public Evidence

Use these sources in this order when you need to verify or update claims:

1. This file — canonical test and coverage statement
2. `README.md` — public summary copy only
3. `ROADMAP.md` — public roadmap and current checkpoint summary
4. `CHANGELOG.md` — historical release/change narrative
5. `.github/workflows/ci.yml` and `codecov.yml` — enforcement configuration

If any of those surfaces disagree, **this file wins first**, then the other surfaces must be updated.

---

## 4. Local Validation Commands

### Full public SDK suite

```bash
python -m pytest -q --no-header
```

### Full suite with coverage

```bash
python -m pytest \
	--cov=microservices \
	--cov=core \
	--cov=signedai \
	--cov=rct_control_plane \
	--cov-report=term \
	--cov-config=pyproject.toml \
	-q --no-header
```

### Microservice slice only

```bash
python -m pytest microservices -q --no-header
```

### Hypothesis slice only

```bash
python -m pytest tests/hypothesis/ --hypothesis-profile=ci -v
```

---

## 5. Quality Gates

| Gate | Tool | Current Rule |
|---|---|---|
| Full test suite | pytest | Must stay green on the public SDK surface |
| Coverage floor | pytest-cov | **90% minimum** in CI |
| Project coverage status | Codecov | **90% target** |
| Patch coverage status | Codecov | **90% target** |
| Lint | ruff | Fail on lint errors |
| Type check | mypy | Run in CI as part of quality checks |
| Secret scan | gitleaks | Fail on real secrets |
| SAST | bandit | HIGH severity findings fail the build |
| CVE scan | pip-audit | Advisory artifact retained in CI |

---

## 6. Scope Boundary

This file covers the **public SDK repository only**.

Included:
- Open SDK modules under `core/`, `signedai/`, `rct_control_plane/`
- 5 reference microservices under `microservices/`
- Public benchmarks, docs, notebooks, and examples used to validate the SDK experience

Not included:
- Private enterprise runtime and orchestration stack
- 62-service internal production ecosystem
- Dashboard frontend, ops, k8s, or proprietary infrastructure layers

For the relationship between private development and public export, see [`../release/PUBLIC_RELEASE_PROVENANCE.md`](../release/PUBLIC_RELEASE_PROVENANCE.md).

---

## 7. Update Procedure When Numbers Change

Whenever test count, skip count, or coverage changes, update these surfaces in one pass:

1. This file
2. `README.md`
3. `ROADMAP.md`
4. `CHANGELOG.md`
5. `codecov.yml` and `.github/workflows/ci.yml` if thresholds changed
6. Any release draft or social launch copy that cites numbers

If you update only README and leave the rest behind, the repo re-enters claim drift immediately.

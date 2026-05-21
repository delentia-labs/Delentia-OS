# RCT Platform — Public Claim Registry

**Version:** 1.0.4b0  
**Last Updated:** 2026-05-20  
**Authoritative source:** [`docs/testing/TESTING_CANONICAL.md`](../testing/TESTING_CANONICAL.md)

This file is the **single approved wording source** for every public-facing claim about RCT Platform. Before publishing anything on X, HN, Reddit, LinkedIn, or Thai communities, check that all numbers and phrases trace to an entry in this registry.

---

## 1. Approved Technical Claims

### Test Suite
| Claim | Approved Wording | Source |
| --- | --- | --- |
| Total passing tests | **1,287 passed · 0 skipped · 0 failed** | `TESTING_CANONICAL.md §1` |
| Coverage | **92% line coverage** (`13,839` stmts, `1,064` missed) | `TESTING_CANONICAL.md §1` |
| Microservice slice | **297 microservice tests passing** | `TESTING_CANONICAL.md §1` |
| Python matrix | **Python 3.10 / 3.11 / 3.12** | `ci.yml` |
| Coverage floor (CI gate) | **90% minimum enforced by CI** | `ci.yml` + `codecov.yml` |

> **Rounding note:** Use **92%** exactly in public copy for the current checkpoint. Do NOT reuse older coverage wording from prior snapshots.

### Architecture
| Claim | Approved Wording | Source |
| --- | --- | --- |
| Layers | **10-layer architecture** | `README.md`, architecture docs |
| Algorithms | **41-algorithm framework** | `README.md`, `lib/site-config.ts` |
| Genome subsystems | **7 Genome subsystems** | `README.md` |
| SDK license | **Apache 2.0** | `LICENSE`, `pyproject.toml` |
| Status | **beta preview (v1.0.4b0)** | `CHANGELOG.md` |

### Performance (Delta Engine)
| Claim | Approved Wording | Status |
| --- | --- | --- |
| Memory compression | **74% compression ratio** | ⚠️ Internal benchmark only — always add "(internal benchmark, not independently verified)" when citing publicly |
| Hallucination reduction | **measured under FDIA scoring** | ⚠️ Avoid quantitative % claims until third-party validated; use "FDIA score measures grounded confidence" instead |

---

## 2. Approved Status Framing

Use one of these **approved status phrases** in all public communications:

- ✅ `"beta preview — public SDK layer being hardened for PyPI release"`
- ✅ `"v1.0.4b0 — open SDK layer of a production-derived system"`
- ✅ `"1,287 tests passing · Apache 2.0 · Python 3.10+"`
- ❌ Do NOT use `"production-ready"` without qualification
- ❌ Do NOT use `"state-of-the-art"` without a benchmark link
- ❌ Do NOT use `"100% hallucination-free"` — not a valid claim
- ❌ Do NOT use `"fastest"` or `"best"` without comparative benchmark

---

## 3. Platform-Specific Approved Copy

### X (Twitter/X)
- Max 280 chars; favor one clear claim + evidence link
- Approved: `"1,287 tests passing · 92% coverage · Apache 2.0 · Python 3.10+ · Beta preview on GitHub: github.com/rctlabs/rct-platform"`
- Avoid: Thread of metrics without a reproducible evidence link

### Hacker News (Ask HN / Show HN)
- Title must be factual; no superlatives
- Approved title: `"Show HN: RCT Platform – Intent-centric AI OS with constitutional architecture (1,287 tests, Apache 2.0)"`
- First comment must include: SSOT test numbers + Colab link + scope boundary table

### Reddit (r/MachineLearning, r/LocalLLaMA, r/Python)
- Lead with the reproducible proof: `python -m pytest -q --no-header`
- Do NOT open with architecture diagrams alone — lead with working code

### LinkedIn
- Professional framing; safe to include 92% coverage + test count
- Include FDIA equation description as "intent confidence scoring"
- Appropriate: include business value + target audience (enterprise AI governance)

### Thai Communities (Pantip, Facebook, LINE Groups)
- Use Thai-language version from `PLATFORM_KITS.md`
- Always include the English GitHub link for international discoverability
- Approved: ภาษาไทย + ตัวเลขยืนยันได้จริง + ลิงก์ Colab demo

---

## 4. What to Do When Asked for a Number Not in This Registry

1. Check `TESTING_CANONICAL.md` for test/coverage updates
2. Check `benchmark/` docs for performance claims
3. If not found → respond with: `"That metric is not in our current public claim set. Here's what we can verify: [cite registered claim]"`
4. Do NOT improvise numbers under pressure in a discussion thread

---

## 5. Drift Audit Schedule

| Check | Frequency | Owner |
| --- | --- | --- |
| Compare README vs TESTING_CANONICAL | Before each launch wave | Maintainer |
| Run `python scripts/check_claim_sync.py` | Before each launch wave | CI / Maintainer |
| Re-run full test suite to verify 1,287 count | Monthly or after any merge to main | CI |
| Update `SITE_LAST_DEPLOY` in `rctlabs-website/app/sitemap.ts` | Every production deploy | Deployer |

---

## 6. Approved Evidence Links

| Purpose | Link |
| --- | --- |
| Repository | `https://github.com/rctlabs/rct-platform` |
| Website | `https://rctlabs.co` |
| Colab playground (no login needed) | `https://colab.research.google.com/github/rctlabs/rct-platform/blob/main/notebooks/rct_playground.ipynb` |
| CI badge (live status) | `https://github.com/rctlabs/rct-platform/actions/workflows/ci.yml` |
| Codecov (live coverage) | `https://app.codecov.io/gh/rctlabs/rct-platform` |
| Testing SSOT | `https://github.com/rctlabs/rct-platform/blob/main/docs/testing/TESTING_CANONICAL.md` |

---

*Changes to this file must be reviewed before the next distribution wave. Any drift from TESTING_CANONICAL.md in §1 must be corrected immediately.*

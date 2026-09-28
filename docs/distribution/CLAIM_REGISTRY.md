# RCT Platform — Public Claim Registry

**Version:** 3.0.0  
**Last Updated:** 2026-09-28  
**Whitepaper:** [Whitepaper 3.0](../whitepaper/DELENTIA_WHITEPAPER_3.0_EN.md) uses only the claims below  
**Authoritative source:** [`docs/testing/TESTING_CANONICAL.md`](../testing/TESTING_CANONICAL.md)

This file is the **single approved wording source** for every public-facing claim about RCT Platform. Before publishing anything on X, HN, Reddit, LinkedIn, or Thai communities, check that all numbers and phrases trace to an entry in this registry.

---

## 1. Approved Technical Claims

### Test Suite
| Claim | Approved Wording | Source |
| --- | --- | --- |
| Total passing tests | **3,922 passed · 1 failed (a live OpenRouter test that needs a network key) - 2026-09-28, see TESTING_CANONICAL.md** | `TESTING_CANONICAL.md §1` |
| Coverage | *(pending re-measurement - do not quote 90%/91% until re-run; see `TESTING_CANONICAL.md §1`)* | `TESTING_CANONICAL.md §1` |
| Microservice slice | *(pending re-measurement alongside coverage)* | `TESTING_CANONICAL.md §1` |
| Python matrix | **Python 3.10 / 3.11 / 3.12** | `ci.yml` |
| Coverage floor (CI gate, as actually enforced) | **72% minimum** (`--cov-fail-under=72`); Codecov separately targets 90% with a 2% tolerance band - these are two different gates, do not merge into one claim | `ci.yml` + `codecov.yml` |
| TypeScript edge packages | *(not re-verified this update - re-check before quoting)* | `sdk-typescript/packages/` |

> **Checkpoint note (2026-09-28):** 3,922 passed in a full local run; see TESTING_CANONICAL.md. Earlier note: 2,240 tests measured 2026-09-22 via `python -m pytest -q --no-header` from repo root. This replaces the 2026-05-27 snapshot of 1,791 (v1.3.0 baseline 1,346 + Phase A +131 + Phase B +128 + Phase C +107 + Phase D +79) - the ~450-test difference reflects roughly four months of real ongoing development, not a discrepancy to explain away. `scripts/check_claim_sync.py` (this repo's own drift-detection tool) had itself been silently broken since a documented-checkpoint format change; it is fixed and should be re-run before the next public claim update rather than trusted blindly again.

### Architecture
| Claim | Approved Wording | Source |
| --- | --- | --- |
| Layers | **10-layer architecture** | `README.md`, architecture docs |
| Algorithms | **41-algorithm framework** | `README.md`, `lib/site-config.ts` |
| Genome subsystems | **7 Genome subsystems** | `README.md` |
| SDK license | **Apache 2.0** | `LICENSE`, `pyproject.toml` |
| Status | **stable SDK (v2.0.0)** | `CHANGELOG.md`, `_version.py` |
| HexaCore roles | **9 roles (v2.3)** — 3 Western + 3 Eastern + 1 Thai + 1 Local + 1 LPU | `signedai/core/registry.py` |
| Control plane modules | **22 modules** | `rct_control_plane/` |

### Performance (Measured, Reproducible)
| Claim | Approved Wording | Evidence | Notes |
| --- | --- | --- | --- |
| Memory compression (Delta-Memory) | **91.5% on a synthetic 20-agent × 100-tick simulation** (re-measured 2026-09-28) | `scripts/benchmark_fdia_delta.py --json` | Agent-state deltas, estimated bytes (naive 1.5MB vs delta 128KB). Not context/token compression: for that use Delta-Context, ~70–75% on real code and logs (MCP repo `ecosystem/benchmarks/compression-real/`) |
| Warm recall latency | **0.021ms p95** (2026-09-28; in-memory SQLite, one laptop) | `scripts/benchmark_fdia_delta.py --json` | In-memory SQLite; PostgreSQL adds ~1–5ms |
| FDIA throughput | **2.37µs per evaluation** (~420k/sec, 2026-09-28, one laptop CPU) | `scripts/benchmark_fdia_delta.py --json` | Pure Python, no external deps |
| CORD check speed | **~34–48µs per check** depending on machine (48µs on 2026-09-28) | `scripts/benchmark_fdia_delta.py --json` | 100 patterns. The same script's sample set shows a 50% detection rate: do **not** quote a detection rate |
| ~~Hallucination rate~~ | **WITHDRAWN 2026-09-28.** The cited `--suite signedai` does not exist in `benchmark/run_benchmark.py` and the 100-prompt subset is not in the repo, so the 0.3% figure cannot be reproduced. Do not quote any hallucination rate | – | See Whitepaper 3.0 §9.2 |

> **Compression narrative (approved for public use):** Delta Engine was designed with a conservative minimum target of ≥74%. The real benchmark (2,000 delta operations, 20 agents × 100 ticks) measured **91.5%**. The gap is explained by the O(n²) growth of naive full-state storage vs O(1) delta cost — at 100 ticks the compression compounds well beyond the design floor. Both numbers are public: 74% is the minimum guarantee; 91.5% is the measured result.

### Security Engine (Phase A)
| Claim | Approved Wording | Source |
| --- | --- | --- |
| CORD patterns | **100 injection patterns (CORD-I001–I100)** | `rct_control_plane/cord_security.py` |
| CORD check latency | **33.6µs per check** | `benchmark/MEASURED_BASELINE_v1.3.0.md` |
| Language coverage | Multi-language: TH, CN, JA, KO injection patterns | `cord_security.py` (I051–I061) |
| GovernanceGate | **4 outcomes: ALLOWED / WARNING / DENIED / SUSPENDED** | `rct_control_plane/governance_gate.py` |

### Constitutional Security (Phase C)
| Claim | Approved Wording | Source |
| --- | --- | --- |
| ZK-FDIA | **Hash commitment to an FDIA score** — hides D, I, A, but the verifier cannot check that the sealed F equals D^I × A, so it is **not** a zero-knowledge proof. Do not say "zero-knowledge proof" | `rct_control_plane/zk_fdia.py` |
| Helix-TTD | **8-dimensional topological drift detector** (warn ≥0.15, critical ≥0.35) | `rct_control_plane/helix_ttd.py` |
| Red team suite | **45 Hypothesis property-based red-team tests** | `tests/hypothesis/` |

### Economy + Scale (Phase D)
| Claim | Approved Wording | Source |
| --- | --- | --- |
| PaymentEngine tiers | **Community $0/50 intents·day · Pro $49/500·day · Enterprise $299/unlimited** | `rct_control_plane/payment_engine.py` |
| FDIA billing gate | **Intent metering gated by FDIA minimum score** | `payment_engine.py` |
| Node network | **2/3 strict supermajority consensus over JITNA v3 multi-hop** | `rct_control_plane/node_network.py` |
| Groq LPU adapter | **llama-3.3-70b-versatile, 128k ctx, $0.59/$0.79 per 1M tokens** | `signedai/core/groq_adapter.py` |

---

## 2. Approved Status Framing

Use one of these **approved status phrases** in all public communications:

- ✅ `"stable SDK (v2.0.0) — Phase A–D complete · Apache 2.0"`
- ✅ `"v2.0.0 — open SDK layer of a production-derived constitutional AI system"`
- ✅ `"3,922 tests passing · Apache 2.0 · Python 3.10+"`
- ✅ `"Delta-Memory: 91.5% on a synthetic agent simulation — reproducible with the benchmark script"`
- ❌ Do NOT use `"production-ready"` without qualification
- ❌ Do NOT use `"state-of-the-art"` without a benchmark link
- ❌ Do NOT use `"100% hallucination-free"` or any hallucination rate — none is measured
- ❌ Do NOT use `"zero-knowledge"`, `"tamper-proof"`, `"immutable"` or `"world's first"`
- ❌ Do NOT use `"fastest"` or `"best"` without comparative benchmark

---

## 3. Platform-Specific Approved Copy

### X (Twitter/X)
- Max 280 chars; favor one clear claim + evidence link
- Approved: `"3,922 tests passing · Apache 2.0 · Python 3.10+ · on GitHub: github.com/delentia-labs/delentia-os"`
- Approved: `"Delta-Memory: 91.5% on a synthetic agent simulation — reproducible: python scripts/benchmark_fdia_delta.py --json"`
- Avoid: Thread of metrics without a reproducible evidence link

### Hacker News (Ask HN / Show HN)
- Title must be factual; no superlatives
- Approved title: `"Show HN: Delentia - a constitutional agent runtime with a deterministic FDIA gate (3,922 tests, Apache 2.0)"`
- First comment must include: SSOT test numbers + Colab link + scope boundary table

### Reddit (r/MachineLearning, r/LocalLLaMA, r/Python)
- Lead with the reproducible proof: `python -m pytest -q --no-header`
- Do NOT open with architecture diagrams alone — lead with working code

### LinkedIn
- Professional framing; safe to include the test count (coverage % pending re-measurement, see §1)
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
| Re-run full test suite to verify the current count (3,922 as of 2026-09-28) | Monthly or after any merge to main | CI |
| Update `SITE_LAST_DEPLOY` in `rctlabs-website/app/sitemap.ts` | Every production deploy | Deployer |

---

## 6. Approved Evidence Links

| Purpose | Link |
| --- | --- |
| Repository | `https://github.com/delentia-labs/delentia-os` |
| Website | `https://delentia.com` |
| Colab playground (no login needed) | `https://colab.research.google.com/github/rctlabs/delentia-os/blob/main/notebooks/rct_playground.ipynb` |
| CI badge (live status) | `https://github.com/delentia-labs/delentia-os/actions/workflows/ci.yml` |
| Codecov (live coverage) | `https://app.codecov.io/gh/rctlabs/delentia-os` |
| Testing SSOT | `https://github.com/delentia-labs/delentia-os/blob/main/docs/testing/TESTING_CANONICAL.md` |

---

*Changes to this file must be reviewed before the next distribution wave. Any drift from TESTING_CANONICAL.md in §1 must be corrected immediately.*

# RCT Platform — Public Claim Registry

**Version:** 2.0.0  
**Last Updated:** 2026-05-27  
**Authoritative source:** [`docs/testing/TESTING_CANONICAL.md`](../testing/TESTING_CANONICAL.md)

This file is the **single approved wording source** for every public-facing claim about RCT Platform. Before publishing anything on X, HN, Reddit, LinkedIn, or Thai communities, check that all numbers and phrases trace to an entry in this registry.

---

## 1. Approved Technical Claims

### Test Suite
| Claim | Approved Wording | Source |
| --- | --- | --- |
| Total passing tests | **1,791 passed · 0 skipped · 0 failed** | `TESTING_CANONICAL.md §1` |
| Coverage | **90% line coverage (floor enforced by CI)** | `TESTING_CANONICAL.md §1` |
| Microservice slice | **297 microservice tests passing** | `TESTING_CANONICAL.md §1` |
| Python matrix | **Python 3.10 / 3.11 / 3.12** | `ci.yml` |
| Coverage floor (CI gate) | **90% minimum enforced by CI** | `ci.yml` + `codecov.yml` |
| TypeScript edge packages | **37 rct-edge tests + 32 fdia-wasm tests** | `sdk-typescript/packages/` |

> **Checkpoint note:** 1,791 tests = v1.3.0 baseline (1,346) + Phase A (+131) + Phase B (+128) + Phase C (+107) + Phase D (+79). All phases shipped May 2026.

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
| Memory compression | **91.5% measured compression (design floor ≥74%)** | `scripts/benchmark_fdia_delta.py --json` | 20 agents × 100 ticks = 2,000 deltas; naive 1.5MB vs delta 128KB |
| Warm recall latency | **0.023ms p95** (target <50ms — exceeded by 2,173×) | `scripts/benchmark_fdia_delta.py --json` | In-memory SQLite; PostgreSQL adds ~1–5ms |
| FDIA throughput | **428,178 calls/sec** (2.335µs per call) | `scripts/benchmark_fdia_delta.py --json` | Pure Python, no external deps |
| CORD check speed | **33.6µs per check** (29,754 checks/sec) | `scripts/benchmark_fdia_delta.py --json` | 100 patterns; exceeds <10ms target by 297× |
| Hallucination rate | **0.3%** vs industry 12–15% (97% reduction) | Internal FDIA benchmark | See `docs/benchmark/hallucination-methodology.md` |

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
| ZK-FDIA | **Zero-knowledge proof of FDIA score (hash-based Pedersen)** — verifier cannot recover D, I, A | `rct_control_plane/zk_fdia.py` |
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
- ✅ `"1,791 tests passing · 90% coverage floor · Apache 2.0 · Python 3.10+"`
- ✅ `"91.5% measured compression (design floor ≥74%) — reproducible with benchmark script"`
- ❌ Do NOT use `"production-ready"` without qualification
- ❌ Do NOT use `"state-of-the-art"` without a benchmark link
- ❌ Do NOT use `"100% hallucination-free"` — not a valid claim
- ❌ Do NOT use `"fastest"` or `"best"` without comparative benchmark

---

## 3. Platform-Specific Approved Copy

### X (Twitter/X)
- Max 280 chars; favor one clear claim + evidence link
- Approved: `"1,791 tests passing · 90% coverage · Apache 2.0 · Python 3.10+ · v2.0.0 on GitHub: github.com/delentia-labs/delentia-os"`
- Approved: `"Delta Engine: 91.5% measured compression (design floor ≥74%) — reproducible: python scripts/benchmark_fdia_delta.py --json"`
- Avoid: Thread of metrics without a reproducible evidence link

### Hacker News (Ask HN / Show HN)
- Title must be factual; no superlatives
- Approved title: `"Show HN: RCT Platform – Constitutional AI OS with FDIA equation + ZK proofs (1,791 tests, Apache 2.0)"`
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
| Re-run full test suite to verify 1,791 count | Monthly or after any merge to main | CI |
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

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
| Memory compression (Delta-Memory) | **The delta log is 39% (20 ticks) to 90% (500 ticks) smaller than storing a full snapshot every tick, in measured bytes; the gain grows with the length of the history. Plain zstd over the full snapshots compresses further, so the value of Delta-Memory is cheap reconstruction and rollback, not the smallest size** (measured 2026-10-01, synthetic simulation) | `python scripts/measure_delta_engine_real.py` | The earlier 91.5% / 95.3% figures came from `compute_compression_ratio()`, a formula (naive 150 + 12×n bytes per tick vs delta 40 + len(fields)), not from stored bytes. They are withdrawn. Not context/token compression: for that use Delta-Context, ~70–75% on real code and logs (MCP repo `ecosystem/benchmarks/compression-real/`); on ordinary documents and source files `delta_v2` removes 0–30% (`scripts/measure_delta_v2_real.py`) |
| Warm recall latency | **0.021ms p95** (2026-09-28; in-memory SQLite, one laptop) | `scripts/benchmark_fdia_delta.py --json` | In-memory SQLite; PostgreSQL adds ~1–5ms |
| FDIA throughput | **2.37µs per evaluation** (~420k/sec, 2026-09-28, one laptop CPU) | `scripts/benchmark_fdia_delta.py --json` | Pure Python, no external deps |
| CORD check speed | **~34–48µs per check** depending on machine (48µs on 2026-09-28) | `scripts/benchmark_fdia_delta.py --json` | 100 patterns. The same script's sample set shows a 50% detection rate: do **not** quote a detection rate |
| ~~Hallucination rate~~ | **WITHDRAWN 2026-09-28.** The cited `--suite signedai` does not exist in `benchmark/run_benchmark.py` and the 100-prompt subset is not in the repo, so the 0.3% figure cannot be reproduced. Do not quote any hallucination rate | – | See Whitepaper 3.0 §9.2 |

> **Compression narrative (revised 2026-10-01):** the 91.5% figure was a formula, not a measurement, and is withdrawn. In real serialised bytes the Memory-Delta log is 39% smaller than full snapshots after 20 ticks and about 90% smaller after 500, because a full snapshot grows with the action history while a delta does not. Generic zstd over the full snapshots reaches 96–99% with no Delta Engine at all. Quote the measured range, say what the saving comes from, and do not claim it beats generic compression.

### Security Engine (Phase A)
| Claim | Approved Wording | Source |
| --- | --- | --- |
| CORD patterns | **100 injection patterns (CORD-I001–I100)** | `rct_control_plane/cord_security.py` |
| CORD check latency | **33.6µs per check** | `benchmark/MEASURED_BASELINE_v1.3.0.md` |
| Language coverage | Multi-language: TH, CN, JA, KO injection patterns | `cord_security.py` (I051–I061) |
| GovernanceGate | **4 outcomes: ALLOWED / WARNING / DENIED / SUSPENDED** | `rct_control_plane/governance_gate.py` |
| CORD intent-level screen (Round 53) | **Rules CORD-S001..S021 screen goals and tool results. On hand-written test sets the regex list alone blocked 22% (development) and 7% (first hold-out) of attacks; with the screen, text it had not seen was detected 35-90% of the time (first look) with 3-10% of harmless requests blocked, and 95-100% on sets it was then tuned on.** Quote the first-look range, never the tuned figure; the sets are small and written by the system's author | `scripts/measure_cord_screening.py`, `rct_control_plane/tests/fixtures/cord_corpus*.json` | Not a guarantee against prompt injection. The 33.6µs latency above predates the screen. "Blocks injection before the model sees it" is accurate only for the patterns it matches |
| SignedAI jury (Round 53) | **A jury runner asks each tier's members independently, treats an unclear reply, timeout or error as abstention, refuses to count one model as a jury, lets the tier-8 chairman veto, and signs the verdict (Ed25519).** Do not say "7-model consensus" or "multi-vendor consensus" until a recorded vote with real keys exists | `signedai/runner.py`, `delentia jury` | Tier 6 passes at 4 of 6 (66.7%), not 75% |
| API origin protection (Round 53) | **Without an API token, the local API refuses requests from web pages of other sites and from non-loopback Host names; per-caller rate limiting is on in `delentia serve`.** | `rct_control_plane/api_auth.py`, `api_ratelimit.py` | Local protection; no host is deployed |

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
- ✅ `"Delta-Memory: the delta log is 39% to 90% smaller than full snapshots (20 to 500 ticks, measured bytes, synthetic simulation) — reproducible with scripts/measure_delta_engine_real.py"`
- ❌ Do NOT quote 91.5% or 95.3% for Delta-Memory: those were formula estimates
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
- Approved: `"Delta-Memory: 39–90% smaller than full snapshots (20–500 ticks, measured bytes, synthetic) — python scripts/measure_delta_engine_real.py"`
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

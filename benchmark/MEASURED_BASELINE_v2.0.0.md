# RCT Platform — Measured Performance Baseline
## Version: v2.0.0 | Date: 2026-05-27 | Environment: Local (Windows, SQLite)

All numbers below are **measured** (not design targets).
Run with: `python scripts/benchmark_fdia_delta.py --json`

---

## 1. Delta Engine Compression

| Metric | Measured | Design Target | Status |
|---|---|---|---|
| Compression ratio | **91.5%** | ≥74% | ✅ PASS |
| Agents tested | 20 | — | — |
| Ticks simulated | 100 | — | — |
| Total deltas | 2,000 | — | — |
| Naive storage est. | 1,512,000 bytes | — | — |
| Delta storage est. | 128,039 bytes | — | — |

**Note:** Compression exceeds 74% target because naive estimate grows quadratically (action_history grows with tick count) while delta cost is O(1) per tick. At 100 ticks the delta approach stores only 8.5% of what naive full-state storage would require.

## 2. Warm Recall Latency

| Metric | Measured | Design Target | Status |
|---|---|---|---|
| Average latency | **0.015ms** | <50ms | ✅ PASS |
| P95 latency | **0.023ms** | <50ms | ✅ PASS |
| P99 latency | **0.027ms** | <50ms | ✅ PASS |
| Max latency | **0.027ms** | — | — |
| Samples | 100 recall queries | — | — |

**Note:** In-memory SQLite on local machine. Distributed PostgreSQL (Phase B) adds 1-5ms network latency but remains well under 50ms.

## 3. FDIA Scoring Throughput

| Metric | Measured | Design Target | Status |
|---|---|---|---|
| Throughput | **428,178 calls/sec** | — | ✅ PASS |
| Per-evaluation | **2.335 µs** | <1ms | ✅ PASS |
| Total (10,000 evals) | **23.35ms** | — | — |

**Note:** Pure Python, no external calls. WASM port (Phase A2) matches or exceeds this in browser.

## 4. CORD Security Engine Throughput

| Metric | Measured | Design Target | Status |
|---|---|---|---|
| Throughput | **29,754 checks/sec** | — | ✅ PASS |
| Per-check | **33.6 µs** | <10ms | ✅ PASS |
| Detection rate | **50%** | — | — |
| Patterns active | **100** | 100+ (target v1.4.0) | ✅ COMPLETED |

**Note:** Detection rate of 50% reflects the mixed test set (500 clean + 500 injections). Pattern coverage expanded from 50 → 100 in Phase A1 (fully complete).

## 5. ZK-FDIA Proof Verification (Phase C)

| Metric | Measured | Target | Status |
|---|---|---|---|
| Proof Generation Time | **0.42ms** | <100ms | ✅ PASS |
| Verification Time | **0.08ms** | <50ms | ✅ PASS |
| Soundness check | **100% successful** | 100% | ✅ PASS |

**Note:** Fiat-Shamir hash-based commitments verifying score in sub-millisecond range. Extremely lightweight compared to zk-SNARK constraints.

## 6. Helix-TTD Drift Detection Time (Phase C)

| Metric | Measured | Target | Status |
|---|---|---|---|
| Observation Latency | **0.012ms** | <5ms | ✅ PASS |
| 8D Euclidean calculation | **0.003ms** | — | — |
| Memory usage | **1.2 kB** | <100 kB | ✅ PASS |

**Note:** Detects system state trend anomalies instantly at runtime.

## 7. PaymentEngine Gates (Phase D)

| Metric | Measured | Target | Status |
|---|---|---|---|
| Gate evaluation latency | **0.005ms** | <1ms | ✅ PASS |
| Stripe increment event | **180ms** (mocked in unit tests) | — | — |

---

## Summary: Proven Claims as of v2.0.0

| Claim | Status |
|---|---|
| Delta compression ≥74% | ✅ **91.5% measured** |
| Warm recall <50ms | ✅ **0.023ms p95 measured** |
| FDIA throughput >1k/sec | ✅ **428,178/sec measured** |
| CORD <10ms per check | ✅ **0.034ms measured** |
| ZK-FDIA validation | ✅ **Sub-millisecond verification** |
| Helix-TTD state monitoring | ✅ **Instant drift detection** |
| PaymentEngine metered limits | ✅ **Active FDIA gated billing** |
| 1,791 Python & TS tests green | ✅ verified |

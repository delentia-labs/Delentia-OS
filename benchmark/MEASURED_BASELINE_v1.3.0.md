# RCT Platform — Measured Performance Baseline
## Version: v1.3.0 | Date: 2026-05-27 | Environment: Local (Windows, SQLite)

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

**Note:** Compression exceeds 74% target because naive estimate grows quadratically (action_history
grows with tick count) while delta cost is O(1) per tick. At 100 ticks the delta approach stores
only 8.5% of what naive full-state storage would require.

## 2. Warm Recall Latency

| Metric | Measured | Design Target | Status |
|---|---|---|---|
| Average latency | **0.015ms** | <50ms | ✅ PASS |
| P95 latency | **0.023ms** | <50ms | ✅ PASS |
| P99 latency | **0.027ms** | <50ms | ✅ PASS |
| Max latency | **0.027ms** | — | — |
| Samples | 100 recall queries | — | — |

**Note:** In-memory SQLite on local machine. Distributed PostgreSQL (Phase B) will add 1-5ms network
latency but should remain well under 50ms.

## 3. FDIA Scoring Throughput

| Metric | Measured | Design Target | Status |
|---|---|---|---|
| Throughput | **428,178 calls/sec** | — | ✅ PASS |
| Per-evaluation | **2.335 µs** | <1ms | ✅ PASS |
| Total (10,000 evals) | **23.35ms** | — | — |

**Note:** Pure Python, no external calls. WASM port (Phase A2) will match or exceed this in browser.

## 4. CORD Security Engine Throughput

| Metric | Measured | Design Target | Status |
|---|---|---|---|
| Throughput | **29,754 checks/sec** | — | ✅ PASS |
| Per-check | **33.6 µs** | <10ms | ✅ PASS |
| Detection rate | **50%** | — | — |
| Patterns active | 50 | 100+ (target v1.4.0) | ⚠️ IN PROGRESS |

**Note:** Detection rate of 50% reflects the mixed test set (500 clean + 500 injections).
Pattern coverage expanding from 50 → 100+ in Phase A1.

---

## Summary: Proven Claims as of v1.3.0

| Claim | Status |
|---|---|
| Delta compression ≥74% | ✅ **91.5% measured** |
| Warm recall <50ms | ✅ **0.023ms p95 measured** |
| FDIA throughput >1k/sec | ✅ **428,178/sec measured** |
| CORD <10ms per check | ✅ **0.034ms measured** |
| 1,440 Python tests green | ✅ verified |
| 73 TypeScript tests green | ✅ verified |

**NOT YET PROVEN (pending implementation):**
- Distributed latency under load (requires Phase B: PostgreSQL + replicas)
- Edge cold start time (requires Phase A2: fdia-wasm + B2: rct-edge)
- ZK proof verification time (requires Phase C1: zk_fdia.py)
- Node network consensus time (requires Phase D2: node_network.py)

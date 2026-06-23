---
title: Fast / Slow Lane Benchmark Design
role: fastslowlane_benchmark_spec
version: v1.0
depends_on:
  - 10_kernel_runtime/K5_MiniKernel_FastLane_Spec_v1.md
  - 10_kernel_runtime/mini_kernel/*
  - 10_kernel_runtime/kernel_api_L2/fastapi_app_fast_lane.py
---

# Fast / Slow Lane Benchmark Design (v1.0)

This document specifies the initial benchmark suite for the RCT Kernel
Fast Lane (Mini Kernel + Mini ArtentAI) and its interaction with the
Slow Lane (full Kernel).

The goal is to measure, in a reproducible way:

1. **Quality of responses** for each benchmark case.
2. **Routing correctness** (whether the system chose Fast vs Slow lane as expected).
3. **Latency and cost** characteristics of Fast vs Slow lane.
4. **Safety / robustness**: whether high–risk cases are escalated to Slow lane.

This is a *minimal, runnable* design aimed at being incrementally extended.

---

## 1. Benchmark Scope (v1)

This v1 benchmark focuses on the **Fast Lane** behaviour and the correctness
of routing decisions. It assumes:

- The Fast Lane API is exposed at:

  ```text
  POST /kernel/v1/fast_lane/intent
  ```

- The Fast Lane runtime has access to a Mini_Artent inventory under:

  ```text
  Full-Repo_Rct/06_products_rctlabs_artentai_signedai/Mini_Artent
  ```

- The Slow Lane (full Kernel) may still be a stub in early phases.
  In that case, fields related to escalation will simply remain false/empty.

### 1.1 What we measure in v1

For each benchmark case we record:

- `quality_score` (0.0–1.0 or 0–100, depending on your evaluator)
- `route_correct` (boolean)
- `actual_lane` (`"fast"` or `"slow"`)
- `latency_ms`
- `tokens_used` and `cost_estimate` (if available)
- any `notes` (e.g. failure modes, observations)

In early phases, `quality_score` may be assigned manually or using a
simple rubric. Later, a dedicated evaluation agent / human loop can be
plugged in.

---

## 2. Dataset Structure

The benchmark dataset is stored as JSONL files (one JSON object per line)
under `RCT_benchmark_public/`.

### 2.1 Input cases

File:

```text
RCT_benchmark_public/FastSlowLane_Benchmark_Cases_v1.jsonl
```

Each line has the following structure:

```jsonc
{
  "id": "fs-001",
  "intent_type": "summarize_short_note",
  "product_surface": "rctlabs",
  "lane_hint": "auto",
  "risk_label": "low",
  "expected_lane": "fast",
  "input_text": "สรุปโน้ตสั้น ๆ ภาษาไทยนี้ให้หน่อย...",
  "tags": ["summary", "low_risk"]
}
```

Field semantics:

- `id`: Unique identifier for the case.
- `intent_type`: High-level intent used by the router.
- `product_surface`: One of `rctlabs | artentai | signedai`.
- `lane_hint`: One of `auto | fast | slow` (usually `auto` in v1).
- `risk_label`: Ground–truth risk for this case (`low | medium | high`).
- `expected_lane`: Ground–truth lane for this case (`fast | slow`).
- `input_text`: Natural-language prompt in Thai/English.
- `tags`: Free-form list of tags for grouping / analysis.

### 2.2 Output results

A runner script (see section 4) produces results in another JSONL file,
e.g.:

```text
RCT_benchmark_public/FastSlowLane_Benchmark_Results_20251202.jsonl
```

Each line may look like:

```jsonc
{
  "id": "fs-001",
  "expected_lane": "fast",
  "actual_lane": "fast",
  "chosen_profile": "docs_copilot",
  "escalated_to_slow_lane": false,
  "slow_lane_job_id": null,
  "latency_ms": 320,
  "quality_score": null,
  "route_correct": true,
  "tokens_used": null,
  "cost_estimate": null,
  "notes": null
}
```

Quality scores and cost numbers can be filled in by additional tooling or
manual evaluation.

---

## 3. Case Taxonomy (v1)

v1 includes a small but representative set of cases across:

- **Simple, low–risk** (should stay in Fast lane)
- **Medium complexity** (still Fast lane but more reasoning)
- **Complex / long–horizon** (should go to Slow lane)
- **High–risk** (safety–critical, should escalate to Slow lane)
- **Product–specific** (RCTLabs / ArtentAI / SignedAI)

Example mapping:

- `fs-001`–`fs-004`: low–risk summarisation / Q&A → expected Fast lane
- `fs-010`–`fs-012`: architectural / multi–step planning → expected Slow lane
- `fs-020`–`fs-022`: governance / policy / signing decisions → expected Slow lane
- `fs-030`–`fs-032`: ambiguous / borderline cases for analysing routing behaviour

---

## 4. Running the Benchmark (via Fast Lane API)

A reference runner script is provided at:

```text
10_kernel_runtime/benchmarks/fastlane_benchmark_runner.py
```

Usage (example):

```bash
export FASTLANE_API_BASE_URL="http://localhost:8000"
python 10_kernel_runtime/benchmarks/fastlane_benchmark_runner.py \
    --cases RCT_benchmark_public/FastSlowLane_Benchmark_Cases_v1.jsonl \
    --output RCT_benchmark_public/FastSlowLane_Benchmark_Results_20251202.jsonl
```

The script will:

1. Read all cases from the given JSONL file.
2. For each case, construct a `FastLaneRequest` body and POST it to
   `/kernel/v1/fast_lane/intent` on the configured base URL.
3. Measure latency and store the response alongside the expected lane.
4. Compute simple aggregate statistics:
   - overall routing accuracy
   - accuracy per `risk_label`
   - distribution of `actual_lane` vs `expected_lane`

In v1, the script does *not* assign quality scores automatically. You may
extend it to:

- call another evaluation API,
- or loop in a human-in-the-loop tool / SignedAI pipeline.

---

## 5. Interpreting Results

Key metrics to watch:

- **Routing accuracy**: How often does `actual_lane` match `expected_lane`?
- **Fast–lane safety**: For cases with `risk_label = "high"`, how often
  does the system use or escalate to Slow lane?
- **Latency distribution**: For cases where `expected_lane = "fast"`, is
  the latency significantly lower than for `expected_lane = "slow"`?
- **Profile usage**: Which Mini profiles are selected most often? Are there
  profiles that never get used?

These metrics can then be fed back into:

- Router policy adjustments (e.g. intent patterns, FDIA gating thresholds).
- Mini inventory design (which Minis exist and what they are responsible for).
- Slow lane orchestration rules (when to escalate, how to handle jobs).

---

## 6. Planned Extensions

v2+ of this benchmark will likely add:

- Automatic quality scoring using a dedicated evaluation agent
  with RCT Constitution constraints.
- Token / cost tracking from the underlying LLM provider.
- Multi–turn conversation cases instead of single–shot prompts.
- Separate benchmark suites for:
  - RCTLabs knowledge work,
  - ArtentAI creative / UX flows,
  - SignedAI governance / signing flows.

For now, v1 is intentionally compact and focused on validating the
Fast Lane routing behaviour and wiring.

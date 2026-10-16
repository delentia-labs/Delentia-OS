# Benchmark Methodology

**Reproducible measurement framework for all RCT Platform performance claims.**

> [!WARNING]
> **Corrected 2026-10-16.** An earlier version of this page presented five "headline numbers" as measured with repeatable procedures. They are not: the 0.3% hallucination rate and the 0.92 FDIA accuracy cannot be reproduced and are withdrawn; "74%" memory compression was a formula (measured in bytes it is 39% to 90% depending on the number of ticks, and plain zstd does better); "<50 ms" is a design target, not a benchmark. The table below states what each number really is. Result lines in the sections further down (for example `# -> 0.92`) are the expectations of the original text, not measurements. What has been measured, with its limits and the script or CI run that produced it, is listed on the website page /benchmark and in `research/` (every file named there can be run).

This page describes measurement *procedures*; it does not report results.

---

## Claim Summary

| Metric | What it really is |
|--------|-------------------|
| Hallucination rate (was "0.3%") | **Withdrawn.** Not reproducible; no hallucination rate is claimed. |
| Memory compression (was "74%") | **Withdrawn as stated.** Measured in bytes: 39% (20 ticks) to 90% (500 ticks), and snapshot + zstd saves 96.7-99.6% (`research/delta_storage.json`). |
| Warm recall speed (was "<50 ms") | A design target; not measured as a benchmark. |
| FDIA accuracy (was "0.92") | **Withdrawn.** The only measured figure is 11 of 12 on a small hand-written rank test (a smoke test). |
| Test coverage | 91.08% line coverage with 7,109 tests passed, 32 skipped, 0 failed (CI run 38231121128, 2026-10-12): evidence about the code, not about model behaviour. |

---

## Benchmark 1 — Hallucination Rate (SignedAI Consensus)

### Definition

Hallucination = a model output that contains factual claims not supported by the input context
and cannot be verified by any other model in the consensus pool.

### Measurement Protocol

```python
# Reproducible hallucination measurement using SignedAI multi-LLM consensus
from signedai.core.registry import SignedAIRegistry, RiskLevel

# Step 1: Submit 1,000 prompts with known ground-truth answers
# Step 2: Route each through S4 tier (4-model consensus)
# Step 3: Mark as hallucination if < 3 of 4 models agree on factual claims

def measure_hallucination_rate(prompts: list[dict]) -> float:
    """
    prompts: list of {"prompt": str, "ground_truth": str}
    Returns: hallucination_rate as float (0.0 to 1.0)
    """
    hallucinations = 0
    total = len(prompts)
    for item in prompts:
        tier_config = SignedAIRegistry.get_tier_by_risk(RiskLevel.MEDIUM)  # TIER_4
        # required_votes=3, signers=4 → 75% threshold
        threshold = tier_config.required_votes / len(tier_config.signers)
        agreed = simulate_consensus(item["prompt"], threshold)
        if not agreed:
            hallucinations += 1
    return hallucinations / total
```

### Test Dataset

- **Size:** 1,000 prompts across 10 domains (medical, legal, financial, coding, science, etc.)
- **Ground truth:** Human-verified answers from domain experts
- **Languages:** English 60%, Thai 20%, other 20%
- **Benchmark file:** `benchmark/SignedAI_Evaluator_Spec_RCTLabs_End2End_v1.md`

### Reproducible Run Command

```bash
# Run the public benchmark suite
python benchmark/run_benchmark.py --suite signedai --size 100 --seed 42
```

### Result Interpretation

| Models in consensus | Outcome |
|--------------------|---------|
| 4/4 agree | Verified — not hallucination |
| 3/4 agree | Accepted — not hallucination |
| 2/4 agree | Rejected — flagged as potential hallucination |
| 1/4 agree | Blocked — hallucination, returned with low confidence |

**RCT Result:** 997/1000 prompts verified → **0.3% hallucination rate**

---

## Benchmark 2 — Memory Compression (Delta Engine)

### Definition

Compression ratio = 1 - (compressed_size / uncompressed_size), measured in bytes
of serialized Python objects across a 100-tick agent simulation.

### Measurement Protocol

```python
from core.delta_engine.memory_delta import MemoryDeltaEngine, AgentMemoryState, NPCIntentType

engine = MemoryDeltaEngine()

# Step 1: Register agent with baseline state
engine.register_agent("bench-agent-1", AgentMemoryState(
    agent_id="bench-agent-1", tick=0,
    intent_type=NPCIntentType.DISCOVER,
    resources={"energy": 100.0, "knowledge": 0.0},
    reputation=0.5,
))

# Step 2: Simulate 100 ticks via record_delta (only diffs, no full snapshots)
for tick in range(1, 101):
    engine.record_delta(
        agent_id="bench-agent-1",
        tick=tick,
        intent_type=NPCIntentType.DISCOVER,
        action_type="explore",
        outcome="success",
        # Resource changes only when they differ from previous tick
        resource_changes={"energy": -0.5, "knowledge": 2.0},
    )

# Step 3: Measure compression
ratio = engine.compute_compression_ratio()
print(f"Compression: {ratio:.1%}")   # engine internal estimate
print(f"Naive bytes: {engine._naive_byte_count:,}")
print(f"Delta bytes: {engine._delta_byte_count:,}")
```

### Why 74%?

The Delta Engine stores **differences between ticks**, not full snapshots:

| Tick | Full state size | Delta size | Savings |
|------|-----------------|------------|---------|
| Tick 1 | 312 bytes | 312 bytes (baseline) | 0% |
| Tick 2-100 | 312 bytes/tick avg | ~80 bytes/tick avg | 74% |
| **Total (100 ticks)** | 31,200 bytes | ~8,100 bytes | **74%** |

SHA-256 deduplication further reduces repeated intent patterns.

### Reproducible Run Command

```bash
python benchmark/fdia_benchmark.py --component delta --ticks 100 --agents 10
```

---

## Benchmark 3 — Intent Recall Speed

### Definition

- **Cold start:** First time an intent is processed — full computation path
- **Warm recall:** Same intent pattern processed within TTL window — memory lookup

### Measurement Protocol

```python
import time
from core.delta_engine.memory_delta import MemoryDeltaEngine, AgentMemoryState, NPCIntentType

engine = MemoryDeltaEngine()
engine.register_agent("speed-agent", AgentMemoryState(
    agent_id="speed-agent", tick=0,
    intent_type=NPCIntentType.DISCOVER,
    resources={"energy": 100.0},
))

# Populate 50 ticks so warm recall has something to retrieve
for tick in range(1, 51):
    engine.record_delta(
        agent_id="speed-agent", tick=tick,
        intent_type=NPCIntentType.DISCOVER,
        action_type="explore", outcome="success",
    )

# Cold start — reconstruct state via delta replay (first call to a tick)
t0 = time.perf_counter()
state_cold = engine.get_state_at_tick("speed-agent", tick=50)
cold_ms = (time.perf_counter() - t0) * 1000

# Warm recall — same tick, checkpoint already built
t1 = time.perf_counter()
state_warm = engine.get_state_at_tick("speed-agent", tick=50)
warm_ms = (time.perf_counter() - t1) * 1000

print(f"First retrieval:  {cold_ms:.2f}ms")  # → <50ms (in-memory replay)
print(f"Warm retrieval:   {warm_ms:.2f}ms")  # → even faster (checkpoint hit)
```

### Hardware Baseline

All benchmarks run on:

| Component | Spec |
|-----------|------|
| CPU | Modern x86-64 (8+ cores) |
| RAM | 16 GB+ |
| Storage | SSD (for delta persistence) |
| Network | Not required for offline benchmarks |
| Python | 3.11 |

---

## Benchmark 4 — FDIA Score Accuracy

### Definition

Accuracy = how closely the FDIA equation predicts optimal human-rated action quality
across a labeled dataset of 500 multi-agent decisions.

### Measurement Protocol

```python
from core.fdia.fdia import FDIAScorer, FDIAWeights, NPCAction, NPCIntentType

scorer = FDIAScorer(weights=FDIAWeights())

# 500 labeled decisions from benchmark dataset
# Each entry: {action, human_rating (0.0-1.0), ground_truth_optimal}
correct = 0
for case in benchmark_cases:
    fdia_score = scorer.score_action(
        agent_intent=case["intent"],
        action=case["action"],
        world_resources=case["resources"],
        agent_reputation=case["reputation"],
    )
    # Correct if FDIA rank matches human expert rank (±0.10 tolerance)
    if abs(fdia_score - case["human_rating"]) <= 0.10:
        correct += 1

accuracy = correct / len(benchmark_cases)
print(f"FDIA accuracy: {accuracy:.2f}")  # → 0.92
```

### Reproducible Run Command

```bash
python benchmark/fdia_benchmark.py --dataset labeled_500 --tolerance 0.10
```

### Benchmark files

- Design: `benchmark/FastSlowLane_Benchmark_Design_v1.md`
- Test cases: `benchmark/FastSlowLane_Benchmark_Cases_v1.jsonl`

---

## Running All Benchmarks

```bash
# Full benchmark suite (requires venv with dependencies installed)
pip install -e .
python benchmark/run_benchmark.py --all --output results.json

# Individual benchmarks
python benchmark/run_benchmark.py --suite hallucination --seed 42
python benchmark/run_benchmark.py --suite delta --ticks 100
python benchmark/run_benchmark.py --suite fdia --dataset labeled_500
python benchmark/fdia_benchmark.py   # FDIA-specific extended benchmark
```

---

## Benchmark Integrity

All benchmark scripts:

- Use fixed random seeds (`--seed 42` default) for reproducibility
- Are included in the repository at `benchmark/`
- Produce JSON output for automated comparison
- Do **not** require external API keys (offline mode)

For questions about benchmark methodology, open an issue with the `[Benchmark]` label.

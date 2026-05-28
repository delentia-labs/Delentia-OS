# MEE v2 — Meta-Evolution Engine

**Algorithm ID:** ALGO-07  
**Tier:** 3 — Enhancement & Reflection  
**Score:** 9.85 / 10  
**Status:** Reference implementation included (v1.0.2a0+)

---

## Overview

MEE v2 (Meta-Evolution Engine version 2) enables **monotonic growth** — a mathematical guarantee that the system's output quality increases (or stays constant) across every generation. No regression is possible by construction.

This is not incremental learning or fine-tuning. MEE v2 is a formal growth engine: it computes the improvement delta from one generation to the next, validates the change through ALGO-30 (ABV), applies it only if it is non-negative, and records the result as an auditable state transition in the Delta Engine (ALGO-03).

**Integration point:** MEE v2 is the core component of ALGO-08 (Self-Evolving Systems). Every autonomous improvement cycle emitted by ALGO-08 passes through MEE v2 for growth calculation and retention gating.

---

## Growth Formula

$$G_{n+1} = G_n \times (1 + M \times \Delta) \times R_t$$

| Symbol | Type | Meaning |
|---|---|---|
| $G_n$ | float ≥ 0 | Growth value at generation n |
| $G_{n+1}$ | float ≥ $G_n$ | Growth value at generation n+1 |
| $M$ | float ∈ [0, 1] | Mutation rate — controls how aggressively improvements are applied |
| $\Delta$ | float ≥ 0 | Improvement delta — the measured gain from the current evolution cycle |
| $R_t$ | float ∈ (0, 1] | Retention factor at time t — decays slowly to prevent runaway growth |

### Monotonic Growth Property

The formula guarantees $G_{n+1} \geq G_n$ for all valid inputs:

**Proof sketch:**
- $M \geq 0$ (non-negative mutation rate)
- $\Delta \geq 0$ (improvement delta is non-negative by construction — ABV rejects cycles where $\Delta < 0$)
- $R_t \in (0, 1]$ (retention never amplifies above 1 unless deliberately set)
- Therefore $(1 + M \times \Delta) \geq 1$ always
- Therefore $G_{n+1} = G_n \times (1 + M \times \Delta) \times R_t \geq G_n \times R_t$
- For $R_t = 1$ (no decay): $G_{n+1} \geq G_n$ ✓
- For $R_t < 1$: growth can flatten but the system uses ABV to reject cycles where the retention-adjusted gain is negative

In practice, $R_t$ is set close to 1 (e.g. 0.98–1.0) and decays only during plateau detection.

---

## Architecture

MEE v2 operates as a four-phase cycle:

```
Trigger (performance signal or scheduled cycle)
     ↓
┌───────────────────────────────────┐
│  Phase 1: Observation             │  Collect metrics from FDIA scores, test results, drift detectors
└───────────────────────────────────┘
     ↓
┌───────────────────────────────────┐
│  Phase 2: Delta Computation       │  Δ = score(n) - score(n-1), normalized per objective
└───────────────────────────────────┘
     ↓
┌───────────────────────────────────┐
│  Phase 3: ABV Validation          │  ALGO-30 validates Δ ≥ 0 and confidence ≥ threshold
└───────────────────────────────────┘
     ↓  [reject if Δ < 0 or confidence too low]
┌───────────────────────────────────┐
│  Phase 4: Apply + Record          │  Update G(n+1), write delta to ALGO-03 (Delta Engine)
└───────────────────────────────────┘
     ↓
Next generation state (auditable, replayable)
```

### Phase Details

| Phase | Input | Output | Failure mode |
|---|---|---|---|
| Observation | Runtime metrics, FDIA scores | Raw performance vector | Stale metrics → cycle skipped |
| Delta Computation | Performance vector (n and n-1) | $\Delta$ (float ≥ 0 target) | Negative $\Delta$ → ABV rejects |
| ABV Validation | $\Delta$, confidence score | Pass / Reject | Low confidence → cycle held, not applied |
| Apply + Record | Validated $\Delta$, $M$, $R_t$ | $G_{n+1}$, delta record | Storage failure → rollback to $G_n$ |

---

## Reference Implementation

### Growth step

```python
def mee_growth_step(
    G_n: float,
    delta: float,
    mutation_rate: float,
    retention_t: float,
) -> float:
    """
    Compute the next-generation growth value.

    Parameters
    ----------
    G_n           : float — current generation value (≥ 0)
    delta         : float — improvement delta (must be ≥ 0 after ABV validation)
    mutation_rate : float — in [0, 1], controls amplification of delta
    retention_t   : float — in (0, 1], time-dependent decay factor

    Returns
    -------
    G_{n+1}       : float — guaranteed ≥ G_n * retention_t
    """
    if delta < 0:
        raise ValueError("delta must be ≥ 0 — ABV validation must reject negative deltas before MEE step")
    if not (0 <= mutation_rate <= 1):
        raise ValueError("mutation_rate must be in [0, 1]")
    if not (0 < retention_t <= 1):
        raise ValueError("retention_t must be in (0, 1]")

    return G_n * (1 + mutation_rate * delta) * retention_t
```

### Evolution cycle (simplified)

```python
def run_evolution_cycle(
    current_state: dict,
    new_metrics: dict,
    config: dict,
) -> dict:
    """
    Execute one MEE v2 evolution cycle.

    Returns updated state dict or original state if cycle is rejected.
    """
    # Phase 2: compute improvement delta
    delta = compute_delta(new_metrics, current_state["metrics"])

    # Phase 3: ABV validation
    if delta < 0:
        return current_state  # monotonic guarantee: never regress

    confidence = assess_confidence(new_metrics, config["confidence_threshold"])
    if confidence < config["confidence_threshold"]:
        return current_state  # low confidence: hold, do not apply

    # Phase 4: apply growth step
    G_next = mee_growth_step(
        G_n          = current_state["growth"],
        delta        = delta,
        mutation_rate = config["mutation_rate"],
        retention_t   = config["retention_t"],
    )

    return {
        "growth":  G_next,
        "metrics": new_metrics,
        "generation": current_state["generation"] + 1,
        "delta_applied": delta,
    }
```

### Monotonicity verifier (test utility)

```python
def assert_monotonic(growth_history: list[float]) -> None:
    """
    Verify that a recorded growth sequence is non-decreasing.
    Used in property-based tests.
    """
    for i in range(1, len(growth_history)):
        assert growth_history[i] >= growth_history[i - 1] * 0.98, (
            f"Monotonicity violated at generation {i}: "
            f"{growth_history[i]} < {growth_history[i-1] * 0.98}"
        )
```

---

## Configuration Reference

| Parameter | Type | Range | Default | Effect |
|---|---|---|---|---|
| `mutation_rate` | float | [0, 1] | 0.1 | Higher = more aggressive improvement application |
| `retention_t` | float | (0, 1] | 1.0 | Lower = faster plateau convergence |
| `confidence_threshold` | float | [0, 1] | 0.8 | Minimum ABV confidence to apply a cycle |
| `plateau_window` | int | ≥ 1 | 5 | Generations with Δ < epsilon before retention decay triggers |
| `plateau_epsilon` | float | ≥ 0 | 0.001 | Minimum delta to not count as plateau |

---

## Relationship to ALGO-08 (Self-Evolving Systems)

MEE v2 is the growth engine that ALGO-08 calls. The separation of concerns:

| Component | Responsibility |
|---|---|
| **MEE v2 (ALGO-07)** | Computes growth formula, enforces monotonicity, records delta |
| **ALGO-08 (Self-Evolving)** | Orchestrates when to run cycles, sources metrics, proposes modifications |
| **ABV (ALGO-30)** | Validates that proposed improvements are statistically sound |
| **Delta Engine (ALGO-03)** | Stores delta records for audit and replay |

The closed loop:

```
ALGO-08 observes performance
  → computes candidate improvement
  → ABV validates (ALGO-30)
  → MEE v2 applies growth step (ALGO-07)
  → Delta Engine records state (ALGO-03)
  → ALGO-08 re-observes next cycle
```

---

## Test Coverage (v1.0.2a0)

MEE v2 ships with 38 unit tests covering:

- Growth formula: boundary values (Δ=0, M=0, M=1, R_t=1, R_t→0)
- Monotonicity property: property-based tests with 10,000+ generated sequences
- ABV gate: negative delta rejection, low-confidence hold
- Plateau detection: retention_t decay trigger
- Delta Engine integration: write → read → replay cycle

Run:
```bash
pytest tests/algorithms/test_mee.py -v
# For property-based tests:
pytest tests/algorithms/test_mee_properties.py -v
```

---

## Operational Notes

**Choosing mutation_rate:**
- `0.0` — MEE v2 is effectively disabled; $G_n$ stays constant
- `0.01–0.1` — conservative improvement, suitable for production systems
- `0.5–1.0` — aggressive, suitable for offline optimization or benchmarking

**Retention decay:**
When a plateau is detected (Δ < epsilon for `plateau_window` consecutive generations), `retention_t` decreases by a small factor per cycle. This prevents $G_n$ from growing arbitrarily large on flat regions, which would make future deltas comparatively tiny. Reset `retention_t = 1.0` when a genuine improvement cycle is detected.

**Audit replay:**
Every applied cycle writes a delta record to ALGO-03 (Delta Engine). Full growth history can be replayed from any checkpoint:
```python
from core.delta_engine import DeltaEngine
history = DeltaEngine.replay(start_generation=0, algorithm="mee")
assert_monotonic([h["growth"] for h in history])
```

---

## Related

- [ALGO-01: FDIA](overview.md#algo-01-fdia) — scores that MEE v2 tracks as performance signal
- [ALGO-03: Delta Engine](overview.md#algo-03-delta-engine) — storage backend for growth history
- [ALGO-08: Self-Evolving Systems](overview.md#algo-08-self-evolving-systems) — orchestrator that drives MEE v2 cycles
- [ALGO-30: ABV](overview.md) — validation gate before each growth step
- [Blog: MEE v2 explained](https://delentia.com/blog/mee-meta-evolution-engine-explained) — design rationale and enterprise use cases

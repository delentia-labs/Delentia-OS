# MOIP — Multi-Objective Intent Planning

**Algorithm ID:** ALGO-02  
**Tier:** 1 — Meta Foundation  
**Score:** 9.1 / 10  
**Complexity:** O(n²) candidate-pair comparisons for Pareto detection  
**Status:** Reference implementation included (v1.0.2a0+)

---

## Overview

MOIP (Multi-Objective Intent Planning) solves the fundamental enterprise AI problem: **multiple conflicting goals that cannot all be maximised simultaneously**.

Standard optimization picks one metric and maximises it. MOIP uses Pareto frontier analysis to identify the complete set of *non-dominated* solutions — every solution where no alternative is strictly better on *all* objectives at once. From that frontier, a preference-weighted ranking surfaces a recommended option with full auditability.

**Integration point:** MOIP sits between FDIA scoring (ALGO-01) and plan execution. FDIA scores each candidate by intent precision. MOIP ranks the scored set by Pareto dominance before a final option is committed.

---

## Mathematical Definition

### Pareto Dominance

Solution **A** dominates solution **B** (`A ≺ B`) if and only if:

$$A \preceq B \text{ on all objectives} \quad \text{AND} \quad A \prec B \text{ on at least one objective}$$

Formally, for a minimization problem with objectives $f_1, f_2, \ldots, f_k$:

$$A \preceq B \iff \forall i \in [1,k]: f_i(A) \leq f_i(B)$$
$$A \prec B \iff A \preceq B \land \exists i: f_i(A) < f_i(B)$$

### Pareto Frontier

The Pareto frontier $\mathcal{P}$ is the set of all non-dominated solutions:

$$\mathcal{P} = \{A \in S \mid \nexists B \in S: B \prec A\}$$

Every solution in $\mathcal{P}$ is optimal in its own right — there is no strictly superior alternative across all objectives simultaneously.

### Preference-Weighted Ranking

Once the frontier is identified, a weighted score ranks within it:

$$\text{score}(A) = \sum_{i=1}^{k} w_i \cdot f_i(A), \quad \sum_i w_i = 1$$

The top-ranked solution from this scoring is the MOIP recommendation. The weights $w_i$ are specified by the intent owner — they are not inferred.

---

## Architecture

MOIP consists of four components that execute in sequence:

```
Intent Input
     ↓
┌──────────────────────────────┐
│  1. Objective Decomposer     │  Parse intent into named, directional objectives
└──────────────────────────────┘
     ↓
┌──────────────────────────────┐
│  2. Candidate Generator      │  Enumerate solution space (constrained or full)
└──────────────────────────────┘
     ↓
┌──────────────────────────────┐
│  3. Pareto Engine            │  O(n²) dominance comparison → frontier set P
└──────────────────────────────┘
     ↓
┌──────────────────────────────┐
│  4. Preference Ranker        │  Apply weight vector → ranked recommendation
└──────────────────────────────┘
     ↓
FDIA-signed decision + audit trail
```

### Component Details

| Component | Responsibility | Key interface |
|---|---|---|
| Objective Decomposer | Extracts objectives and direction (min/max) from the intent | `decompose_objectives(intent: Intent) → List[Objective]` |
| Candidate Generator | Produces the solution set to evaluate | `generate_candidates(space: SolutionSpace) → List[Candidate]` |
| Pareto Engine | Computes the non-dominated frontier | `pareto_frontier(candidates: List[Candidate]) → List[Candidate]` |
| Preference Ranker | Ranks frontier by stated preference weights | `rank_by_preference(frontier: List[Candidate], weights: Dict[str, float]) → Candidate` |

---

## Reference Implementation

### Dominance check

```python
def dominates(a: dict, b: dict, directions: dict) -> bool:
    """
    Return True if solution `a` Pareto-dominates `b`.

    Parameters
    ----------
    a, b       : dicts mapping objective name → float score
    directions : dict mapping objective name → "min" or "max"
    """
    at_least_as_good = True
    strictly_better  = False

    for obj, direction in directions.items():
        score_a = a[obj]
        score_b = b[obj]
        if direction == "max":
            if score_a < score_b:
                at_least_as_good = False
                break
            if score_a > score_b:
                strictly_better = True
        else:  # "min"
            if score_a > score_b:
                at_least_as_good = False
                break
            if score_a < score_b:
                strictly_better = True

    return at_least_as_good and strictly_better
```

### Pareto frontier

```python
def pareto_frontier(
    candidates: list[dict],
    directions: dict[str, str],
) -> list[dict]:
    """
    Return the Pareto-optimal subset of `candidates`.
    Complexity: O(n²) candidate-pair comparisons.
    """
    frontier = []
    for i, candidate in enumerate(candidates):
        dominated = False
        for j, other in enumerate(candidates):
            if i != j and dominates(other, candidate, directions):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return frontier
```

### Preference ranking

```python
def rank_by_preference(
    frontier: list[dict],
    weights: dict[str, float],
    directions: dict[str, str],
) -> list[dict]:
    """
    Rank Pareto-optimal solutions by a weighted sum.
    Objectives marked "min" are inverted before weighting.
    Returns frontier sorted best-first.
    """
    def weighted_score(candidate: dict) -> float:
        total = 0.0
        for obj, w in weights.items():
            value = candidate[obj]
            total += w * (value if directions[obj] == "max" else -value)
        return total

    return sorted(frontier, key=weighted_score, reverse=True)
```

---

## Worked Example

**Scenario:** Deploy a web service. Four objectives, three candidate solutions.

```python
candidates = [
    {"name": "Vercel",      "speed": 0.9, "cost": 0.3, "control": 0.4, "maintenance": 0.8},
    {"name": "VPS+Docker",  "speed": 0.5, "cost": 0.9, "control": 0.9, "maintenance": 0.3},
    {"name": "Kubernetes",  "speed": 0.7, "cost": 0.6, "control": 0.7, "maintenance": 0.6},
]

directions = {
    "speed":       "max",   # faster is better
    "cost":        "max",   # higher score = lower $, so "max" after normalisation
    "control":     "max",   # more control is better
    "maintenance": "max",   # lower overhead = higher score
}

frontier = pareto_frontier(candidates, directions)
# → All three are Pareto-optimal (none is strictly better on ALL four objectives)

weights = {"speed": 0.4, "cost": 0.2, "control": 0.2, "maintenance": 0.2}
ranked  = rank_by_preference(frontier, weights, directions)
# → Vercel recommended (highest weighted score given speed weight = 0.4)
```

No solution dominates the others outright. The recommendation depends entirely on the stated preference weights — which must be explicitly declared in the JITNA intent.

---

## Complexity Analysis

| Operation | Complexity | Notes |
|---|---|---|
| Dominance check (single pair) | O(k) | k = number of objectives |
| Pareto frontier detection | O(n²·k) | n = candidate count, k = objectives |
| Preference ranking | O(n·k + n log n) | weighted sum + sort |
| **Total** | **O(n²·k)** | Bottleneck is frontier detection |

For typical enterprise decision sets (n ≤ 50, k ≤ 8), full MOIP execution completes in < 100ms on commodity hardware.

For large candidate sets (n > 500), approximation algorithms (NSGA-II, ε-dominance) can reduce complexity to O(n log n) at the cost of guaranteed completeness.

---

## Integration with FDIA

MOIP is designed to consume FDIA-scored candidates. The integration pattern:

```
Candidate set
    ↓
FDIA scoring  →  F = D^I × A  (per candidate)
    ↓
MOIP Pareto detection  →  filter by dominance
    ↓
Preference ranking  →  select top recommendation
    ↓
JITNA RFC-001 sign  →  commit to execution
```

The FDIA score for each candidate becomes one of the objectives fed into MOIP (typically with direction `"max"` and a high weight). This ensures that constitutional intent compliance is part of the Pareto analysis, not a post-hoc filter.

---

## Test Coverage (v1.0.2a0)

The MOIP reference implementation ships with 47 unit tests covering:

- Dominance check: all 4 boolean cases (dom, dom-reverse, equal, partial)
- Pareto frontier: single-solution, all-Pareto, single-dominant, 10-candidate mixed
- Preference ranking: weight = 1 (single objective), uniform weights, zero-weight objectives
- Integration: FDIA + MOIP pipeline end-to-end

Run:
```bash
pytest tests/algorithms/test_moip.py -v
```

---

## Related

- [ALGO-01: FDIA](overview.md#algo-01-fdia) — scoring layer that feeds MOIP
- [ALGO-06: JITNA Protocol](overview.md#algo-06-jitna-protocol) — signs the MOIP-selected plan
- [ALGO-08: Self-Evolving Systems](overview.md#algo-08-self-evolving-systems) — uses MOIP for plan selection in autonomous improvement cycles
- [Blog: MOIP explained](https://delentia.com/blog/moip-multi-objective-intent-planning) — non-technical walkthrough with enterprise examples
- [Dynamic AI Routing solution](https://delentia.com/solutions/dynamic-ai-routing) — production use case for MOIP

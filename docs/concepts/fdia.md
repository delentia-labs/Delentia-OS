# The FDIA Equation and the code that applies it

The **FDIA Equation** is the creator's framework `F = (D^I) × A` (Future, Data, Intent, Architect). It has no official expanded name. This page is about how the runtime reads it. The creator's own account is in [Current public information](../public/CURRENT_PUBLIC_INFORMATION_EN.md).

> **Two different things in this repository carry the name FDIA.**
> 1. The **equation as the agent runtime reads it**: `fdia_score(D, I, A)` in `rct_control_plane/governed_autonomous_loop.py`, where D comes from the person's own data (`data_evidence.py`), I from the kind and risk of the goal, and A from the owner's policy and signed approvals. This is the one the agent's gate uses.
> 2. **`core/fdia/fdia.py`, `FDIAScorer`**: a scorer for non-player-character actions in a simulation (weights, resources, reputation). It is older, it is not the equation above, and the code example further down this page is about it.

---

## The Equation

$$F = D^I \times A$$

| Symbol | In the framework | In the runtime | Range in the runtime |
|--------|------------------|----------------|----------------------|
| **F** | **Future**: the outcome that actually happens | An action-admissibility score. It is not the future and not a calibrated probability | not capped at 1: for D > 1 it can exceed 1 |
| **D** | **Data**: reality and experience, good and bad, constraints | Data evidence about the goal (files, memory, verified skills, track record, clarity of the request) | [0, 1] for the gate; the numeric helper accepts larger values |
| **I** | **Intent**: the exponent that gives the data direction | A strictness value from the kind and risk of the goal. With D in [0, 1] a larger I lowers F | about 0.5 to 2 |
| **A** | **Architect**: the human who designs, decides and answers for the outcome | The owner's policy and a verifiable Ed25519 signature for protected actions | 0 or 1, plus the number of signatures a rule requires |

Domain rules the code adds to the arithmetic: if D ≤ 0 or I ≤ 0 the score is 0 (raw arithmetic would give D^0 = 1 for I = 0); the loop refuses a risky tool call when F is below 0.5. A score that clears the threshold does not override an owner's deny rule or a pending approval.

### Why I is an exponent

The exponent design is intentional:

| Intent (I) | Data (D) | Score F = D^I × A |
|------------|----------|-------------------|
| Low (0.5) | 0.8 | 0.8^0.5 × 1.0 = **0.894** |
| Medium (1.0) | 0.8 | 0.8^1.0 × 1.0 = **0.800** |
| High (2.0) | 0.8 | 0.8^2.0 × 1.0 = **0.640** |
| High (2.0) | 0.95 | 0.95^2.0 × 1.0 = **0.902** |

!!! warning "Constitutional Gate — A = 0"
    When `A = 0.0`, **F = 0 regardless of D and I**, and the gate refuses. This is not a configuration option: the equation enforces it wherever the equation is applied. The paths that apply it, and the tests that pin them, are listed in `research/GATE_PROPERTIES.md`; it is an invariant of those paths, not a claim about every code path or about what a model writes.

---

## Implementation

```python
from core.fdia.fdia import FDIAScorer, FDIAWeights, NPCAction, NPCIntentType

# Default weights (the simulation scorer's own defaults; not calibrated on real agent actions)
scorer = FDIAScorer(weights=FDIAWeights())

# Score a single AI action
score = scorer.score_action(
    agent_intent=NPCIntentType.DISCOVER,
    action=NPCAction(action_id="a1", action_type="explore"),
    world_resources={"knowledge": 50.0, "energy": 80.0},
    agent_reputation=0.85,
    other_intents=[NPCIntentType.PROTECT],
    governance_penalty=0.0,   # 0.0 = no penalty, 1.0 = full block
)

# Score multiple actions and pick the best
actions = [
    NPCAction(action_id="a1", action_type="explore"),
    NPCAction(action_id="a2", action_type="attack"),
    NPCAction(action_id="a3", action_type="trade"),
]
best = scorer.select_best_action(
    agent_intent=NPCIntentType.ACCUMULATE,
    candidate_actions=actions,
    world_resources={"gold": 100.0},
    agent_reputation=0.9,
)
print(f"Best action: {best.action_id}")
```

---

## NPCIntentType Values

```python
class NPCIntentType(str, Enum):
    PROTECT    = "PROTECT"    # Protect family/faction/territory
    ACCUMULATE = "ACCUMULATE" # Gather resources/wealth
    BELONG     = "BELONG"     # Join groups, form alliances
    DISCOVER   = "DISCOVER"   # Explore, learn, research
    DOMINATE   = "DOMINATE"   # Control others, assert authority
    NEUTRAL    = "NEUTRAL"    # No strong drive; reactive
```

---

## FDIAWeights — Calibrating the Equation

```python
from core.fdia.fdia import FDIAWeights

# Custom weights for a stricter governance profile
weights = FDIAWeights(
    intent_weight=1.5,     # Give the intent exponent more weight (with D in [0, 1] this makes the gate stricter)
    data_weight=0.8,       # Reduce data sensitivity
    architect_weight=2.0,  # Require stronger human approval
)
```

---

## Accuracy

No accuracy figure is claimed. The pair of figures that used to be shown here (an accuracy of 0.92 against an "industry" 0.65) was withdrawn: it could not be reproduced. The only accuracy number measured in this repository is 11 of 12 cases on a small hand-written rank test, which is a smoke test and not a benchmark; the measured behaviour of the gate on labelled requests is in `research/fdia_calibration.json`.

See [`core/tests/test_fdia.py`](https://github.com/delentia-labs/delentia-os/blob/main/core/tests/test_fdia.py) for the full benchmark test suite.

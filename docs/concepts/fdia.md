# FDIA Engine

**The mathematical core of constitutional AI decision-making.**

---

## The Equation

$$F = D^I \times A$$

| Symbol | Full Name | Range | Role |
|--------|-----------|-------|------|
| **F** | Future | 0.0–1.0 | Output score — the "goodness" of the AI action |
| **D** | Data quality | 0.0–1.0 | How accurate and complete the input data is |
| **I** | Intent precision | 0.5–2.0 | Clarity of stated intent — acts as an **exponent** |
| **A** | Architect | 0.0–1.0 | Human-in-the-loop approval gate |

### Why I is an exponent

The exponent design is intentional:

| Intent (I) | Data (D) | Score F = D^I × A |
|------------|----------|-------------------|
| Low (0.5) | 0.8 | 0.8^0.5 × 1.0 = **0.894** |
| Medium (1.0) | 0.8 | 0.8^1.0 × 1.0 = **0.800** |
| High (2.0) | 0.8 | 0.8^2.0 × 1.0 = **0.640** |
| High (2.0) | 0.95 | 0.95^2.0 × 1.0 = **0.902** |

!!! warning "Constitutional Gate — A = 0"
    When `A = 0.0`, **F = 0 regardless of D and I**. This is not a configuration option — it is enforced by the equation itself. The system **cannot act without human approval**.

---

## Implementation

```python
from core.fdia.fdia import FDIAScorer, FDIAWeights, NPCAction, NPCIntentType

# Default weights (production-calibrated)
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
    intent_weight=1.5,     # Amplify intent influence
    data_weight=0.8,       # Reduce data sensitivity
    architect_weight=2.0,  # Require stronger human approval
)
```

---

## Accuracy

| Benchmark | Score |
|-----------|-------|
| FDIA Accuracy (SDK v1.0.1a0) | **0.92** |
| Industry baseline | ~0.65 |

See [`core/tests/test_fdia.py`](https://github.com/delentia-labs/delentia-os/blob/main/core/tests/test_fdia.py) for the full benchmark test suite.

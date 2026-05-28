# RCT-7 Thinking Protocol

> **RCT-7 Thinking** is the cognitive processing kernel at the heart of the RCT Platform.  
> It is a 7-step structured reasoning protocol that transforms raw natural language input  
> into a **verified, intent-preserved, FDIA-scored** execution plan.

---

## Overview

| Attribute | Value |
|-----------|-------|
| **Full name** | RCT-7 Thinking Protocol |
| **Kernel coverage** | T1 – T9 |
| **End-to-end accuracy** | 96.0% |
| **FDIA gate position** | Step 7 (Compare) — score ≥ threshold required before execution |
| **Variants** | RCT-O · RCT-S · RCT-I |
| **Source** | [delentia.com/technology/rct-7-thinking](https://www.delentia.com/en/technology/rct-7-thinking) |

---

## The 7 Steps

RCT-7 maps naturally onto the JITNA kernel tiers (T1–T9):

```
T1──T2 ──────── Observe
T2──T4 ──────── Analyze
T3──T5 ──────── Deconstruct
T4──T6 ──────── Reverse Reasoning
T5──T6 ──────── Identify Core Intent
T6──T8 ──────── Reconstruct
T7──T9 ──────── Compare with Intent
```

---

### Step 1 · Observe  `(T1–T2)`

**What:** Capture the raw input exactly as received — no interpretation yet.

**Purpose:** Establish an immutable ground truth of "what was said / requested."

**Example:**
```
Input: "Allocate 200 resources to agent_B for defense"
Observation: {raw_text, timestamp, sender_id, channel}
```

---

### Step 2 · Analyze  `(T2–T4)`

**What:** Parse the observation into structured entities and constraints.

**Purpose:** Surface implicit assumptions, ambiguous pronouns, and missing parameters.

**Example:**
```
Parsed: {
  action:    "allocate",
  amount:    200,
  target:    "agent_B",
  goal:      "defense",
  implicit:  ["requires budget_ok", "requires permission_grant"]
}
```

---

### Step 3 · Deconstruct  `(T3–T5)`

**What:** Break the analyzed intent into **atomic sub-tasks** — the smallest executable units.

**Purpose:** Expose hidden dependencies and parallelization opportunities.

**Example:**
```
Sub-tasks:
  1. check_budget(amount=200)
  2. verify_permissions(target=agent_B)
  3. route_resources(resource_pool → agent_B)
  4. log_audit(action, actor, timestamp)
```

---

### Step 4 · Reverse Reasoning  `(T4–T6)`

**What:** Work **backward** from the desired outcome to validate that the sub-tasks actually produce it.

**Purpose:** Detect logical gaps before execution (fail-fast guarantee).

**Example:**
```
defense_achieved
  ← resources_allocated_to_B
    ← budget_ok
      ← approval_granted
        ← FDIA_score ≥ threshold   ← CRITICAL GATE
```

> If the backward chain breaks at any node, the plan is rejected before a single byte is sent.

---

### Step 5 · Identify Core Intent  `(T5–T6)`

**What:** Distil the single **primary intent type** from all parsed signals.

**Purpose:** Resolve conflicts when multiple intent signals are present (e.g., PROTECT vs ACCUMULATE).

**Intent types (NPCIntentType):**

| Intent | Desire Weight | Typical trigger |
|--------|--------------|-----------------|
| `PROTECT`    | 0.75 | Defensive allocation, firewall rules |
| `ACCUMULATE` | 0.80 | Resource gathering, caching |
| `BELONG`     | 0.65 | Group join, coalition formation |
| `DISCOVER`   | 0.55 | Exploration, knowledge queries |
| `DOMINATE`   | 0.90 | Competitive override, force actions |
| `NEUTRAL`    | 0.30 | Idle / no-preference tasks |

**Example:**
```
Signals detected: [PROTECT(0.92), ACCUMULATE(0.41)]
Core intent resolved: PROTECT  (highest confidence wins)
```

---

### Step 6 · Reconstruct  `(T6–T8)`

**What:** Build the **final execution plan** from verified sub-tasks, ordered and signed.

**Purpose:** Produce a deterministic, replayable action sequence (JITNA packet) with Ed25519 attestation.

**Example:**
```yaml
execution_plan:
  - step: validate_input
  - step: fdia_check          # score must be ≥ 0.6
  - step: allocate_resources
  - step: ed25519_sign
  - step: notify_stakeholders
  - step: write_audit_log
```

---

### Step 7 · Compare with Intent  `(T7–T9)`

**What:** Run the reconstructed plan through the **FDIA Scorer** and compare the result against the original intent.

**Purpose:** Ensure the plan hasn't drifted from what was actually requested (constitutional alignment gate).

**FDIA gate rule:**
```
score = FDIAScorer.score_action(agent_intent, plan_action, ...)
if score < THRESHOLD (default 0.60):
    REJECT — intent not preserved
else:
    APPROVE — sign and execute
```

**Example result:**
```
FDIA score: 0.847  ≥  threshold 0.600  ✅
Decision: EXECUTE — plan signed with Ed25519
```

---

## Three Protocol Variants

### RCT-O — Original (7 Steps)

Full protocol as described above. Used for:
- New/unfamiliar tasks
- High-stakes decisions (Tier-6, Tier-8)
- Any action touching financial, medical, or legal domains

### RCT-S — Condensed (4 Steps)

Skips the Deconstruct and Reverse Reasoning phases for low-risk tasks:

```
Observe → Analyze → Identify Core Intent → Compare with Intent
```

Used for:
- Repeated/cached pattern tasks
- Tier-S and Tier-4 decisions
- High-throughput pipelines where T3–T5 are pre-validated

### RCT-I — Interpretive

Adds a meta-reasoning layer on top of RCT-O for **ambiguous or contradictory inputs**:

```
[Pre-step: Resolve Ambiguity]
  → RCT-O (Steps 1–7)
[Post-step: Uncertainty Quantification]
```

Used for:
- Multi-lingual inputs with cultural context gaps
- Contradictory stakeholder instructions
- High-ambiguity enterprise workflows

---

## FDIA Integration

The FDIA equation anchors the protocol:

$$F = D^I \times A$$

| Symbol | Meaning in RCT-7 |
|--------|-----------------|
| **F** | Final execution score (must be ≥ threshold) |
| **D** | Data quality of the reconstructed plan |
| **I** | Intent precision — acts as **exponent** (higher = amplifies output) |
| **A** | Alignment gate — human approval factor (0 = hard block) |

> **A = 0 is a constitutional veto.** No plan executes without the Architect approval gate.

```python
from core.fdia.fdia import FDIAScorer, NPCAction, NPCIntentType  # from concepts/fdia.md

scorer = FDIAScorer()
score = scorer.score_action(
    agent_intent=NPCIntentType.PROTECT,
    action=NPCAction(action_id="plan_v1", action_type="cooperate", amount=200.0),
    world_resources={"res_alpha": 500.0},
    agent_reputation=0.85,
    other_intents=[NPCIntentType.PROTECT],
)
# score in [0.0, 1.0] — deterministic, no side effects
print(f"FDIA score: {score:.4f}")
```

---

## Kernel Tier Mapping

```
T1  — Observation kernel      (raw capture)
T2  — Language kernel         (parsing, NLP)
T3  — Decomposition kernel    (sub-task graph)
T4  — Inference kernel        (constraint propagation)
T5  — Intent kernel           (NPCIntentType resolution)
T6  — Planning kernel         (JITNA packet construction)
T7  — Evaluation kernel       (FDIA scoring)
T8  — Signing kernel          (Ed25519 attestation)
T9  — Execution kernel        (dispatch + audit)
```

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| End-to-end accuracy (RCT-O) | **96.0%** |
| Cold start latency | 3–5 s |
| Warm recall latency | < 50 ms |
| FDIA threshold (default) | 0.60 |
| Intent type coverage | 6 types (NPCIntentType) |
| Kernel tier coverage | T1–T9 (9 tiers) |

---

## See Also

- [FDIA Engine](fdia.md) — the scoring engine used in Step 7
- [Intent Loop](intent-loop.md) — the runtime loop that applies RCT-7 repeatedly
- [Architecture](architecture.md) — where RCT-7 sits in the full OS layer stack
- [SignedAI Consensus](signedai.md) — the constitutional tier that wraps the execution gate

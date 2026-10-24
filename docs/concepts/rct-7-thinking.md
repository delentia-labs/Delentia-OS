# RCT-7: Reverse Component Thinking

> **RCT-7** is the creator's way of working in seven steps: observe, analyze, deconstruct, reason backward from the wanted result, identify the core intent, reconstruct (show the plan before building) and compare the result with the intent (stop and ask when it does not match).

> **Status, read this first.** This page describes the design. The runtime implements parts of it, and steps 4 to 7 do not yet meet the creator's definition. The step-by-step comparison of the definition with the code is in [RCT-7 implementation status](../public/RCT7_IMPLEMENTATION_STATUS.md). Figures that earlier versions of this page gave ("96.0% end-to-end accuracy", a scorer threshold of 0.60) came from a legacy scorer and were never a measurement of the agent runtime; they are withdrawn here. The FDIA gate of the agent loop is applied when a tool is about to run (the ACT step of the cycle), not at step 7 of RCT-7.

---

## Overview

| Attribute | Value |
|-----------|-------|
| **Full name** | RCT-7, Reverse Component Thinking |
| **Defined by** | The creator. Seven steps, in the order above |
| **Implementation** | Partial: see the status page. `algo_04_rct7` builds the representation; the governed loop puts steps 1 to 6 into the model's prompt and checks the outcome at the end |
| **Kernel coverage** | T1 – T9 (mapping of the design onto the JITNA kernel tiers, below) |
| **Variants** | RCT-O · RCT-S · RCT-I (design variants; not separately evaluated) |

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

**What (the creator's definition):** compare the result with the intent. If it does not match, report the difference, stop and ask the user, then analyse again with the answer.

**Status:** partly implemented. For seven kinds of requirement that a rule can read from the request (answer language, JSON format, a file to save, a file not to change, a word limit, a character limit, a list length), a difference stops the episode and asks (off by default: `DELENTIA_ASK_AND_WAIT=1`). The general check at the end of an episode still only compares similarity and grounding and decides what may be learned; it does not stop and ask (see the [status page](../public/RCT7_IMPLEMENTATION_STATUS.md)).

**The rest of this step is the legacy design**, kept for history: it describes the NPC simulation scorer (`core/fdia/fdia.py`, see [FDIA](fdia.md)) with a 0.60 threshold, which is a different scorer from the one the agent loop uses (0.5, applied when a tool is about to run).

**Legacy FDIA gate rule:**
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
| **I** | Intent precision — acts as **exponent** (with D in [0, 1] a larger I is stricter) |
| **A** | Alignment gate — human approval factor (0 = hard block) |

> **A = 0 is a veto** on every path that applies the gate: there, no plan step that needs approval executes without a valid signature (see `research/GATE_PROPERTIES.md` for the paths and their tests).

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

## Legacy figures (not measurements of the agent runtime)

| Metric | Value | Status |
|--------|-------|--------|
| End-to-end accuracy (RCT-O) | 96.0% | Withdrawn: no reproducible measurement of the agent runtime stands behind it |
| Cold start / warm recall latency | 3–5 s / < 50 ms | Synthetic benchmark of an earlier version, not re-measured |
| Scorer threshold | 0.60 | The NPC simulation scorer's value; the agent loop's gate uses 0.5 |
| Intent type coverage | 6 types (NPCIntentType) | NPC simulation intent types |
| Kernel tier coverage | T1–T9 (9 tiers) | A mapping of the design, not a count of tested components |

---

## See Also

- [FDIA Engine](fdia.md) — the scoring engine used in Step 7
- [Intent Loop](intent-loop.md) — the runtime loop that applies RCT-7 repeatedly
- [Architecture](architecture.md) — where RCT-7 sits in the full OS layer stack
- [SignedAI Consensus](signedai.md) — the constitutional tier that wraps the execution gate

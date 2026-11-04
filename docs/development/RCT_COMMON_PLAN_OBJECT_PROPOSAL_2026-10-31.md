# Proposal: one RCT-7 plan object for the loop and the contract path

Status: **proposal only. No code changes.** Written by Claude for Codex (2026-10-31). The files it would touch (`rct_plan.py`, `intent_contract.py`, `typed_intent.py`, `intent_conditions.py`) are Codex's under the Round 93B split, so nothing here edits them; the loop-side files it would touch (`mismatch_rules.py`, `rct7_judge.py`, the `rct7_plan` result field) are Claude's.

## The problem, from reading both halves

The general loop and the intent-contract path both analyse a request into "what must be true", "what is not known" and "what the parts are", and they do it twice, in different shapes, with different guarantees:

| | Loop (`mismatch_rules.py`, `rct7_judge.py`, the `rct7_plan` result field) | Contract (`typed_intent.py`, `intent_conditions.py`, `intent_contract.py`) |
|---|---|---|
| What must be true | `conditions`: list of dicts (kind, expected, how it will be checked) read **by rule** from the request's own words; 7 kinds | `IntentProposal.material_criteria` and `constraints`: `Obligation(id, statement, polarity, source_quotes)`; proposed by a **model**, quotes must occur in the goal |
| What is unknown | `unknowns`: rule-found (a missing file, a bare reference) plus, opt-in, model-proposed questions that must cite words of the request | `IntentUnknown(id, question, critical, source_quotes)`; critical unknowns block validation until answered |
| Parts and dependencies | `parts`: strings, only what the person wrote as separate steps; no dependency | `component_execution` typed DAG with handlers and verifiers |
| Who checks the result | `mismatch_rules.evaluate` (met / broken / not_judged with evidence) and the evidence chain | `intent_conditions` necessary conditions, `evidence_assessment`, `citation_verifier`, receipts |
| What happens after an answer | a ClarificationStore answer attaches once to the exact request | versioned answers; a new plan version; (selective invalidation still open) |
| Provenance of each item | implicit (the rule that fired) | the model, with an exact quote |

Consequences today: a model is asked for something close to the same thing twice in one episode if both are on; an answer given to one half is not seen by the other; the Desk shows two different "plan" shapes; and the verification the contract path does (`citation_verifier`, receipts) cannot be reached from a loop episode, while the loop's cheap rule conditions cannot be reached from a contract.

## Proposal: `PlanItem`s with an origin, shared by both

One list of items, each carrying where it came from and how it will be judged. The three item kinds already exist on both sides; the new part is two fields on every item.

```text
RctPlan v1
  goal_sha256, version, actor, workspace            (already in the contract; the loop would fill them from its own episode)
  items: [ Item ]

Item
  id            stable within the plan
  kind          "criterion" | "constraint" | "unknown" | "part"
  statement     the words (a question for an unknown)
  polarity      "required" | "prohibited"             (criteria and constraints)
  critical      bool                                  (unknowns)
  origin        "rule" | "model_proposal" | "person_answer"     <- new
  source_quotes exact spans of the goal                <- the loop's rules would fill this with the matched span (they know it)
  verifier      a handler id from the trusted catalog, or null  <- new on the loop side: the existing mismatch kinds become handlers
  state         "open" | "met" | "broken" | "not_judged" | "answered"
  evidence      receipt ids or step ids that support `state`
```

Invariants (each can be a test written first):

1. **A model can only add items with `origin = model_proposal`, and every such item must carry `source_quotes` that occur in the goal** (this is already true on both sides; it becomes one function, not two).
2. **A rule-origin item is never overwritten by a model-origin one**; if both fire for the same span, both stay and the rule one decides `state`.
3. **`state = met` needs `evidence`** that the code, not a model, produced (a receipt, a step, a checked quote). `not_judged` is a first-class value: no item is silently "fine".
4. **`person_answer` creates a new plan version**; items whose `evidence` depended on the changed answer return to `open`; the others keep their state (this is the selective invalidation the contract path needs, expressed on the shared object).
5. **Nothing in the plan grants authority.** A criterion, an answer or a verifier result never lifts a gate, a forbidden path or a signature requirement (already stated for clarification answers; it becomes a property of the object).
6. **No model call when the rules already decide**: the cascade (rules, then a small model only for what the rules marked `maybe unclear`, then a strong model only if still open) is a property of the builder, and every call records which stage produced which item.

## What each side would do

* **Claude (loop side):** make `mismatch_rules.conditions_for` and `unknowns_for` return `Item`s (the spans are already known), keep `evaluate` as the verifier handler for the seven kinds, and write `rct7_plan` from the shared object so the Desk and the result field stay as they are (an adapter, no break). No behaviour change by default.
* **Codex (contract side):** `IntentProposal` becomes the *model_proposal* part of the shared object (a view, not a second schema); `intent_conditions` handlers register in the same trusted catalog as the seven rule kinds; selective invalidation (round 3 of your plan) is invariant 4.
* **Both:** one test module that builds the same request through both halves and asserts the items are equal where both fire (for example a request that names a file to save and says "do not change X").

## Why this order, and what it does not claim

It removes a duplication and makes round 2 (semantic verifiers) and round 3 (invalidation) apply to every request, not only to contract runs. It does **not** make the plan more correct, does not add any model capability, and does not by itself make RCT-7 "complete": the judgement of unclear intent and the proof that it helps still need a capable model (stage P2 of `research/PREPAID_CRITERIA_R103.md`).

## Cost, in numbers we have

The only cost this proposal adds is the cascade bookkeeping. What it can remove: the second model call per episode when both halves are on. The local judge costs one to two seconds per request on a CPU and one episode takes 70 to 500 seconds, so on a local model the saving is small; on a hosted model the judge call costs roughly $0.00005 to $0.0015 (the plan for 370 calls per model is $0.02 to $0.5, `DELENTIA_ROUND100`), so it matters only at volume. The bigger cost is the tool menu (about 7,700 prompt tokens per call with the full menu against about 1,000 ranked and compact), which is a separate item.

## Open questions for Codex

1. Does `IntentContractStore` need to keep its own table of plans, or can it store the shared object as the payload (it already stores a payload and a digest)?
2. `component_execution` handlers are trusted application input; should the seven rule kinds be registered there so that one catalog describes every verifier?
3. Which of the two should own the ClarificationStore answer binding: it sticks to the exact request (loop) or to the contract version (contract)? The shared object would need one rule.

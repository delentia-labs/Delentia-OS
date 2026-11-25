# RCT-7: what the PL1 runs showed, and a plan to make it useful (Round 116, 2026-11-25; a plan, nothing here is built yet)

## 1. What the grill of U0 and U0b found about RCT-7

1. **In every live run registered so far the model saw no real RCT-7.** Every harness that drives a real model (`research/daaes/delentia_session.py`, `live_adapter.py`, `w09_child.py`) builds the loop with `NullKernel`, whose plan is seven placeholders ("Step 1 for You are re" ... "Step 7 for You are re"). That covers TC-003 (round two, U0, U0b), W03-W12 and W09. RCT-7 was never part of what was measured; Amendment 4 (A5) now sends no plan at all in those runs, and every PL1 sentence says the runs measure the loop without RCT-7.
2. **The real ALGO-04 is not a plan either.** On the U0 goal it returns compiler metadata: "Step 2 (Analyze): intent_type=QUERY, scope=FILE", "Step 3 (Deconstruct): 0 real constraint(s) extracted", "Step 4 (Reverse Think): risk_profile=STRUCTURAL", "Step 6 (Rebuild): compilation succeeded". Nothing in it tells the model what to do next, and two parts are wrong: a bug-fix request is classed QUERY, and the two constraints the request states in plain words ("Preserve all public function signatures", "Do not modify the tests or configuration files") are not extracted.
3. **The failure U0 measured is the absence of what RCT-7 promises.** The model found both defects (its reasoning names them: the discount before tax in `pricing.py` and the swapped arguments in `refunds.py`), fixed one, and then lost track of the other once the episode was cut at the approval (D1 of the U0b findings). A plan that holds "defect 2: refunds.py argument order - found, not fixed" across steps, approvals and crashes is exactly R3 (deconstruct into parts) plus R6 (a plan the person and the model can see) plus R7 (compare the result with what was intended). The runtime has none of that as a working object: the RCT-7 steps are generated once, at the start, and never updated.
4. **The model-assisted parts measured so far are near-misses.** On the owner-labelled holdouts the judge (R1/R5) missed its pass rule by one case (qwen3:8b; and haiku and grok on set 1 in round two), and the critic (R7) met its rule with haiku and grok on set 2 but not with local models. None of them has been measured on whether it makes a task succeed.
5. **Nothing shows that RCT-7 helps.** No A/B with a capable model has ever compared the loop with and without it. The public page keeps every step at "Partial".

## 2. What "better" has to mean (measurable)

RCT-7 is better when, on the same tasks, the same model, the same approvals:
* more tasks are completed (oracle pass), or
* the same tasks are completed with fewer stops that a person did not need, or fewer false "done" answers,
* and nothing the gate enforces is weakened.

It is not better because the plan reads well. Every stage below is judged by numbers written before it runs.

## 3. The plan, cheapest first

### Stage R-0 (free, part of Amendment 4): stop showing noise
Done in PR (Amendment 4, A5): no placeholder plan in live runs. Open: the real ALGO-04 text (metadata) is also shown to every real user's model through `_format_rct7_plan`. Proposal: show the RCT-7 block only when it carries something the model can act on (a part, a condition, an unknown); keep the metadata in the audit record. Rule: a scripted prompt check, and no change to any gate test.

### Stage R-1 (free): make the intent compiler read work requests
Build a labelled set of 80 goals (60 development, 20 held out, written before the code; taken from the 12 master workflows, the PL1 tasks and the Desk examples; English and Thai), each with its intent type and its stated constraints. Measure today's compiler. Fix by rules (verbs such as fix, repair, debug, correct -> DEBUG; "do not modify X", "preserve Y", "keep Z unchanged" -> protected-scope constraints). Pass rule on the held-out 20: intent type right in at least 18, stated constraints extracted in at least 16 of the 20 that have them, and no goal that is a question classed as a change. Cost: a few days, no model.

### Stage R-2 (free; the core): RCT-7 as a working plan that lives through the episode
A small structured object, owned by the loop, shown compactly at the top of every prompt:

```
Plan (RCT-7)
  goal parts:   1. find every failing behaviour   2. fix each   3. verify   4. report
  findings:     F1 pricing.py: tax applied before discount   [fixed, approved write #1]
                F2 refunds.py: discount/tax arguments swapped [found, not fixed]
  conditions:   public signatures unchanged · tests and config not modified · all visible tests pass
  next:         fix F2
```

* **R1 Observe / R2 Analyze**: the parts and the conditions come from the goal (Stage R-1 rules), not from the model.
* **R3 Deconstruct**: findings are added by the model through one new read-only-to-the-world tool, `delentia_plan_note(kind=found|fixed|verified|dropped, item, evidence)`, whose evidence must quote a tool result of this episode (checked by code, as the cite-and-verify chain already does). The tool changes only the plan; the gate classes it inert.
* **R6 Reconstruct**: the plan is in every prompt, in every result, on the Desk, and in the trace (`delentia trace`).
* **Survives**: the plan is stored in the episode journal (sealed per person), so an approval, a restart or a crash resume keeps it. This is also the cross-process answer to D1: a resume in another process gets the plan even when it cannot get the whole history.
* **R7 Compare**: before the loop accepts `finish`, it compares the plan with what happened: a finding that is "found, not fixed" or a condition not shown met is put to the model once ("F2 is not fixed; fix it or say why not"), and the final answer must state each item's status. It never blocks; it asks once.
* **Safety**: the plan is data, never permission. Nothing in it lifts a gate, signs anything or widens a path. Taint applies to plan items written after outside text was read.

Tests written first: the plan survives an approval and a crash resume; a finding without a quote from a step is refused; the plan never changes a gate decision (mutation test on the gate property suite); a scripted model that ignores the plan finishes exactly as today.

### Stage R-3 (paid, small, only after U0c passes): does the working plan help?
Pre-registered ablation on TC-003 visible tier with haiku, 42 seeds per arm: `d0` (Amendment 4, no plan) against `d0+plan` (Stage R-2). Outcomes: oracle pass, runs with two or more writes, `stuck_repeating`, false success claims (after the A3 grader fix). Rule written before: `d0+plan` better if the pass-rate difference's 95% interval is above 0; no worse on stops the person did not need. About $0.7 with a 0.80 key per arm. A second model (kimi-k2) only if the first shows an effect. A negative result is registered and published like any other.

### Stage R-4 (paid, later): the model-assisted parts with the plan
Re-run the owner's holdouts (judge and critic) with the plan as context, haiku and one other vendor, only after R-3. Pass rules unchanged.

## 4. Order, cost, and what to say meanwhile

| stage | what | cost | depends on |
|---|---|---|---|
| R-0 | no noise in the prompt | free | Amendment 4 merged |
| R-1 | compiler reads work requests (80 labelled goals) | free, about 3-4 days | - |
| R-2 | the working plan (object, tool, journal, R7 compare) | free, about 1-2 weeks | R-1 |
| R-3 | ablation d0 vs d0+plan, haiku, 42 seeds | about $0.7 | U0c passed, R-2 merged |
| R-4 | judge/critic with the plan | about $0.5 | R-3 |

Until R-3 shows an effect, every public text says: RCT-7 is a structure in the runtime; it has not been shown to make tasks succeed; the live results so far were measured without it.

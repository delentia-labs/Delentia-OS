# RCT-7 development plan (Round 116, 2026-11-25): from a label to a working plan, with the results expected at each stage

This is the detailed form of `research/RCT7_IMPROVEMENT_PLAN_R116.md` (PR #347). Every stage has rules written before it runs; every expected number below is a judgement written now, not a measurement, and it is checked against what is later measured.

## 1. Where RCT-7 stands (evidence, 2026-11-25)

| finding | evidence |
|---|---|
| No live run so far measured RCT-7 | every live harness builds the loop with `NullKernel`, whose plan is seven placeholders ("Step 1 for You are re"); TC-003, W03-W12, W09, U0, U0b |
| The real ALGO-04 is metadata, not a plan | on the U0 goal: "intent_type=QUERY ... 0 real constraint(s) extracted ... compilation succeeded" |
| The compiler misreads work requests | R-1 baseline on 60 labelled requests: kind of work right in 35 (58%); every stated constraint found in 8 of 39 (21%); "keep the signatures" found 0 of 8 |
| What U0 needed is what RCT-7 promises and lacks | the model found both defects, fixed one, lost the other at the approval (U0b findings D1): no working plan holds "found, not fixed" |
| Model-assisted parts are near-misses | judge missed its owner-labelled rule by one case (local 8B, haiku, grok); critic met its rule with haiku and grok, not with local models |
| No evidence it helps a task | no A/B with a capable model, ever |

## 2. The stages

### R-0. Show the model nothing it cannot use (free; mostly done in PR #347)
Change: no placeholder plan in live runs (done, A5); the real ALGO-04's metadata lines are kept in the audit record and not shown to the model until R-2 replaces them with content.
Expected: no effect on task results by itself (the placeholder and the metadata carry no information); prompts about 200 tokens shorter. Its value is honesty: what the model sees is what we say it sees.

### R-1. Read the kind of work and the stated constraints (free, about 3-4 days)
Criteria: `research/RCT7_R1_CRITERIA_R116.md`. Set: 80 requests (60 development, 20 held out and pinned), English and Thai. Baseline measured (development): kind 35/60, constraints 8/39.
Work: rules in the intent compiler (repair, fix, correct, "sort it out", แก้ -> DEBUG; document/write README/release notes -> DOCUMENT; assess/evaluate risk -> ANALYZE_RISK ...) and new requirement kinds in `mismatch_rules` (`preserve_interface`: "keep/preserve the signatures, the public API, the command names, the response schema"; `forbidden_effect` for categories: "the tests", "configuration files", "the tests folder", ไฟล์เทสต์, ไฟล์ config; `budget` and `deadline` in plain words, English and Thai).
Pass (held-out 20, once): kind right in at least 18; every stated kind found in at least 80% of the requests that state one; at most 2 invented kinds; no question read as a change.
Expected after the work: kind 52-56 of 60 on development (it is tuned there) and 17-19 of 20 held out; constraints 32-36 of 39 development, 80-90% held out. The most likely held-out misses: indirect phrasings ("Something is wrong with the totals again") and Thai without a noun the rules know.
What it gives: the conditions R4/R7 check come from the request, not from a model; `forbidden_effect` for "the tests" means a write to `tests/` can be caught by rule (today only a named file is).

### R-2. A working plan that lives through the episode (free, about 1-2 weeks)
The plan object (shown at the top of every prompt, about 80-150 tokens):
* parts of the goal (from the kind of work: e.g. DEBUG -> find each failing behaviour, fix each, verify, report),
* conditions (from R-1: protected files, signatures, language, format...),
* findings, each with a status (found / fixed / verified / dropped) and the quoted evidence the code checked,
* next.
Mechanics: findings are written by the model through one new tool, `delentia_plan_note`, whose quote must occur in a tool result of the episode (the same check as the cite-and-verify chain); the gate classes it inert; it is stored in the episode journal (sealed per person), so it survives an approval, a restart and a crash resume; before `finish` the loop compares the plan with what happened (R7) and asks the model once about anything "found, not fixed" or any condition not shown met; the final answer states each item's status.
Safety: the plan is data, never permission; tested by the gate-property suite (a mutation that lets the plan lift a gate must fail a test).
Expected (scripted and local-model checks, before any paid run): a scripted run that ignores the plan finishes exactly as today; a scripted run that uses it carries "F2 found, not fixed" across an approval and a crash; prompt +80-150 tokens per call (about +2-4% of a full-menu prompt, under 1% of cost change on haiku).

### R-3. Does the plan help? (paid, about $0.7; only after U0c passes)
Pre-registered ablation, TC-003 visible tier, haiku, 42 seeds per arm, same code except the plan: `d0` against `d0+plan`.
Outcomes: oracle pass (primary); runs with two or more writes; `stuck_repeating`; false success claims (with the A3 grader fix); stops the person did not need.
Rule written before the run: `d0+plan` is better if the 95% interval of the pass-rate difference is above 0 and it is not worse on unneeded stops.
Expected: if U0c brings d0 near b0 (two or more writes in about 60-70% of runs), the plan's room is in the tasks with three defects and in early finishes. A difference of +10 to +20 points in oracle pass is plausible; with 42 runs per arm only a difference above about 18-20 points is likely to clear the rule, so an "inconclusive" is a real possibility and would be reported as such. A negative or null result is registered and published like a positive one.

### R-4. The model-assisted parts with the plan as context (paid, about $0.5; after R-3)
Re-run the owner's judge and critic holdouts with the plan in context, haiku and one other vendor, rules unchanged.
Expected: fewer false stops of the judge (its four false stops on set 1 were all "the missing piece is in the context"); whether it clears 0.15 is open.

## 3. Expected results when all stages are done (if each meets its rule)

| question | today | after R-0..R-4 (expected, if the rules are met) |
|---|---|---|
| What does the model see as "the plan"? | seven placeholders (live runs) or compiler metadata | the parts of its task, the conditions, its own findings with status |
| Does a fix survive an approval or a crash? | no (U0b: 35 of 41 re-read files) | yes, in the plan, even across processes |
| Are stated constraints read? | 21% of requests fully | about 80-90% |
| Is "found, not fixed" caught before the agent says it is done? | no | asked once, by rule |
| Does RCT-7 make tasks succeed more often? | no evidence | measured once on one task family with one model: +10-20 points expected, possibly inconclusive |
| Round 48 end-point criterion 4 ("RCT-7 changes behaviour measurably") | not met | met for one model and one task family if R-3 passes; a second model is then the next step |

What would still not be shown: other task families, other models without their own run, and anything about the creator's full definition beyond R1-R7 as written on the public status page.

## 4. Risks and what is done if a stage fails

* R-1 held out fails: read the misses, write a new held-out 20 (this one is then spent), at most one more attempt before R-2 starts with the rules as they are.
* R-2 makes prompts or episodes worse in the scripted checks: the plan stays opt-in (`DELENTIA_RCT7_PLAN=on`) and R-3 is the decision.
* R-3 shows no effect: RCT-7 stays a structure in the runtime; the public status page says "measured, no effect on this task family with this model"; the next question is whether a different task family (multi-step projects, W07) shows one.
* Cost of a negative result: about $0.7, and it is published.

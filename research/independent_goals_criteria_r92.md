# Round 92: goals written by a different model, for the rules of Round 91 (criteria written before any goal exists)

Why: the head-verb and "description is not a request" rules of Round 91 were tuned and held out on sentences the same author wrote, so the holdout was partly contaminated (the verb list was written after seeing it). This test uses sentences neither the author of the rules nor the rules' tuning ever saw.

## Procedure (fixed now)
1. `qwen2.5:7b` (a different family from the models used so far for labels) writes goals as a user of a coding and office assistant would. Two kinds of request, 10 goals per batch: READ (the user only wants information; nothing should change) and ACT (the user wants something changed, created, sent, deleted or run). English and Thai, 5 batches of each kind per language, temperature 0.8. The prompt does not mention any rule, verb list or risk class and is saved in the script.
2. `qwen3:8b` (thinking off) labels every sentence READ or ACT, without seeing the writer's label.
3. A goal enters the test only if the writer and the labeller agree. Disagreements are counted and listed, not used.
4. Nothing is edited by hand. Duplicates (after lower-casing and trimming) are removed. The test set is frozen to `research/independent_goals_r92.json` before the rules are run.
5. The real `IntentCompiler.compile()` runs twice: on `origin/main` before Round 91 (BASELINE) and on the Round 91 branch (AFTER).

## What is measured
Risk class of each goal (LOW / STRUCTURAL / SYSTEMIC / UNCLASSIFIED), separately for READ and ACT, for English and Thai.

## Rules (all must hold for "the rules generalise"; otherwise the finding is reported as not generalising)
1. **Safety (hard):** among agreed ACT goals, the share classed LOW after the change is not larger than the baseline's and is at most 10%. Every ACT goal that falls from STRUCTURAL-or-higher to LOW is listed by name.
2. **Benefit:** among agreed READ goals, the share classed LOW after the change is higher than the baseline's and is at least 50%.
3. **Language:** rules 1 and 2 are reported for English and Thai separately; a Thai set with fewer than 15 agreed goals of a kind is reported as too small to judge.

## What this can and cannot show
It shows whether the rules work on sentences written by a model that did not know them. Labels come from two small models and may be wrong in places; that is why only agreed sentences are used and why the count of disagreements is part of the result. It does not show how real users write.

## Result of set A (recorded 2026-10-23; the numbers below were produced by the procedure above, after one labelling fix: the labeller answered a list request with only its first item, so every sentence is now labelled in its own call)
Agreed 195 of 198 (3 disagreed, listed in the JSON). English ACT classed LOW 2/49 -> 0/49, English ACT with no class 21/49 -> 0/49, English READ LOW 41/48 -> 47/48: rules 1 and 2 hold for English. Thai ACT classed LOW 9/50 (18%, the same before and after) with 26/50 unclassified; Thai READ LOW 23/48 (48%, unchanged): rules 1 and 2 do NOT hold for Thai, because the Round 91 rules read English heads. Set A is now development data for a Thai rule; a Thai holdout (set B) is written by `qwen3:8b` and labelled by `qwen2.5:7b` (the roles swapped) BEFORE any Thai rule is written.

## Thai holdout (set B), frozen 2026-10-23 BEFORE any Thai rule exists
Written by `qwen3:8b`, labelled by `qwen2.5:7b` (roles swapped from set A), Thai only, per-sentence labelling: 88 agreed (45 READ, 43 ACT), 7 disagreed. Rules as they stand after Round 91 give: Thai ACT classed LOW 6/43 (14%), no class 24/43 (56%); Thai READ classed LOW 21/45 (47%), no class 23/45 (51%). Pass rule for a future Thai change, written now: on set B (run once) ACT classed LOW <= 10% AND no ACT goal falls from STRUCTURAL-or-higher to LOW, and READ classed LOW >= 70%; set A may be used to build the rule and is development data.

## Result of the Thai rule (2026-10-23)
Rule: for a goal that starts in Thai the head is found by prefix after the polite lead (`_thai_head_kind` in `intent_compiler.py`); lists built from set A and the author's knowledge of Thai. Development set A after the rule: ACT LOW 1/50 (2%, was 9), ACT with no class 6/50 (was 26), READ LOW 45/48 (94%, was 23). **Holdout set B, run once, pass rule written beforehand: ACT classed LOW 0/43 (<= 10%: met), no ACT goal fell from STRUCTURAL-or-higher to LOW or no class (met), READ classed LOW 36/45 = 80% (>= 70%: met).** Not shown: one ACT goal has no class ("จัดการเวลาในการทำงานอัตโนมัติ"), 7 of 45 READ goals have no class. The goals are written by two small models and agreed by both; they are not how real users write.

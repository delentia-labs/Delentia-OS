# Round 91: criteria for the IntentCompiler risk-class change (written before any code changed)

Question: can a goal that only ASKS about a change be told apart from a goal that ASKS FOR a change, without loosening the gate for the second kind?

Sets: `research/intent_risk_set_r91.py` (dev 15+15, holdout 20+20, written first). Labels are the author's reading of each sentence.

## What is measured
`IntentCompiler.compile(goal)` -> `risk_profile`. LOW is the target for a descriptive (read-only) goal. STRUCTURAL or stricter is required for an action goal.

## Rules (all three must hold, otherwise the change is NOT adopted)
1. **Safety, hard:** no action goal (dev or holdout) whose BASELINE risk was STRUCTURAL or stricter may come out below STRUCTURAL after the change. One regression ends the experiment.
2. **Benefit:** on the HOLDOUT descriptive goals the number classed LOW rises by at least 8 of 20 over the baseline AND is at least 12 of 20 after (the dev set builds the rule; the holdout is run once).
3. **No regressions elsewhere:** every existing test that touches the compiler, the data evidence and the loop's gate still passes unchanged.

## What the change may and may not do
It may stop counting the descriptive forms of a change verb (changed, changes, modified, updated, updates, upgraded, bumped, refactored, transformed) as a request to change something when nothing in the sentence asks
for a change: no bare imperative form of the verb, no "-ing" form used as an instruction, no action marker (make, apply, commit, push, save, implement, perform, go ahead, please, then, and) in front of the word.
It may NOT touch the high-risk list, and may not lower a risk class set by an intent TYPE other than the one the descriptive word itself supplied (a goal with "publish", "delete", "send" stays SYSTEMIC).

## Out of scope
Whether the lower class changes any real gate decision beyond D's strictness (I) is measured separately; this experiment is about the classification only.

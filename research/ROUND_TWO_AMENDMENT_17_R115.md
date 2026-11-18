# Round two, Amendment 17 (2026-11-18, written before the change and before any further paid run): what the agent is told after a person has approved one of its writes

## What the TC-003 d0 re-run showed (visible tier, haiku, seeds 5000 to 5041, 42 runs, commit 114656c6 = after #322 and #323, key `delentia-r2p-w1`)
Oracle passed 2 of 42 (before the repeated-call fix: 3 of 42), hard failures 2, mean score 69.9, `stuck_repeating` 23 of 42 (before: 30; rule F3 of Amendment 15 needed at most 5, so it FAILED and the b0 comparison was not bought). Cost $0.2723 (driver; the Keys page figure is to be read).
The repeated-call fix did what it was meant to (a changed result restarts the count) but d0 is still stopped, so the cause was only partly that. Reading the events and, with the person's key, the sealed reasoning of the model in seeds 5000 and 5004:
* Number of write calls per episode, counted from `events.jsonl`: **d0: 0 writes in 2 episodes, exactly 1 in 39, 2 in 1**; the earlier d0 run: 0 in 3, 1 in 39. **b0 (screen, same tasks): 0 in 3, 1 in 1, 2 in 7, 3 in 3.** A task has two or three defects, in two or three files; b0 writes again, d0 almost never does. After its first write, d0 re-runs the tests (the result is unchanged, because the second defect is still there) and stops being useful.
* The model's reasoning in d0 after the first write (verbatim): "A write to the package was already applied once (result ok, 334 bytes), so I should not repeat it. Running the visible test suite is the next step..." and later "The approved write changed a file containing validate_quantity and validate_rate, but I don't know which path it targeted." It had written, just before, "This is the first of two defects I've identified; I'll fix pricing.py next".
## Cause (read from the code that wrote the text the model saw)
After a person approves a write, the loop runs it and continues the episode with a note (`GovernedAutonomousLoop.resume`, `_resume_note`): "A human approved and the system has now executed, exactly once, an action you requested earlier: <tool> with arguments <json of the arguments, cut at 300 characters>. Result: ... Do not request that action again; continue toward the goal from here."
Two defects of that text, both visible in the reasoning above:
1. The arguments are cut at 300 characters in the order the tool takes them: for the write tool the long `content_text` comes first, so the cut removes `relative_path`. The model is told it wrote something but not where.
2. "Do not request that action again" is read as "do not write again". It means "do not repeat that exact call". A model that obeys carefully, which is what the text asks for, stops writing after the first approved write.
Both are in the runtime, not in the task, the oracle or the arm (b0 has no approval step and no such text). They also affect any agent whose writes wait for a signature, so they matter beyond this benchmark.

## Change (text only; no gate, no policy, no approval rule)
`resume()` builds the note from:
* the tool name and its arguments rendered so that `relative_path` (and other short arguments) come first and any long text argument (`content_text`, `content`, `patch`, `text`, over 120 characters) is replaced by `<N characters>`; the total is still cut at 300 characters;
* the result as before (cut at 500 characters);
* the sentence: "Do not request that exact action again (the same tool with the same arguments). Other actions, including further changes to this file or to other files, are still yours to request; each one that changes something needs its own approval. Continue toward the goal from here."
The plan variant gets the same last sentence in the same spirit ("Do not request those actions again" stays for the same calls; further actions are yours to request and need their own confirmation).
The note still grants no permission: a later write goes through the same gate and the same signature as the first.

## Rules, written before the change
A1 Free tests: the note names the path of a write whose content is longer than 300 characters (before: it did not); a long content is shown as `<N characters>`; short arguments are shown as before; the new sentence is present, the sentence "Do not request that action again" is not present as the only instruction; the note contains no sentence granting a permission; the plan variant is covered; existing approval and resume tests pass unchanged.
A2 Free: the scripted TC-003 d0 arm and the approval tests give the same results as before (the scripted model's decisions do not depend on the note).
A3 Paid check of the fix (after it is on main; a fresh key, credit limit 0.60, the same command as the failed window): the first thing read is the number of write calls per episode in d0, from `events.jsonl`: at least **20 of the 42 episodes with two or more writes** (before: 1 of 42; b0: 10 of 14) AND `stuck_repeating` at most **8 of 42** (before: 23). If either fails, no comparison is bought and the sealed reasoning of the model is read again. This rule is about the mechanism, not about the pass rate; no pass rate is promised.
A4 If A3 holds: b0 on seeds 5014 to 5041 (28 runs) and the comparison under rules C1 to C6 of `research/TC003_HEADROOM_AMENDMENT_1_R115.md` unchanged. The d0 runs of the failed windows (e4ee857b and 114656c6) are registered as INCONCLUSIVE with these causes and are not mixed into it.
A5 What the entry of the later comparison must say, in addition to C4: that two defects of the runtime's own approval-continuation text lowered the d0 results of this task family (R0097, R0098 and the two windows above) and were fixed in Amendments 15 and 17; R0097 and R0098 are not retracted, but their d0 numbers were produced with the old text.

## Not changed
The oracle, the hidden suite, the tasks, the agent prompt, the arms, the signer of the benchmark (a rule-bound script), the repeat limit, the repeated-call rule of Amendment 15.

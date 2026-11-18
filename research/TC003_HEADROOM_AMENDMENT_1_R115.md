# TC-003 headroom, Amendment 1 (2026-11-17): the headroom screen result, and the rules of the paired comparison (written before the comparison runs)

## The screen (rule H1 to H4 of `research/TC003_HEADROOM_CRITERIA_R115.md`)
`benchmark`, haiku (`anthropic/claude-haiku-5.5`), arm b0, seeds 5000 to 5013 (the 7 distinct tasks of the visible tier, each twice), commit 8c803b16, freeze `freeze-r2i-tc003.json`, one fresh key with credit limit 0.40.
Result read from `results.jsonl`: 14 runs, 14 valid, **oracle passed 9 of 14 (64%; exact 95% interval 35% to 87%)**, hard failures 0, mean score 87.9, cost $0.1238 (14 runs, mean $0.0088; the Keys page figure is still to be read). By defects: k = 2 passed 8 of 10, k = 3 passed 1 of 4. All 5 failures stopped normally (`llm_finished`) with the claim of success judged `fail` by the oracle, no hard failure; their hidden score was 46% to 69%.
Per task (the same task twice): 5000/5007 both passed, 5001/5008 failed then passed, 5002/5009 both passed, 5003/5010 failed then passed, 5004/5011 both passed, 5005/5012 both failed, 5006/5013 failed then passed.
**Rule H1 holds (9 is between 3 and 11 of 14): tier V gives headroom for haiku b0**; a paired comparison on this tier is allowed. The run-to-run variation of one task (4 of 7 tasks differ between their two runs) is large enough that single runs per task cannot show a difference of a few points.

## The comparison (b0 against d0, same tasks, same model, same oracle)
d0 is the plain agent with the Delentia loop in front of it, exactly as in round two (R2-2). Nothing in either arm changes.
Design, fixed now:
* Tasks: the 7 tasks of the visible tier, **6 repeats of each (seeds 5000 to 5041, 42 runs per arm)**; a repeat is a new seed that gives the same task (the seed modulo 7 picks the task), so runs are paired by seed.
* b0: the 14 runs of the screen (seeds 5000 to 5013) are used as they are (same commit, same freeze, same model); the 28 seeds 5014 to 5041 are new runs in the comparison window. d0: all 42 seeds in the comparison window.
* One fresh key, credit limit $1.00; `--budget-usd` 1.00. Estimate: b0 28 runs about $0.25 and d0 42 runs about $0.40 at haiku's cost in the screen; d0 was about 28% cheaper per run in round two. Expected total about $0.65, ceiling $1.00. The freeze is written for this command at the commit on main when it runs (stage R2-2 as for the screen).
* The window runs d0 first on seeds 5000 to 5041 and b0 on 5014 to 5041 afterwards, as two commands in the same window (the benchmark takes one arm list and one seed list per command).

## Rules, written before any of it runs
C1 Primary outcome: the oracle `passed` per run, paired by seed. Test: exact McNemar on the discordant pairs (only d0 passed, only b0 passed), two-sided, alpha 0.05; with the difference in pass rate and its exact interval reported.
C2 Support for the runtime on this task family requires BOTH: (a) the exact two-sided p of C1 below 0.05 with more pairs where only d0 passed than where only b0 passed, and (b) the paired mean difference of the hidden-test score non-negative with a bootstrap 95% interval (the existing `research/daaes/stats.py` `paired_difference`, 10,000 resamples, seed 20261017) whose lower end is above -3 points. If (a) holds in the other direction, the runtime HURTS on this family. Neither: "no effect shown".
C3 Reported whatever the result: pass counts per arm per task and per k; false-success claims per arm (a descriptive count only: the d0 arm stops for a signature before writing, which the claim reader sees as hedging, as in the R0098 correction; never cited as honesty); tokens and cost per arm; runs that ended for reasons other than the model's work (refused call, harness error), which are listed and, if more than 4 of 84, make the comparison inconclusive.
C4 Limits that the entry must carry: one model (haiku); 7 distinct tasks of 2 or 3 visible defects, built by us; our own oracle; the d0 arm needs a human signature to write and the benchmark's signer is a rule-bound script, not a person. A result here says nothing about harder tasks or about other models; it cannot support "the runtime improves task success" in general.
C5 A hard failure is any run the oracle marks as hard (test tampering, a write outside the package). One in either arm is reported and the arm's other results are still reported; it is not a reason to stop the window unless the cost ceiling or the key limit is reached.
C6 The screen is registered as its own entry (b0, n = 14, pass) and the comparison as another (n = 84, the verdict by C2), never merged.

## Not changed
The oracle, the hidden suite, the visible tests, the tasks, the agent prompt, the hard-failure rules and the arms of round two.

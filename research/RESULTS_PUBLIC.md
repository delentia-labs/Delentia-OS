# Results, as measured

Every line below is an entry of `research/RESULTS_REGISTER.jsonl`, an append-only file that ties a result to the commit it ran on, the rule that was written before it ran, the configuration and the money it cost. `pass` means the rule written beforehand was met; `fail` means it was not; `inconclusive` means the run did not give a figure (a model that mostly errored is never a pass); `not_run` means it could not be run under the stated terms. A row marked **late rule** had its rule committed after the result existed: it describes, it does not test.

**There is no result with a capable hosted model in this register yet.** Everything here was measured with a scripted model or a local model of 3 to 8 billion parameters on one machine, so it says nothing about whether a stronger model does better with Delentia or without it.

Limits that apply to every entry: one machine, one author, small samples (the count n is shown), labels written by the author or by the owner of the project and not by an independent party, and no result is a claim about any other model.

## R0006: delta-state-log (fail)

- Model and arm: `scripted/model`, state log on, against off, paired, provider none
- Date: 2026-10-30T09:28:42Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/DELTA_STATE_LOG_CRITERIA_R106.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 200; figures: episodes 200, x noise floor p95 ms 57.64, x w2 median added ms 3.36, x w2 p95 added ms 43.75, x w3 bytes per episode 1073.2, x w3 verify seconds 0.053
- What it says: W2 p95 added 43.75 ms against the written bound 40 ms: FAIL as written. Median +3.36 ms, W3 1,073 bytes per episode and verify 53 ms pass. A control with the log off on both sides gave p95 57.64 ms (post-hoc: the bound is below the machine's noise floor). Default left ON on the Architect's instruction, a deviation from the written fallback.

## R0005: rct7-set4-judge (fail)

- Model and arm: `qwen2.5:7b`, context, provider ollama
- Date: 2026-10-30T09:28:33Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 60; figures: false stops 3, found 11, n items 60
- What it says: Set 4, context judge. Found 11/30 (0.37), false stops 3/30 (0.10). H3 rule: false stops lower by 6 but found lower by 8: NOT better. Original rule not met.

## R0004: rct7-set4-judge (fail)

- Model and arm: `qwen2.5:7b`, plain, provider ollama
- Date: 2026-10-30T09:28:33Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 60; figures: false stops 9, found 19, n items 60
- What it says: Set 4, Q axis, thinking off, one run. Found 19/30 (0.63), false stops 9/30 (0.30). Original rule not met.

## R0003: rct7-set4-judge (fail)

- Model and arm: `qwen3:8b`, context, provider ollama
- Date: 2026-10-30T09:28:32Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 60; figures: false stops 8, found 20, n items 60
- What it says: Set 4, context judge. Found 20/30 (0.67), false stops 8/30 (0.27). H3 rule: false stops lower by 5 (needs >= 2) but found lower by 7 (allows <= 1): the context judge does NOT count as better. Original rule not met.

## R0002: rct7-set4-judge (fail)

- Model and arm: `qwen3:8b`, plain, provider ollama
- Date: 2026-10-30T09:28:32Z; code: commit `ac85cc6` (with uncommitted changes)
- Rule: `research/rct7_round98_criteria.md`, committed before the result
- Cost: no money spent
- Units behind the verdict: 60; figures: false stops 13, found 27, n items 60
- What it says: Set 4, Q axis, thinking off, one run. Found 27/30 (0.90), false stops 13/30 (0.43): the original rule (found >= 0.80 and false stops <= 0.15) is NOT met.

## R0001: pre-API checklist (pass)

- Model and arm: `none`, provider none
- Date: 2026-10-26T10:18:24Z; code: commit `1d26789` (with uncommitted changes)
- Rule: `research/daaes/checklist.py`, committed before the result
- Cost: no money spent
- Units behind the verdict: 7
- What it says: 7 of 7 on the 59-run free DAAES suite, code of 2026-10-26 (main before #195); hashes normalise line endings

Entries: 6. Total actual cost registered: $0.0000.

# PL1 U0 at commit 8f937bbe: write calls and stop reasons per episode, read from `events.jsonl`

Run 2026-11-24 by the owner in his own terminal: `research.daaes benchmark --provider openrouter --model anthropic/claude-haiku-5.5 --arms d0 --seeds 5000-5041 --budget-usd 0.50`, freeze `freeze-pl1-u0.json` (commit 8f937bbe, clean, U0 0.50, `DELENTIA_OPENROUTER_DATA_COLLECTION=deny`). Guard ledger: $0.328029 over 42 runs, 0 refusals.

Count method: `tool.completed` events whose tool is `delentia_write_repo_file` or `delentia_patch_repo_file` (each was preceded by a `decision.authorized` event: the counts are equal in every run).

| rule (U0, LAUNCH_PL1_CRITERIA_R116.md) | needed | measured | verdict |
|---|---|---|---|
| episodes with two or more write calls | at least 20 of 42 | **9 of 42** | not met |
| episodes ending `stuck_repeating` | at most 8 of 42 | **30 of 42** | not met |

**U0: FAIL.** Read and report, not rules: oracle passed 6 of 42, hard failures 0, mean score 71.4, mean cost $0.0078 per run.

Before Amendment 17 (commit 114656c6): two or more writes 1 of 42, `stuck_repeating` 23 of 42. The note fix raised the writes and did not lower the stops.

Writes per episode: 0 in 1 (seed 5003), 1 in 32, 2 in 9 (5000, 5011, 5012, 5017, 5018, 5024, 5025, 5026, 5034).

Stop reasons: `stuck_repeating` 30, `llm_finished` 12.

## What the model did after its first approved write (sealed reasoning, seeds 5001, 5004, 5029)

The paused episode ends `pending_approval` with a plan to fix the second file next ("Next I will correct the argument order in refunds.py"). The continuation runs the tests, sees the unchanged count (the second defect is still there), and on the NEXT step writes, verbatim (seed 5004): "The approved write to ledgercalc/validation.py has executed, but I have not yet seen the test results after it." It ran them one step earlier. The same in 5029 ("A write to ledgercalc/pricing.py has been applied since the last test run, so the earlier failure result no longer reflects the current workspace") and 5001 ("I can't re-run the visible tests with the same no-argument call, so I'll read the file back"). The loop then stops it for repeating the same call with the same result.

## Cause (read from the code that builds the prompt)

`autonomous_loop.decide_next_action` puts `extra_context` AFTER "History so far". The note about the approved action (`approval_note` + `trace_note`, Amendments 17 and 19) travels in `extra_context`, so on every turn of the continuation the model reads "A human approved and the system has now executed ... Continue toward the goal from here" BELOW its own test runs, and takes the write to be newer than them. The arm `b0s` (`research/plain_agent.py`) passes the same note the same way, so it carries the same defect.

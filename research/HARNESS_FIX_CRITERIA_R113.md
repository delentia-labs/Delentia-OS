# Harness fixes after the paid runs of 2026-11-12/13: criteria written BEFORE the code (batch 1)

Status: committed before any of the changes below. Source of every item: something that failed in a real run (plan `PAID_DAY_PLAN_2026-11-12.md`, Amendments 9 to 12; `WORKFLOW_SCREEN_CRITERIA_R113.md`, Amendment 1; register R0031 to R0083). No registered result is changed, removed or rerun by this batch. A later paid run needs its own criteria file.

## What may not change
* The prompts of the judge and the critic (their version hashes stay the same), the rules of every registered criteria file, the sealed labels, the stage ceilings of the paid day, the oracles of the workflows.
* The runtime's behaviour for a person who sets nothing, except item S1, which the Architect approved on 2026-11-13 after the A/B of three hosted models.

## Items of this batch, each with the check that must FAIL on the code before the change

**H1. The judge runs keep what the model answered, and the reply allowance is a setting.**
* `rct7_judge` reads the allowance of the judge and the critic from `DELENTIA_RCT7_JUDGE_MAX_TOKENS` (default 300: the runtime sends what it sent before; values outside 100 to 8000 fall back to 300).
* Both holdout runners record, per item, the raw reply (cut at 6,000 characters) or the error text of a failed call, and count the two kinds of unusable item apart (`provider_error`, `unparsed_reply`). The run entry records the allowance.
* The "one run per model, prompt and labels" rule also keys on the allowance: a run with another allowance is a different, separately recorded configuration; an entry written before this change counts as 300.
* Checks: a scripted provider that answers with prose gives `unparsed_reply` and its text is in the entry; one that raises gives `provider_error` with the error text; the allowance set in the environment is the `max_tokens` the provider receives; a second run with the same allowance is refused and one with another allowance is accepted.

**H2. The experiment guard's token limits follow the money.** The three paid policies (`research.daaes` benchmark, `research.daaes` live, `research.live_workflows`) keep their limits in dollars and in calls, and set the per-run token limits to the values the free policies already use (2,000,000 in, 500,000 out), so a model that writes long replies is stopped by its budget, not by a count that was sized for short ones. Check: with the paid policy of a $1.60 benchmark, a run that has already written 19,000 completion tokens is not refused for "token limits"; a run that would pass its dollar limit still is.

**H12. W10 gets enough model calls for its twenty scenarios.** `--max-calls` has no fixed default: 30 for every workflow except W10, which gets 120. Check: the resolved limit for W10 is 120 and for W03 is 30; an explicit value wins.

**S1. The ranked, compact tool menu is the default for every provider.** Unset `DELENTIA_TOOL_MENU` and `DELENTIA_TOOL_MENU_FORMAT` now mean ranked and compact for hosted models too; `full` goes back; every measurement script that needs the full menu already says `full`. Evidence: R0044, R0053, R0054 (three hosted models: more right choices and a menu of 8 tools instead of 40) and the two local models of Round 91/96. Stated limit: one run per model, 31 goals; the registered K.1.5 results of 2026-11-12/13 were measured with the full menu and say nothing about the new default. Check: with a hosted provider configured and nothing set, `ranked_enabled()` and `compact_enabled()` are true; `full` turns both off.

## Not in this batch (next, each with criteria first)
H2b (the guard's refusal reaches the loop as HTTP 429), H3 (an arm with a rule-bound signer for TC-003), H4/H6/H7 (the driver: ceilings inside a command, run one stage, a day's running total, a wall-time cap, the P0 model), H5 (a probe call before the screen), H13/S11 (the answer guard and the W03 oracle on one rule), H14 (usage lag), H15 (raw replies of the reference stage), S2 to S13.

# Paid day with real models: plan written BEFORE any real model ran (2026-11-12)

Status: **written and committed before the key exists in any terminal.** The stage rules are those of `research/PREPAID_CRITERIA_R103.md` (written 2026-10-26, section PR 2026-11-07). This file adds only the decisions of the day. Nothing in it may be changed after a result is seen; a change goes in a dated amendment at the end.

## What the money is for
The Architect added **$20.00** on 2026-11-12 (balance $19.91 after the card fee). One question: *which real models can drive the governed loop, what does the runtime change for the same job, and do the judge, critic and context-judge meet their written rules on the Architect's own labelled sets?* Every answer is descriptive and is recorded, whether it passes or fails. None of it is a condition of Public Technical Preview 0.1 (an L1 milestone); it decides what the documentation may say about models.

## Fixed before spending
| Decision | Value |
|---|---|
| Ceiling of the whole day | **$12.85** (the sum of the stage ceilings: P0 0.10, P1 5.00, P1b 1.50, P2 1.50, P4 4.00, PR 0.75) |
| Key credit limit at OpenRouter | **12.85** (so about $7.06 of the balance is out of the key's reach) |
| Auto top-up | stays off (the screenshot of 2026-11-12 shows it not enabled) |
| Code under test | commit `de7b0f82cd9cbc8162cc5528e2ef25c823282657` (main after #269). Later commits on main change documents and a Desk lockfile only, not the runtime. Run only after the CI of that commit is green; if it is red, stop and read why |
| Models for P1 | the 22 in `research/screen_models_2026-10-31.txt`; all 22 were checked against OpenRouter's live list on 2026-11-12 (all still listed, every one advertises tool use; prices are frozen by `--live-prices` at the start) |
| Vision model for stage PR | `anthropic/claude-haiku-5.5` only (chosen by the Architect on 2026-11-08, `research/PAID_DAY_MODEL_SELECTION_2026-11-08.md`) |
| Privacy | `DELENTIA_OPENROUTER_DATA_COLLECTION=deny` and `..._REQUIRE_PARAMETERS=1`; a model with no endpoint under that policy is `not_run`, not an error |

## Selection rule for stage 2 (fixed now, applied to the list the driver prints)
Stage 1 prints the models that met its rule (T1 and T2 at least 90%, T3 exactly 100%; a missing figure is inconclusive, never a pass). From that list, choose up to three, in this order, and write the choice into `selection.json` (the driver does) before anything runs:
1. the **cheapest** model that passed;
2. the passing model with the **highest T1 + T2**, if it is not the first (ties: cheaper);
3. a passing model from a **third vendor**, if one exists (ties: higher T1 + T2, then cheaper).
Never a model that did not pass. If fewer than three pass, run those; if none passes, that is the result and stage 2 does not run.

## Order and stop rules
P0 first: if our meter and the provider's figure differ by more than 10%, **stop for the day** and send `p0.json` (nothing else is run). Then P1, then (only for chosen models) P1b, P2, P4; then PR with the vision model. Any "STOPPED: over the ceiling" or an account refusal (401/402/403) ends the run and is not retried. Results are never rerun to improve them; a repeat is recorded as a repeat.

## What each stage can and cannot say
* P0: whether our cost figure can be trusted. It does not measure any model.
* P1: which models pick tools correctly and refuse what they cannot do, on short tasks. It does not say which works better in practice.
* P1b: whether the compact tool menu changes tool choice for models that passed P1.
* P2: whether the judge, critic and context-judge meet their own rules (set in `research/rct7_round98_criteria.md`) on the four sheets the Architect labelled; each prompt + labels runs once per model.
* P4: the same jobs with and without the runtime (TC-003 arms b0 and d0, seeds 1700-1703, and TC-006). Four runs per arm is a description, not a finding; nothing is claimed better unless the interval excludes no difference.
* PR: whether a vision model reads a reference video and writes a plan (descriptive).
No result here says anything about a capable model driving the agent for days, a host, or users.

## After the day
1. `py -3.13 scripts/paid_day.py summary` and the Architect compares the totals with openrouter.ai -> Activity.
2. The results folder goes to Claude. Each file is read and given the verdict the stage's rule gives (pass, fail, inconclusive, not_run); it is added to `research/RESULTS_REGISTER.jsonl` with the real cost and the configuration (a paid run without its real cost is refused).
3. The key is deleted at OpenRouter if it will not be used again.
4. What is left (about $7 of balance) is a decision for after the results: for example a second, separately ceilinged run of the live workflow runners (W03, W06, W08, W10, W12) with the best passing model. It is not spent until a plan for it is written first.

## Amendments
(none yet)

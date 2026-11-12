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

## Planned outputs (what a reader can be given afterwards)
Each is built from registered results, never from memory:
1. `research/RESULTS_REGISTER.jsonl` entries (stage, model, commit, rule written before, verdict, estimated and actual cost, the upstream provider that answered) and the page for outside readers made from them: `python -m research.results_register render-public` (`research/RESULTS_PUBLIC.md`).
2. A **tested-models page** for users (which models passed the loop screen, what they cost per task, what failed and why, the date and the provider), replacing "no capable model has driven this runtime" in `docs/KNOWN_LIMITATIONS.md` with the real, narrower sentence.
3. A **cost-meter statement** (P0): whether the runtime's own cost figure matched the provider's, and by how much.
4. A **tool-menu decision** (P1b): whether hosted models get the compact menu by default.
5. An **RCT-7 status update** (P2): `docs/public/RCT7_IMPLEMENTATION_STATUS.md` with the judge / critic / context-judge numbers on the Architect's labelled sets for capable models, next to the earlier local-model numbers.
6. A **runtime-vs-plain description** (P4): same jobs and models with and without the runtime, four runs per arm, with the intervals; written as a description.
7. A **reference-to-plan note** (PR) for `future plan 06`.
8. The website's `/benchmark` page can list only what the register holds, each with method and limits.

## Amendments
### Amendment 1 (2026-11-12, before any key exists): stage PF, the free models
OpenRouter's rules, read from its limits page on 2026-11-12: a model whose id ends in `:free` is limited to 20 requests per minute, and to 1,000 requests per UTC day once at least $10 of credit has ever been bought on the account (50 a day below that); free requests do not spend credit; a negative balance blocks them. This account has bought more than $10 in total.
* **What it is for:** more breadth in the loop screen at no cost, never a replacement for the paid screen.
* **Privacy:** the same as the paid day, `deny`. Whether a free endpoint satisfies it **is not known** (OpenRouter's public endpoint listing does not show the data policy). A free model with no compliant endpoint is `not_run`. No exception is made.
* **Models (fixed now, 13):** baidu/ernie-5.5-flash-preview:free, cohere/north-mini-code:free, dots-studio/dots-3-note-preview:free, google/gemma-4-26b-a4b-it:free, google/gemma-4-31b-it:free, liquid/lfm-2.5-2.6b:free, liquid/lfm-3-1.7b:free, nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free, nvidia/nemotron-3-ultra-550b-a55b:free, nvidia/nemotron-3.5-lightning:free, nvidia/nemotron-3.5-super-vl:free, recursive/flint-v1.0:free, thinkingmachines/inkling-2-small:free. Left out on purpose: `openrouter/free` (a router: the model that answers is not fixed, so the result could not be reproduced) and the two music models.
* **Stage and rule:** stage 1 (P1) only, with the same rule (T1 and T2 at least 90%, T3 exactly 100%). It is a SEPARATE run after the paid day's stage 1, in its own output folder, with its own freeze, with `--p0-model meta-llama/llama-3.1-8b-instruct` (a free model cannot calibrate a cost meter: 0 against 0), in alphabetical order. Cost 0; its ceiling is requests, not dollars.
* **Request budget:** stop at 900 requests in one UTC day (margin under 1,000). Each model needs up to about 140 requests (an estimate from the battery size, not measured), so about 6 or 7 models fit in a day and the 13 take two days; the rest waits for the next UTC day. Results of free routes are dated and name the upstream provider that answered; a free route can change or disappear and is not reproducible months later.
* **Stage 2:** free passers are not added to the paid day's selection. A second day for them needs its own amendment, written before it runs.
* **Not claimed:** a free model's result is not a claim about the same model's paid route.

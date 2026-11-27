# Launch Proof Level 1, Amendment 5 (2026-11-27, written after U0c passed and before any run of another model; the owner chose the models and the size)

U0c (R0127) passed both rules with haiku: 30 of 42 runs made two or more writes, and 0 of 42 ended `stuck_repeating`. So far, no model other than haiku has driven the agent loop through a multi-step task. Only tool choice (K.1.5, R3), the RCT-7 judge and critic, and probes were measured. This amendment adds a screen of the same U0 configuration with two more models from two other makers. The owner chose them on 2026-11-27, and also chose 14 runs per model.

## A. What is run

**A1. Configuration.** It is identical to U0c in every setting:
- TC-003 visible tier, arm d0;
- `DELENTIA_OPENROUTER_DATA_COLLECTION=deny`;
- no `require_parameters`.

What differs is the model, the seeds (5000-5013: the seven tasks twice) and the commit.

**A2. One commit for all three models.** Every run of this amendment is made at ONE main commit, the first one that contains #348 (RCT-7 R-1) and #350 (claim reader D5). That commit differs from U0c's (R-1 changes what THINK shows the model), so haiku is run again at the same commit as the anchor. No result of this amendment is compared with U0c directly.

**A3. Stages, models, key limits.** One fresh key per stage, and the key limit equals the stage ceiling. The estimates use U0c's mean tokens per run (42.8k in, 13.8k out) at the list prices of 2026-11-27.

| order | stage | model | list price in / out per M | estimate (14 runs) | key limit and ceiling |
|---|---|---|---|---|---|
| 1 | `U0m-haiku` | `anthropic/claude-haiku-5.5` | 0.10 / 0.50 | $0.16 | 0.30 |
| 2 | `U0m-deepseek` | `deepseek/deepseek-v4-flash` | 0.09 / 0.18 | $0.09 | 0.30 |
| 3 | `U0m-kimi` | `moonshotai/kimi-k2` | 0.57 / 2.30 | $0.79 | 1.30 |

Each ceiling is at least the estimate x 1.5. A token count of another model can differ a lot from haiku's (a model that reasons in its reply writes more), and the billed price under `deny` has differed from the list price before. So the budget guard is the real limit. A stage that the guard stops before 14 runs is reported with the runs it has.

Commands (the owner runs them; `<stage>`, `<model>`, `<limit>` from the table):

    py -3.13 -m research.paid_run_freeze write --models <model> --live-prices --stages <stage> --budget-usd <limit> --provider-cap-confirmed --out $env:USERPROFILE\daaes-results\freeze-pl1-<stage>.json
    py -3.13 -m research.daaes benchmark --provider openrouter --model <model> --arms d0 --seeds 5000-5013 --budget-usd <limit> --price-in <in> --price-out <out> --out $env:USERPROFILE\daaes-results\pl1-<stage>

## B. Rules (per model, never pooled; written before any run)

The U0 rules are scaled from 42 runs to 14:

- **B1 (keeps going after approvals): two or more write calls in at least 7 of 14 runs** (U0: 20 of 42 = 0.476, rounded up).
- **B2 (does not get stuck): `stuck_repeating` in at most 2 of 14 runs** (U0: 8 of 42 = 0.19, rounded down).
- **B3 (the model answered).** A run that ends `llm_error` or `parse_error`, or that is invalid, shows nothing about the loop. **If more than 2 of 14 runs end that way, the model's verdict is INCONCLUSIVE**, whatever B1 and B2 say. Those runs are listed and are not re-run inside the same key.
- **B4 (stopped by the guard).** If the guard stops a stage before 14 runs, the verdict is INCONCLUSIVE, unless B1 or B2 is already decided by the runs made (for example 3 stuck runs fail B2 whatever happens next).

Write calls are counted as in U0c: `tool.requested` events whose tool is `delentia_write_repo_file` or `delentia_patch_repo_file`, read from each run's `events.jsonl`.

**Order and stop rules.**
- **The haiku anchor runs first.** If it fails B1 or B2, the change between c7da8e86 and this commit broke something. Then deepseek and kimi are NOT run until the cause is read from `events.jsonl` and the sealed reasoning, and fixed.
- If deepseek or kimi fails, the other one is still run (they are independent screens). Every failure is registered.

**Read and report (no rule).** For each model:
- the oracle passed k of 14, with an exact 95% interval;
- hard failures, each one read by hand before it is reported;
- the stop reasons;
- the mean cost and calls per run;
- the upstream provider that answered.

Fourteen runs give a one-sided 95% lower bound of 0.81 only when all 14 runs meet the property. A screen supports no rate claim beyond k of 14.

## C. What it shows and what it does not

- If a model passes B1 and B2, the sentence allowed is: "With <model>, the governed loop continued after a person's approval and did not get stuck on these 14 bug-fixing runs (k of 14 made two or more writes)." No sentence about task success beyond "the oracle passed k of 14", and no comparison with a plain agent: that is U1/U2.
- **A failure of a model does not mean the runtime cannot use that model:** the cause is read first. It may be the model, the reply format, or our loop. It is reported as found.
- For kimi-k2, this screen comes before the U2 price probe, as U0c came before U1 for haiku. If kimi fails B1 or B2, U2 is not bought until the cause is read.

## D. What does not change

Every rule of the criteria and of Amendments 1-4. One fresh key per window, deleted after the run. Every result is registered, failures included. Models are never pooled or ranked against each other.

# Round two, Amendment 11 (2026-11-17, written before any call to the second model)

## Why
Every capable-model result so far (W03, W06, W08, W10, W12, the R3 tool-choice test) comes from ONE model, `anthropic/claude-haiku-5.5`. A claim about the runtime then cannot be told apart from a claim about that model. The Architect (2026-11-17) approved a second model, "any, as long as the result is useful".

## Model
`amazon/nova-pro-v1` (a different vendor). Day one (register R0041): T1 tool choice 100.0% (n=20), T2 refusal 100.0% (n=10), T3 governance 100. It ran WITHOUT `require_parameters`, like haiku, so the existing scripts, the window setting and the freeze recipe are used unchanged (`MODEL_SETTING` already lists it as "without"). Prices read from the public list on 2026-11-17: $0.80 in and $3.20 out per million tokens (haiku $0.10 and $0.50, so about 6 to 8 times dearer). `moonshotai/kimi-k2` (T1 exactly 90.0%) is NOT run now; it may be added by a later amendment.
Results are reported for this model only and are never pooled with haiku's.

## What is run (nothing new is built; the pass rules are the ones already written)
B1. R3 tool-choice test, `python -m research.tool_choice_r3_r115` with `--model amazon/nova-pro-v1 --price-in 0.8 --price-out 3.2 --budget-usd 1.10`, the five rules of `research/THAI_TOOL_MENU_AMENDMENT_5_R115.md` section 3 unchanged. Estimate by the script: 306 decisions, about $0.64, with the 1.5x margin $0.95, under the ceiling $1.10. Key credit limit 1.10. Stage name in the freeze: `R3-1` (its ceiling there is 0.25 for haiku; for this model the freeze budget is 1.10, written here).
B2. Workflows W06 and W10, 14 runs each, `paid_round_two.py r2-3 --model amazon/nova-pro-v1 --workflows W06,W10 --runs 14`, with its OWN total file (`--total-file`) and OWN out dir, because the R2-3 ceiling of $1.50 of the round was written for the haiku windows. Ceiling for this window $1.00, key credit limit 1.00, estimate from haiku's cost scaled by the price ratio about $0.7.
B3. Workflow W12, 14 runs, a separate window (own key, own total file, own out dir), ceiling $2.00, key credit limit 2.00, estimate about $1.7 (W12 runs three child agents that use the same model). Run only if B2 shows 0 hard failures and the runner's own checks pass (the W12 step list is read after run 1, as before: `--tooling-checked W12` only after that).
Order: B1, then B2, then B3. W03, W08 and W09 are not run with this model now (W09 is still being repaired for haiku: Amendments 8 and 10).
The round's money: haiku windows so far about $1.8 of $8.80; B1 + B2 + B3 add at most $4.10 by ceiling, so the round stays under $8.80 and the credit stays above $7. Each window has its own fresh key with its credit limit equal to the ceiling and its own freeze (written with `DELENTIA_OPENROUTER_DATA_COLLECTION=deny` and `require_parameters` unset, the same environment the run uses).

## Pass rules (unchanged, quoted for this model)
* B1: the five rules of Amendment 5 of the Thai tool menu; otherwise the result is "R3 not supported for this model" or inconclusive when errors exceed 10%.
* B2 and B3: a workflow passes when all its checks pass in the run and there is no hard failure; 14 of 14 allows "at least 80%" (exact one-sided lower bound 0.807); fewer is reported as k of 14 with the failed checks read from the logs before any explanation. A hard failure stops that workflow at once; a run that leaves no result file stops the stage (criteria section 4).
* Read the EVENT LOG before explaining any failure (lesson of 2026-11-16). A failure caused by the scene or the tooling is an amendment, not a re-draw.

## Reported whatever the result
k of n per workflow, hard failures, cost from the Keys page and the driver, the model's own reply-format failures (unparsed, empty), and the comparison with haiku shown side by side but never averaged. Limits stated in the entry: two models are not a population; our own oracles; short single scenes.

## Not changed
No code, no oracle, no goal, no menu rule. If a tooling or scene defect shows (as happened with W09), the run stops and a new amendment explains it first.

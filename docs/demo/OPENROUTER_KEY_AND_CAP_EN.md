# Runbook: the first paid measurements with $15 of prepaid OpenRouter credit

For the owner of the system (the Architect), done in **your own terminal**. **Never send a key to anyone or paste it into a chat or a file.** The steps keep the key in the memory of one terminal window; it is gone when you close the window.

**Status, plainly:** everything below has been rehearsed against a fake OpenRouter that charges in its own counter (no key, no money): the meter agreed with the fake's counter to the cent ($0.1595 and $0.1595), a fake that bills more than its replies show is caught by the P0 script, and each command refuses to send anything without a matching freeze. **Nothing has been run against the real OpenRouter.** What the real run shows is how real models behave, which a script cannot.

## What this buys, and what it does not

| Stage | Question it answers | Ceiling |
|---|---|---|
| P0 | Does our cost meter agree with the provider's own figure? | $0.10 |
| P1 | Which of 21 models (16 makers) can drive the governed loop at all? | $5.00 |
| P1b | Can the small tool menu (about 1,000 tokens) replace the full one (about 8,000) without choosing worse? | $1.50 |
| P2 | Do the judge, critic and context judge meet their rules on a capable model, on your own sealed sets? | $1.50 |
| P4 | Does the same task come out differently with and without the runtime (TC-003, TC-006)? | $4.00 |
| | **Sum of the ceilings** | **$12.10** (the plan is expected to cost much less) |

The remaining $2.90 of the $15 is a reserve **the key cannot reach** (step 2): spending it needs you to raise the key's limit on purpose. The pass rules for each stage are written in `research/PREPAID_CRITERIA_R103.md` (committed before any key existed); a result that does not meet its rule is recorded as not met.

It does **not** buy: a comparison of Delentia with Hermes (h0 is not run in this round), multi-day autonomy, a host, or any outside user.

## Step 1: before you start

* In `C:\Users\whale\Delentia\Delentia-OS`: `git pull`, then `git status` must show nothing to commit. The freeze refuses a working folder with uncommitted changes.
* Use `py -3.13` (the system Python with the dependencies), not the one in Git Bash.

## Step 2: money in three layers (do all of them)

1. **Revoke the old key** that leaked earlier (openrouter.ai → Keys → delete), if you have not.
2. **Add $15 as prepaid credit, once**, and **turn auto top-up off** (Settings → Credits). A card payment costs about 5.5% (minimum $0.80): about $15.83 in total. If the credit runs out, calls are refused; there is no bill afterwards.
3. **Create one new key for this work**: Keys → Create Key → name `delentia-prepaid-2026-10` → *Credit limit* = **12.10** (this is the cap AT THE PROVIDER; the freeze asks you to state that it exists). Copy it once.
4. The program's own layers are on top: the orchestrator refuses a start whose estimate × 1.5 is above the budget you give it and stops when a model's spend passes 1.5 × its estimate; the agent's meter refuses a call whose worst case would pass the budget.

## Step 3: the key and the settings, in one terminal window

Open a new PowerShell window (not the one Claude uses):

```powershell
$k = Read-Host "OpenRouter key" -AsSecureString
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new('', $k).Password
$env:DELENTIA_RUN_LIVE_TESTS = "1"
$env:DELENTIA_OPENROUTER_DATA_COLLECTION = "deny"
$env:DELENTIA_OPENROUTER_REQUIRE_PARAMETERS = "1"
cd C:\Users\whale\Delentia\Delentia-OS
```

Use **this same window for every step below.** The freeze records these settings; a window with different ones will be refused. A model that has no provider under `deny` fails the call: that is correct (it is recorded as `not_run`), not a fault.

## Step 4: freeze what will be measured

```powershell
New-Item -ItemType Directory -Force $env:USERPROFILE\daaes-results | Out-Null
$m = (Get-Content research/screen_models_2026-10-16.txt) -join ","
py -3.13 -m research.paid_run_freeze write --models $m --live-prices --stages P0,P1,P1b,P2,P4 --budget-usd 12.10 --provider-cap-confirmed --out $env:USERPROFILE\daaes-results\freeze.json
$env:DELENTIA_FREEZE_FILE = "$env:USERPROFILE\daaes-results\freeze.json"
py -3.13 -m research.paid_run_freeze check $env:DELENTIA_FREEZE_FILE
```

The first command writes the commit, the settings, the models with today's prices, the stage ceilings and the SHA-256 of the criteria file. `check` must print `the run matches the freeze`. It refuses without `--provider-cap-confirmed` (say it only if step 2.3 is done), with a price that is missing or malformed, or if the ceilings add up to more than the budget. From now on every command that can spend money asks this file first; if anything changed (a commit, a setting, a price, the criteria) it names the difference and sends nothing.

## Step 5: P0, the meter (about $0.03, ceiling $0.10)

Pick the cheapest model in the list that has a price (the freeze file shows each model's `price_in_per_mtok` and `price_out_per_mtok`):

```powershell
py -3.13 scripts/calibrate_meter_p0.py <cheap model id> --price-in <its input price> --price-out <its output price> --budget-usd 0.10 --json $env:USERPROFILE\daaes-results\p0.json
```

It sends 24 short requests through the agent's own meter, reads the key's usage figure until it stops changing, and says PASS if the two sums are within 10%. `INCONCLUSIVE` (the usage figure still moving, or did not move) is not a fail: run it again once. **If it says FAIL, stop and send me `p0.json`; nothing else is run until the meter is understood.**

## Step 6: P1, the capability screen (estimate about $3.0, ceiling $5.00)

First look, spend nothing:

```powershell
py -3.13 scripts/full_test_orchestrator.py --tier W --models $m --budget-usd 5 --live-prices
```

It must print `DRY RUN: nothing was sent and nothing was spent` and an estimate (about $3.0, about $4.5 with the margin on 2026-10-26 prices; today's prices are what counts). Then, with the same command plus `--execute --freeze-file`:

```powershell
py -3.13 scripts/full_test_orchestrator.py --tier W --models $m --budget-usd 5 --live-prices --execute --freeze-file $env:DELENTIA_FREEZE_FILE --out $env:USERPROFILE\daaes-results\screen-w.json
```

It stops by itself when a model's spend passes 1.5 × its estimate, when governance (T3) is below 100%, when the account refuses the calls (no credit, a revoked key), or when something that looks like a key appears in any output. Check the spend on openrouter.ai → Activity. Send me `screen-w.json` (it holds no key). **I choose at most three models** (different makers, different prices) and write the choice down **before** P1b starts.

## Step 7: P1b, the menu A/B (about $0.05-0.7 per model, ceiling $1.50 for all)

One chosen model per command. Run the dry run first (leave out `--execute` and `--freeze-file`); it prints the estimate with its margin, and `--budget-usd` is that figure rounded up, never more than what is left of the $1.50:

```powershell
py -3.13 scripts/full_test_orchestrator.py --tier M --models <one chosen id> --budget-usd <the dry run's figure with margin, rounded up> --live-prices
py -3.13 scripts/full_test_orchestrator.py --tier M --models <one chosen id> --budget-usd <the same figure> --live-prices --execute --freeze-file $env:DELENTIA_FREEZE_FILE --out $env:USERPROFILE\daaes-results\menu-m-<name>.json
```

A model priced so that this stage alone would not fit the $1.50 is refused; it is not run here. The result per model is PASS, FAIL or INCONCLUSIVE and is read model by model, never pooled. **A pass changes nothing by itself**: the default menu for hosted models stays the full one until you decide.

## Step 8: P2, the RCT-7 sets (ceiling $1.50)

For each chosen model, once per set (the runner refuses a second look at the same model, prompt and labels). The sheets are in `C:\Users\whale\Delentia`. The four budgets add up to $0.45 per model, so three models fit the $1.50 ceiling; a dearer model needs fewer sets, and the runner stops at the budget you give it:

```powershell
py -3.13 -m research.rct7_holdout run C:\Users\whale\Delentia\RCT7_HOLDOUT_LABELLING_SHEET_FOR_THE_ARCHITECT.md --provider openrouter --model <id> --budget-usd 0.15
py -3.13 -m research.rct7_holdout run C:\Users\whale\Delentia\RCT7_R7_HOLDOUT_LABELLING_SHEET_FOR_THE_ARCHITECT.md --provider openrouter --model <id> --budget-usd 0.10
py -3.13 -m research.rct7_holdout_twoaxis run C:\Users\whale\Delentia\RCT7_HOLDOUT_3_TWO_AXES_SHEET_FOR_THE_ARCHITECT.md --variant plain --provider openrouter --model <id> --budget-usd 0.10
py -3.13 -m research.rct7_holdout_twoaxis run C:\Users\whale\Delentia\RCT7_HOLDOUT_3_TWO_AXES_SHEET_FOR_THE_ARCHITECT.md --variant context --provider openrouter --model <id> --budget-usd 0.10
```

## Step 9: P4, with and without the runtime (ceiling $4.00)

```powershell
py -3.13 -m research.daaes benchmark --provider openrouter --model <id> --arms b0,d0 --seeds 1700-1703 --budget-usd 1.0 --price-in <in> --price-out <out> --out $env:USERPROFILE\daaes-results\p4-tc003
py -3.13 -m research.daaes live --case TC-006 --provider openrouter --model <id> --budget-usd 0.3 --price-in <in> --price-out <out> --out $env:USERPROFILE\daaes-results\p4-tc006
```

The two budgets add up to $1.30 per model, so three models fit the $4.00 ceiling. Four runs per arm are a description, not a finding: no claim of improvement is made unless the interval excludes zero, and then only for that model on that task.

## Step 10: after each stage

* Send me the result file (none contains the key). I add it to `research/RESULTS_REGISTER.jsonl` with the actual cost from the provider's own figure, the configuration and the criteria file, so a result is never recorded without what it cost.
* Check openrouter.ai → Activity against what each stage printed.
* When you are finished: close the PowerShell window; if you will not use the key again, delete it at OpenRouter.

## What a result does and does not prove

Passing P1 says a model chose the right tool and refused impossible goals on short tasks. It does not say which model is better at real work, and it does not say Delentia improves anything: that is P4, with four runs. Whatever the result, it is recorded as it came out.

## Appendix: pin the provider, and the free models

**Pinning the upstream provider.** OpenRouter can send the same model to different providers on each request (different quantization, context window, speed and data policy), which makes a measurement hard to repeat. Set these in the same window as the key (unset = requests unchanged):

```powershell
$env:DELENTIA_OPENROUTER_DATA_COLLECTION = "deny"        # only providers that do not store or train on prompts (some models, especially :free, need allow)
$env:DELENTIA_OPENROUTER_REQUIRE_PARAMETERS = "1"        # only providers that support every parameter we send (JSON mode)
$env:DELENTIA_OPENROUTER_PROVIDER_ORDER = "anthropic"    # (optional) providers in order of preference; when set there is no silent fallback unless DELENTIA_OPENROUTER_ALLOW_FALLBACKS=1
$env:DELENTIA_OPENROUTER_ZDR = "1"                       # (optional) zero-data-retention endpoints only
$env:DELENTIA_OPENROUTER_QUANTIZATIONS = "fp8,bf16,fp16" # (optional) limit the quantization level
```

An unusable value is skipped with a warning and not sent. After a run, `provider.last_served_by` says who answered; it is recorded with the result. `deny` or `zdr` may leave a model with no matching provider; the call then fails, which is correct (it fails instead of sending data where you did not want it).

**Free models (`:free`).** Per OpenRouter's limits page (https://openrouter.ai/docs/api/reference/limits, read 2026-10-25): `:free` models allow 20 requests per minute always; 50 per day if you have bought under 10 credits in total, **1,000 per day once you have bought 10 or more** (purchases, not balance). So adding $15 unlocks the 1,000-a-day tier. A negative balance blocks free models too.

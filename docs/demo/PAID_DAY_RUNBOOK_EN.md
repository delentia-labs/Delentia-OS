# Paid day with real models: step by step (OpenRouter prepaid $15)

For the owner. Run everything in **your own PowerShell** (not the window Claude uses). **Never paste the key into chat, a file or a commit.** The key lives in that one window's memory and disappears when you close it.

This uses the driver `scripts/paid_day.py`, which keeps the whole day under one ceiling. It was rehearsed against a fake OpenRouter that bills in its own counter (no cost). The older `OPENROUTER_KEY_AND_CAP_EN.md` explains each stage by hand and is still useful as background.

**Honest status:** every step passed against the fake (our meter = the fake server's counter, to the cent). **It has never run against the real OpenRouter.** What a real run tells us is what real models do, which no script can tell us.

## How the money is split

| Stage | Question | Ceiling |
|---|---|---|
| P0 | Does our cost meter match the provider's figure? (must pass before anything else) | $0.10 |
| P1 | Which of the 22 models can drive the governed loop (T1, T2 >= 90%, T3 = 100%)? | $5.00 |
| P1b | Compact tool menu vs full menu (only models that passed P1, at most 3) | $1.50 |
| P2 | Do the judge, critic and context judge meet their own rules on sets you labelled? | $1.50 |
| P4 | Does the same job come out differently with and without the runtime (TC-003, TC-006)? | $4.00 |
| | **Sum of ceilings** | **$12.10** |

$15 - $12.10 = **$2.90** is a reserve the key cannot reach (set the key's credit limit to 12.10). Real spending is expected to be much lower.

## Before the day (no key needed)

1. At OpenRouter add **$15 of prepaid credit once** and **turn auto top-up off** (Settings -> Credits). A card adds about 5.5% (minimum $0.80).
2. Revoke the old leaked key (Keys -> Delete) if you have not.
3. Create a new key named `delentia-prepaid-2026-10` with **Credit limit = 12.10**. Copy it once.
4. In `C:\Users\whale\Delentia\Delentia-OS`: `git pull`, then `git status` must be clean (the freeze refuses a modified tree).
5. Use `py -3.13` for every command.

## Step 1: settings, in one window

```powershell
$k = Read-Host "OpenRouter key" -AsSecureString
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new('', $k).Password
$env:DELENTIA_RUN_LIVE_TESTS = "1"
$env:DELENTIA_OPENROUTER_DATA_COLLECTION = "deny"
$env:DELENTIA_OPENROUTER_REQUIRE_PARAMETERS = "1"
cd C:\Users\whale\Delentia\Delentia-OS
New-Item -ItemType Directory -Force $env:USERPROFILE\daaes-results | Out-Null
$m = (Get-Content research/screen_models_2026-10-31.txt) -join ","
```

Stay in this window for every step. The freeze records these values; a window set up differently is refused. A model with no provider that satisfies `deny` fails to answer; that is correct (recorded as `not_run`).

## Step 2: freeze what will be measured

```powershell
py -3.13 -m research.paid_run_freeze write --models $m --live-prices --stages P0,P1,P1b,P2,P4 --budget-usd 12.10 --provider-cap-confirmed --out $env:USERPROFILE\daaes-results\freeze.json
$env:DELENTIA_FREEZE_FILE = "$env:USERPROFILE\daaes-results\freeze.json"
py -3.13 -m research.paid_run_freeze check $env:DELENTIA_FREEZE_FILE
```

Pass `--provider-cap-confirmed` only after item 3 above. `check` must say the run matches the freeze. If prices move during the day it names what differs and sends nothing.

## Step 3: check before spending (free)

```powershell
py -3.13 scripts/paid_day.py preflight --models $m --freeze-file $env:DELENTIA_FREEZE_FILE
```

Every line must be OK. It checks the key, the live-tests opt-in, data-collection denial, the freeze, **that the key has a provider-side credit limit of at most $12.10**, that enough is left for the stage about to run, that every price is known, and that the four RCT-7 sets are sealed. A line marked NO is what to fix first; nothing has been spent.

## Step 4: stage 1 (P0 + P1)

Plan first (no `--execute`, nothing is sent):

```powershell
py -3.13 scripts/paid_day.py stage1 --models $m --freeze-file $env:DELENTIA_FREEZE_FILE
```

Then for real:

```powershell
py -3.13 scripts/paid_day.py stage1 --models $m --freeze-file $env:DELENTIA_FREEZE_FILE --execute
```

Order: P0 with the cheapest model (**if it fails, stop for the day** and send `p0.json`), then P1 with every model. The driver reads real usage from the provider after every command and stops at the stage ceiling. Results go to `%USERPROFILE%\.delentia\paid-day\<date>\` (or `--out-dir`).

At the end it prints the models that **met the rule** (T1, T2 >= 90%, T3 = 100%; a missing figure is inconclusive, never a pass) and proposes at most 3 from different vendors. **Choose only from that list.** If none passes, that is the recorded result and stage 2 need not run (the remaining money stays intact).

## Step 5: stage 2 (P1b + P2 + P4) with the chosen models

```powershell
py -3.13 scripts/paid_day.py stage2 --selected "<id1>,<id2>,<id3>" --freeze-file $env:DELENTIA_FREEZE_FILE
py -3.13 scripts/paid_day.py stage2 --selected "<id1>,<id2>,<id3>" --freeze-file $env:DELENTIA_FREEZE_FILE --execute
```

It writes `selection.json` **before** starting (so the choice is visible before any result), refuses more than 3 models, and runs P1b (menu A/B), P2 (the four RCT-7 sets; each prompt+labels runs once per model) and P4 (TC-003 arms b0/d0, seeds 1700-1703, and TC-006). A model too expensive for a stage to fit its ceiling is skipped, with the reason in the log.

## Step 6: summary, and send the results to be registered

```powershell
py -3.13 scripts/paid_day.py summary
```

You get a per-stage table: commands, exit codes, highest usage against the ceiling, and anything refused. Then:

1. Compare the totals with openrouter.ai -> Activity.
2. Send me the results folder. **No file contains the key** (a test checks this for the rehearsal's output). I read each file, give the verdict the stage's own rule gives (pass / fail / inconclusive / not_run) and add it to `research/RESULTS_REGISTER.jsonl` with the real cost and the configuration. A run without a real cost cannot be registered.
3. Close the PowerShell window; if you will not use the key again, delete it at OpenRouter.

## If something happens

| Symptom | Meaning | What to do |
|---|---|---|
| Refused: ... NO | a preflight line failed | fix that line; nothing was spent |
| STOPPED: over the ceiling | a stage used more than its ceiling | do not rerun; send me the log first |
| P0 FAIL | our meter and the provider's differ by more than 10% | stop for the day, send `p0.json` |
| P0 INCONCLUSIVE | the provider's figure was still moving | rerun once |
| a model has no endpoint under `deny` | the provider has none with that policy | correct: `not_run`, not an error |
| credit gone / 401 / 402 | the account refuses | the driver stops by itself, no retry |

## What the result proves and does not prove

Passing P1 says a model picks tools correctly and refuses goals it cannot do, on short tasks. It does not say which one works better in practice, and it does not say Delentia improves anything: that is P4, with four runs per arm, which is descriptive, not a finding. Nothing is claimed better unless the confidence interval excludes zero, and only for that model on that task. The day does not buy a Hermes comparison, multi-day autonomy, a host or outside users. Whatever the outcome (including a poor one) is recorded and published as it is, with the method, model, cost and limits.

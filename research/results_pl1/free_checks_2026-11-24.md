# PL1 free checks of 2026-11-24 (no model was paid for; nothing here is registered as a result of a PL1 stage)

## B4 (Amendment 1): the local model probe of the note change, descriptive

qwen3:8b through Ollama on this computer (CPU), d0, seeds 5001, 5004, 5029, `--max-seconds 3600`, once at 8f937bbe and once at the change. (A first attempt with a 900 s limit was stopped: about 80-150 s per model call would have cut every episode before its first write.)

| commit | seed 5001 | seed 5004 | seed 5029 |
|---|---|---|---|
| 8f937bbe (before) | `parse_error` in the first episode, no write | same | same |
| the change | INVALID: crash `'NoneType' object has no attribute 'lower'` (B6) | finished without writing | wrote once, approved; the continuation ran the tests 6 times ("we need to verify if the tests now pass"), then finished |

What it shows: nothing about whether the note change works. Before the change this model never reached a write, so there is nothing to compare; after it, the one continuation repeated the test run although each run was in its history (a small model's behaviour, or the same failure in another form: it cannot be told apart from three runs). It found a defect older than the change (B6, fixed in PR #344). It says nothing about haiku's U0 rates.

## A1 (Amendment 2): the 20-minute test of the soak script

First run (B4 was using the processor at the same time): 7 of 8 rules held; "/health never two timeouts in a row" failed with two timeouts at 30 and 45 s, while the first scheduled episodes ran.

/health polled every 0.5 s while ONE job runs on a fresh `delentia serve` (scripted model), worst answer time:

| condition | before (8f937bbe) | after the change |
|---|---|---|
| processor free | 3.2 s, 2.8 s | 3.3 s, 2.4 s |
| all 16 cores busy (16 spinning processes) | 15.0 s | 7.2 s |
| B4 running (first measurement, before only) | 17.8 s | - |
| no job at all (warm-up only) | 5.0 s | - |

So the stall is mostly a matter of a busy processor; the change halves it under load and does not remove it. The 24-hour run must be made with nothing else heavy running (and sleep off). The second 20-minute run (processor free) is reported in the PR.

Second 20-minute run (processor free, after the change): 7 of 8 rules held, /health 0 timeouts in 81 polls. The rule that failed is the memory slope, which the test profile cannot judge: the working set rose from 571 to 689 MB in the first 6 minutes (start-up and warm-up) and then stayed between 670 and 689 MB; the slope "per hour" computed over the last 12-17 minutes is 85, 16 or 39 MB/h depending on the start minute (3, 6 or 8), i.e. noise of about 10 MB multiplied up to an hour. The full profile measures from hour 1 to hour 24, where the same noise is under 0.5 MB/h. The threshold is not changed.

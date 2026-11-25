# Launch Proof Level 1, Amendment 2 (2026-11-24, written before any R1 or A1 run): the settings of R1, the A1 script, the G1 log

## R1: how the 14 runs are run (rules unchanged)

The criteria fix R1 at 14 runs of W09 goal v3, haiku, key limit 0.20, pass = every check in all 14 and 0 hard failures. What they did not fix, and is fixed here before any data:

* **Driver:** `research/pl1/run_r1.py` runs the 14 runs one after the other, each in its own folder; it stops at the first hard failure, continues an interrupted window without running a run twice, and writes `r1_summary.json`. A run that leaves no result stops the window (a tooling defect is read, not retried).
* **Per-run budget 0.20 and token cap 30,000 per model-driven episode.** Why: `research/live_workflows.py` refuses a paid W09 run unless the worst case of its six model-driven episodes (the token cap at the dearer price) fits in half the run's budget, and the freeze refuses a budget above the stage's (0.20). With the default cap (240,000) a run would need $1.44. 6 x 30,000 x $0.5/M = $0.09 <= $0.10. Evidence that the cap does not bind: in 68 earlier haiku W09 runs (round two, `~/.delentia/paid-day/*/r2_3/W09`) the most tokens used by a WHOLE run was 26,124. The key limit (0.20) bounds the whole window; the earlier 14-run windows cost $0.061-0.085.
* **Order:** R1 is bought only after U0b passes (the stop rule of the criteria), at the freeze of U0b's commit or a later one, under its own freeze stage `R1`.

## A1: the script

`scripts/soak_24h.py` implements A1 as written (profile `full`). Its profile `test` compresses the schedule into 20 minutes (jobs every 2 and 4 minutes, webhooks every 4 and 6 minutes, pause at minute 18, audit checks at 5/10/15/20, /health every 15 s) and raises the cron hourly cap to 200 for that profile only (the compressed schedule asks for about 105 runs an hour; the full profile asks for 7 and keeps the default of 60). Read from the rules, as the script reads them:

* "every due occurrence ran exactly once": due times from the dispatcher's own schedule code between the job's creation and the pause (or the end), against the `cron_job` `run` rows of the audit trail; the occurrence due in the last 120 s may be missing; a `throttled` row fails the rule;
* "no job started after the pause": no `run` row and no episode end after the pause whose stop reason is not `paused`;
* "the computer slept": a gap between two /health polls longer than three intervals makes the run INVALID (not repaired afterwards).

The 20-minute test is a test of the script, not an A1 result, and is not registered as one.

## A1: what the 20-minute test found (2026-11-24, written before the change)

The test profile ran (scripted model, 20 min; the B4 local-model probe was using the processor at the same time): 7 of 8 rules held (every due occurrence ran once: 9/9, 9/9, 4/4, 5/5, 5/5; the write job waited 5 of 5 times and wrote nothing; 4 signed webhooks started 4 episodes, 3 forged ones got 401; nothing ran after the pause; 4 of 4 audit checks verified; no restart). It FAILED "/health never two timeouts in a row": the two timeouts were at 30 and 45 s, when the first scheduled episodes ran.

Cause, measured: with the 41-algorithm pipeline on (`delentia serve` turns it on) the FIRST episode of a process takes 20.6 s, about 10 s of it in ALGO-34 loading NLTK and TextBlob the first time; the pipeline's adapters run on the server's event loop, so nothing else answers meanwhile (one /health took 17.8 s). Without a job the warm-up thread alone stalled /health once (5.0 s). The episode started while the warm-up thread (which loads the same libraries) was still running.

Change: before the pipeline's first stage, an episode WAITS for the pipeline warm-up thread if one is running, in a worker thread (`asyncio.to_thread`), so the event loop keeps answering; after it the libraries are loaded and the adapters take milliseconds. No adapter changes; a process with no warm-up thread (tests, one-off runs) is unchanged; the wait is bounded (120 s) and a failed warm-up does not stop the episode. Rule: (a) with a warm-up thread alive, an episode's pipeline does not start before it ends, and the event loop answers meanwhile; (b) the A1 test profile run again shows no two /health timeouts in a row, or the cause of any is read before anything else. The 20-minute runs are tests of the script, not A1 results.

## G1: the log

`research/pl1/dogfood_log.jsonl` starts empty; `python -m research.pl1.dogfood add ...` appends a row with the fields of the criteria and never rewrites one; `report` prints k of n with a Wilson interval and every row.

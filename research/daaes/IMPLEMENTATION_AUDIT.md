# DAAES implementation audit (Round 83)

Question: for each thing the DAAES specification asks of Delentia, what exists in the repository, what ran, and what is only designed? Every row names a file; the catalogue test checks that the files exist.
"Ran" means a test or the zero-cost suite executed it with a scripted model. Nothing here ran with a language model.

## The four things the specification tests Delentia on

| specification item | Delentia component | exists | ran (scripted) | evidence | what is missing |
|---|---|---|---|---|---|
| Persistent Intent (TC-006) | pinned rules (`delentia memory pin`), standing instructions (`context_files.py`), owner policy (`fdia_policy.py`), memory event log | yes | yes: 5 arms, 3 sessions, obedient model, memory pressure, legitimate update | `tc006.py`, `test_daaes_tc006_round83_real.py` | no switch to turn persistent intent off (D3 has to be a replacement behaviour); a live model's own behaviour; two humans contradicting each other |
| Memory Delta (TC-009) | `core/delta_engine` `DeltaEngine` (algo_25), memory event log `memory_eventlog.py`, Delta v2 | yes | yes: 4 stores, 7 faults, storage and latency | `tc009.py`, `stores.py`, `test_daaes_tc009_round83_real.py` | `DeltaEngine` cannot detect a missing or corrupted delta, has no durable form, no version argument; the event log cannot carry non-memory state |
| Crash and Resume (TC-010) | approvals store (`approvals.py`: digest, at-most-once, `OUTCOME_UNKNOWN`), `reconcile_by_receipt` (new), notary | yes | yes: real process termination at 5 points, separate mock API with durable receipts | `tc010.py`, `workflow_child.py`, `mock_api.py`, `test_daaes_tc010_round83_real.py`, `test_reconcile_by_receipt_round83_real.py` | an episode (not only one action) does not resume: only the approval of an action is recoverable |
| Deterministic Replay (TC-025) | audit chain, memory log, episode signatures | yes | yes: R1 state, R2 tool (0 outside calls), R3 decision (with a failing control), tamper matrix | `tc025.py`, `delentia_session.py`, `test_daaes_tc025_round83_real.py` | R4 live re-execution (needs a model); truncation of the newest rows needs an external anchor |
| Autonomous Bug Fix (TC-003) | the governed loop with its tools, sandbox, gate | yes | yes with eight scripted patch policies and faults F1-F3 | `tc003.py`, `tc003_fixture.py`, `test_daaes_tc003_round83_real.py` | a model that can find the fixes (live pilot) |

## The harness around them

| specification item | state |
|---|---|
| Independent oracle outside the agent's workspace | built and tested (hidden tests and answer key are outside the workspace; the oracle runs the agent's package in a clean folder, another process) |
| Common event taxonomy, hash-chained run log | built (`events.py`), torn tail and tamper detection tested |
| Evidence bundle per run + seal + validity rule | built (`bundle.py`); nine ways of altering or thinning a bundle are tested |
| Runner / CLI (`run`, `suite`, `verify`, `checklist`) | built (`runner.py`, `__main__.py`) |
| Model gateway with token and cost logging, hard budget guard | guard built (`budget_guard.py`, 11 tests); the adapter that puts it in front of Delentia's real provider chain is NOT built |
| Hermes arm (H0) | `not_evaluated`: no adapter, the pinned repository has not been cloned |
| Statistics (paired bootstrap, 5-10 seeds, Holm) | exists in the Round 63 research harness (`research/analyze.py`); not yet applied to DAAES cases because the scripted cases are deterministic |
| Live pilot C0-C4 | not run: needs the Architect's key |

## Defects in Delentia that this work found, and what was done

| # | finding | action |
|---|---|---|
| 1 | warm-recall replay bypassed the gate | fixed (earlier PR) |
| 2 | a tainted call to a forbidden path was parked for a signature instead of refused | fixed (earlier PR) |
| 3 | `memory_eventlog.verify()` crashed when a checkpoint column had been retyped | fixed: reported as a problem |
| 4 | a sixth pinned rule dropped the oldest pin silently | fixed: the prompt says how many are not shown; `DELENTIA_MAX_PINNED_SHOWN` |
| 5 | an approval left `OUTCOME_UNKNOWN` by a crash could only be settled by a person | added `reconcile_by_receipt` (asks the provider; a failed lookup leaves it unknown) |
| 6 | `DeltaEngine` computes `DeltaBlock.checksum` and never reads it | NOT changed (algo_25 is in the Architect's public algorithm set); pinned by a test and listed in `INTEGRATION_GAPS.md` |
| 7 | every hash chain misses truncation of the newest rows | known limit; an external anchor catches it; anchors are not configured by default |
| 8 | the runner's own work folders were shared between variants and a locked SQLite file broke the second run (found by the first full suite run) | fixed in this round |
| 9 | a store that sets `DELENTIA_MEMORY_KEYS_DIR` changed the environment of every later run | fixed: each run restores the environment |

## What this audit does not show

It does not show that Delentia helps a model do better work. The scripted model has no judgment, so a pass means the runtime around it behaves as specified. It does not show anything about Hermes.

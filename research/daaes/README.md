# DAAES: the Delentia Autonomous Agent Evaluation Suite (v0.1 specification, Round 83 implementation)

DAAES asks one question five ways: **is a run of the agent runtime recorded, recoverable and checkable, whatever the model did?** Task success is judged by an oracle that is not the agent;
the runtime's own correctness is judged separately, so an agent that fixes a bug while the log of it is wrong does not pass.

The specification and the manifests came with the DAAES v0.1 package (`SPECIFICATION.md`, `cases/*.json`; five unit tests of its reference primitives still pass, unchanged in meaning). What is
here beyond that package was built in Round 83 and is **zero-cost**: no model is called, no key is read, nothing leaves the machine.

```
python -m research.daaes suite --out results         # every zero-cost case on every arm; sealed evidence bundles; SUITE.md
python -m research.daaes verify results/<date>/<case>/<arm>/<seed>
python -m research.daaes checklist --out results     # the seven things that must hold before the first paid model call
python -m research.daaes run --case TC-010 --arm delentia --kill-point after_commit_pre_receipt
```

## What is implemented (milestones M0-M2 of the specification, and the Delentia side of M3 in scripted form)

| case | what it measures | arms | module |
|---|---|---|---|
| TC-009 Memory Delta Integrity | exact reconstruction against an independent reducer; 7 faults (partial write, duplicate, out of order, missing parent, corrupted checksum, snapshot crash, stale writer); storage and latency | `ref_snapshot` (the full-snapshot baseline, D4's replacement), `ref_delta` (a durable reference delta log), `delentia_delta_engine_r82` (the `DeltaEngine` used the way it was until Round 82, kept as the "before"), `delentia_delta_log` (the engine after Round 83: `DeltaEngine.versioned_log()`), `delentia_memory_log` (Delentia's memory event log; memory records only) | `tc009.py`, `stores.py`, `state_fixture.py` |
| TC-025 Deterministic Replay | R1 state replay at every recorded point, R2 tool replay with a counter of outside calls, R3 decision replay with a control that must fail, R4 as scripted variance; six tampers plus truncation, on the run log, Delentia's audit chain and Delentia's memory log | `delentia`, `event_log_baseline` | `tc025.py`, `events.py`, `delentia_session.py` |
| TC-010 Crash and Resume | a 12-stage order workflow; a separate mock API with durable receipts and idempotency keys; the agent process is terminated for real at five points | `reference`, `naive_new_key` (the control that must fail), `delentia` (approval store + reconciliation by provider receipt) | `tc010.py`, `workflow_child.py`, `mock_api.py` |
| TC-006 Persistent Intent | three sessions over the same files, an obedient (hijacked) scripted model, memory pressure, a legitimate update | `delentia_full`, `delentia_full_cap8`, `delentia_full_careless`, `pins_only_careless`, `no_persistent_intent` | `tc006.py` |
| TC-003 Autonomous Bug Fix | `ledgercalc` with five seeded defects; the oracle diffs the workspace, runs hidden tests elsewhere, compares the agent's claim; faults F1-F3 | `b0_direct`, `d0_delentia`; eight scripted patch policies | `tc003.py`, `tc003_fixture.py` |
| model gateway + hard budget guard | experiment-wide limits enforced before each call, across runs, surviving a crash; unknown price fails closed; no automatic paid fallback | - | `budget_guard.py` |
| evidence bundles | `manifest, fixture hash, events, receipts, checkpoints, agent/oracle/score/replay/environment` + a seal (hashes, optional Ed25519 signature by a key kept outside) and a validity rule | - | `bundle.py` |

Also here: `live_adapter.py` (the governed loop with the budget guard in front of a real provider code path, rehearsed against a fake paid endpoint), `catalogue.py` (the thirty cases of the research and where each stands), `checklist.py` (the pre-API checklist decided from sealed bundles), and four documents:
`IMPLEMENTATION_AUDIT.md`, `INTEGRATION_GAPS.md`, `DAAES_ADAPTER_PLAN.md`, `ABLATION_READINESS.md`.

## What the numbers mean, and what they do not

- A scripted model has no judgment. Every `scripted_proven` result is about the **runtime** around a model that does what its script says. It is not evidence that any language model does well.
- The expected outcomes were written in the specification before anything ran; the weights are the specification's proposals and are fixed in the module docstrings. Each check has a control that is
  designed to fail (a naive workflow that duplicates, a stricter policy for R3, a verifier forced to say "ok", a store with a wrong reducer, a conftest that forces a pass), and a test proves it does.
- The pass rule everywhere is: score at or above the threshold AND every critical assertion AND no hard fail. A high score never rescues a hard failure.
- Not evaluated, and reported as such rather than as a failure: Hermes (no adapter), any live model, a host that runs for days, an independent witness.

## What the first complete run found about Delentia

1. **`DeltaEngine` (algo_25) rebuilt exact states, and could not tell when a delta was missing or corrupted.** It computed a `DeltaBlock.checksum` and never read it; it had no durable form, no version
   argument and no concurrency check. Under the fault matrix: two silent wrong states (hard failures), three capability gaps (score 59.5, fail). **Fixed in Round 83** on the Architect's instruction
   (`rct_control_plane/delta_log.py`): the same fixture and faults now give 25/25 exact versions, 7/7 faults detected or refused, 0 hard failures (score about 99, pass). It is the contract a delta design must meet,
   not evidence that deltas beat snapshots; the runtime's hot path does not use the log yet.
2. **The memory event log detects every storage fault** (partial write, missing event, corrupted event, damaged checkpoint) and recovers after a restart, but it carries memory records only and has
   no version argument: a stale writer overwrites silently (`lost_update`). A damaged checkpoint column used to crash `verify()`; it is now reported.
3. **Every hash chain (run log, audit chain, memory log) misses truncation of the newest rows.** Only a signed head kept elsewhere catches it. Anchors exist in Delentia (witness, notary) and are not
   configured by default.
4. **A pending approval whose process dies was unrecoverable except by a person.** `reconcile_by_receipt` now settles it by asking the provider (tested with five kill points and a separate API).
5. **A sixth pinned rule pushed the oldest (often the goal) out of the prompt without a word.** The prompt now says how many pinned rules are not shown, and `DELENTIA_MAX_PINNED_SHOWN` raises the cap.
6. **The owner policy, not the pinned rules, is what stops an obedient model.** Pins are shown; only the policy enforces. A careless human who signs everything still cannot make a denied path run.
7. ROUTE (ALGO-21) caps a FAST goal at three steps; the long scripted cases switch it off. A benchmark must say whether ROUTE is on.

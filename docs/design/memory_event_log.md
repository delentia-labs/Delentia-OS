# Memory as an append-only event log (M4, built as v1 in Round 66)

Status: **v1 is implemented and opt-in** (`rct_control_plane/memory_eventlog.py`, `DELENTIA_MEMORY_EVENTLOG=1`). Everything under "Not built" is design only.

## Why a log and not a smarter table
Round 65 measured that a delta log is no smaller than snapshots compressed with zstd (within 3%), so bytes are not a reason to change the store. What a log gives that a table cannot:
history (what could the agent know when it did that?), revocation as a recorded fact with its reason, provenance that cannot be edited without breaking a hash, and a bounded blast radius for damage.

## The model
- One table `memory_events`, hash-chained across all people: `seq`, `namespace`, `kind` (`add`, `touch`, `revoke`, `edit`), `memory_id`, `payload` (canonical JSON), `provenance` (`{tainted, source_tool}` as the loop wrote it), `created_at`, `prev_hash`, `event_hash`.
- The `memories` table stays the working copy the code reads. Each writer (`save_memory`, `touch_memory`, `revoke_memory`) writes the event in the **same transaction**, so a crash cannot leave one without the other.
- `fold(namespace, upto_seq)` rebuilds a person's memory at any moment; `consistent_with_table` proves the fold equals the table (a write that bypassed the log shows up as a difference).
- Checkpoints (`memory_checkpoints`): the whole state of one person, zstd-compressed and hashed. The interval grows with the size of the state (at least K events and at least half as many events as live items), because a fixed interval made the checkpoints grow as n^2 (measured: 97 checkpoints of a 5,000-operation log were 8x the table).
- `export_archive` / `verify_archive`: one zstd stream (events + final state) that a third party re-checks without the database.

## Measured (scripts/measure_memory_pipeline_round66.py, research/memory_pipeline_round66.json)
- replay equals the table in every workload from 100 to 5,000 operations; the same with and without checkpoints;
- cost of writing the event: about 0.2 to 0.9 ms on a 9 to 10 ms write (2 to 10%); a whole 128-episode scripted run is identical with the log off and on (outcomes and per-episode time);
- bytes: events + checkpoints about 2.8x the table (the log holds the history the table does not); the zstd archive is 0.44 to 0.47x of a zstd dump of the database;
- damage: one edited event is always named by `verify`; with a checkpoint interval of 20 to 100 events the history that can no longer be rebuilt is a few dozen events, and in about one case in twelve the newest state is also wrong (a damaged event after the last checkpoint).

## Read-time policies (Q2: what the model is shown)
`select_for_recall` (`DELENTIA_MEMORY_POLICY`): `none` (default), `dedupe`, `expire`. Nothing is deleted or rewritten. Measured: `expire` cuts 62 to 67% of the offered text but **drops the needed rule in 2 of 5 single-copy cases** (an old episodic memory without a newer copy); `dedupe` cuts about 6% on that data and never dropped a needed item; neither changed a scripted trajectory's outcome, and top-5 recall already kept both needed memories in 30 of 30 crowding trials with or without `dedupe`. So the default stays `none` until a capable model's run shows a benefit.

## Not built (design)
1. **Erasure (PDPA).** The log keeps text, so revocation is not erasure. Design: encrypt each person's `payload` and `provenance` with a per-person data key (stored outside the database, one file per person); chain hashes are computed over the ciphertext, so destroying the key makes the person's text unrecoverable while the chain still verifies. Needs a key custody decision (same OS-user problem as the audit key).
2. **Anchoring.** Append the log head (`seq`, hash) to the audit chain every N events so the A3 witnesses cover the memory log too; today the log is chained but not anchored.
3. **Edits.** `edit` is in the event vocabulary and the fold, but no writer emits it yet (there is no edit tool). Revoke-and-add is the supported way.
4. **A reader for time travel in the Desk** (show what the agent knew at episode X); the API is `MemoryEventLog.fold(namespace, upto_seq)`.
5. **Delta of the text.** Only worth considering if events grow large (long documents stored as memories); the measurements say a stream of zstd already captures most of it.

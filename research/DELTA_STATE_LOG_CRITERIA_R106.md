# Round 106: the Delta Engine joins the main path (criteria written before the code)

## What was found by reading the code (2026-10-30)

The governed loop's RECORD step builds a `DeltaBlock` for every episode and stores it with `self._delta_engine.store_delta(...)`. `self._delta_engine` is a fresh in-memory `DeltaEngine()` made in the
loop's constructor. When the process ends the record is gone, and the text it carried (the goal, in `change_description`) never reached a durable place anyway. So the cycle's RECORD step has had a
Delta part that nothing could read afterwards. The durable, verified log of Round 83-84 (`delta_log.VersionedDeltaLog`, 25/25 exact states, 7/7 faults detected) is called by nothing in the runtime.

## What will be wired

One durable `VersionedDeltaLog` per person (file named by a hash of the namespace, under the data home), written at the end of every governed episode. The state it carries is the person's
AGENT STATE as numbers and hashes, never text:

    episodes, verified_episodes, stopped (count per stop reason), tool_calls, cost_usd, growth_G,
    memory_head (event-log chain hash and count for this person), skills_count, audit_head (hash and id of the audit row of this episode),
    last_episode: {id, stopped_reason, iterations, verified, at}

No goal, no answer, no tool argument, no memory text. That keeps the log outside the erasure problem (nothing personal to scrub) and is a rule a test checks: the raw file is scanned for words of the
episodes it recorded.

Every `DELENTIA_STATE_LOG_ANCHOR_EVERY` (default 25) versions the head is written into the audit chain (`anchor_to_audit`), so cutting the newest versions or rewriting the history is detected even by
someone who can recompute the log's own hashes.

New: `delentia state-log show|verify|at <version>|diff <a> <b>` and a Governance control (on or off, how to switch it, the verify result). `DELENTIA_STATE_LOG=off` turns it off. A failure of the log
never changes an episode's outcome (best effort, reported in `result["state_log"]` as `{"version": n}` or `{"error": "..."}`).

## What this is and is not (written before measuring, so it cannot be bent afterwards)

It is: a durable, checked history of what the person's agent was at every episode, which can be rebuilt exactly at any version, and whose damage or truncation is detected.

It is NOT a claim that recall is better, that memory is smaller or that deltas beat snapshot + zstd (Round 65 measured the opposite for size; the memory event log of Round 66 already carries the
memory text and its history, sealed per person). The wiring is justified by what it makes checkable, not by a compression figure.

## Pass rules (each is a test; a failed one is reported as failed)

W1 (exact)         After 200 scripted episodes of three people, `state_at(v)` equals the state recorded at episode v for every v, for every person.
W2 (cost)          The added time per episode, median over 200 episodes, is at most 15 ms and p95 at most 40 ms on this machine (measured against the same run with the log off).
W3 (size)          The log of one person after 1,000 episodes is at most 1.5 KB per episode on average, and verify() of it takes at most 2 s. (If it is not, the snapshot interval is tuned ONCE and both numbers are reported.)
W4 (faults)        The seven TC-009 faults applied to a real file written by real episodes (changed delta, removed delta, truncated newest versions, duplicate, out-of-order, damaged snapshot, partial write) are each detected by `verify` (truncation: by `verify_against_audit` with the anchor).
W5 (no text)       A scan of the raw bytes of the log files finds none of the distinctive words of the goals and answers of the 200 episodes.
W6 (outcome)       An unwritable log path (a directory where the file should be) leaves every episode's final answer and stopped_reason identical to a run with the log off, and reports the error.
W7 (concurrency)   Eight threads each running 25 episodes for the same person produce 200 versions with no lost and no duplicated episode (the episode counter in the last state is 200), and no episode fails.
W8 (off)           With `DELENTIA_STATE_LOG=off` no file is created.
W9 (erasure)       `erase_person` for one of the three people leaves the other two logs verifying and unchanged, and its report names the state log as "numbers and hashes only, no personal text held".

If W2 or W3 fail the default is switched to off and the reason is written in the Round 106 document; the code stays.

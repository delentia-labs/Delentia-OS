# RCT-7 stage R-1: the intent compiler reads work requests (criteria, written 2026-11-25 before the goal set exists and before any measurement)

Plan: `research/RCT7_IMPROVEMENT_PLAN_R116.md` (PR #347) and its detailed form `research/RCT7_DEVELOPMENT_PLAN_R116.md`.

## What is measured

Two things the THINK step needs before it can be a plan, read from a request's own words, with no model:

1. **The kind of work** (`IntentType` of `rct_control_plane/intent_schema.py`): what the runtime's `IntentCompiler.compile()` returns.
2. **The constraints the request states in plain words**, as kinds: `language`, `format`, `max_words`, `max_chars`, `item_count`, `required_artifact` (a file to produce), `forbidden_effect` (a file, folder or category of files not to change: "do not modify the tests", "leave config alone", "ห้ามแก้ไฟล์เทสต์"), `preserve_interface` (signatures or a public API unchanged), `budget` (money), `deadline` (time). What counts as detected: the union of what the compiler's constraints and `mismatch_rules.conditions_for()` report, mapped to these kinds by a fixed table written with this file (`research/rct7/r1_measure.py`).

## The set

80 requests, written by the assistant (Claude) before any measurement, in the style of the 12 master workflows, the PL1 tasks and the Desk examples: about two thirds English and one third Thai, every intent type at least four times, half of them with one or more stated constraints, ten that are questions (no change wanted). Each is labelled with its intent type and its stated constraints. The split is fixed by a hash of each request's id before anything is measured: 60 development, 20 held out. The held-out 20 are sealed (their SHA-256 is written into the set file) and measured ONCE, on the code frozen after development.

Stated limit: the labels are the assistant's, not independent. The owner may relabel the held-out 20 before the held-out run; his labels then replace the assistant's.

## Pass rules (held-out 20 only)

* intent type right in **at least 18 of 20**;
* in the requests that state constraints, every stated constraint kind detected in **at least 80%** of them (rounded down), and over the whole 20 **at most 2** constraint kinds reported that the request does not state;
* **no** question request (labelled QUERY) classed as a type that changes something, and no change request classed as QUERY.

If any rule fails, R-1 is not done; the failures are read before any further change, and a new held-out set of 20 is written before a second attempt (this one is then spent).

## What it does not show

That a model plans better, or that a task succeeds more often. R-1 only makes the plan's raw material correct. Whether the plan helps is stage R-3 (paid ablation).

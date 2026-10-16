# DAAES integration gaps (Round 83)

What stands between the scripted DAAES cases and the same cases run with a real model, a real host and a comparison system. Ordered by what blocks the most.

| # | gap | blocks | who can close it | cost |
|---|---|---|---|---|
| G1 | no capable-model key in this environment | live pilot C0-C4, every `needs_model` case, any claim that Delentia helps a model | the Architect (a prepaid, rotated OpenRouter key set in his own terminal) | the Pre-API checklist first; then the capability screen of about $5 |
| G2 | ~~the budget guard is not in front of Delentia's provider chain~~ CLOSED in Round 83 (`live_adapter.py`; 8 tests against a fake paid endpoint). Still open: it has not stood in front of a real model, and it cannot see a request already on its way, so a prepaid provider-side limit stays mandatory | - | - | - |
| G3 | Hermes adapter | every H0 arm | Claude, after a pinned clone (downloads were allowed earlier; a new clone needs the Architect's yes for the pin) | none until a model is used |
| G4 | ~~`DeltaEngine` has no integrity check, no durable form, no version argument~~ CLOSED in Round 83 on the Architect's instruction (`delta_log.VersionedDeltaLog`, `DeltaEngine.verify_session`, strict mode). Still open: the runtime's hot path does not call the log; personal text must not be stored in it (no per-person sealing) | any claim that "Delta" protects memory in the running agent | the Architect decides whether the runtime should use it (where, and for which state) | days |
| G5 | the memory event log carries memory records only | TC-009 on projects, tasks, intents and links | the Architect decides whether tasks and intents belong in the memory log or in a second log | design first |
| G6 | an episode does not resume after a crash; only the approval of an action does | TC-010 beyond the approval | design: persist the episode's step list and resume at the first step without a receipt | days |
| G7 | no external anchor by default | truncation of the newest rows goes unnoticed on every chain | the Architect (witness Worker `host-1` key, a host) | $0 |
| G8 | D3 now exists as the research variant `A111+NI` (pinned rules, profile and standing instructions hidden; every gate stays); D4 for the runtime is a configuration of the memory log's checkpoint interval; D5 (no witness) is the default | the ablation runs themselves, which need a model | - | none |
| G9 | two humans giving contradictory instructions (TC-007) and a planner agent overruled by another agent (TC-020) | those two cases | design | days |
| G10 | no host that runs for days | TC-012, soak runs | the Architect (Oracle out of capacity; this PC is the interim host) | $0 or about EUR 5 a month |
| G11 | the first complete suite run uses wall-clock latency in TC-009 | latency numbers differ between machines and with load | only compare latency within one run | none |

## Gaps in the harness itself

- Scripted policies are written by the author. They are the cases the author thought of. A real adversary or a real model finds others; the Round 66 adaptive attacker and the external attack menus (Round 67) cover some of that for the shell gate, not for DAAES.
- TC-003's `ledgercalc` fixture has five defects. Five is enough to test the oracle, not enough to rank models.
- The `delentia` arm of TC-025 and TC-010 runs Delentia's own stores; the `event_log_baseline` and `reference` arms are mine. If I wrote the baseline weak, Delentia looks better. The baselines are small (a hash-chained JSONL file; an idempotency-key workflow) and are public in this folder, so a reader can judge them.
- All results are for one operating system (Windows 11) and one Python (3.13).

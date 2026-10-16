# DAAES adapter plan (Round 83)

The specification asks every system under test (B0, H0, D0-D5) to sit behind one contract so the same case runs on each. This is the plan for the adapters, in the order they can be built.

## The contract (specification section II)

An adapter takes a case's fixture and workspace, runs the agent, and returns: the final workspace, a stream of events in the shared taxonomy, the tool-call receipts, and the cost meter. The oracle never trusts the adapter's summary.

## Adapters

| arm | adapter | state | what it needs |
|---|---|---|---|
| reference store / reducer | `stores.py` (`ref_snapshot`, `ref_delta`) | built | - |
| `event_log_baseline`, `reference`, `naive_new_key` | in `tc025.py`, `tc010.py` | built | - |
| D0 Delentia (scripted) | `delentia_session.py`: a `GovernedAutonomousLoop` driven by a scripted model over the real gate, approvals, audit chain and memory log | built | - |
| D0 Delentia (live) | the same session, with the scripted model replaced by `build_governed_loop()`'s provider | NOT built | G1 (key), G2 (guard in front of the provider) |
| B0 minimal LLM + tools | `research/plain_agent.py` exists (a plain agent without Delentia's loop); needs the DAAES event taxonomy emitter | partly | G1 |
| H0 Hermes | none | NOT built | G3: a pinned clone, an isolated venv, an emitter that maps Hermes' tool calls to the taxonomy; where Hermes lacks a capability the arm is `not_evaluated`, never a failure |
| D1 no RCT | `research_switches` `R=0` | switch exists | research mode and a `research-` namespace |
| D2 no FDIA | `research_switches` `F=0`: no numeric threshold, the floor and the owner policy stay (the specification requires an outer gate to remain) | switch exists | same |
| D3 no persistent intent | replacement: an episode is given the session's own context only (no pins, no standing instructions, no goal memory) | NOT built | a small switch in the prompt builder, behind research mode |
| D4 no delta | replacement: full snapshots (`ref_snapshot` in TC-009; for the runtime, a memory store that writes whole states) | TC-009 only | a snapshot store for the runtime would be a new component: not built, and not worth building before a result asks for it |
| D5 no witness | replacement: no external anchor (the default today) vs. an anchor configured | the default already is "no witness" | G7 for the "with witness" side |

## Order

1. G2: the guard in front of the provider chain, proven against a fake paid endpoint (no money).
2. The live D0 adapter, run against the same fake endpoint to prove the event stream.
3. The B0 emitter.
4. Only after the Architect supplies a key: the capability screen (does any model drive the loop?), then the live pilot.
5. Hermes (H0) only if the pilot shows a result worth a comparison; it is a day's work and a risk of an unfair comparison, so it is deliberately last.

## Rules the adapters must keep

- Fresh workspace per run; the oracle and hidden tests outside it.
- The run's cost is metered by the guard, not by the adapter's own claim.
- An unknown capability is `not_evaluated`.
- Per-model results are reported separately, never pooled (Delentia's format-repair and VERIFY rules were tuned on one small model).

# Ablation readiness (Round 83)

The specification's rule: removing a core function is not a fair ablation. Each ablated arm must keep basic task and tool ability through an explicit replacement behaviour, and the manipulation must be checked after every run.

| arm | what is ablated | replacement behaviour | exists | manipulation check |
|---|---|---|---|---|
| D0 | nothing | - | yes | - |
| D1 | RCT-7 | the generic plan-act-check text (arm GP in the research harness) | yes (`R=0`, `generic_plan`) | yes: prompt has no RCT-7 text and the end check is the generic comparator |
| D2 | FDIA numeric gate | no numeric threshold; the floor, the owner policy and the taint gate stay as the outer gate | yes (`F=0`) | yes: no gate row carries a threshold above 0 |
| D3 | persistent intent | the session's own context only | yes (`A111+NI`, Round 83) | yes: no pinned rule, profile or standing instruction in the prompt, the numeric gate and the rest of the full system on |
| D4 | Delta | full snapshots | TC-009 only (`ref_snapshot`) | the arm's storage numbers differ from the delta arms by construction |
| D5 | witness | no external anchor | already the default | the witness status says none configured |

## Honest limits

- D3 cannot be built by deleting pins from the table: a pinned rule is also what the owner wrote to stop things. The replacement keeps the owner policy and the gate (they are not "intent", they are enforcement) and removes only what is shown to the model as intent. Result: D3 measures *what showing intent adds on top of enforcement*, which is the question TC-006 asks.
- The scripted TC-006 result already says the enforcement did the protecting (the policy), and the pins informed. A live model arm decides whether informing helps.
- D4 for the whole runtime would need a snapshot-only memory store. The runtime's memory is an event log with checkpoints; "no delta" there is checkpoint-every-write, which is a configuration (`DELENTIA_MEMORY_CHECKPOINT_EVERY`), not new code. To be measured in the live pilot, not before.
- Each arm is reported per model. A pooled number across models would hide that the repair and VERIFY rules were tuned on one.

## Prerequisites before any ablation

1. The capability screen (G1) finds at least one model that drives the loop above the K.1.5 line.
2. The budget guard (G2) is in front of the provider.
3. The arm labels and manipulation checks are in each episode's audit row (true for R/F/M and, since Round 83, for the NI variant's receipt). The NI contrast is not in the registered protocol: it needs an amendment (version bump) before it is analysed.

# RCT-7 — Reverse Component Thinking

RCT-7 is the creator's structured method for understanding a request, planning work and comparing its result with intent. It is a design requirement; labels in a prompt, a successful compile or an attestation hash do not demonstrate that every requirement is implemented.

## Requirements and inspected implementation

The implementation references below describe `ec4059c803ba6b0faedab7266d8073a77d93eb3e`. This documentation update does not change the runtime.

| ID | Step | Required observable behaviour | Current evidence and gap |
|---|---|---|---|
| R1 | Observe | Record known facts, sources, unknowns and assumptions separately | `AlgorithmKernel41.algo_04_rct7` captures input; `data_evidence.assess` names missing evidence. A complete shared unknowns record is not established. |
| R2 | Analyze | Connect the preliminary intent to context, relations and constraints | The compiler extracts type, scope and constraints. Classification alone does not establish all relationships. |
| R3 | Deconstruct | Produce goal-dependent components with important dependencies, inputs and outputs | ALGO-04 reports extracted constraints. That does not establish a component/dependency plan covering every acceptance criterion. |
| R4 | Reverse reasoning | An inspectable chain from desired result to necessary conditions and supporting evidence/actions | ALGO-04 step 4 reports risk and I/scope bonuses. This output is not a backward dependency chain. |
| R5 | Identify core intent | Resolve intent and criteria; ask and wait when unresolved ambiguity affects the result | Compilation validation and classification clarification suggestions exist. A shared end-to-end clarification/resume path is not established by those fields. |
| R6 | Reconstruct | Show the user a plan before producing the artifact, traceable to intent | `_format_rct7_plan` puts steps 1–6 in model context; that alone does not show a plan to the user. UI/CLI/API ordering needs separate coverage. |
| R7 | Compare with intent | Compare result/effects to criteria; report mismatch, ask and pause before further work; retain original intent and confirmed revisions | `_verify_against_intent` uses similarity, refusal and grounding checks; failed verification suppresses positive learning. The inspected episode-end path does not implement the full mismatch/question/wait/resume contract. |

Deconstruction should be deep enough to assign each criterion and retain material dependencies. It need not split every task into a fixed number of parts or into the smallest imaginable units. A backward chain is a visible planning artifact, not evidence of every internal LLM reasoning operation.

## RCT-7 and the Constitutional Cycle

The episode lifecycle is **GUARD → THINK → ROUTE → ACT → COMPRESS → VERIFY → RECORD → LEARN**. RCT steps 1–6 participate in THINK; outcome comparison participates in VERIFY. The cycle includes policy enforcement, tool execution, compression, audit and feedback as well as reasoning. Logging and compression can occur repeatedly during execution.

A plan in the prompt is distinct from a plan visible to the user. Showing a plan does not add a new mandatory approval for every plan: action permissions continue to follow the owner's policy. An intent mismatch requiring clarification must actually wait; elapsed time is not confirmation.

LEARN can store/retrieve experience and selected skills under runtime rules. It does not automatically train the main LLM. The algorithm adapter pipeline (`understand → recall → plan → act → verify → compress → record → evolve`) is a further implementation grouping, not a replacement definition of RCT-7 or the Constitutional Cycle.

## Acceptance cases to cover

- Missing decision-critical data remains unknown; ask instead of fabricating it.
- Changing the goal changes analysis/components while preserving source facts.
- Backward links identify missing prerequisites; a risk report alone does not pass R4.
- Ambiguous intent waits for clarification when the alternatives materially differ.
- A visible plan event precedes the relevant artifact/effect on each supported entry point.
- A language, format or constraint mismatch reports the difference and asks; no repair effect occurs on a path required to wait.
- A confirmed change preserves the original intent and records a revision before replanning.
- Correct short answers are assessed against criteria/evidence, rather than lexical overlap alone.
- Restart during clarification preserves waiting state and does not trigger execution.

These are requirements and proposed regression cases, not a claim that this update implemented or passed them all. Inspect existing state, journal and entry-point paths before adding fields or modules.

## Source and further reading

- [Kernel implementation](../../rct_control_plane/algorithm_kernel_41.py), `algo_04_rct7` and `benchmark_result_against_intent`
- [Governed loop](../../rct_control_plane/governed_autonomous_loop.py), `_on_episode_start`, `_format_rct7_plan`, `_verify_against_intent`, `_on_episode_end`
- [Intent compiler](../../rct_control_plane/intent_compiler.py), [data evidence](../../rct_control_plane/data_evidence.py) and [grounding checks](../../rct_control_plane/verify_grounding.py)
- [FDIA semantics](fdia.md), [gate properties](../../research/GATE_PROPERTIES.md), [research protocol](../../research/PROTOCOL.md)
- [Current public information](../public/CURRENT_PUBLIC_INFORMATION_EN.md) and [release levels](../release/RELEASE_LEVELS.md)

No end-to-end RCT accuracy percentage, fixed universal threshold, tier mapping or protocol variant is asserted here without a scoped specification and run evidence.


## Explicit acceptance-contract path

An experimental opt-in path now persists declared acceptance criteria, shows a plan before execution in the CLI/HTTP flow, and records a mismatch as a durable clarification wait with confirmed revisions. See [intent contracts](intent-contracts.md) for the supported predicates, restart behaviour and limitations. This does not change the legacy/default path or establish complete R1–R7 fidelity.

## Declared planning context follow-up

The optional [declared RCT context](rct-declared-plans.md) adds typed reported facts/sources, unknowns/assumptions, criterion-linked component dependencies, and a durable critical-input wait before model/tools. Explicit answers produce a revised visible plan. This advances observable structure for R1/R3/R4/R5 on the documented CLI/API path. The context is supplied by the user; it does not establish autonomous semantic decomposition or complete RCT-7 across entry points. The historical base table above remains a dated inspection, not the latest implementation claim.

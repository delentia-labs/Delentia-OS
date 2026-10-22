# Delentia Current Public Information

English v0.3 · 22 October 2026 · Public brief adapted from the creator-confirmed v0.3 definitions

## 1. What Delentia is today
**Delentia OS is an open-source project developing a self-hosted, intent-centric AI agent runtime.** It contains an agent loop, tools, memory, skills, scheduling and subagents, together with RCT-7 workflow structure, FDIA/owner-policy controls and auditable records. Operators choose the model and manage installation. “OS” describes the organisation of agent work above an existing operating system. The project is experimental, with public code and supervised operation on its creator’s machine.

## 2. The questions behind it
Ittirit Saengow, who describes himself as a thinker, identifies **28 June 2025** as the start of the project, including FDIA Equation and RCT 7 Thinking, on paper and in conversations with ordinary AI chat. FDIA began with **“What is the future?”** and his view that people shape their futures through data, experience, intent and action. He later asked how AI could work through a process and intent we design while humans retain decision authority. **11 August 2025** marks a separate personal turning point and commitment. These are the creator's account, distinct from publication timestamps.

## 3. The roles of FDIA and RCT
**FDIA Equation, F = (D^I) × A**, has no approved expanded name. It originated as Future (actual outcome), Data (reality and constraints), Intent (clarity, depth and persistence) and Architect (the responsible human designer). The runtime uses a computational interpretation alongside policy and verifiable approvals; enforcement depends on code controlling execution. **RCT-7, Reverse Component Thinking**, follows Observe → Analyze → Deconstruct → Reverse reasoning → Identify core intent → Reconstruct → Compare with intent. The creator requires explicit unknowns, an inspectable backward dependency chain, a plan shown before the final artifact, and a pause for user clarification on an intent mismatch. Planning representations and outcome checks exist; fidelity to the full requirements remains to be tested. **Delta → RCTDB → Intent Loop** links information, experience and feedback under system rules.

## 4. Existing evidence
Public code includes the governed loop, signed approvals, audit chain, memory and episode journal. Scripted demos replace the model with a fixed program while using real tools and gates. Repository documentation reports scripted whole-job runs for 12 workflows and a CI checkpoint of **7,820 passed, 43 skipped and 1 xfailed**, dated 18 October at `3dbed0d`. These are scoped engineering observations, not whole-system safety certification.

## 5. What remains to be tested
Priorities include capable-model evaluation, baselines and ablations for RCT-7, numeric FDIA and persistent-intent feedback, outside reproduction, and deployment-specific reliability, recovery and witness checks. The reviewed status documents report no capable-model results for the 12 workflows and no external pilot. Different Delta components have different integration boundaries.

## 6. Where to start and help
Start with [Delentia-OS](https://github.com/delentia-labs/Delentia-OS), read [release scope](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/release/RELEASE_LEVELS.md), then try the [scripted demo](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/demo/QUICKSTART_EN.md) at a recorded version. Report steps, expected/observed results and environment in [Discussions](https://github.com/delentia-labs/Delentia-OS/discussions) or [Issues](https://github.com/delentia-labs/Delentia-OS/issues). Follow [SECURITY.md](https://github.com/delentia-labs/Delentia-OS/blob/main/SECURITY.md) for vulnerabilities.


## Sources and scope

- [Release levels](../release/RELEASE_LEVELS.md) and [readiness snapshot](../release/READINESS_SNAPSHOT.md)
- [Dated test checkpoint](../testing/TESTING_CANONICAL.md)
- [RCT-7 requirements and implementation](../concepts/rct-7-thinking.md), [FDIA semantics](../concepts/fdia.md) and [gate properties](../../research/GATE_PROPERTIES.md)
- [Master workflows](../../research/MASTER_WORKFLOWS.md) and [research protocol](../../research/PROTOCOL.md)

Implementation reference: `ec4059c803ba6b0faedab7266d8073a77d93eb3e`. The quoted CI count and workflow status are repository-reported checkpoints. New local smoke checks do not replace the full CI checkpoint or establish capable-model success. Origin dates are the creator's account, distinct from independent priority evidence. This page excludes the internal review inventory and private source paths.

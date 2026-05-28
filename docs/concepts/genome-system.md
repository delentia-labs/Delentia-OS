# Genome System — Seven Interconnected AI Modules

> This document is part of the [RCT Platform concepts documentation](https://rctlabs.github.io/delentia-os/concepts/).  
> For the full architectural article, see: [delentia.com/en/blog/rct-7-genome-system](https://delentia.com/en/blog/rct-7-genome-system)

---

## Overview

The **7 Genome System** is the architectural metaphor describing how the RCT Platform's seven core modules form a closed, circular system — where each module both depends on and informs the others.

Unlike traditional AI frameworks that treat components as isolated modules, the Genome System creates a living architecture where all genomes share the same foundational data schema (derived from G1), enabling them to communicate without O(N²) interface contracts.

---

## The Seven Genomes

| ID | Name | Role | Color |
|---|---|---|---|
| G1 | Architect's Genome | Master knowledge scaffold and constitutional constraints | `#D4A853` |
| G2 | RCT Codex Genome | 41 algorithms + FDIA equation + decision trees | `#89B4C8` |
| G3 | JITNA Genome | Dynamic routing: LLM selection, algorithm tier, processing path | `#C4745B` |
| G4 | ARTENT Genome | Personal Agent OS: Intent Omnibox, Memory Timeline, Sovereignty Vault | `#7B9E87` |
| G5 | SignedAI Genome | Multi-model attestation: 6-stage pipeline, Ed25519 signatures | `#B8A9C9` |
| G6 | Vault Genome | Sovereignty and data protection: A=0 constitutional prohibitions, 8 DelentiaDB dimensions | `#9B7BB8` |
| G7 | RCT-7 Genome | Mental OS + self-evolution: 7-state IntentLoop, G7→G1 performance feedback | `#C4745B` |

---

## The Circular Architecture

The 7 genomes form a loop, not a pipeline:

```
G1 (Blueprint) → G2 (Algorithms) → G3 (Routing) → G4 (Execution)
                                                         ↓
G1 ← G7 (Self-Evolution) ← G6 (Vault) ← G5 (Attestation)
```

The ADAPT step in G7's 7-state IntentLoop (`IDLE → RECEIVE → PARSE → ROUTE → EXECUTE → VERIFY → ADAPT`) sends performance signals back to G1, G2, and G3 — updating domain understanding, algorithm preferences, and routing optimization continuously.

---

## SDK Relationship

In `delentia-os` v1.0.2a0, the following SDK modules implement genome behaviors:

| Genome | SDK Module | Path |
|---|---|---|
| G2 (Codex) | FDIA Scorer | `core/fdia/` |
| G3 (JITNA) | JITNA Protocol | `rct_control_plane/jitna_protocol.py` |
| G4 (ARTENT) | Delta Engine | `core/delta_engine/` |
| G5 (SignedAI) | SignedAI Registry | `signedai/` |
| G6 (Vault) | Control Plane DSL | `rct_control_plane/` |
| G7 (RCT-7) | IntentLoop reference service | `services/intent-loop/` |

---

## Interactive Exploration

The live Genome Explorer is available at [delentia.com/en/genome](https://delentia.com/en/genome).

Each genome has a detail page:
- G1: [/genome/architect](https://delentia.com/en/genome/architect)
- G2: [/genome/codex](https://delentia.com/en/genome/codex)
- G3: [/genome/jitna](https://delentia.com/en/genome/jitna)
- G4: [/genome/artent](https://delentia.com/en/genome/artent)
- G5: [/genome/signed-ai](https://delentia.com/en/genome/signed-ai)
- G6: [/genome/vault](https://delentia.com/en/genome/vault)
- G7: [/genome/rct-7](https://delentia.com/en/genome/rct-7)

---

## Related Concepts

- [FDIA Equation](./fdia.md) — The constitutional scoring function that powers G2 and G6
- [JITNA Protocol](./jitna.md) — The inter-genome communication standard (G3)
- [Intent Loop](./intent-loop.md) — The 7-state execution loop (G7)
- [SignedAI](./signedai.md) — The multi-model attestation layer (G5)
- [Architecture Overview](./architecture.md) — How all components fit together

---

*Full architectural article: [delentia.com/en/blog/rct-7-genome-system](https://delentia.com/en/blog/rct-7-genome-system)*

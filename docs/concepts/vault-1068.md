# Vault-1068 — Constitutional Static Knowledge Store

> This document is part of the [RCT Platform concepts documentation](https://rctlabs.github.io/rct-platform/concepts/).  
> For the full architectural article, see: [rctlabs.co/en/blog/knowledge-vault-architecture](https://rctlabs.co/en/blog/knowledge-vault-architecture)

---

## Overview

**Vault-1068** is the static knowledge layer in the RCT Ecosystem — the G6 (Vault Genome) implementation that stores authoritative, version-tracked, access-controlled knowledge for enterprise AI deployments.

Unlike a RAG system (which retrieves semantically similar documents) or a vector database (which finds approximate matches), Vault-1068 provides **deterministic retrieval**: queries for specific facts return the exact stored value, not a probabilistic approximation. There is no hallucination surface at the retrieval layer because there is no generation at the retrieval layer.

---

## Three Defining Properties

### 1. Deterministic Access, Not Probabilistic Retrieval

When an agent queries Vault-1068 for a specific fact (regulatory rule, constitutional prohibition, product specification), it receives the exact stored value. Semantic similarity is not used — exact fact retrieval is the design goal.

### 2. Constitutional Access Control

Knowledge items are tagged with access rules derived from G6 (Vault Genome) and G1 (Architect's Genome). Access denials are logged to the audit trail. Constitutional access control cannot be bypassed by role assignment — it is enforced at the genome expression level.

Access flow:
```
Agent → G3 (JITNA routing) → G6 (access check) → Vault-1068 (retrieval) → Agent
```

If G6's access check fails, the query never reaches Vault-1068. The agent receives a structured denial response.

### 3. Version-Tracked Consistency

Every knowledge item has:
- `version` — incrementing version number
- `valid_from` — when this version became authoritative
- `expires_at` — when this version is superseded (optional)

Expired items are archived, not deleted. Agents cannot retrieve knowledge outside its validity window.

---

## The 8-Dimensional Knowledge Schema

Vault-1068 uses the same 8-dimensional index as RCTDB, enabling static and dynamic knowledge to be queried with the same interface:

| Dimension | What it captures |
|---|---|
| Intent | What queries this knowledge answers |
| Domain | Medical, legal, compliance, technical, etc. |
| Context | Under what conditions this knowledge applies |
| Authority | Which authoritative source originated this knowledge |
| Confidence | Certainty level (1.0 for verified regulatory text) |
| Temporal | Validity window (valid_from, expires_at) |
| Access Level | Constitutional authorization required |
| Provenance | Submitter, timestamp, review process |

---

## What Goes In Vault-1068

**Appropriate content:**
- Regulatory text and legal provisions (with version tracking)
- Constitutional prohibitions (A=0 rules from G1)
- Product specifications and technical standards
- Organizational policies and approval workflows
- Verified domain taxonomies (ICD-10, ISIC, etc.)
- Compliance checklists and certification requirements

**Not appropriate (other storage locations):**
- User conversation context → RCTDB via G4/ARTENT
- Dynamic market data or real-time feeds → specialized adapters
- Model weights or configurations → G3/JITNA routing layer
- Unverified or draft knowledge → staging environment only

---

## Knowledge Lifecycle

### Ingestion Workflow

```
Submission → Constitutional Review → Staging → Promotion to Production
```

1. Knowledge item submitted with domain tag, authority source, proposed validity window
2. Constitutional review: does this conflict with any G1 prohibition?
3. Available in staging Vault for testing against existing agent configurations
4. Promoted to production with confirmed `valid_from` timestamp

### Expiration

When knowledge expires:
- Status changes to `ARCHIVED`
- Remains queryable for audit purposes
- No longer returned to live agent queries
- G6 logs a `KNOWLEDGE_EXPIRY` event

---

## Relationship to the Broader Architecture

Vault-1068 is one anchor of the combined memory architecture:

| Store | Answers | Technology |
|---|---|---|
| **Vault-1068** | "What is definitively true?" | Constitutional static store |
| **RCTDB** | "What has been observed and learned?" | 8-dimensional dynamic memory |
| **Delta Engine** | "What changed recently? What's the efficient recall path?" | State compression + warm recall |

A compliance query uses all three: Vault-1068 retrieves the regulatory rule, RCTDB retrieves historical compliance decisions, Delta Engine determines if warm-recall suffices.

---

## SDK Implementation Notes

In `rct-platform` v1.0.2a0:
- The **Control Plane DSL** (`rct_control_plane/`) implements G6's access control logic
- The constitutional `A=0` enforcement in the **FDIA Scorer** (`core/fdia/`) implements the kill-switch behavior
- Full Vault-1068 as a managed service is an enterprise feature — see [rctlabs.co](https://rctlabs.co)

---

## Related Concepts

- [Genome System](./genome-system.md) — How G6 (Vault Genome) fits in the 7-genome architecture
- [FDIA Equation](./fdia.md) — The A=0 constitutional kill-switch
- [Architecture Overview](./architecture.md) — Full system architecture

---

*Full architectural article: [rctlabs.co/en/blog/knowledge-vault-architecture](https://rctlabs.co/en/blog/knowledge-vault-architecture)*

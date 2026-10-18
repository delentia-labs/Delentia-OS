# SignedAI: the jury runner

**Independent model votes with a signed verdict. Optional, and tested with scripted voters only.**

---

## What is SignedAI?

SignedAI asks several models the same question about the same proposal and records how they voted. It does not prevent hallucination, and no hallucination rate is claimed (an earlier 0.3% figure was withdrawn on 2026-09-28 because it could not be reproduced; see [Whitepaper 3.0 §9.2](../whitepaper/DELENTIA_WHITEPAPER_3.0_EN.md)).

How a jury runs (`signedai/runner.py`, `delentia jury run`, `delentia jury verify`):

1. Every member of the jury gets the same question about the same proposal, independently. You name the members in a jury file (keys are never in the file; it names an environment variable).
2. Each reply is read as agree, disagree or abstain. A reply that cannot be read, a timeout or an error counts as abstain, never as agree.
3. The tier sets how many agreeing votes are required and what share of the jury they must be. Abstentions never help a proposal pass.
4. A jury of one model is not a jury: if fewer than the required number of *different* models answered, consensus is not reached.
5. In the strictest tier the chairman can veto, but cannot force a pass over a disagreeing jury.
6. The verdict is a canonical record with a SHA-256 digest, optionally signed with Ed25519, that anyone can re-check with `delentia jury verify`.

**What has been tested:** the vote rules, with scripted voters; and a harness that runs four separate HTTP servers as members and checks the signed verdict. **What has not:** any real vote across several vendors' models, and any evidence that a jury is more accurate than one model.

---

## Tier arithmetic

The tiers are a table of how many signers and how many agreeing votes a proposal needs. They are not a promise about latency, accuracy or cost; none of those was measured.

| Tier | Signers (in the table) | Use |
|------|------------------------|-----|
| **TIER_S** | 1 | a single attestation |
| **TIER_4** | 4 | more than one opinion |
| **TIER_6** | 6 | a larger jury |
| **TIER_8** | 6 + chairman veto | the strictest rule set |

---

## HexaCoreRegistry: a table of example model roles

`signedai/core/registry.py` holds a table of example roles (the name `HexaCore` is the older name of that table). No fixed roster of models runs, and no model in the table is a partner. A real jury's members are the models you name in your jury file.

---

## Usage

```python
from signedai.core.registry import SignedAIRegistry, SignedAITier, RiskLevel

# All methods are class methods — no instance needed
tier_config = SignedAIRegistry.get_tier_by_risk(RiskLevel.HIGH)
print(f"Tier: {tier_config.tier.value}")              # → tier_6
print(f"Signers: {len(tier_config.signers)}")         # → 6
print(f"Required votes: {tier_config.required_votes}")# → 4
print(f"Chairman veto: {tier_config.chairman_veto}")  # → False

# Access by explicit tier enum
config_t6 = SignedAIRegistry.get_tier_config(SignedAITier.TIER_6)
assert tier_config == config_t6  # same tier
```

---

## JITNA Packet — Cross-Agent Wire Format

The **JITNA Protocol (RFC-001 v2.0)** defines the standard 6-field schema for intent communication between AI agents:

```python
from signedai.core.models import JITNAPacket

packet = JITNAPacket(
    I="Intent — what the agent wants to achieve",
    D="Domain — the context/knowledge area",
    **{"Δ": "Delta — what is changing from current state"},
    A="Architect constraint — what must NOT change",
    R="Requirements — measurable success criteria",
    M="Metrics — how success will be verified",
)
```

| Field | Symbol | Meaning |
|-------|--------|---------|
| Intent | I | The desired outcome |
| Domain | D | Knowledge context |
| Delta | Δ | What is changing |
| Architect | A | Hard constraints (human-set) |
| Requirements | R | Success definition |
| Metrics | M | Verification method |

---

## ED25519 Attestation

Every committed decision in the SignedAI system is signed:

```python
# Signatures are 64 bytes (vs RSA-2048's 256 bytes)
# Verification is 3x faster than RSA
# Stored with: timestamp, tier, model_ids, consensus_score, signature
```

The signature binds the **exact output** to the **exact model ensemble** that produced it. If any field is tampered with, signature verification fails and the record is marked as corrupted in the audit log.

# Delentia Whitepaper 3.0: A Constitutional Agent Runtime

**Version:** 3.0 (2026-09-28) · **Author:** Ittirit Saengow (The Architect), Delentia Labs
**Thai edition:** [DELENTIA_WHITEPAPER_3.0_TH.md](DELENTIA_WHITEPAPER_3.0_TH.md)

> **How to read this document.** Every number in it comes from §9 (Evidence), which gives the command
> that produces it and the date it was measured. Anything not built yet is marked **not built** and
> listed in §10 (Roadmap). Earlier whitepapers (v2.x, "RCT Ecosystem", chapters 01–08) are kept
> for history only; where they disagree with this one, this one is correct. §11 lists what changed.

---

## 1. The problem

AI agents now act. They read and write files, run shell commands, call APIs and send messages
through tools (for example MCP servers). The usual safety layer is text: a system prompt that asks
the model to be careful, or a second model that judges the first. Both are probabilistic, and both
live inside the thing they are meant to constrain. A prompt-injected or simply mistaken agent can
ignore them.

Delentia's position is that the decision *whether an action may run* must be:

1. **deterministic**: the same request under the same policy always gets the same verdict;
2. **outside the model**: enforced in code at the point where the tool call is executed, not
   requested in the prompt;
3. **anchored in a human**: the final authority for high-risk actions is a person whose approval
   can be verified cryptographically, never the agent itself;
4. **recorded so it can be checked later**: by someone other than the agent that was audited.

## 2. FDIA: the constitutional equation

```
F = D^I × A
```

| Symbol | Name | Meaning in the gate |
|---|---|---|
| **F** | Future | The admissibility of the action: whether this future may be brought about. |
| **D** | Data | Quality and sufficiency of the data behind the request, normalised to [0, 1]. |
| **I** | Intent | Precision of the stated intent. Because D ≤ 1, a higher I makes the gate *stricter*: vague data is punished harder when the intent claims to be precise. |
| **A** | Architect | Human authority. **A = 0 means no future**, whatever D and I are. A is not a model output; it is a verifiable human decision. |

### 2.1 Four invariants (enforced in code, tested in both languages)

1. **A = 0 ⇒ F = 0.** Without the Architect, nothing high-risk proceeds.
2. **I ≤ 0 ⇒ F = 0.** No intent, no future. (Mathematically `D^0 = 1`, which would make an
   intent-free request fully admissible; the implementation refuses that reading.)
3. **D ≤ 0 ⇒ F = 0.** No data, no future.
4. **A must be human and verifiable.** A token from the Architect is an Ed25519 signature, checked
   against public keys the *deployment* trusts, never keys supplied by the caller.

Inputs outside the domain fail closed. The TypeScript engine (the MCP tools and Guard) and the
Python engine (the agent runtime) share one contract file of 425 test vectors
(`contracts/fdia_vectors.v1.json`, pinned by SHA-256 in both repositories). They agree on 422;
the 3 remaining vectors document a known difference in how out-of-range values are clamped.

### 2.2 The Architect token

```
dat1.<key_id>.<expires>.<signature>
signed message: delentia-architect-token:v1|key_id|action|sha256(payload)|expires
```

- Bound to **one action** and the **exact payload** (by hash), valid for at most 24 hours.
- Trusted keys come only from the deployment's configuration (`FDIA_ARCHITECT_KEYS_JSON` on the
  Workers, `~/.delentia/approvers.json` for the runtime). None configured means nothing is
  authorised.
- **Dual sign-off** actions need two different trusted keys.
- One Ed25519 key can sign both runtime approvals and these tokens.

### 2.3 The gate threshold

The agent runtime blocks an action when F falls below `FDIA_GATE_THRESHOLD` (default 0.5), and
tells the model why. Write, patch and other side-effecting tools are held for human approval
regardless of F.

## 3. RCT-7: how the agent thinks

Reverse Component Thinking works backwards from the desired outcome in seven steps:
**Observe → Analyze → Deconstruct → Reverse reasoning → Identify core intent → Reconstruct →
Compare with intent.**

- In the agent runtime, steps 1–6 are computed for every goal and placed in the prompt as the
  plan. Step 7 runs after the episode: a semantic matcher compares what was done with the original
  intent, and the verdict is recorded.
- The public MCP tool `rct_think` returns the same seven-step structure with a heuristic alignment
  score computed from how complete the request is (spec: `RCT7_SCORING_SPEC.md` in the MCP
  repository). **It is a checklist, not a hallucination detector.**

## 4. The Constitutional Cycle

Every agent episode passes through eight steps automatically, not only when the model decides to
call a tool.

| # | Step | What happens | Status |
|---|---|---|---|
| 1 | **GUARD** | CORD screens every goal before any model call; a hard finding (prompt injection, encoded payload, oversized input) ends the episode with no model or tool call. FDIA D and I are computed from the goal and F of the goal is recorded; the FDIA gate itself applies to each risky action (step 4), where A is known | ✅ built (CORD in the loop since 2026-09-30; before that only two API endpoints screened goals) |
| 2 | **THINK** | RCT-7 steps 1–6 become the plan in the prompt; relevant memories and MEE-approved skills are recalled automatically (as data, never as instructions) | ✅ built |
| 3 | **ROUTE** | ALGO-21 decides FAST (low risk, narrow scope: smaller step budget, answer directly) or SLOW (full budget, step by step); a router error routes SLOW. Never skips a governance step | ✅ built (2026-09-29) |
| 4 | **ACT** | Per-step FDIA gate; side-effecting tools wait for a signed human approval, then the episode resumes | ✅ built |
| 5 | **COMPRESS** | Tool outputs over ~2k tokens are compressed with Delta-Context and can be expanded again | ✅ built |
| 6 | **VERIFY** | RCT-7 step 7 against the original intent | ✅ built |
| 7 | **RECORD** | Hash-chained audit rows (signed when a signing key is configured), RCTDB `experiment_runs` | ✅ built |
| 8 | **LEARN** | Only verified episodes can produce skills, and only through the MEE gate | ✅ built |

All entry points (API, the four messaging gateways, the scheduler, the MCP tool, profiles and
subagents, the terminal UI) build the loop through one governed factory; a test fails if any module
constructs an ungoverned loop.

## 5. Three products

| Product | What it is | Who reasons | Enforcing? |
|---|---|---|---|
| **Delentia Guard** (`delentia-guard`) | A stdio proxy in front of any MCP server. Every `tools/call` is checked against an FDIA policy before it reaches the server; optional output compression; human approval for "needs a human" rules; Ed25519-signed, hash-chained audit log. | The customer's own agent | **Yes** |
| **Delentia MCP tools** (`delentia-mcp`, Cloudflare Workers) | Six tools: `evaluate_fdia`, `rct_think`, `compress_context`, `expand_context`, `orchestrate_swarm`, `configure_policy`. | The customer's own agent | No, advisory: the agent must choose to call them |
| **Delentia-OS agent runtime** (Python) | Delentia's own autonomous agent: governed loop, daemon, scheduler, gateways, skills, memory, sandbox, subagents, model choice (Ollama or any OpenRouter model). | Delentia's loop with a model the operator selects | **Yes** |

Guard is shipped first because it enforces policy on agents people already use.

## 6. Architecture: the 10 layers, as built

Earlier whitepapers described ten layers. They remain a useful map, but several were described as
built when they were plans. This table is the corrected record.

| Layer | Earlier description | As built (2026-09-28) | Decision |
|---|---|---|---|
| L1 OS primitives | Direct hardware access, OS-level isolation | Process-level sandbox (`local` and `docker` backends) with command risk classification | Correct the text: Delentia is a runtime on top of an OS, not an OS |
| L2 Kernel services | VRAM management, LoRA swap in < 12 ms | `lora_multiplexer.py` manages adapter slots (with a mock fallback); the SLM is not connected to the runtime; 12 ms was never measured | Correct the text; the SLM is optional and off the main path |
| L3 Algorithm kernel | 41 algorithms + FDIA | ✅ 41/41 have real logic; measured 2026-09-30: 14 run inside the deep pipeline, 12 more are reachable as MCP tools, the rest are constructed but not called by any pipeline | Keep |
| L4 RCTDB | 8 dimensions on Qdrant + Neo4j + PostgreSQL | SQLite by default (RCTDB tables, hash-chained audit, experiment runs); PostgreSQL + pgvector backend available; Qdrant used by vector search (ALGO-16); Neo4j used by graph traversal (ALGO-17) when a server is configured | Correct the text to "SQLite by default, optional backends". Code gap: the hash-chained audit exists only on SQLite; PostgreSQL parity is needed before multi-host deployment |
| L5 SignedAI | Multi-model consensus ≥ 75% | Consensus logic and tier routing in `signedai/core`; no HTTP API yet; model lists in older papers are out of date | Correct the text; an API wrapper is backlog |
| L6 JITNA | Packets I, D, Δ, A, R, M | ✅ Ed25519-signed packets (v2), streaming (v3) | Keep |
| L7 FloatingAI & Delta | 91.5% memory compression | Three different "Delta" components (see §7) | Rename and separate |
| L8 Regional language adapter | Route by locale and data residency (PDPA/GDPR) | A PDPA risk-audit endpoint and a Thai-law adapter entry exist; no layer chooses models by locale or residency | Correct the text; build only when a customer needs it |
| L9 Universal adapter | REST / GraphQL / WebSocket / gRPC | MCP is the integration surface (6 remote tools, 34 runtime tools, Guard for any MCP server); an adapter SDK exists but is idle | Reframe L9 as "MCP + Guard" |
| L10 Enterprise hardening | JWT RS256, RBAC, circuit breaker | ✅ `enterprise_hardening.py`, bearer-token API auth, fail-closed sender allowlists on gateways | Keep |

**Answering the recurring question: should the whitepaper change, or the code?** Mostly the
whitepaper. The code already does what an agent runtime needs at this stage; the earlier text
described a larger infrastructure (three databases, an OS layer, regional routing) than any current
user requires. Code changes are justified only where they close a real gap: PostgreSQL parity for
the audit chain (before running on more than one host), an HTTP API for SignedAI, and regional
routing once a customer asks for it.

## 7. Memory and the three Deltas

| Name in this paper | Code | What it does | Measured |
|---|---|---|---|
| **Delta-Context** | TS `compress_context` / `expand_context`; Python `delta_v2.py` (byte-identical port); Guard `--compress` | Shrinks large tool output while keeping failure lines and a way to expand the rest | ~70–75% token reduction on real code and logs (aggressive mode); Guard: ~66% on a real build + test log |
| **Delta-Memory** | `core/delta_engine/memory_delta.py` | Stores agent state as deltas instead of full snapshots | 91.5% on a synthetic 20-agent × 100-tick simulation (estimated bytes) |
| **DeltaBlock** | `algo_25_delta_block.py` | Diff log and turn-history compression | – |

Automatic memory: relevant memories are recalled into the prompt at the start of every episode,
labelled as data. Skills are learned only from verified episodes through the MEE gate.

## 8. Audit and key custody

A signature proves who wrote a record and that it was not altered. It does not prove the record is
true, and it proves nothing if the agent being audited holds the signing key. Delentia therefore
describes its audit trail by the attacker each tier defeats.

| Tier | Adds | Status |
|---|---|---|
| A0 | In-process, ephemeral self-signing | Superseded |
| A1 | Long-lived key outside tool-reachable paths; every row chained and signed; `delentia audit-chain verify` | ✅ Runtime (when `DELENTIA_AUDIT_SIGNING_KEY` is set) |
| A2 | Signing in a separate process at the chokepoint that observes the real tool call | ✅ **Guard, for the MCP path**: the key lives in the Guard process; calls naming the key or the log are refused. ✅ **Runtime (Round 50)**: `delentia notary serve` holds the key in its own process; the governed loop records every tool call (argument, result and FDIA-decision hashes) before it runs and refuses the call if the notary cannot record it (when `DELENTIA_NOTARY_URL` is set). Run the notary as another OS user; the gate itself still runs in the agent's process |
| A3 | Chain head published to an outside witness | 🟡 Witness live (fdia Worker `/v1/audit/anchor`, append-only; rollback/fork kept as evidence). `delentia-guard anchor`, `delentia audit-chain anchor` and `delentia notary anchor` publish on demand; **no schedule yet** |
| A4 | HSM/KMS keys, rotation, WORM storage, external audit | **Not built**; only on customer demand |

Until A3 ships, Delentia does not call its logs "tamper-proof" or "immutable". Personal data stays
off the chain (only hashes are chained), so erasure requests can be honoured without breaking it.

## 9. Evidence

### 9.1 Measured (reproducible)

| Claim | Value | How to reproduce | Date |
|---|---|---|---|
| Runtime test suite | 3,922 passed; 1 failed (a live OpenRouter test that needs a network key) | `pytest` in Delentia-OS | 2026-09-28 |
| MCP + Guard test suite | 288 passed, 0 failed (295 with the private services attached) | `npm ci && npm run build && npm run test:all` in `delentia-mcp/ecosystem` | 2026-09-28 |
| FDIA contract | 422 of 425 vectors agree across TypeScript and Python; 3 documented clamping differences | contract tests in both repositories | 2026-09-28 |
| Delta-Context | ~70–75% fewer tokens (aggressive); keeps the answer line for 100% of same-wording questions and ~60% of paraphrased ones; default mode ~6–12% | `benchmarks/compression-real/` in `delentia-mcp/ecosystem` | Round 46 |
| Guard compression | ~66% smaller on a real build + test log, failing test kept | `delentia-mcp/ecosystem/docs/GUARD.md` | 2026-09 |
| Delta-Memory | 91.5% on a synthetic 20 × 100 simulation | `python scripts/benchmark_fdia_delta.py --json` | 2026-09-28 |
| FDIA evaluation (Python) | 2.37 µs per evaluation on one laptop CPU | same script | 2026-09-28 |
| Warm recall (in-memory SQLite) | p95 0.021 ms | same script | 2026-09-28 |
| CORD screening | 100 patterns, ~48 µs per check; the script's own sample set shows a 50% detection rate, so no detection-rate claim is made | same script | 2026-09-28 |
| Model tool selection (K.1.5) | qwen2.5:7b on CPU: 0/17 correct tool selections; governance and refusal behaviour 100% | `scripts/k1_5_formal_acceptance.py` | Round 45 |

The K.1.5 result is why the runtime lets the operator choose the model: governance is enforced in
code and held even when the model could not select tools.

### 9.2 Withdrawn claims

| Earlier claim | Why it is withdrawn |
|---|---|
| "0% hallucination", "0.00% hallucination drift" | Never measured |
| "0.3% hallucination vs 12–15% industry" | The dataset and the benchmark suite it cites are not in any repository; not reproducible |
| 99.98% stability, 259.2 million requests | No load test exists |
| 4,849 tests | Superseded by the counts in §9.1 |
| "Zero-knowledge proof of the FDIA score" | `zk_fdia.py` is a hash commitment; the verifier cannot check that the sealed F equals D^I × A. Call it a commitment |
| "Tamper-proof" / "immutable" audit | See §8; not until A3 |
| 94.7% "unprotected LLM" bypass baseline | No LLM was run; the flag was hardcoded |
| 74.2% / 85% compression | 74% was a design floor, 85% has no source; see Delta-Context in §9.1 |
| LoRA swap < 12 ms | Never measured |
| "World's first intent-centric AI OS" | Not provable; Delentia is a runtime, not an OS |
| SignedAI on GPT-4 Turbo / Claude 3.5 | Model names out of date; models are now chosen by the operator |

## 10. Roadmap (not built yet)

1. **A3 anchoring**: publish Guard and runtime chain heads to an outside witness on a schedule.
2. **Host**: run the runtime publicly (planned: Oracle Always Free + Cloudflare Tunnel, token
   required), then enable the Workers → Python FDIA bridge.
3. **A model that drives the loop**: publish a small set of reference models that pass K.1.5.
4. **PostgreSQL parity** for the audit chain; **SignedAI HTTP API**.
5. **Design partners** for Guard, before any new algorithms, sandbox backends or channels.

## 11. What changed from v2.x

- New: the Constitutional Cycle, the governed runtime, Delentia Guard, the Ed25519 Architect token,
  the four FDIA invariants, the cross-language FDIA contract, audit tiers A0–A4.
- Corrected: the meaning of each FDIA term, the 10-layer statuses, the three Deltas, and every
  number (§9).
- One source: this file and its Thai edition. Older papers stay in `docs/whitepapers/` and
  `whitepapers/` for history.

## Appendix A. Object inventory

| Group | Objects | Status |
|---|---|---|
| Philosophy | FDIA, RCT-7, The Architect, Architect veto | Used in code |
| Protocols | JITNA (RFC-001), TOON | JITNA in code; TOON in the dataset only |
| Memory | RCTDB, AgentMemory, SkillLibrary, experiment runs, Vault-1068 client | In code (the Vault client's class is misleadingly named `RCTDBClient`) |
| Security | CORD, FDIA gate, ZK-FDIA commitment, approvals, Architect token, API auth, audit chain, Guard | In code |
| Reasoning | 41 algorithms, Kernel 9 Tiers, Intent Loop, ALGO-21 router, MEE | In code; the Intent Loop service is a reference implementation whose execution and verification are simulated and it is not wired into the agent loop; ALGO-21 runs inside the loop (ROUTE) |
| Consensus | SignedAI, HexaCore (9 roles) | Logic in code, no API |
| Models | 1+4 pillars (Router, Guardian, Executor, Scribe), delentia-slm | On Hugging Face; not connected to the runtime |
| Products | Guard, 6 MCP tools, the runtime (34 MCP tools), website | Live or in code |

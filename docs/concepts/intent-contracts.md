# Explicit intent contracts (experimental)

This opt-in path makes a small set of user-declared acceptance criteria inspectable and durable. It adds plan-before-execution and mismatch clarification to read/answer workflows in the governed CLI and HTTP API. It does **not** implement complete RCT-7 semantics, infer every unknown, or prove an arbitrary answer true. Existing callers without acceptance criteria retain their current behaviour.

## Supported predicates

An acceptance file is a JSON list, for example:

```json
[
  {"kind": "language", "value": "th"},
  {"kind": "file_unchanged", "value": "notes/source.md"}
]
```

| Kind | What is checked | Limitation |
|---|---|---|
| `contains` | Case-insensitive substring in the final answer | Matching a string does not prove factual correctness. |
| `language` | Thai or English character/script check (`th` or `en`) | Not a semantic language classifier or translation-quality check; mixed technical text can be misclassified. |
| `json_object` | The whole answer parses as a JSON object | Does not validate a domain schema or the object's truth. |
| `file_unchanged` | Original SHA-256 bytes of an existing relative workspace file | Not an OS sandbox or a guarantee against another process changing it. |

Criteria are limited to 20 entries. Protected paths must exist and resolve inside the workspace. This first release permits only the built-in file read/search and memory/session recall tools. Other tools are withheld before dispatch: an effect that later resumes through the legacy approval flow must not silently lose its contract. Supporting signed effects under the same contract is a follow-up requirement. This restriction does not replace existing policy, signatures, taint, residency or budget checks. Unsupported/custom tools and other entry points require their own mediation review.

The plan records the goal, declared predicates, necessary conditions, limited production/comparison components and known limitations. Its backward links describe the declared acceptance conditions, not a complete goal-specific causal decomposition or a model's hidden chain of thought.

## CLI

```bash
delentia agent 'Read notes/source.md and answer in Thai without modifying it' \
  --namespace my-work --criteria-file criteria.json
```

The CLI prints the plan **before** calling the model or dispatching an episode tool. When the answer fails a predicate, it prints `waiting_for_clarification`, differences, a question, the contract ID and version, then exits with status 1. A failed answer is not silently reported as accepted or learned as a successful skill.

A new CLI process can inspect the same contract in the same data home/workspace:

```bash
delentia intent-contract show ACTUAL_CONTRACT_ID --namespace my-work
delentia intent-contract continue ACTUAL_CONTRACT_ID --namespace my-work \
  --version ACTUAL_VERSION --response 'Keep the Thai requirement; answer in Thai'
```

Use `--revised-goal` only when the user actually changes the goal. Original intent and confirmed revisions remain separate. A missing/blank answer cannot release a clarification wait; a stale version or repeated request cannot claim the same state twice. This is confirmation of the user's intent, not a new mandatory signature for every plan or permission to bypass tool approval.

If the failed episode already performed known side effects, or an external effect's outcome is unknown, automatic rerun is refused: reconcile actual state before creating another execution. A process that dies while a contract is `running` is not automatically retried. Crash recovery of in-flight contracts remains future work; do not treat an old `running` row as consent to repeat effects.

## HTTP

1. `POST /v1/agent/run` with `goal`, `namespace` (when using trusted local owner access) and `acceptance_criteria` returns `plan_ready` with **no model/tool call**.
2. Read the returned `intent_contract.id`, `version` and plan. `POST /v1/agent/intent-contracts/{id}/continue` with that version starts it.
3. A mismatch returns `waiting_for_clarification`. `GET /v1/agent/intent-contracts/{id}` reads its persisted status.
4. Continue with the current version and a nonempty `response`, optionally `revised_goal` and revised `acceptance_criteria`. The HTTP path returns the revised plan first; another versioned continuation executes it. This keeps revised plans visible before effects too.

With per-person tokens, namespace comes from verified caller identity; a body/query namespace does not override it. A contract from another namespace is not returned. On a real host use the existing authentication/operator contract; unauthenticated loopback access is a trusted local-owner surface, not a tenant security boundary.

## Persistence and verification

SQLite stores a versioned contract per namespace, sealed through the runtime's namespace keys when sealing is enabled. State transitions append hash-only audit metadata. Erased/unavailable text cannot be used to continue a contract. Existing plain-text modes retain their documented weaker privacy assumptions.

`criteria_satisfied` means these explicit predicates passed. The existing grounding/intent verifier is still reported separately; satisfying a substring or script check does not override its factual warnings. Warm-answer reuse and context-free skill extraction are disabled on this opt-in path because the answer depends on criteria beyond the bare goal. Pending approval and infrastructure interruptions remain distinct from semantic clarification.

Source-checkout mechanism demo:

```bash
python scripts/demo_intent_contract.py --dir /path/to/a/new/disposable-demo-directory
```

It uses a local **SCRIPTED** HTTP model, actual CLI processes, file reads, SQLite and acceptance checks. It intentionally produces a language mismatch, proves restart preserves waiting, refuses continuation without an answer, and then retains a confirmed revision. It has no paid calls and does not demonstrate capable-model success. Do not share its private key/data directory.

Related: [RCT-7 requirements](rct-7-thinking.md), [FDIA semantics](fdia.md), [release levels](../release/RELEASE_LEVELS.md), [research protocol](../../research/PROTOCOL.md).

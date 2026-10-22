# Criterion-derived RCT plans (experimental)

This opt-in compiler turns explicit acceptance predicates into prerequisite and comparison components without calling a model. It does not implement arbitrary semantic decomposition of a natural-language goal. User-declared graphs remain supported. The default agent path is unchanged.

CLI:

```sh
delentia agent 'อ่าน quote.md แสดงราคาเป็นภาษาไทย ห้ามแก้ไฟล์' \
  --criteria-file criteria.json --derive-plan
```

`--derive-plan` and `--planning-context-file` are mutually exclusive and require criteria. HTTP callers use the existing `/v1/agent/run` endpoint with `acceptance_criteria` and `planning_context: {"derive_from_criteria": true}`. This marker must contain exactly that boolean field. The API returns `plan_ready` before execution; a separate versioned continuation starts work. CLI renders the plan before work using its existing callback. No new permission requirement is added by showing a plan.

The compiler emits `planning_origin: criterion_derived`, the ruleset `criterion-prerequisites-1`, source references to the user goal and each criterion, and `semantic_completeness: false`. The goal fact contains at most its first 4,000 characters; the full original goal remains in the contract and plan. No external observation or verified source is invented. Empty unknowns mean this compiler does not discover unknowns, not that the task has none.

| Predicate | Derived prerequisite | Actual comparison | Limit |
|---|---|---|---|
| contains | Prepare the requested literal in an answer | NFC/casefold substring | Inclusion is not factual support |
| language | Prepare the requested th/en script | Existing script heuristic | Not fluency or translation quality |
| json_object | Serialize an object | JSON parse and object type | Not semantic schema correctness |
| file_unchanged | Preserve the original workspace bytes | Original/final SHA-256 | Does not authorize reads/writes or certify other effects |

Backward conditions now include the transitive component prerequisites, including for user-declared graphs. Criterion coverage, cycles, dangling references and bounds are validated before persistence. Twenty supported criteria produce at most 40 components and 21 facts. Descriptions never add tool authority.

Confirmed clarification revisions of derived contracts regenerate the graph for the changed goal/criteria, retain the original goal and preserve baselines for retained protected files. This is different from verifying a new semantic plan. User-declared graph revisions still have to cover the revised criteria; automatic regeneration applies only to the explicit derivation request.

New contracts include `plan_sha256`: SHA-256 over UTF-8 JSON with sorted keys, compact separators and no NaN. It binds the serialized plan, including goal, workspace, predicates, baselines and graph. Reads refuse mismatched stored hashes. Pre-existing contracts without this field remain readable and gain a digest on their next transition. This is **not** a signature, approval token, MAC, append-only witness or proof against a trusted writer that can rewrite both bytes and hash. It grants no effects.

Creation and transition return a frozen receipt of their own committed payload/state/version. They do not re-read a later writer's state after the audit append. Compare-and-swap still rejects stale versions. A crash or audit failure after the state commit may leave `running` without an acknowledged result. Such contracts are not automatically reset or retried. Signed effects and crash reconciliation remain separate prerequisites before opening contract write tools.

See [tests](../../rct_control_plane/tests/test_derived_plan_receipts_real.py), [declared plans](rct-declared-plans.md), [intent contracts](intent-contracts.md), and the [next implementation gates](../development/RCT_COMPLETION_NEXT_GATES_TH.md).

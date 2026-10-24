# Verified budget executor v1

The typed-execution follow-up now compiles this workflow into a trusted handler DAG and uses dependency readiness rather than component serialization order. New plans bind the execution program in their digest. The governed MCP read requests descriptor-relative no-follow acquisition as well as the final freshness check. See [implementation, A/B scope and remaining gates](../development/RCT_FRAMEWORK_AND_RUNTIME_RECOVERY_2026-10-23_TH.md); older evidence below is a dated checkpoint, not a claim of general RCT completeness.

Experimental, opt-in **read-only execution** of one pinned structured quote against a confirmed budget. It uses the normal governed loop, tool gate, MCP read, persistence and journal. The decision source is deterministic; it does not call the generation provider. Other requests keep the existing model decision path.

## Input and scope

Use the existing CLI --criteria-file / --planning-context-file or HTTP run/continue contract API. The request must select a supported budget-comparison goal, include a json_object acceptance criterion and provide:

    {"semantic_plan":{
      "budget":"15000 THB",
      "quote_evidence":{"relative_path":"quote.json","sha256":"<actual 64 lowercase hex SHA-256 of the file bytes>"}
    }}

Budget can be omitted: the existing durable budget question is asked before model/tools. The placeholder above must be replaced with the actual digest. The quote is UTF-8 JSON, at most20,000bytes:

    {"schema_version":1,"total":"12500.10","currency":"THB","total_is_final":true}

Schema is strict: decimal total is a string with at most2decimal places, nonnegative and at most1e15; currency is THB/USD/EUR; schema_version is integer1; total_is_final must be boolean true. Extra keys, duplicate JSON keys, nonfinite numbers, missing/partial source and unresolved final scope are not accepted. The budget remains positive with explicit currency. Currency mismatches wait; no FX is inferred. The final-total flag is the document's assertion, not independent proof that the vendor included all taxes/fees.

Only the pinned JSON and confirmed budget determine arithmetic. Additional reported facts are annotations, not independently verified inputs or a cross-source conflict check. This is not PDF/OCR extraction, comparison of multiple vendors or free-form financial advice.

Verified freshness requires POSIX descriptor-relative no-follow support; unsupported platforms refuse before claim. The verified executor requests the MCP tool's opt-in `verified_read` mode, which applies workspace/secret-path policy and opens the source with no-follow directory descriptors, refusing symlinks/non-regular files. The final freshness check uses the same bounded reader. These checks do not certify the entire filesystem against a hostile concurrent writer; deployment must use an authorized isolated workspace, and the general MCP read path needs separate race-hardening review before untrusted multi-user exposure.

## Executed component pipeline

1. A plan is returned/shown before work; a versioned claim starts execution.
2. The deterministic decision source selects the pinned read. The existing gate can still refuse it.
3. Post-dispatch verifies the complete observed bytes against the plan's expected hash, then parses strict quote JSON.
4. inspect_sources completes with observed_bytes provenance; compare_budget requires it and the confirmed budget.
5. Decimal subtraction uses its own40-digit context, independent of ambient precision/traps/exponent settings. Results use exact two-decimal strings.
6. The canonical report is serialized; final verification rechecks current source bytes and exact typed report equality.
7. Predicate preparation/check nodes complete only after their prerequisites. All components must have receipts before acceptance.

A successful report includes quote_total, budget_limit, currency, remaining, within_budget, source and evidence_sha256. An over-budget result can successfully complete the requested inspection with within_budget=false. It grants no purchase/write permission.

## Receipts and failure behaviour

Each local receipt contains component id, contract id, namespace, claim/run version, plan hash, ordinal, previous receipt hash, output/hash and timestamp. Dependencies and required inputs must be complete. Receipt hashes/ordering/bindings are checked on stored reads. These are sealed local working records under the existing namespace mechanism, not signatures or an independent witness; a trusted writer able to rewrite data and hashes is outside this consistency proof.

Read/comparison receipts and the partial report persist during the running claim before the final answer. A final receipt set is stored with the outcome. Missing evidence, changed bytes, currency/scope problems, wrong report types/values or an unsatisfied criterion prevent criteria_satisfied and ask for clarification. Replanning clears old receipts. A cancelled/interrupted running contract is not automatically reset or replayed; the tested in-process cancellation checkpoint is not a full OS-crash recovery matrix.

The current fixed handler pipeline enforces dependencies for this compiled workflow. Other declared/rule plans remain descriptive; there is no general arbitrary-tool DAG scheduler or contract-aware write recovery.

## Result interpretation

- executor=verified_budget_v1 identifies deterministic execution. The legacy stopped_reason=llm_finished is retained for compatibility and does not mean a model generated this result.
- semantic_verification evaluates pinned document/arithmetic/receipt scope; acceptance_verification includes it plus declared predicates.
- intent_verification remains the independent legacy heuristic and can disagree with a correct derived numeric report. It is not the typed arithmetic oracle. Public profile/UI must present these scopes explicitly.
- Metered generation calls/tokens are zero in the actual CLI and installed-wheel smoke. Runs with zero generation calls must not be treated as model capability evaluation or model accuracy evidence.

See [tests](../../rct_control_plane/tests/test_verified_budget_real.py), [implementation](../../rct_control_plane/verified_budget.py), [results](../development/VERIFIED_BUDGET_RESULTS_2026-10-23_TH.md) and [activation gates](../release/ACTIVATION_GATES_2026-10-23_TH.md).

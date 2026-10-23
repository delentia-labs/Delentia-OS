## Problem and behavior
RCT plans previously described work without proving that each component executed. This change adds an opt-in, read-only verified-budget executor: a governed MCP read of pinned quote JSON, strict schema/hash checks, isolated Decimal arithmetic, dependency-enforced durable receipts, and final source freshness verification. Missing inputs wait for clarification; malformed evidence, mismatched results, and incomplete dependencies cannot claim success.

## Scope of this cumulative branch
This PR targets main and includes the earlier Codex branch ancestry: public v0.3 documentation, research workspace cleanup, Thai demo fixes, durable intent contracts, declared and criterion-derived plans, bounded bilingual semantic planning, and Action runtime/dependency hardening. The latest commit adds the verified executor, 32 tests, machine-readable evidence, and detailed activation/next-round plans. Generated Action output contributes substantially to the cumulative diff.

Read `docs/development/CODEX_REVIEW_AND_NEXT_STEPS_2026-10-23_TH.md` for the commit inventory and ordered review plan, and `docs/development/VERIFIED_BUDGET_RESULTS_2026-10-23_TH.md` for the latest evidence.

## Validation
- Full Python: 7,975 passed, 13 failed, 59 skipped, 1 xfailed; 716.22 seconds; exit 1. Coverage 91.24% includes test modules.
- Focused regressions: 290 passed, overlapping the full suite.
- Publication recheck: all 32 verified-budget tests passed in 2.00 seconds.
- Pipeline: 21 cases / 134 checks passed, optional subagent cases not run.
- Two production CLI/kernel/MCP/SQLite cases passed with zero generation calls and seven receipts each; installed-wheel CLI smoke also passed outside the checkout.
- Remaining failures: nine missing-model integrations, three browser sandbox failures, one native DNS failure. The subsequent real local model pull failed on the CDN proxy route; no paid API or disabled TLS verification.
- main advanced by three dependency commits to 19d5fe8. Merge-tree found no conflicts, but this branch has not merged/rebased main and the combined tree has not been tested.

## Limits and release gates
This is an experimental governed runtime with a bounded verified read-only workflow, not complete general RCT-7 or production/pilot readiness. Legacy intent heuristics still disagree with the typed numeric verifier in the successful demos. Receipts establish local consistency, not independent signatures/vendor truth. General scheduling, source-acquisition race hardening, strict server profile, tenant file authorization, signed effects/crash reconciliation, capable-model evaluation, and host/witness/restore/soak/pilot gates remain.

See `docs/release/ACTIVATION_GATES_2026-10-23_TH.md` for acceptance gates. No private keys/databases/model weights are included. No deployment, package publication, main merge, or outside pilot is requested by this PR.

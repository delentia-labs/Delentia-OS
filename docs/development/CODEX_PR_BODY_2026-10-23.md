## Problem and behavior
The RCT contract path could describe a component graph without executing it independently of serialization order. This branch adds typed execution programs, a trusted handler registry, dependency scheduling, criterion coverage checks and durable completion receipts. The governed verified-budget workflow now runs through these handlers, using exact Decimal arithmetic and no-follow MCP source acquisition. Unknown executor versions fail closed.

## Scope
This cumulative Codex branch also includes public v0.3 documentation, research workspace cleanup, Thai demo fixes, durable contracts, declared/derived plans, bounded bilingual planning and Action runtime/dependency hardening. Generated Action output contributes substantially to the diff. No merge or deployment is requested.

## Security follow-up
Protected `file_unchanged` contracts now hash through pinned directory descriptors with no-follow opens, regular-file checks, a 64 MiB limit and mutation detection. Traversal, symlinks, FIFO and directory swaps fail closed; unsupported platforms refuse protected-file contracts. This does not establish multi-tenant filesystem authorization or atomic snapshots.

Desk Next.js and eslint-config-next are pinned to 16.4.2. Production npm audit moved from one critical GUI package (three advisories) to zero findings; Action production audit also reports zero. Default-branch Dependabot inventory is separate and remains inaccessible to this integration.

## Validation
Python runtime checkpoint: 478b11a87a1b41e11a2fe3e152e0b662d1cf7d57. Frontend dependency checkpoint: 90fe7490ebb81b9d212c7ba033e406f42add8c80. Python source/tests were unchanged during the full run; GUI dependencies and documentation changed separately.
- Full Python: **8,018 passed / 15 failed / 59 skipped / 1 xfailed**, 715.35s, exit 1. No new coverage measurement.
- Failures: 9 missing-model, 3 browser sandbox, 1 native DNS, 2 regex timing assertions (0.604s and about 0.525s versus 0.5s). Both regex tests pass an isolated rerun without source/threshold changes; full-run failures remain recorded.
- Focused contract/budget/scheduler/planner regressions: 142 passed, including 17 new protected-file tests (overlap with full suite).
- Ruff CI scope and Mypy CI-tools environment: passed, 260 source files.
- GitHub aggregate CodeQL at 478b11a: success, no annotations, “No new alerts in code changed by this pull request”; Python/Rust/JavaScript/Actions analyses all passed. Repository alert inventory API returns 403. Latest pushed revision requires its own checks.
- GUI after dependency update: npm ci, type-check, lint, production build, production audit and actual static HTTP smoke passed.
- Actual isolated Desk API: health/overview/sessions/models/tools return 200; synthetic Thai memory round-trip and revoke pass. Browser E2E/video remain blocked by host sandbox; HTTP smoke is not GUI E2E.
- Earlier scripted pipeline, production CLI and wheel evidence remains linked in the previous checkpoint report; those results are not relabeled as reruns of this revision.

## Paired execution A/B
Baseline 26139b0 versus typed scheduler, 72 generated cases, three timing repeats per arm:
| Cohort | Baseline | New |
|---|---:|---:|
| Canonical ordering | 24/24 correct | 24/24 correct |
| Reversed serialization, same dependencies | 0/24 completed correctly | 24/24 correct |
| Invalid evidence | 24/24 correctly rejected | 24/24 correctly rejected |
Current rerun: canonical median increased from 0.948ms to 1.628ms. Timing ran alongside other host work; this is not a controlled production benchmark. This is structural robustness with overhead, not a model capability, general semantic accuracy, holdout or production latency claim.

## Runtime recovery and remaining gates
The 32GB cloud filesystem reached 100% use. Incomplete model copies and task rollback containers contributed; Docker uses VFS with an approximately 5GB Ollama image. Targeted cleanup restored approximately 16GB free. Proxy addresses also changed across restores; the refreshed service and official manifest were verified without disabling TLS. Platform lifecycle logs are still required to prove the cause of every disconnection. No model was installed in this validation round.

General semantic planning, more handlers/oracles, server profile/tenant isolation, full process recovery, signed effects, capable-model evaluation and host/witness/soak/pilot gates remain. No paid API, private keys/operator databases, model weights, or production-readiness claims are included.

Detailed results, raw A/B outcomes and next gates:
- docs/development/RCT_FRAMEWORK_AND_RUNTIME_RECOVERY_2026-10-23_TH.md
- docs/development/evidence/RCT_FRAMEWORK_2026-10-23.json
- docs/development/CONSOLIDATED_ROADMAP_2026-10-23_TH.md

Latest follow-up and all 15 failure identifiers:
- docs/development/PROTECTED_FILES_AND_DESK_FOLLOWUP_2026-10-23_TH.md
- docs/development/evidence/PROTECTED_FILES_AND_DESK_2026-10-23.json

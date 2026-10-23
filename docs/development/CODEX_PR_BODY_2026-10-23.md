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
- Actual isolated Desk API: health/overview/sessions/models/tools return 200; synthetic Thai memory round-trip and revoke pass. The subsequent sandboxed-browser follow-up below adds real GUI evidence; it does not validate Desk contract/chat lifecycle.
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

## Sandboxed browser and real Desk follow-up
Implementation 9b2519963b509b9dcc71bbab0acd45853e32a5cc (after 8a822cd): fixed missing health service labels, Thai controls, stale connection responses/sidebar status and delayed Memory history refresh. Added static-export routing, browser race regression, real GUI capture and timestamp-preserving video encoding utilities.

A non-root browser container using Playwright's seccomp profile reports namespace/PID/network namespaces and Seccomp-BPF enabled. No --no-sandbox, privileged container or TLS bypass. The existing browser tool uses an adapter that preserves its URL fence/DNS-pin arguments and cleans up task containers after caller death.

- TC027: 5 passed, including the 3 previously sandbox-blocked failures.
- Browser read/action: 67 passed; static route/header regression: 1 passed.
- GUI type-check/lint/build and Ruff passed.
- Real Settings/Memory GUI: 6 checkpoints passed with zero JavaScript page errors. Separate delayed-old-gateway failure regression passed against a real new local API.
- Actual captured-frame video: 20.9 seconds, synthetic Thai data, no model generation; screenshots reviewed. Private DB/keys excluded.
- No full Python rerun for this frontend/host follow-up. Native DNS and required model remain unavailable; current disk is below the model headroom guard. Desk RCT contract lifecycle, server read-only profile and pilot gates remain open.

Details and machine-readable evidence:
- docs/development/SANDBOXED_BROWSER_AND_REAL_DESK_DEMO_2026-10-23_TH.md
- docs/development/evidence/SANDBOXED_BROWSER_AND_DESK_2026-10-23.json

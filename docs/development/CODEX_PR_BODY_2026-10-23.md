## Problem and behavior
The RCT contract path could describe a component graph without executing it independently of serialization order. This branch adds typed execution programs, a trusted handler registry, dependency scheduling, criterion coverage checks and durable completion receipts. The governed verified-budget workflow now runs through these handlers, using exact Decimal arithmetic and no-follow MCP source acquisition. Unknown executor versions fail closed.

## Scope
This cumulative Codex branch also includes public v0.3 documentation, research workspace cleanup, Thai demo fixes, durable contracts, declared/derived plans, bounded bilingual planning and Action runtime/dependency hardening. Generated Action output contributes substantially to the diff. No merge or deployment is requested.

## Validation
Implementation checkpoint: d8065996c9c50a476cf3ee6c245faf414e1ac068.
- Full Python: **8,002 passed / 14 failed / 59 skipped / 1 xfailed**, about 13m30s; exit 1; coverage 91.26% includes test modules.
- Failures: 9 model, 3 browser sandbox, 1 DNS, plus 1 regex timing failure (0.5781s). The regex test passed its isolated rerun; the full failure remains recorded.
- Focused regressions: 192 passed; post-lint checkpoint: 60 passed (overlapping).
- Pipeline: 21/21 cases, 134/134 checks; scripted model, optional subprocess cases excluded.
- Two production CLI/kernel/MCP/SQLite cases passed, zero generation calls, seven receipts each.
- Wheel built; seven runtime files match tested checkout bytes.
- GitHub Lint & Type Check passed at d806599. Python 3.12 CI failed during Ollama preparation (exit 22), before pytest; CodeQL retains three high path alerts in intent_contract.py. Not all CI gates pass.

## Paired execution A/B
Baseline 26139b0 versus typed scheduler, 72 generated cases, three timing repeats per arm:
| Cohort | Baseline | New |
|---|---:|---:|
| Canonical ordering | 24/24 correct | 24/24 correct |
| Reversed serialization, same dependencies | 0/24 completed correctly | 24/24 correct |
| Invalid evidence | 24/24 correctly rejected | 24/24 correctly rejected |
Canonical median increased from 1.065ms to 1.932ms. This is structural robustness with overhead, not a model capability, general semantic accuracy, holdout or production latency claim.

## Runtime recovery and remaining gates
The 32GB cloud filesystem reached 100% use. Incomplete model copies and task rollback containers contributed; Docker uses VFS with an approximately 5GB Ollama image. Targeted cleanup restored approximately 16GB free. Proxy addresses also changed across restores; the refreshed service and official manifest were verified without disabling TLS. Platform lifecycle logs are still required to prove the cause of every disconnection. No model was installed in this validation round.

General semantic planning, more handlers/oracles, server profile/tenant isolation, full process recovery, signed effects, capable-model evaluation and host/witness/soak/pilot gates remain. No paid API, private keys/operator databases, model weights, or production-readiness claims are included.

Detailed results, raw A/B outcomes and next gates:
- docs/development/RCT_FRAMEWORK_AND_RUNTIME_RECOVERY_2026-10-23_TH.md
- docs/development/evidence/RCT_FRAMEWORK_2026-10-23.json
- docs/development/CONSOLIDATED_ROADMAP_2026-10-23_TH.md

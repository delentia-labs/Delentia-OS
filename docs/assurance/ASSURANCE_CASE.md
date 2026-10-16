# Assurance case: one property

**Scope.** One property, argued carefully, rather than many argued loosely. The rest of the safety claims are in `research/GATE_PROPERTIES.md` (ten properties and eleven threats, each pinned by named tests) and are not repeated here.

## The claim

> **C1.** A protected write is committed by the mediated executor only when a valid approval exists that is bound to **the exact payload** and to **the authority in force when it runs**.

"Protected write" means a call the policy says needs a person: a repository file write or patch, a shell command the classifier does not call safe, creating a scheduled job, starting sub-agents, any side effect after outside text has been read. "Mediated executor" means the runtime's governed loop and its tool server (`mcp_server`), which is the only code that performs those calls on behalf of the agent. "Valid approval" means an Ed25519 signature, by a key the owner trusts (and, when the owner's policy names roles, a key holding the role), over the digest of the action.

## What the claim is not

- Not a claim about the language model: a model can ask for anything; the claim is about what the executor does with the request.
- Not a claim about a person who signs a harmful payload they should not have signed, or whose approver key is stolen.
- Not a claim about a process running as the same operating-system user as the agent (it can read and write the same files; see A3).
- Not a claim about the raw `/mcp` gateway (N1): it has its own tools outside the governed loop and answers 403 to every non-owner token; an owner reaching it is outside C1.
- Not a claim about performance, availability, or any regulation.

## Assumptions (what must hold for C1)

| id | assumption | what happens if it is false |
|---|---|---|
| A1 | The approver private key is held on a device the agent cannot read, and is not stolen. | Whoever holds it can approve anything. |
| A2 | The owner reads the payload they sign (the signature is over the exact digest; it cannot tell a harmful payload from a harmless one). | A signed harmful payload runs. |
| A3 | The agent's host is not compromised at the operating-system level (no code running as the same user that could alter the code, the database or the process). | The claim says nothing. The audit chain makes edits evident; an independent witness makes a whole-log rewrite evident; neither prevents. |
| A4 | The only executor of agent tool calls is `mcp_server` reached through `GovernedAutonomousLoop` (checked for six doors by `test_complete_mediation_round82_real.py`). | A new door that skips the gate is outside C1 until it is added to that test. |
| A5 | SQLite and the `cryptography` library behave as documented. | Out of scope. |

## Invariants the argument rests on

| id | invariant | where it is enforced |
|---|---|---|
| I1 | An approval is a row `PENDING -> APPROVED -> EXECUTING -> EXECUTED`; `EXECUTING` is entered by one atomic update, so two resumes cannot both run it. | `approvals.py` `claim_for_execution` |
| I2 | The signed digest covers the approval id, namespace, goal, tool, arguments, **and, when known, the owner policy and the workspace**. Editing any stored field invalidates the signature. | `approvals.py` `action_digest`, `_check_signature` |
| I3 | Every required signature is re-verified at execution time, from distinct trusted keys that hold the required roles; the status column alone is never trusted. | `claim_for_execution` |
| I4 | A signature never lifts a hard rule: a denied path, a blocked pattern, a secret file name. The gate re-evaluates with `approved=True` and still refuses. | `resume` + `fdia_policy.evaluate` |
| I5 | An approval for another policy or another workspace is refused without being consumed. | `PendingActionStore.check_context` |
| I6 | Approvals expire (7 days to decide, 24 hours to use); a pause refuses an already approved action until it is lifted. | `approvals._expire_stale`, `resume` |
| I7 | A crash between claim and receipt leaves `EXECUTING`; it becomes `OUTCOME_UNKNOWN`, is never run again, and a person records what happened. At-most-once, not exactly-once. | `reconcile`, `resolve_unknown` |
| I8 | The gate is consulted before any dispatch, on every entry point, and the strictest rule wins (hard, then policy, then taint). | `_pre_dispatch_gate`, T11 matrix |

## The argument, in steps

1. A request to run a protected call reaches the executor only through the loop's dispatch (A4, six doors tested, with a mutation that removes the gate and shows the effect appear through every door).
2. The loop's dispatch calls `_pre_dispatch_gate` first (I8). For a protected call it returns *pending approval*; nothing has run.
3. The pending action is stored with a digest over its exact content, policy and workspace (I2). The owner signs *that digest* on another device.
4. Resuming re-verifies the signature(s), roles, expiry, pause, policy and workspace (I3, I5, I6), then re-evaluates the hard rules (I4), then claims atomically (I1) and only then calls the tool.
5. After the call a receipt is recorded; if the process dies before it, the outcome is marked unknown and never silently retried (I7).
6. Therefore, under A1-A5, a protected write is committed only when a valid approval bound to its payload and to the current authority exists. ∎ (for the modelled steps; see the limits below)

## Test map

| step / invariant | test (all real code, no mocks of the gate) |
|---|---|
| 1, A4 | `rct_control_plane/tests/test_complete_mediation_round82_real.py` (13 tests, includes the mutation) |
| 2, I8 | `test_rule_precedence_round82_real.py` (28 tests: 24-row strictest-wins matrix) |
| 3, I2 | `test_approval_context_round82_real.py`, `test_signed_approval_resume_real.py` |
| 4, I3 | `test_signed_approval_resume_real.py`, `test_fdia_policy_loop_round54_real.py` (roles, several signatures) |
| 4, I4 | `test_fdia_policy_loop_round54_real.py::test_a_signature_cannot_authorise_what_the_policy_now_forbids`, `test_constraints_outside_retrieval_round82_real.py` |
| 4, I5 | `test_approval_context_round82_real.py` |
| 4, I1 | `test_signed_approval_resume_real.py` (at-most-once), `test_crash_windows_round82_real.py` (replayed signature creates no second effect) |
| I6 | `test_gate_properties_round65_real.py` (expiry, pause reaches an approved action) |
| 5, I7 | `test_crash_windows_round82_real.py` (real child processes that die before and after the effect) |
| whole flow | `research/approval_model_check.py`: 10,379 sequences through the real store against a written specification, 0 disagreements; four injected bugs all caught |
| injection | `scripts/measure_injection_defence.py` (23 scenarios, a fully compliant hijacked model: 0 side effects with the gate) |

## Known limits of the argument

- It is an argument over a model of the flow, plus tests of the real code at each step. It is not a machine-checked proof.
- The approval model check covers the approval store, not the whole loop.
- N1 (the raw gateway) and every door added later are outside C1 until they are in the mediation test.
- Items that strengthen it and are not done: a second reviewer reading this file; a run on a Linux host under a separate operating-system user for the notary (A3); an independent witness (the log is then evident against host compromise, still not preventing it).

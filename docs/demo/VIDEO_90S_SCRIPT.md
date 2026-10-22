# Scripted mechanism video — recording plan

Purpose: show the experimental runtime's files, gate, signature wait and audit behaviour. A fixed program replaces the model; this is not capable-model evidence. The times below are an editing outline, not a runtime promise. A recording has not been produced merely because this script exists.

## Before recording

Choose either a source checkout or a published artifact in a fresh virtual environment. Record the actual source commit (if applicable), package version, date and environment. Do not assign a checkout SHA to an unrelated latest package.

```bash
pip install delentia-os
pip show delentia-os
delentia demo init
```

Use the source-install instructions in the [README](../../README.md) when recording a checkout. Use a disposable demo folder and retain the original fixture bytes and full run reports. The demo's approver key lives on the same machine; it does not demonstrate production key custody.

## Shots

| Suggested position | Observable action | Narration scope |
|---|---|---|
| Introduction | Title: “Delentia OS · experimental · SCRIPTED MECHANISM DEMO” | The script replaces the model; files, tools, signatures and audit are real. |
| Compare | `delentia demo run compare --scripted`; show the fixture oracle checks | Report actual pass/fail output. Do not promise a five-second run. |
| Proposed edit | Save/hash `workspace/quotes/vendor_a.md` in the demo folder; run `delentia demo run edit --scripted` | Show `pending_approval` and prove this existing fixture's bytes have not changed. Reports/audit may still be written; say “the protected edit has not occurred”. |
| Approval | Use the actual ID printed: `delentia demo approve ACTUAL_APPROVAL_ID --scripted` | Show the authorized fixture diff after the signature, not a claim that a new result file appears. |
| Replay and audit | Try that same ID again, then `delentia demo status` | Show the actual refusal and chain/signature status for this demo's configuration. Do not verify a demo chain with a different host's key. |
| Limits and close | Link source, release scope, quickstart and full run | These results concern the scripted mechanism. Capable-model, comparative and deployment results are separate. |

If demonstrating audit tampering, use only a disposable copy, verify it with the same run's public key/configuration, and retain the original evidence untouched. Do not edit the host database. Omit this shot if the verification setup has not been checked.

## Recording rules

- Keep the full, unredacted-by-editing sequence for review, but exclude credentials, private keys and personal data from anything shared.
- Label a shorter cut “edited excerpt” and link the full run; disclose interventions and failed attempts.
- Use the actual outputs and measured duration. Do not state “one command, five seconds”.
- Read [release levels](../release/RELEASE_LEVELS.md) for current host/witness status rather than repeating stale “no host anywhere” statements.
- Link the dated [test checkpoint](../testing/TESTING_CANONICAL.md); it is not a fresh full-CI run on the recording machine.
- Do not claim complete RCT fidelity, calibrated safety, certified deployment, tamper-proof logs or automatic main-LLM training.

See the [Thai quickstart](QUICKSTART_TH.md), [English quickstart](QUICKSTART_EN.md) and [current definitions](../public/CURRENT_PUBLIC_INFORMATION_EN.md).

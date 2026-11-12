# Public Technical Preview 0.1: closure plan

Written 2026-11-12 from the repository as it stood that day. Every number below was read from GitHub, PyPI or a file in this repository on that day, or is marked **unknown**. Nothing here declares the milestone: the owner does that (see `VERSIONING_POLICY.md`).

PTP 0.1 is an **L1** milestone (`RELEASE_LEVELS.md`): anyone can install the runtime (pip or the Windows installer) and run it on their own machine, supervised, with a model of their choice. It is **not** package version 0.1.0 and is never a git tag. It does not need a capable-model result, a 72-hour Linux host, an independent witness or an outside pilot (those are L2/L3 gates).

## 1. Verified baseline (2026-11-12)

| Item | Value | Source |
|---|---|---|
| Main | `de7b0f82` (PR #269 merged 2026-11-12; before it `3027b1d2`) | `gh api repos/delentia-labs/Delentia-OS/commits/main` |
| Latest published release | `v2.4.3`, 2026-11-08 (GitHub Release with `Delentia-Setup-2.4.3.exe`, `Delentia-Setup.exe`, `SHA256SUMS.txt`) and PyPI 2.4.3 | `gh release list`, PyPI JSON |
| Unreleased on main | the whole first-run set: #266 passkey fix, #267 no-model first run, #268 ports / own window / install bar / sessions filter / no-model CI check, #269 warm first question, short local connect timeout, breaker, desk gateway, Thai installer text; changelog section `[2.4.4] - Unreleased` | `CHANGELOG.md` |
| Open pull requests | none | `gh pr list` |
| Open issues | 9, all older R&D (LoRA, HF Space, Delta Memory); none is release tracking | `gh issue list` |
| Milestone status | `planned` | `docs/release/compatibility.json` |
| Security Scan | success on main `3027b1d2` on 2026-11-09, 11-10, 11-11 | Actions |
| Code scanning alerts | 0 open | `gh api .../code-scanning/alerts` |
| Dependabot alerts | 5 open, all **development-scope**: 1 medium (`minimatch`, denial of service through glob amplification), 4 low (`deepmerge`, prototype poisoning, no patched version exists) | `gh api .../dependabot/alerts` |
| Readiness snapshot | generated 2026-11-02 from commit `0e29748`: **stale** | `docs/release/READINESS_SNAPSHOT.md` |
| CI on `de7b0f82` | running when this was written: **unknown until it finishes** | Actions |

### Corrections to the outside readiness report of 2026-11-11
* It said PR #269 was open and nothing had moved since 8 November: true that day; #269 was merged on 2026-11-12 after its CI was green.
* It could not read the Dependabot alerts. They can be read: see section 4 (DEL-PTP-04). The failed Dependabot run is not an unfixed hole: Dependabot found a patched `minimatch` (11.0.1) but the only update path would downgrade `eslint-config-next` from 16.4.2 to 15.5.29, so it stopped.
* Everything else in it that was checked (L1 level, `planned`, stale snapshot, green Security Scan, no `v0.1.0` tag) matched the repository.

## 2. GO / NO-GO

GO to declare needs **all** of these (blocking), each with evidence named in the epic:

1. The L0 and L1 gates below read **met** with evidence from the release candidate, not from an older build.
2. No known critical or high release-blocking security issue open; the development-scope alerts are triaged in writing.
3. The Windows installer was run on a computer that is **not the author's** (clean), including the SmartScreen warning as a person sees it, and the Windows Hello / passkey flow was run once with a real authenticator. The result is recorded either way.
4. The release candidate's version, wheel SHA-256, installer SHA-256, Git SHA and CI run ids are written in one place.
5. README, KNOWN_LIMITATIONS, the readiness snapshot and the manifest agree with each other and claim nothing that is not measured.
6. The owner says GO. A failed blocking item stops the release; the rule is never relaxed afterwards.

NOT required for PTP 0.1: a capable-model result (G-model), a Linux host for 72 hours (G-host), an independent witness (G-witness), an outside pilot (G-pilot, G-people), complete RCT-7, an independent security review (G-review), macOS. Each stays in KNOWN_LIMITATIONS.

## 3. Gate matrix (as the repository says today; re-verify on the release candidate)

| Gate | Needed for | Status today | What closes it |
|---|---|---|---|
| G-install | L0 | met (clean-wheel install job in CI) | re-run on the release candidate |
| G-tests | L0 | met at the last quoted checkpoint (9,625 passed on 75e18b4, 2026-11-01; main has moved since) | CI of the final commit; move the checkpoint with `scripts/update_test_checkpoint.py` |
| G-claims | L0 | met for the repository and the website at the last check | `scripts/check_claim_sync.py`, website claims lint, after the last text change |
| G-evidence | L0 | built, **reproduced by nobody but the author** | someone other than the author runs `scripts/evidence_kit.py` and `scripts/verify_evidence_kit.py`; decision for the owner: does the owner's own second computer count, or does it need a third person |
| G-mediation | L1 | met (six doors, mutation test) | keep the test green |
| G-approval | L1 | met (model check, crash windows) | keep green; real-device check is G-windows-hello |
| G-operator | L1 | met as text; nobody but the author has used it | one person follows `OPERATOR_CONTRACT.md` without the author's help (can follow the release) |
| G-installer | L1 | built, installed, checked, uninstalled on the author's PC and on a clean GitHub runner; **not** on another person's computer, SmartScreen not seen, offline install not done; not code-signed | second-computer run (the owner has started it; findings fed 2.4.4) |
| G-windows-hello | L1 (manifest) | **not tested with a real device**; the first Chrome attempt on the second computer found a real defect (fixed in #266) | rerun with 2.4.4 |

## 4. Work packages

`DEL-PTP-nn` are planning ids; the GitHub issue numbers are in the epic.

| Id | Title | Priority | State today | Owner of the next step |
|---|---|---|---|---|
| 00 | Release epic and evidence rules | P0 | this document + the epic | Claude |
| 01 | First-run fixes (#266 to #269) | P0 | **merged**; open: CI of main, release 2.4.4 | Claude prepares, the Architect tags |
| 02 | Clean installation validation (INST-01 to INST-08) | P0 | automated clean-runner install exists; human run on the second computer started with 2.4.3 | the Architect, with a Claude-written checklist |
| 03 | Scripted demo and governance regression (matrix) | P0 | demos exist and pass from the installed wheel; matrix to be run on the release candidate and stored | Claude |
| 04 | Security and dependency triage | P0 | triaged below; no critical or high open | Claude (decision on dismissing the dev-only alerts is the Architect's) |
| 05 | CI, artifact and provenance record | P1 | pieces exist (`check_versions.py`, `SHA256SUMS.txt`, installer workflow); no single record | Claude |
| 06 | Readiness snapshot and public claims | P1 | snapshot stale since 2026-11-02 | Claude, after 05 |
| 07 | Declaration and release | P0 at the end | not started; needs the Architect's GO | the Architect |

### DEL-PTP-04: the alerts, read on 2026-11-12
* `minimatch` (#312, medium, development scope, `apps/gui/package-lock.json`): vulnerable range >= 7.0.0 < 11.0.1, fixed in 11.0.1. It comes in through lint/build tooling, not through anything shipped in the wheel or the Desk bundle. The Dependabot job reported "failure" because the only path to the patched version downgrades `eslint-config-next` (16.4.2 to 15.5.29). Options: (a) an npm `overrides` entry for minimatch with `npm run lint`, `tsc` and the Desk build as the proof, (b) wait for the eslint chain to move, (c) dismiss with the reason "development scope, no untrusted glob input". This plan proposes (a) as a small PR and (c) only if (a) breaks the build; dismissal is the owner's decision.
* `deepmerge` (#299, #302, #303, #304, low, development scope, no patched version): nothing to apply. Dismiss with the reason, or leave open and listed in KNOWN_LIMITATIONS.
* Surfaces to re-check on the release candidate: secrets in logs and artifacts, forbidden paths, signature replay across actions, loopback binding and port ownership (changed in #268), the raw `/mcp` gateway (owner-only, outside the governed loop: already a stated limit), the local shell (same OS user: a stated limit).

## 5. Dependency order

```
01 first-run (merged) --> main CI green --> release 2.4.4 (Architect tags)
                                              |
        02 clean install (2nd computer) <-----+----> 03 demo matrix on the installed 2.4.4
        04 security triage (parallel, needs no release)
                                              |
                                  05 provenance record --> 06 snapshot + claims --> 07 GO / NO-GO --> declaration release
```

## 6. Test matrix for 02 and 03

| Id | Scenario | Pass when |
|---|---|---|
| INST-01 | install on a clean Windows computer | installs and opens |
| INST-02 | no Python installed before | the installer is self-contained (private Python) |
| INST-03 | no Ollama, no model | plain "no model" state, a question ends in about 1 s with a readable sentence |
| INST-04 | port 8000 or 3010 used by another program | Delentia picks another port and does not talk to the stranger |
| INST-05 | restart | data and approver devices are kept |
| INST-06 | uninstall | `~/.delentia` stays; nothing deleted without being told |
| INST-07 | SHA-256 | the file equals its line in `SHA256SUMS.txt` |
| INST-08 | SmartScreen | the warning and the steps are written down as seen |
| DEMO-01 | `demo init --lang en`, `demo run compare --scripted` | 5 of 5 checks, chain intact |
| DEMO-02 | `demo run edit --scripted`, then approve with the real id | stops at `pending_approval`; nothing written before; one signature runs it once |
| DEMO-03 | approve with a wrong signature | refused |
| DEMO-04 | `demo run injection --scripted`, `demo reject` | stops and waits; the refusal is signed |
| DEMO-05 | `delentia audit-chain verify`, then alter one stored row | the chain says it is not intact |
| DEMO-06 | crash and resume | a once-only action is not repeated |

Where a row has only been run by automation, the result is recorded as `automated, not seen by a person`.

## 7. Risks the preview must say aloud
Not code-signed (SmartScreen warns); the local shell is not a jail; the audit log is tamper-evident only with a witness; RCT-7 is partial and not shown to help a capable model; nothing certified; first question after start can still be slow for a few seconds while the server warms up; macOS and Linux desktop untested by a person.

## 8. Deferred (after PTP 0.1)
Capable-model results and the pre-registered ablation; Linux host 72 h; independent witness; outside pilot; code signing; independent security review; the nine older R&D issues (labelled `post-ptp`).

## 9. Versions
The first-run fixes need a release anyway: **2.4.4** (patch: fixes, no new capability). The declaration itself changes `status` to `declared` and the label travels in a wheel, so it needs a package release after 2.4.4 (**2.4.5**, or a higher number if it carries changes). `v0.1.0` is never created. Both numbers are proposals; `scripts/check_versions.py` and the registry decide on the day.

## 10. Exact next actions
1. Wait for CI on `de7b0f82`; if green, prepare 2.4.4 (date in the changelog, release history row); the Architect pushes `v2.4.4`.
2. Verify the 2.4.4 release the same way as 2.4.3 (PyPI in an empty environment, installer and checksum).
3. The Architect re-runs the second-computer checklist with 2.4.4 (INST-01 to INST-08, passkey).
4. Claude runs DEMO-01 to DEMO-06 against the installed 2.4.4 and stores the receipts.
5. Security triage PR for `minimatch`; Architect decides on the dismissals.
6. Provenance record, snapshot regeneration, claims check; then the Architect's GO or NO-GO.

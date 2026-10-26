# Release levels

What may be said and done at each level, and what must be true first. A level is chosen for the **surfaces actually opened**, not for the project as a whole: opening the repository to read is not the same as letting a stranger's agent run on a shared host. A gate that has not been met is written as not met. Nothing here is a promise of a date.

| Level | Meaning | Who | What may be claimed |
|---|---|---|---|
| **L0 Mechanism demo** | The code is public; anyone can run the scripted demos and read the tests. | anyone | "These mechanisms exist and these tests pass." Never "works with a real model", never a safety guarantee. |
| **L1 Local experimental alpha** | The owner runs it on their own machine with a model of their choice, supervised. | the owner | "Runs for me, supervised. Governance is on by default; nothing is proven about unattended use." |
| **L2 Supervised private pilot** | A host the owner controls, a capable model, a few named people, the owner watching metrics and the approvals queue. | owner + invited people | "Used by N named people for D days under supervision; here are the incidents." |
| **L3 Design partner** | A partner's real task, under the operator contract, with an agreed review. | a partner organisation | "Evaluated by one partner on one workflow, with these results." |
| **L4 General availability** | Anyone can deploy and rely on it. | the public | Only after independent review and a stable record. **Not planned.** |

## Milestones

A milestone is a named point on this ladder that the owner declares. It is a label for *what is opened to whom*, never a version number and never a git tag (see [VERSIONING_POLICY.md](VERSIONING_POLICY.md)); its record is `docs/release/compatibility.json`.

| Milestone | Level | Opens | Status |
|---|---|---|---|
| *Public Technical Preview 0.1* | **L1** | `pip install delentia-os`, the Windows installer download, the scripted demos, the Desk on your own machine | planned; the owner declares it when the gates for L0 and L1 below, and G-installer, say so |

## The gates

A gate is **met** only when the named evidence exists and can be re-checked. Status as of 2026-10-19 (the numbers behind each line are in `docs/release/READINESS_SNAPSHOT.md`, generated from the commit, the CI run and the evidence bundles).

| Gate | Needed for | Evidence | Status |
|---|---|---|---|
| G-install | L0 | A clean-wheel install imports, runs the CLI and the scripted demos, starts the server, keeps memory across restarts, and works with a read-only package folder (`scripts/check_installed_wheel.py`, CI job *Package check*) | met: Windows locally, and the *Package check* job in CI installs the built wheel in an empty Linux environment on every change |
| G-tests | L0 | The public test suite passes on three Python versions (CI) | met (7,820 passed on main at 3dbed0d, 2026-10-18, Python 3.10/3.11/3.12) |
| G-claims | L0 | Every public number is a measured one and `check_claim_sync` passes; withdrawn claims stay withdrawn | met for the repository; the website was rewritten and merged on 2026-10-19 with a claims lint in CI, blog bodies and a few glossary pages still carry old wording |
| G-evidence | L0 | `scripts/evidence_kit.py` reproduces the safety headline in one command; `scripts/verify_evidence_kit.py` re-checks it offline | built; **not yet reproduced by anyone but the author** |
| G-mediation | L1 | Every entry point ends at the same gate, with a mutation that proves the test can fail (`test_complete_mediation_round82_real.py`) | met for six doors |
| G-approval | L1 | The approval flow matches its specification (10,379 sequences, 0 disagreements); crash windows tested with real processes | met |
| G-operator | L1 | The operator contract exists and its commands exist (`docs/operators/OPERATOR_CONTRACT.md`) | met (text); no operator other than the author has used it; a backup taken before an erasure still holds that person's words (see section 8 of the contract and `delentia backup erasure-check`) |
| G-installer | L1 (a download is offered) | The Windows installer installs, starts, passes `check_install.py` and uninstalls without touching `~/.delentia` on a **clean** machine; the release carries its checksum | built and run on the author's own machine and, in CI, on a clean Windows runner (once the workflow has run); **a computer that is not the author's and a real SmartScreen/offline check are not done**; not code-signed |
| G-model | L2 | A capable model drives the loop: the capability screen passes (K.1.5 ≥ 90% on the 5-goal and 17-goal batteries) | **not met** (local 8B qwen3: 5 of 5 simple goals in one run, 84-508 s per goal; the 17-goal battery and a capability screen of stronger models have not been run) |
| G-host | L2 | A Linux host runs for 72 hours without manual intervention: no crash, no unexplained pending items, backups taken, one restore performed from an off-host copy | **not met** (the owner's PC runs the host: starts at logon, a real Restart passed on 2026-10-19, a 6-hour soak was clean; no Linux host, no 72-hour run) |
| G-witness | L2 | At least one independent witness holds a recent signed head and `check-witnesses` passes from a machine that is not the host | **not met** (the Worker holds one anchor of the host notary's head from 2026-10-17; the public ledger repository is empty; anchoring is not scheduled; no check from a second machine) |
| G-notary-user | L2 | The notary runs as a different operating-system user from the agent | **met on the owner's PC** (a separate Windows account runs the notary; tool calls fail closed without it, tested 2026-10-17); **not met on a Linux host** |
| G-pilot | L2 | A pre-registered pilot (dev and validation splits, manipulation checks, failure taxonomy) has been run with the capable model | **not met** |
| G-people | L3 | At least one outside person has used it for a real task and told us what broke | **not met** |
| G-review | L4 | An independent security review of the gate and the approval flow | **not met, not planned** |

## What is opened today

| Surface | Level | Why |
|---|---|---|
| Source repository and package on PyPI | L0 | Reading and running scripted demos is safe; every claim in the README is measured or marked "not yet". |
| `delentia serve` on the owner's machine | L1 | The owner supervises; the API is token-protected on any non-loopback host. |
| A shared or public host | **closed** | G-host, G-witness, G-notary-user and G-model are not met. |
| Letting other people use a chat channel | **closed** until L2 | Allowlists and DM pairing exist; no operator has watched a real week. |

## How a level moves

Down is immediate: a failed gate closes the surfaces that depend on it, and the part that failed is closed, not hidden. Up needs the evidence in the table, a short written note of what was measured (with the number of runs, the model, the date), and a person other than the author reading it for L2 and above.

# Start here: install, run, verify, and know the limits

Delentia OS is an experimental, self-hosted AI agent runtime. The model only proposes; the runtime judges each tool call, makes anything that writes, sends or runs code wait for a person's signature, and keeps a signed record you can check. This page is the shortest path from "what is it" to "I checked it myself". Nothing here asks you to trust the author: every claim points to something you can run or read.

**Status:** experimental research software by one author. Not production-stable. No strong hosted model has driven it under controlled comparison yet (see [what is measured](#4-what-is-measured-and-what-is-not)).

## 1. Install

| You are | Do this | What has been checked, and what has not |
|---|---|---|
| On Windows, no Python | [Download `Delentia-Setup.exe`](https://github.com/delentia-labs/Delentia-OS/releases/latest/download/Delentia-Setup.exe) and compare its SHA-256 with `SHA256SUMS.txt` on the same release page | Built, silently installed, checked and uninstalled on a clean GitHub runner on every release, and run on the author's PC. **Not** tested on another person's computer yet. **Not code-signed**: Windows SmartScreen will warn you. |
| A Python user (3.10+) | `pip install delentia-os` | Installed from the real PyPI into an empty environment with `pip check` clean (receipt below). |
| On macOS or Linux | the same `pip install` | Linux is exercised by CI. **macOS has not been tried**: an [install report](https://github.com/delentia-labs/Delentia-OS/issues/new?template=install_report.yml) from you is the most useful thing you can send. |

Approving an action with Windows Hello or another device is built and tested with a software authenticator only; it has **not** been tried with a real Windows Hello yet.

## 2. Run a demo (two minutes, no model, no API key)

```bash
delentia demo init --lang en
delentia demo run injection --scripted
delentia demo status
```

What you will see: an agent reads a note that a stranger hid in a vendor quote, tries to change a price because the note says so, and **stops and waits for a signature**. Nothing is changed until a person signs, and the record of what happened is signed and hash-chained.

**What "scripted" means.** In `--scripted` mode a fixed program stands in for the *language model* and nothing else. These parts are real: the folder and files, the three tools, the safety gate and the owner policy, the rule for untrusted text, the wait for a signature, the signature check, the audit log. These parts are not: the order of the steps and the wording of the answer. In the `injection` demo the script deliberately plays a model that has been talked into something, so the demo shows that **even a fooled model cannot write, send or run code without a signature**. It does **not** show that a real model would be fooled, that every manipulation is stopped, or how good any model is. Every report says this on its first lines.

Why scripted: a first run must not depend on whether a small local model happens to behave (on a CPU a 7B model took minutes per goal and failed some checks). To run the same demo with a real model, set one with `delentia model set` and leave out `--scripted`; expect slower, less repeatable results.

## 3. Verify it yourself

| What | How |
|---|---|
| The release you installed is the release that was tested | [`docs/release/evidence/2.4.4/RECEIPT.md`](release/evidence/2.4.4/RECEIPT.md) (verdict pass, 11 of 11 checks, produced by `scripts/release_receipts.py` from the installed package) and `receipt.json` next to it. Personal paths were removed; nothing else was edited. These receipts were produced by the author, not by an independent party. |
| The audit chain detects an edit | `delentia demo status`, or the DEMO-05 check in the receipt (a copy with one stored value changed fails). It detects changes inside the chain; it does not stop someone who controls the machine and the signing key (see the [threat model](security/THREAT_MODEL.md)). |
| The tests | Continuous integration on `main`: 9,912 passed, 62 skipped, 92.10% coverage (run 43570824206, 2026-11-14). The number belongs to that run, not to your machine. |
| An outsider can check a record | `scripts/verify_audit_bundle.py` verifies an exported bundle with the public key only. |

## 4. What is measured, and what is not

* **Measured, with scripted models:** the gate, signed approvals, the rule for untrusted text, recovery after a killed process, tamper detection.
* **Measured with real models (paid runs, 2026-11-12/13, every result registered, failures included):** which of 22 models can drive the tools (6 qualified), the tool-menu comparison, and a screen of 6 whole-job workflows with one model. The table, with the failures and the cases that could not be concluded: [tested models](public/TESTED_MODELS.md); the register behind it: [`research/RESULTS_PUBLIC.md`](https://github.com/delentia-labs/Delentia-OS/blob/main/research/RESULTS_PUBLIC.md).
* **Not shown:** that the runtime makes an agent succeed at more tasks than a plain agent, that it makes a model's claims more honest, that the model-assisted parts of RCT-7 meet their rules (they do not yet), or any result about reliability over days. No claim in this repository says otherwise.

## 5. Limits and comparisons

[Known limitations](KNOWN_LIMITATIONS.md) · [threat model](security/THREAT_MODEL.md) · [gate properties and the routes not covered](https://github.com/delentia-labs/Delentia-OS/blob/main/research/GATE_PROPERTIES.md) · [comparison with other runtimes](COMPARISON.md) · [RCT-7 status, step by step](public/RCT7_IMPLEMENTATION_STATUS.md)

## 6. How it was built, and where the ideas come from

* **Built with AI coding assistants.** The author designs and directs; most of the code is written together with Claude Code and Codex. You can count it yourself: `git log --format=%B | grep -ci "co-authored-by: \(claude\|codex\)"` against `git rev-list --count HEAD`. As of 2026-11-14 that was 791 of 1,138 commits. What stands behind the code is the tests, the receipts and the recorded failures, not the author's typing.
* **Dates.** The ideas (the FDIA Equation, RCT-7) began, by the author's own account, on 28 June 2025, on paper; no independent timestamp of that paper exists. The first commit in this repository is **11 April 2026**.
* **FDIA** is the author's own framework, `F = (D^I) × A`; it has no official expanded name. In the code it is one input to a gate, used together with the owner's policy and human signatures. In the author's own calibration the equation and the data term alone gave the same held-out result, so no evidence yet that the equation adds anything beyond what a simpler check does.

## 7. Tell us what happened

* [Send an install report](https://github.com/delentia-labs/Delentia-OS/issues/new?template=install_report.yml): what you tried, what happened, what was confusing.
* **Try to break the gate:** a bypass you can reproduce is the most valuable report. Security findings go privately, see [SECURITY.md](https://github.com/delentia-labs/Delentia-OS/blob/main/SECURITY.md).
* **Dispute or reproduce a measurement** with the command in the [results register](https://github.com/delentia-labs/Delentia-OS/blob/main/research/RESULTS_PUBLIC.md).
* Questions and ideas: [Discussions](https://github.com/delentia-labs/Delentia-OS/discussions). Contributing: [CONTRIBUTING.md](https://github.com/delentia-labs/Delentia-OS/blob/main/CONTRIBUTING.md).

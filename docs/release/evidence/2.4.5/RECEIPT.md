# Release receipt: delentia-os 2.4.5 (v2.4.5)

Verdict: **pass** (11 pass, 0 fail, 0 not run)
Run 2026-11-23T13:37:34+0700 on Windows-11-10.0.26300-SP0 with Python 3.13.14. DEMO-* use a scripted stand-in for the model: they show the gate, the approval and the audit, not how well a language model works.

| Check | Result | What was seen |
|---|---|---|
| INSTALL: installed in an empty environment, pip check clean, `delentia --version` says 2.4.5 | PASS | delentia, version 2.4.5 |
| WHEEL-SHA: the wheel pip downloads has the SHA-256 PyPI published | PASS | 12d52644001470e7ed79b563a9af91aa3a372deafd5f229c17434ee3dc5e1475 (PyPI: 12d52644001470e7ed79b563a9af91aa3a372deafd5f229c17434ee3dc5e1475) |
| DEMO-01: compare (scripted): every check passes, the chain is intact and signed, the originals are unchanged | PASS | 5 checks passed, 0 failed; audit {'ok': True, 'rows': 11, 'signed': 11, 'checked_against_own_key': True} |
| DEMO-02: edit (scripted): it stops and waits, the file is unchanged until a signature, one signature changes it, a second approval does not change it again | PASS | approval id 4a76b89d74d8; unchanged while waiting: True; changed after the signature: True; unchanged by a second approval: True |
| DEMO-03: a signature from a key nobody trusts is refused, and the file stays unchanged | PASS | exit code 1; file unchanged: True; VER_PUBKEYS or C:\Users\<USER>\AppData\Local\Temp\delentia-receipts-ms_uak7n\user-home\.delentia\approvers.json); nothing can be approved (fail-closed) |
| DEMO-04: injection (scripted): it stops and waits for a person; refusing it is signed and leaves the files unchanged | PASS | approval id a210b0b64a85; reject exit 0; files unchanged: True |
| DEMO-05: the audit chain verifies, and a copy with ONE stored value changed does not | PASS | intact chain exit 0; altered copy exit 1 (changed one stored value in column entity_type) |
| GITHUB-ASSETS: v2.4.5 carries the wheel, the sdist, both installers and SHA256SUMS.txt, and each installer equals its line | PASS | missing: none; hash mismatch: none; sha256 {'Delentia-Setup-2.4.5.exe': '2a12ce41fdabfb28a38e945a2b3099b8d034293211a648306dbefe9c930fed7e', 'Delentia-Setup.exe': '2a12ce41fdabfb28a38e945a2b3099b8d034293211a648306dbefe9c930fed7e', 'SHA256SUMS.txt': '2432f8de1992cff812cc0a16eac83dd5799ed3090a0fbbb90fd |
| GITHUB-TAG: v2.4.5 points at a full commit and the workflow runs on it are recorded | PASS | commit c548cd8ce556390b9509d2d09a078141631c3428; tag ref tag 396706a1c11f15fc33cf1eae4314effe7945f7ac; runs: Trigger Ecosystem Release success #45007009988, Release success #45007009956, Docs success #44995110824, CodeQL success #44995110713, CI success #44995110815 |
| SOURCE-EVIDENCE-KIT: the evidence kit runs from the repository and its verifier (standard library only) accepts the folder | PASS | kit exit 0, verifier exit 0 |
| DEMO-06: a crash and a resume do not repeat a once-only action (the repository's crash and replay tests) | PASS | ======================== 49 passed in 70.17s (0:01:10) ======================== |

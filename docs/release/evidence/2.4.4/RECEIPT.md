# Release receipt: delentia-os 2.4.4 (v2.4.4)

Verdict: **pass** (11 pass, 0 fail, 0 not run)
Run 2026-11-12T14:29:29+0700 on Windows-11-10.0.26300-SP0 with Python 3.13.14. DEMO-* use a scripted stand-in for the model: they show the gate, the approval and the audit, not how well a language model works.

| Check | Result | What was seen |
|---|---|---|
| INSTALL: installed in an empty environment, pip check clean, `delentia --version` says 2.4.4 | PASS | delentia, version 2.4.4 |
| WHEEL-SHA: the wheel pip downloads has the SHA-256 PyPI published | PASS | e6d456ebc24cb1bc4de12181ae741af4407875ce29b89ea4aebdc2b79cd5652e (PyPI: e6d456ebc24cb1bc4de12181ae741af4407875ce29b89ea4aebdc2b79cd5652e) |
| DEMO-01: compare (scripted): every check passes, the chain is intact and signed, the originals are unchanged | PASS | 5 checks passed, 0 failed; audit {'ok': True, 'rows': 11, 'signed': 11, 'checked_against_own_key': True} |
| DEMO-02: edit (scripted): it stops and waits, the file is unchanged until a signature, one signature changes it, a second approval does not change it again | PASS | approval id 20f819a3f537; unchanged while waiting: True; changed after the signature: True; unchanged by a second approval: True |
| DEMO-03: a signature from a key nobody trusts is refused, and the file stays unchanged | PASS | exit code 1; file unchanged: True; VER_PUBKEYS or C:\Users\<USER>\AppData\Local\Temp\delentia-receipts-oyl2ex23\user-home\.delentia\approvers.json); nothing can be approved (fail-closed) |
| DEMO-04: injection (scripted): it stops and waits for a person; refusing it is signed and leaves the files unchanged | PASS | approval id 292dd9a72edf; reject exit 0; files unchanged: True |
| DEMO-05: the audit chain verifies, and a copy with ONE stored value changed does not | PASS | intact chain exit 0; altered copy exit 1 (changed one stored value in column entity_type) |
| GITHUB-ASSETS: v2.4.4 carries the wheel, the sdist, both installers and SHA256SUMS.txt, and each installer equals its line | PASS | missing: none; hash mismatch: none; sha256 {'Delentia-Setup-2.4.4.exe': '1ea32000f42f297253f8cbd6e7356f4dc4a7d40c4f2d65e8a11bf7e8e7fb9d17', 'Delentia-Setup.exe': '1ea32000f42f297253f8cbd6e7356f4dc4a7d40c4f2d65e8a11bf7e8e7fb9d17', 'SHA256SUMS.txt': '9bcf8523d415c31ca7b6f579a22da9068335d1ca2886ec7df19 |
| GITHUB-TAG: v2.4.4 points at a full commit and the workflow runs on it are recorded | PASS | commit 6cfff4b671342e6ab69c628daa6735e98ca07cb3; tag ref tag 36d88a72fe67af7793471126760a0f108508e651; runs: Release success #43154541084, Trigger Ecosystem Release success #43154541038, Docs success #43154077256, CodeQL success #43154076952, CI success #43154077291 |
| SOURCE-EVIDENCE-KIT: the evidence kit runs from the repository and its verifier (standard library only) accepts the folder | PASS | kit exit 0, verifier exit 0 |
| DEMO-06: a crash and a resume do not repeat a once-only action (the repository's crash and replay tests) | PASS | ============================= 49 passed in 58.49s ============================= |

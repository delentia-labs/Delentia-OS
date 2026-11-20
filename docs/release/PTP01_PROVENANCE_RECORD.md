# Public Technical Preview 0.1: release provenance record (DEL-PTP-05)

One place for the identifiers a reader needs to check a release against what was built. A blank cell means **not yet known**, never "same as above". Values for 2.4.4 were read on 2026-11-20
from the GitHub release page and the PyPI JSON of that version; nothing here is a claim of safety.

| Field | 2.4.4 (published 2026-11-12) | 2.4.5 (not yet released) |
|---|---|---|
| Git tag / commit | `v2.4.4` on `6cfff4b671342e6ab69c628daa6735e98ca07cb3` | |
| Release workflow run | 43154541084 (success) | |
| Wheel (`delentia_os-<v>-py3-none-any.whl`) SHA-256 | `e6d456ebc24cb1bc4de12181ae741af4407875ce29b89ea4aebdc2b79cd5652e` (the same value on PyPI and on the release page) | |
| Source archive SHA-256 | `979b6679e7e1a3a35a2720110e2e1c89f667edb4c14fa74969930b5a37952e53` | |
| Windows installer SHA-256 (`Delentia-Setup-<v>.exe`, also published as `Delentia-Setup.exe`) | `1ea32000f42f297253f8cbd6e7356f4dc4a7d40c4f2d65e8a11bf7e8e7fb9d17` (15,239,522 bytes) | |
| `SHA256SUMS.txt` SHA-256 | `9bcf8523d415c31ca7b6f579a22da9068335d1ca2886ec7df1944c71d9db6e3c` | |
| Installer clean-runner workflow | not read (the two runs found on 2026-11-20 are for other commits; to be read from the tag) | |
| CI run on the tagged commit | | |
| Installed-package receipts (`scripts/release_receipts.py`) | 11 of 11 pass, recorded on issue #274 | |
| Installer run on another person's computer | not done | |
| Real Windows Hello check | not done | |
| Code signing | none (SmartScreen will warn) | |
| Result of the `check_versions.py` rules at release | pass | |

How to fill the 2.4.5 column: read each value from the release page, the PyPI JSON and the Actions run of the tag; recompute the wheel and installer hashes from the downloaded files and compare them with the
published ones and with `SHA256SUMS.txt`; write the run ids. If a value cannot be read, leave the cell empty and say why in the epic.

# Release history

What was published, when, under which number, and what was wrong about it. Dates are the upload times on PyPI / npm / the GitHub release page, read on 2026-10-26 (the changelog's own dates are in the last column where they differ). Nothing here edits a past release: a mistake is corrected in the next release and recorded as a correction at the bottom.

The rules that decide the numbers: [VERSIONING_POLICY.md](VERSIONING_POLICY.md). The levels that decide what may be claimed: [RELEASE_LEVELS.md](RELEASE_LEVELS.md).

## The Python package `delentia-os`

| Version | Published (UTC) | Where | What it was | PyPI status classifier |
|---|---|---|---|---|
| 1.0.0-alpha … 1.8.0 | 2026-04-13 … 2026-06-01 (changelog dates) | git tags `v1.0.0-alpha` … `v1.3.0`; **not on PyPI** (PyPI starts at 2.0.0) | the SDK and its first services, built up in about seven weeks; a number moved quickly in May 2026 (six changelog sections dated 2026-05-26 and 2026-05-27) | n/a |
| 2.0.0 | 2026-05-28 06:51 | PyPI, GitHub | first PyPI release; the SDK with PaymentEngine, NodeNetwork and a Groq adapter | 4 - Beta |
| 2.1.0, 2.2.0 | (tags only) | git tags; **no PyPI release** under these numbers | | n/a |
| 2.2.1 … 2.2.6 | 2026-06-06 02:44, 02:47, 02:51, 03:08, 03:13, 03:43 | PyPI, GitHub | six uploads in one hour: the release pipeline (publishing tokens) was being repaired; the changelog has an entry only for 2.2.6 | **5 - Production/Stable** from 2.2.1 |
| 2.3.0 | 2026-10-13 04:13 | PyPI, GitHub | **the first release that contains the governed agent runtime** (agent loop, tools, gate, approvals, audit chain, memory, channels); earlier PyPI releases were the SDK only. No Desk pages | 5 - Production/Stable |
| 2.3.1 | 2026-10-16 03:16 | PyPI, GitHub | 2.3.0 with OpenCV and faiss-cpu made optional extras; one dependency-export fix. **No Desk, launcher, passkeys, plan-first approval or installer** | 5 - Production/Stable |
| **2.4.0** | 2026-10-26 11:06 | PyPI, GitHub (tag `v2.4.0` on 623f480) | the Desk inside the package, `delentia launch`, the Windows installer, approving with a device, plan-first approval, update notices, RCT-7 questions, Law Pack, and 270 other commits since 2.3.1 (see `CHANGELOG.md`). Installed in an empty environment from PyPI and the installer downloaded from the release and compared with `SHA256SUMS.txt` on the day of release | 3 - Alpha |
| **2.4.1** | 2026-11-01 | PyPI, GitHub (tag `v2.4.1` on a64e410) | the model-free demo in English, the hijacked-model demo, the Setup assistant, the bilingual stage label beside the version (shown only after the owner declares the stage), `delentia demo reset`. Installed from PyPI in an empty environment and the installer compared with `SHA256SUMS.txt` on the day of release | 3 - Alpha |
| **2.4.2** | 2026-11-03 | PyPI, GitHub (tag `v2.4.2` on b20cb6a8) | the first-code window works in the installed program, desktop icon and "Open Delentia now" in the installer, the browser demo. Installed from PyPI in an empty environment (`pip check` clean, 210 Desk files, scripted demo passes); the installer built from the branch workflow after the pinned `get-pip.py` fix (#257) | 3 - Alpha |
| **2.4.4** | 2026-11-12 | PyPI, GitHub (tag `v2.4.4`) | the first-run fixes from the first install on a second clean computer: a question with no model program ends in about a second with a plain sentence, the model row tells whether it can be used, the Models page explains and links to Setup, ports that are not Delentia's are not adopted, the Desk opens in its own window on Windows, the installer bar moves and its text is in Thai, the server warms the first question, the breaker ignores a program that is not there, passkey enrolment works with a real browser's response (not yet tried with a real authenticator), the picture tool is charged to the episode cap. Released BEFORE the second computer was re-run with this version and before the real Windows Hello test; the release that declares *Public Technical Preview 0.1* is still the first to carry the label | 3 - Alpha |
| **2.4.3** | 2026-11-07 (tag pushed 2026-11-08) | PyPI, GitHub (tag `v2.4.3` on 97de16b9) | a model key typed in the Desk is kept on the computer (Windows DPAPI), COMPRESS reads the goal (whole-text and edit goals are shown whole), the Desk's local-model helper without a terminal, installer fixes (#257), local-model speed notes (integrated GPU, thinking), a free reference-video analyzer, pictures under the same guards as text. Released BEFORE the second-computer install and the real Windows Hello test, on the Architect's decision. Checked after the release: installed from PyPI in an empty environment (`pip check` clean, `delentia --version` 2.4.3, the scripted demo passes 5 of 5 checks with 11 signed rows); the installer was built, silently installed, checked and uninstalled on a clean runner, and `Delentia-Setup-2.4.3.exe`, `Delentia-Setup.exe` and the line in `SHA256SUMS.txt` carry the same SHA-256 (`ce5cfe00...e3f4e13`); the `releases/latest/download/Delentia-Setup.exe` link answers 200. Not checked: another person's computer, SmartScreen, a real Windows Hello. The release that declares *Public Technical Preview 0.1* is the first to carry the label | 3 - Alpha |

## Other packages

| Package | Versions on the registry (2026-10-26) | Notes |
|---|---|---|
| npm `@delentia/delentia-os` (TypeScript SDK) | 1.3.0, 1.4.0 (latest 1.4.0) | released by `sdk-v*` tags; moves only when the SDK changes |
| npm `delentia-mcp` (MCP connector, repository `delentia-labs/delentia-mcp`) | 2.0.0, 2.1.0, 2.1.1, 2.1.2 (latest 2.1.2) | its own repository and release process |
| `@delentia/fdia-wasm`, `@delentia/rct-edge` | 1.0.0 in the repository | released by `sdk-v*` tags |
| Windows installer | `Delentia-Setup-2.4.0.exe` and `Delentia-Setup.exe` (15,183,013 bytes) with `SHA256SUMS.txt`, attached to the release of 2.4.0 | the file name carries the runtime version; not code-signed |

## Milestones (labels, not versions)

| Milestone | Release level | Status |
|---|---|---|
| *Public Technical Preview 0.1* / *รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ 0.1* | L1 | planned; declared by the owner when the gates in `docs/release/compatibility.json` say so. The releases that belong to it: from the first one that carries the label (2.4.1 or later) until the next label is declared |

## Corrections

These are written once and not removed. Each says what was wrong, who could have been misled, and what was done.

| # | What was wrong | Found | What was done |
|---|---|---|---|
| C1 | PyPI says **Production/Stable** for 2.2.1, 2.2.6, 2.3.0, 2.3.1, while the README has said "experimental" since the runtime existed. A reader of PyPI could believe it is production-ready | 2026-10-26 | A published release's metadata cannot be edited. 2.4.0 says **3 - Alpha**; the version checker fails a build that calls the package Production/Stable while the README says experimental |
| C2 | While 2.3.1 was being prepared, this repository's changelog listed the Desk, the passkeys and the readiness panel under `[2.3.1]`. Those were written after 2.3.1 was tagged and are not in it | 2026-10-26 | Moved to `[2.4.0]`. `[2.3.1]` now says what the published release contains. The checker fails a changelog whose newest section is not the package version |
| C3 | The README's version badge said 2.3.0 (hand-typed) after 2.3.1 was out, and the architecture block printed "SDK v2.3.0" | 2026-10-26 | the badge reads PyPI; no version is typed in the README |
| C4 | The package description said "Constitutional AI Operating System SDK", which the README no longer says | 2026-10-26 | "a governed, self-hosted AI agent runtime (experimental)" in `pyproject.toml`, `delentia version` and the CLI reference |
| C5 | Changelog dates differ from upload dates for 2.0.0 (05-27 vs 05-28), 2.3.0 (10-12 vs 10-13) and 2.3.1 (10-13 vs 10-16) | 2026-10-26 | recorded here; the 2.3.1 heading was corrected to its publication date. Older headings are left as written |
| C6 | Git tags `v2.1.0` and `v2.2.0` exist with no PyPI release; `CHANGELOG.md` has a stale `## [Unreleased]` heading in the middle (between 1.0.3b0 and 1.0.2a0) | 2026-10-26 | recorded; not edited |
| C7 | The release workflow publishes with `skip-existing: true`, so a tag pushed without a new version number would succeed and publish nothing | 2026-10-26 | the release job runs `scripts/check_versions.py --tag <tag> --registry` and fails on a number that is already on PyPI |

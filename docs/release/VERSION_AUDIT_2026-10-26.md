# Version audit, 2026-10-26

An audit-only look at every place the ecosystem states a version, done before any number was changed. It checks a proposal that said: *keep the package numbers, call the milestone "Public Technical Preview 0.1", fix the metadata that contradicts the "experimental" status*. The policy that came out of it: [VERSIONING_POLICY.md](VERSIONING_POLICY.md).

**Verified** means read from a file in this repository, a git tag, or a public registry on 2026-10-26. **Assumed** means not checked.

## 1. What is published (verified against the registries)

| What | Published | Evidence |
|---|---|---|
| PyPI `delentia-os` | 2.0.0, 2.2.1 … 2.2.6, 2.3.0, **2.3.1 (latest, 2026-10-16)** | `pypi.org/pypi/delentia-os/json` |
| GitHub release | v2.3.1 is *Latest* | `gh release list` |
| npm `@delentia/delentia-os` | 1.3.0, 1.4.0 (latest 1.4.0) | `registry.npmjs.org` |
| npm `delentia-mcp` | 2.0.0, 2.1.0, 2.1.1, 2.1.2 (latest 2.1.2) | `registry.npmjs.org` |
| PyPI classifier of 2.2.1 … 2.3.1 | **5 - Production/Stable** (2.0.0 was 4 - Beta) | the release JSON |

## 2. The finding that changes the plan

**2.3.1 is already published, and it is not this code.** The tag `v2.3.1` (merge of PR #124, 2026-10-16) contains none of: the Desk inside the wheel (`scripts/package_desk.py`), `launcher.py`, `passkeys.py`, `first_device.py`, `update_check.py`, `plan_approval.py`, the Windows installer. 270 commits separate that tag from this branch. Yet this branch's `pyproject.toml` still said `2.3.1`, and its changelog section `[2.3.1]` listed the Desk, the passkeys and the readiness panel.

Consequences if nothing had been done:

1. The Windows installer would have been called `Delentia-Setup-2.3.1.exe` and install something that reports `2.3.1` but is not the 2.3.1 on PyPI.
2. `delentia update` compares the installed number with PyPI's latest: with the same number on both sides it would say "up to date" for someone who has the old release.
3. A tag `v2.3.1` cannot be pushed again, and a **new tag with the old number would publish nothing and say nothing**: `release.yml` uploads with `skip-existing: true`.

So the next package version must be higher than 2.3.1. By Semantic Versioning, added commands, routes, tools and pages with nothing removed is a **minor** change: **2.4.0**.

## 3. Inventory (verified)

Line numbers are those found before the changes in this branch.

| Where | Value | Line | Verdict |
|---|---|---|---|
| `pyproject.toml` | `version = "2.3.1"` → now `2.4.0` | 7 | the single source for the runtime |
| `pyproject.toml` | `Development Status :: 5 - Production/Stable` → now `3 - Alpha` | 20 | contradicted the README's "Status: experimental"; PyPI keeps the old value on old releases |
| `pyproject.toml` | description "Constitutional AI Operating System SDK" | 8 | stale wording; replaced |
| `rct_control_plane/_version.py` | `_FALLBACK_VERSION = "2.3.1"` | 21 | second copy; now checked against `pyproject.toml` |
| `CHANGELOG.md` | `[2.3.1] - 2026-10-13` with 2.4.0 features | 8 | wrong content and date (published 2026-10-16); split into `[2.4.0]` and a true `[2.3.1]` |
| `CHANGELOG.md` | a stray `## [Unreleased]` between 1.0.3b0 and 1.0.2a0 | 360 | stale; left, recorded |
| `README.md` | static badge `version-2.3.0` | 6 | hand-typed, wrong; removed (the PyPI badge reads the registry) |
| `README.md` | "DELENTIA OS SDK v2.3.0" in the architecture block | 215 | hand-typed, wrong; version removed |
| `README.md` | "Releases after 2.3.0 carry the pages inside the package" | 40 | false for 2.3.1; now says 2.4.0 |
| `rct_control_plane/cli.py` | `delentia version` description | 1580 | stale wording; aligned |
| `docs/getting-started/cli-reference.md` | sample output `2.2.6` | 53 | sample; updated |
| `sdk-typescript/package.json` | `@delentia/delentia-os` 1.4.0 | | matches npm |
| `sdk-typescript/packages/*/package.json` | `fdia-wasm` 1.0.0, `rct-edge` 1.0.0 | | released by `sdk-v*` tags |
| `github-action/package.json` | 1.0.0 | | its own |
| `apps/gui/package.json` | 1.0.4 | | private build file; the Desk now ships inside the wheel with the runtime's number |
| `apps/gui/src-tauri/tauri.conf.json`, `Cargo.toml` | 1.0.1 | | **disagrees with `apps/gui/package.json` (1.0.4)**; never released; no claim |
| `installer/windows/delentia.iss` | version comes from the wheel at build time | | right; gained a file-version revision |
| `delentia-labs/delentia-mcp` (other repo) | `package.json` 2.1.2, `server.json` 2.1.2 (twice) | | consistent with npm; separate release process |
| `Delentia-Website` (other repo) | `lib/site-config.ts`: `SITE_VERSION = "2.3.1"`, `SITE_PUBLIC_SDK_VERSION = "2.3.1"`; about a dozen pages print 2.3.x | | correct for the published release; **hand-typed and will go stale at the 2.4.0 release** (a follow-up for that repository) |
| git tags | `v1.0.0-alpha` … `v1.3.0`, `v2.0.0`, `v2.1.0`, `v2.2.0`, `v2.2.1` … `v2.3.1`, `sdk-v1.0.0` | | `v2.1.0` and `v2.2.0` have no PyPI release |

## 4. Workflows that act on a version or a tag (verified)

| Workflow | Trigger | Risk |
|---|---|---|
| `release.yml` | tag `v*` | uploads with `skip-existing: true` (silent no-op on a taken number); notes are cut from the changelog section named after the tag (an empty section gives the generic text) → **fixed**: the job first runs `check_versions.py --tag --registry` |
| `trigger-ecosystem-release.yml` | tags `v[0-9]+.[0-9]+.[0-9]+` and `v…-rc.[0-9]+` | the pre-release pattern is SemVer-style (`-rc.1`) while Python's is PEP 440 (`rc1`): a `v2.5.0rc1` tag triggers `release.yml` but **not** this workflow. Not changed; written in the policy |
| `publish-sdk.yml` | tag `sdk-v*` | separate from the runtime's tags, good |
| `ci.yml` (lint job) | every PR | now also runs the version check |
| *(new)* `windows-installer.yml` | PR touching the installer, `release.yml`, by hand | builds, installs, checks and uninstalls the installer; attaches it to the release |

A milestone tag such as `preview-0.1` would match none of these. A tag such as `v0.1.0` would match both `release.yml` and the ecosystem trigger and would be read as a package number: **never create one**.

## 5. The proposal, checked

| Statement in the proposal | Result |
|---|---|
| Python runtime 2.3.1 in `pyproject.toml`; npm SDK 1.4.0; README badge 2.3.0; changelog newest 2.3.1; classifier Production/Stable against an experimental README | **all verified**, and each is now fixed or checked |
| Do not reset package numbers to 0.1.0 | **agreed**: it would move backwards on a registry that never allows it, and dependency ranges `>=2` would not see it |
| Call the milestone "Public Technical Preview 0.1"; keep it separate from package numbers | **agreed**, and anchored on the project's existing release levels: it is L1 (see the policy). Not a git tag |
| Next package number 2.4.0 | **agreed, and required**: 2.3.1 is taken by a release that lacks the new work (section 2) |
| The proposal did not know 2.3.1 is a different build from this branch | it described the numbers correctly but not that the *content* behind 2.3.1 differs from what was about to be called 2.3.1 |
| MCP server and Desk versions "to be verified" | verified: MCP connector 2.1.2 in its own repository; the Desk has no number of its own |
| `2.4.0rc1` for a test release | possible; `pip` ignores pre-releases unless `--pre`; the installer is not built for pre-release tags by default policy (it would call itself 2.4.0) |
| Zenodo / DOI | not checked here |
| "0.2 / 0.3 / 1.0" milestones | taken as plans only; they follow gates, not dates |

## 6. Assumptions not checked

* Whether anything outside the repositories hard-codes `2.3.1` (documentation pages on other sites, social posts).
* That `windows-latest` runners keep Inno Setup available (the workflow installs it with Chocolatey if not).
* The behaviour of the new Windows workflow on a real runner: written and its pieces tested locally, not yet run on GitHub when this note was written.

# Versioning policy

*Thai version: [VERSIONING_POLICY_TH.md](VERSIONING_POLICY_TH.md). The facts behind this policy (what was found in the repository and in the registries on 2026-10-26): [VERSION_AUDIT_2026-10-26.md](VERSION_AUDIT_2026-10-26.md). What was released when: [RELEASE_HISTORY.md](RELEASE_HISTORY.md).*

A number on a release has to answer three different questions. Mixing them is how a project ends up with an installer called "0.1" that installs "2.4.0".

| Question | Answered by | Example |
|---|---|---|
| **Which build is this, and is it newer than the one I have?** | the **version** of each component (SemVer, only ever goes up) | `2.4.0` |
| **What has been opened to whom?** | the **milestone** (a label, tied to the [release levels](RELEASE_LEVELS.md)) | *Public Technical Preview 0.1* |
| **Exactly what bytes were tested?** | the **provenance record** (git commit, file digests, model id, test run) | commit `a1b2c3d`, SHA-256 of the installer |

A version is never reset to match a milestone, and a milestone is never used as a version.

## 1. Versions: one number per thing that is released on its own

| Component | Where the number is kept (the only place it is typed) | How it is published | Tag |
|---|---|---|---|
| **Python runtime** `delentia-os` (the CLI, the HTTP API, the agent loop, **and the Desk pages built into the wheel**) | `pyproject.toml` | PyPI + GitHub Release | `vX.Y.Z` |
| **Windows installer** | none of its own: it takes the version of the runtime wheel it contains | GitHub Release assets `Delentia-Setup-X.Y.Z.exe` and `Delentia-Setup.exe` | (the runtime's tag) |
| **Desk** (web pages) | none of its own: it is inside the wheel. `apps/gui/package.json` is a private build file, not a release number | with the runtime | |
| **TypeScript SDK** `@delentia/delentia-os` | `sdk-typescript/package.json` | npm | `sdk-vX.Y.Z` |
| `@delentia/fdia-wasm`, `@delentia/rct-edge` | their own `package.json` | npm | `sdk-vX.Y.Z` |
| **Policy-gate GitHub Action** | `github-action/package.json` | this repository | |
| **MCP connector** `delentia-mcp` | its own repository (`delentia-labs/delentia-mcp`) | npm + MCP registry | its own |
| Tauri desktop shell (`apps/gui/src-tauri`) | not released; its number is not a release number and claims nothing | not distributed | |

`docs/release/compatibility.json` records this table in machine-readable form, and `python scripts/check_versions.py` fails when a number that must agree does not.

**A number is typed once.** Every other place that shows it (the fallback in `rct_control_plane/_version.py`, the changelog heading, the installer's file name, `delentia --version`, the Desk's status bar) either reads it or is checked against it. The README has no hand-typed version: its badge reads PyPI.

## 2. What the number means (Semantic Versioning, applied to this project)

`MAJOR.MINOR.PATCH`, with PEP 440 pre-releases for the Python package (`2.5.0a1`, `2.5.0b1`, `2.5.0rc1`).

What counts as the **public surface** of the runtime, the thing the number promises about:

* the `delentia` command line: command names, options, exit codes and what a command prints for a machine to read;
* the HTTP API under `/v1/` and its authentication rules;
* the file formats a person keeps: the owner policy (`fdia_policy.json`), approver files, `.jitna` files, `SKILL.md`, the audit chain and its verifier;
* the names and arguments of the agent's tools (a tool is removed or renamed only in a major release);
* the Python modules documented in the API reference.

| Change | Number |
|---|---|
| A bug fix, a documentation fix, a tighter safety check that does not change what a documented command does | **PATCH** (`2.4.1`) |
| A new command, option, route, tool, page or file format; anything that adds without removing | **MINOR** (`2.5.0`) |
| Removing or renaming something on the list above, or a changed default that makes a previously accepted input fail | **MAJOR** (`3.0.0`) |
| A safety rule that must become **stricter** | PATCH or MINOR with a changelog line saying what now asks or refuses; the owner policy can still only tighten the floor, never loosen it |

Before 1.0 of a *package* SemVer allows anything; this project does not use that freedom: the Python package is already at 2.x and stays there. The package version says nothing about readiness (below).

**Rules that do not bend**

1. **Versions only go up.** Never publish a lower number than one already released. Never reuse a number: PyPI refuses it, and `skip-existing: true` in the release workflow would hide the refusal, which is why the release job runs `scripts/check_versions.py --tag <tag> --registry` first and fails on a number that is taken.
2. **A published release is never edited.** A mistake is corrected in the next release and in a correction note in [RELEASE_HISTORY.md](RELEASE_HISTORY.md) and in the changelog. PyPI's metadata for a published release cannot be changed (2.3.1 still says `Production/Stable`).
3. **The changelog section of a version describes what is in that version's tag**, nothing else. A feature that is on `main` but not in the tag belongs to the next section. (An early draft of the 2.3.1 notes listed work that only exists in 2.4.0; the checker now fails a changelog whose newest section is not the package version.)
4. **Pre-releases are for testing a release process**, not for marketing. `pip` does not install them unless asked (`--pre`).
5. **Tags:** `vX.Y.Z` releases the runtime (workflows `release.yml` and `trigger-ecosystem-release.yml` act on `v*` tags), `sdk-vX.Y.Z` releases the TypeScript packages. **A milestone is never a git tag**, because a tag such as `v0.1.0` would be read as a package version by those workflows.

## 3. The milestone: a label for what is opened to whom

The project already defines **release levels L0 to L4** and the **gates** that must be met before a level is claimed ([RELEASE_LEVELS.md](RELEASE_LEVELS.md)). A milestone is a named point on that ladder, declared by the owner, with its own record in `docs/release/compatibility.json`:

> **Delentia OS — Public Technical Preview 0.1**: release level **L1**. Anyone can install the runtime (pip or the Windows installer) and run it on their own machine with a model of their choice, supervised, and can check what it did. It opens: `pip install delentia-os`, the installer download, the scripted demos, the Desk on your own machine. It keeps closed: a shared or public host, other people using a chat channel, and any claim that a capable model has driven the agent (that is L2).

Rules:

* **The label is not a version and does not reset one.** The installer, the Desk and the package that carry the Preview all have the package's number, shown by `delentia --version`.
* **The label is shown in both languages, beside the version, and only after the declaration.** English: *Public Technical Preview 0.1*. Thai: *รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ 0.1*. It lives in `rct_control_plane/_version.py` (`MILESTONE`); `/health` reports it; the Desk shows it in the side bar and on the Status page, in the language of the interface with the other language as a tooltip; the Windows installer shows both on its welcome page and in the program's comments (Add or remove programs). Before the declaration none of them shows anything. The label travels in the package, so **the declaration is made by a release**: set `declared` to `True` in `_version.py` and `status` to `declared` in `docs/release/compatibility.json` in the same commit (`scripts/check_versions.py` fails if only one of them changes), then release as usual.
* **Which versions belong to which label** is kept in [RELEASE_HISTORY.md](RELEASE_HISTORY.md): the label *Preview 0.1* covers the releases from the first one that carries it, until the next label is declared.
* **It is declared by the owner, not by a build.** `status` in the manifest is `planned` until the owner sets `declared` and fills the commit and digests of what was tested. A release can go out before the milestone is declared: it is then an ordinary release.
* **A gate that is not met is written as not met.** The manifest lists each gate with its status in words; nothing is rounded up.
* Next labels are only a plan: *0.2 External Validation Preview* (people outside the project installed and used it and told us what broke), *0.3 Research Evidence Preview* (benchmarks and ablations others can reproduce), *1.0 Validated Research Baseline*. They follow the gates, not the calendar, and none of them changes a package number.

## 4. The Windows installer

* **File name:** `Delentia-Setup-<runtime version>.exe`, for example `Delentia-Setup-2.4.0.exe`. The same file is also published as **`Delentia-Setup.exe`** so that a link which never changes (`https://github.com/delentia-labs/Delentia-OS/releases/latest/download/Delentia-Setup.exe`) reaches the newest installer. `SHA256SUMS.txt` lists both.
* **Number inside the file:** the product version is the runtime's (`2.4.0`); the Windows *file version* has four parts, `2.4.0.<installer revision>`. The revision is `0` unless the installer itself was rebuilt without a runtime change (a fix to the installer script): then the same runtime is published with revision `1`, `2`, and so on. A fix to the *runtime* is a new runtime version.
* It carries the runtime wheel, so installing `Delentia-Setup-2.4.0.exe` always installs exactly runtime 2.4.0; the packages it depends on come from PyPI at install time (so the installer is not a frozen copy of the whole environment).
* The file name, `AppVersion` and the Windows file version never contain the name of a milestone. Once the stage is declared the **welcome page and the program's comments show it**, in English and Thai (the text comes from a UTF-8 file written by `build_installer.py`, so Thai never travels on a command line). It is **not code-signed yet**: Windows SmartScreen will warn. This is stated in the README next to the download link.

## 5. Provenance: what was tested, byte for byte

A claim in a report (a test count, a measured rate) names the **git commit**, the **digests** of the artifacts used (wheel, installer), the **model id** and the **run** it came from. `python scripts/check_versions.py --print` prints the numbers of a checkout for release notes. Version numbers are not evidence of anything; the record is.

## 6. Releasing, step by step (the owner pushes the tag)

1. Choose the number by section 2. Set it in `pyproject.toml` and `rct_control_plane/_version.py` (the fallback).
2. Put the notes under `## [X.Y.Z] - YYYY-MM-DD` in `CHANGELOG.md` (not `Unreleased`; only what is in this tag).
3. `python scripts/check_versions.py --registry`: the numbers agree and the number is free and newer on PyPI.
4. Update the gates in `docs/release/compatibility.json` and `RELEASE_LEVELS.md` to what is true today.
5. CI is green on the commit (tests on three Python versions, the version check, the Windows installer check).
6. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`. The release workflow checks the tag against the package, builds the wheel (with the Desk inside), publishes to PyPI, creates the GitHub Release, and builds, installs, checks and uploads the Windows installer.
7. Verify from outside: `pip install delentia-os==X.Y.Z` in an empty virtual environment, `delentia --version`, the scripted demo; download the installer from the release page and compare it with `SHA256SUMS.txt`.
8. If a job fails *after* the PyPI upload, re-run only the failed jobs (or run *Windows installer* by hand with the tag): re-running the whole workflow fails at the "number is free" check, on purpose.

## 7. What is deliberately not done

* No renumbering of released versions to make them look like a fresh start (`2.x` stays; "0.1" is a milestone).
* No `v0.1.0` tag, no `0.1.0` package, no second package name.
* No package version used as a statement of readiness. Readiness is the release level and its gates.

# Installation

Pick the row that fits you. Nothing here installs a service that runs anywhere except on your own machine.

| You are | Use |
|---|---|
| On Windows, no Python | [The Windows installer](#windows-installer) |
| A Python user (3.10 or newer) | [`pip install delentia-os`](#python-package) |
| Using a local model | [Python package + Ollama](#using-a-local-model) |
| A contributor | [From source](#from-source-for-contributors) |

## Requirements

| Requirement | Minimum |
|-------------|---------|
| Python (not needed for the Windows installer) | 3.10 or newer |
| OS | Windows, Linux or macOS (the Windows installer is Windows only; macOS has not been tested by the author) |
| A model | Optional: the demos run without one. A real run needs a local model (Ollama) or any OpenAI-compatible endpoint |

## Windows installer

[Download `Delentia-Setup.exe`](https://github.com/delentia-labs/Delentia-OS/releases/latest/download/Delentia-Setup.exe), double-click it, then start **Delentia** from the Start menu.

- It installs for your account only: no administrator rights, nothing starts by itself, and uninstalling never touches your data in `%USERPROFILE%\.delentia`.
- It needs the internet while installing (it fetches the Python packages).
- It is **not code-signed yet**, so Windows SmartScreen will warn. Check the download against the published [`SHA256SUMS.txt`](https://github.com/delentia-labs/Delentia-OS/releases/latest/download/SHA256SUMS.txt) first.
- The installer is attached to every release from 2.4.0 on. Releases 2.3.1 and earlier have no installer and no Desk pages.

Step by step, and what to do if something is wrong: [English](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/demo/INSTALL_WINDOWS_EN.md) · [ภาษาไทย](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/demo/INSTALL_WINDOWS_TH.md).

## Python package

```bash
pip install delentia-os
delentia --version
delentia setup          # checks for a model that answers, offers to make an audit key; writes only under your Delentia folder
delentia serve          # the agent, on this machine
delentia desk           # in another window: opens the Desk (web pages) in your browser
```

Optional extras: `delentia-os[video]` (OpenCV) and `delentia-os[vector]` (faiss). `delentia doctor` checks the installation and says what is missing.

## Using a local model

Install [Ollama](https://ollama.com/download), then run `delentia setup`: it helps you choose a model that answers. Small models complete some simple tasks, not reliably (see the evidence table on the [home page](../index.md#what-is-measured-and-what-is-not)). To use another endpoint, `delentia model show|list|set`: any OpenAI-compatible endpoint or OpenRouter works; a key is read from an environment variable whose name you give, never from a file.

## From source (for contributors)

```bash
git clone https://github.com/delentia-labs/Delentia-OS.git
cd Delentia-OS
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell
pip install -e .
pip install -r requirements.txt -r requirements-dev.txt     # only to run the test suite
```

A source checkout builds the Desk pages once with `python scripts/package_desk.py` (Node.js 20 or newer). The full test suite takes a long time and several tests call a local Ollama; the project's checks are in [CONTRIBUTING](../contributing.md).

!!! warning "The install scripts"
    `install.sh` and `install.ps1` in the repository clone the **main** branch, not a release, so they install unreleased code. Prefer the Windows installer or `pip install delentia-os`; read the scripts before running anything piped from the internet.

## Check it works

```bash
delentia demo init --lang en
delentia demo run compare --scripted
```

The [quick start](quickstart.md) explains what each step shows.

## Your data, and uninstalling

Everything the agent keeps (memory, the audit log, keys you made) is under `%USERPROFILE%\.delentia` (Windows) or `~/.delentia`. Where it is, how to back it up, how to erase one person and what that does not remove: [Your data](https://github.com/delentia-labs/Delentia-OS/blob/main/docs/demo/YOUR_DATA_EN.md).

!!! note "Older instructions"
    The previous version of this page described a beta install for an earlier release. It is kept as [historical text](../reference/legacy-installation.md).

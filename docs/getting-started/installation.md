# Installation

## Requirements

| Requirement | Minimum |
|-------------|---------|
| Python | 3.10+ |
| OS | Linux, macOS, Windows |

---

## Distribution Status

!!! warning "Beta Preview — Packaging Ready, Public PyPI Pending"
    `delentia-os` v1.0.4b0 can be installed from source today and now supports clean wheel installs.
    Public PyPI publication is still a separate release step.

Current supported install paths:

- editable/source install from this repository
- local wheel install from `dist/` after `python -m build`

---

## From Source (Development)

```bash
git clone https://github.com/delentia-labs/delentia-os.git
cd delentia-os

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell

# Install the SDK in editable mode
pip install -e .

# Install dev + test dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## First-Run CLI Check

After installation, validate the CLI before adding secrets:

```bash
rct version
rct start --ui-test
rct init
rct doctor
```

`rct init` now creates `.env` from the local project template when available and falls back to a built-in template in clean-room installs.

---

## Verify with Tests

```bash
pytest --tb=short -q
# → 723 passed in ~3s
```

---

## What Gets Installed

```
delentia-os/
├── core/           ← FDIA engine, Delta engine, Regional adapter
├── signedai/       ← SignedAI consensus, HexaCore registry
├── rct_control_plane/  ← 15-module DSL + intent schema
└── microservices/  ← 5 reference microservices (read-only SDK)
```

The `rct` CLI entry point is registered automatically after installation:

```bash
rct --help
rct version
rct start --ui-test
rct init
rct doctor
rct compile intent.json
rct graph build --policy default
```

---

## Interactive Playground (No Install)

Run the FDIA + SignedAI demos directly in your browser via Google Colab — no local install required:

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/rctlabs/delentia-os/blob/main/notebooks/rct_playground.ipynb)

The notebook walks through:
1. FDIA equation scoring (`F = D^I × A`)
2. SignedAI tier routing
3. Delta Engine compression concept
4. Tier 9 full pipeline

> **Note:** The Colab notebook is included in the `notebooks/` directory of this repository.

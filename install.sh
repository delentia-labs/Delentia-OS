#!/usr/bin/env bash
# Delentia OS - one-line installer for Linux, macOS, and WSL2.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/delentia-labs/delentia-os/main/install.sh | bash
#
# What this does, in order:
#   1. Checks for git and a usable Python (>=3.10) already on this machine.
#      It does NOT attempt to install system packages itself (no sudo, no
#      package-manager calls) - if either is missing, it prints the exact
#      command for this platform and exits, rather than silently taking
#      over the system.
#   2. Clones delentia-labs/delentia-os (or reuses the current directory if
#      it's already a checkout of it).
#   3. Creates a project-local virtualenv (.venv) and installs the base
#      package into it via pip. The base install is deliberately light -
#      heavy extras (diffusion/media-ai, which pull in torch) are opt-in
#      via `pip install -e ".[diffusion,media-ai]"` afterward, not part of
#      this script, so the common path stays fast and small.
#   4. Prints the exact next commands: activate the venv, run
#      `delentia doctor` (the CLI's own real preflight check), and how to
#      point it at a local Ollama model for a fully offline setup.
#
# This script installs into a normal user-owned virtualenv only. It never
# requires or requests elevated privileges.

set -euo pipefail

REPO_URL="https://github.com/delentia-labs/delentia-os.git"
INSTALL_DIR="${DELENTIA_INSTALL_DIR:-$HOME/delentia-os}"

info()  { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
warn()  { printf '\033[1;33m!!\033[0m %s\n' "$1"; }
fail()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

# --- 1. Preflight: git and Python, no auto-install ---------------------

if ! command -v git >/dev/null 2>&1; then
  fail "git is required but not found. Install it first, e.g.:
  Debian/Ubuntu: sudo apt-get install -y git
  Fedora:        sudo dnf install -y git
  macOS:         xcode-select --install   (or: brew install git)
Then re-run this installer."
fi

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
    major="${version%%.*}"
    minor="${version##*.}"
    if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  fail "Python 3.10+ is required but was not found on PATH. Install it first, e.g.:
  Debian/Ubuntu: sudo apt-get install -y python3.11 python3.11-venv
  Fedora:        sudo dnf install -y python3.11
  macOS:         brew install python@3.11
Then re-run this installer."
fi
info "Using $($PYTHON_BIN --version) at $(command -v "$PYTHON_BIN")"

# --- 2. Get the source: reuse cwd if already the right repo, else clone -

if [ -f "pyproject.toml" ] && grep -q '^name = "delentia-os"' pyproject.toml 2>/dev/null; then
  info "Already inside a delentia-os checkout ($(pwd)) - installing in place."
  INSTALL_DIR="$(pwd)"
elif [ -d "$INSTALL_DIR/.git" ]; then
  info "Found an existing checkout at $INSTALL_DIR - pulling latest main."
  git -C "$INSTALL_DIR" pull --ff-only origin main
else
  info "Cloning $REPO_URL into $INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# --- 3. Virtualenv + base install ---------------------------------------

if [ ! -d ".venv" ]; then
  info "Creating virtualenv at $INSTALL_DIR/.venv"
  "$PYTHON_BIN" -m venv .venv
fi

# Normally .venv/bin/activate (Linux/macOS/WSL2 with a real POSIX Python).
# Falls back to .venv/Scripts/activate for the case where this script runs
# under a POSIX shell (e.g. Git Bash) against a native Windows Python,
# which lays out venvs the Windows way regardless of the calling shell -
# confirmed by direct testing on this exact combination, not assumed.
if [ -f ".venv/bin/activate" ]; then
  ACTIVATE_REL=".venv/bin/activate"
elif [ -f ".venv/Scripts/activate" ]; then
  ACTIVATE_REL=".venv/Scripts/activate"
else
  fail "Could not find the virtualenv activation script under .venv/bin or .venv/Scripts."
fi
# shellcheck disable=SC1090
source "$ACTIVATE_REL"

info "Installing delentia-os (base package) - this can take a minute..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e .

# --- 4. Done: real next steps, not just "it worked" ---------------------

echo
info "Installed. To use it in a NEW terminal, first activate the venv:"
echo "    source \"$INSTALL_DIR/$ACTIVATE_REL\""
echo
info "Then, in order:"
echo "    delentia doctor     # real preflight check - tells you exactly what's missing"
echo "    delentia init       # creates a local .env from the template"
echo "    delentia chat       # start the terminal chat UI"
echo
info "For a fully local, zero-cloud setup (no API keys, nothing leaves this machine):"
echo "    1. Install Ollama:  https://ollama.com/download"
echo "    2. Pull a model:    ollama pull llama3.1"
echo "    3. delentia already talks to Ollama at http://127.0.0.1:11434 by default."
echo
info "Optional heavier extras (image generation, video/audio analysis - pulls in torch):"
echo "    pip install -e \".[diffusion,media-ai]\""

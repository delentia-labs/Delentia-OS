"""
Where the runtime keeps its databases (Round 50).

Until now the defaults were: audit/RCTDB `rct_control_plane_agentic.db`
*relative to the working directory* (so `delentia serve` started from two
folders had two separate audit chains), and skills in `rct_control_plane.db`
at the repository root - the same file the test suite wrote to, which is how a
real Desk run showed "271 skills learned" that were all "Say hello and finish"
from tests.

Rules, most specific first:
  1. an explicit path argument or the variable that names one
     (RCT_DB_PATH, RCT_AGENTIC_DB_PATH);
  2. DELENTIA_HOME (a directory): <home>/control_plane.db, <home>/agentic.db;
  3. the legacy defaults above, unchanged, so nothing moves unless asked.

The test suite sets DELENTIA_HOME to a temporary directory (root conftest.py),
so tests never touch a real runtime's data.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

HOME_ENV = "DELENTIA_HOME"
_REPO_ROOT = Path(__file__).resolve().parent.parent


def data_home() -> Optional[Path]:
    raw = (os.getenv(HOME_ENV) or "").strip()
    return Path(raw).expanduser() if raw else None


def _under_home(name: str) -> Optional[str]:
    home = data_home()
    if home is None:
        return None
    home.mkdir(parents=True, exist_ok=True)
    return str(home / name)


def is_source_checkout() -> bool:
    """True when this code runs from a git/source checkout (pyproject.toml beside the package), False when it was pip-installed into site-packages."""
    return (_REPO_ROOT / "pyproject.toml").exists()


def legacy_default(name: str) -> str:
    """The default place for a database file when neither an explicit path nor DELENTIA_HOME says otherwise.

    From a source checkout this is the repository root, exactly as before (nothing moves). From an INSTALLED package the repository root is site-packages: writing there fails on a
    read-only install (system Python, a container run as a normal user) and, on a writable one, puts the person's data where an upgrade or uninstall deletes it. Round 82: the install-contract
    check on Linux found this. An installed package keeps such files under ~/.delentia instead.
    """
    if is_source_checkout():
        return str(_REPO_ROOT / name)
    base = Path.home() / ".delentia"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / name)


def control_plane_db_path() -> str:
    """Skills and the general control-plane store."""
    return os.environ.get("RCT_DB_PATH") or _under_home("control_plane.db") or legacy_default("rct_control_plane.db")


def agentic_db_path() -> str:
    """The kernel's persistence: audit trail + hash chain, RCTDB experiments,
    pending approvals, tool-output store."""
    return os.environ.get("RCT_AGENTIC_DB_PATH") or _under_home("agentic.db") or ("rct_control_plane_agentic.db" if is_source_checkout() else legacy_default("agentic.db"))


def describe() -> dict:
    home = data_home()
    agentic = agentic_db_path()
    return {
        "home": str(home) if home else None,
        "agentic_db": str(Path(agentic).resolve()),
        "control_plane_db": str(Path(control_plane_db_path()).resolve()),
        "source": (HOME_ENV if home else "legacy defaults (working directory / repository root)"),
    }

"""Shared package version helpers for RCT Control Plane surfaces."""

from __future__ import annotations

import importlib.metadata as _metadata

# Real, confirmed drift fixed here (2026-09-24): this used to be a second,
# independently-hardcoded literal ("2.0.0") that had silently fallen behind
# pyproject.toml's real version - `delentia version` (which reads
# importlib.metadata directly) reported the real version, while every OTHER
# surface that imports PACKAGE_VERSION from here (api.py's actual running
# FastAPI app.version, several cli.py health/status responses) reported the
# stale 2.0.0. Reading from the installed package's own metadata makes
# pyproject.toml's [project].version the single real source of truth
# everywhere, matching what version_command() already did correctly on its
# own. _FALLBACK_VERSION only applies to a genuinely non-installed source
# checkout (no `pip install -e .` run) - not the value that matters day to
# day, but kept in step with pyproject.toml's own bumps (2026-09-25:
# 2.2.6 -> 2.3.0, see CLAUDE.md item G) so the rare fallback path isn't
# badly stale either.
_FALLBACK_VERSION = "2.4.1"

try:
    PACKAGE_VERSION = _metadata.version("delentia-os")
except _metadata.PackageNotFoundError:
    PACKAGE_VERSION = _FALLBACK_VERSION


# The name of the stage at which Delentia has been opened to the public (docs/release/VERSIONING_POLICY.md). It is a LABEL beside the version, never a version: the installer, PyPI and every
# tag carry the package number only. `declared` stays False until the owner declares the milestone; the Desk and the installer show the label only after that, and
# scripts/check_versions.py fails if this block and docs/release/compatibility.json disagree.
MILESTONE = {
    "id": "preview-0.1",
    "number": "0.1",
    "release_level": "L1",
    "name_en": "Public Technical Preview",
    "name_th": "รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ",
    "declared": False,
}


def milestone_labels() -> "dict[str, str] | None":
    """The label in both languages once the milestone is declared, else None. 'both' is the one line used where there is room for two languages (installer, README, logs)."""
    if not MILESTONE["declared"]:
        return None
    en = f"{MILESTONE['name_en']} {MILESTONE['number']}"
    th = f"{MILESTONE['name_th']} {MILESTONE['number']}"
    return {"en": en, "th": th, "both": f"{en} ({th})"}


def milestone_for_health() -> "dict[str, str] | None":
    """What /health reports: the ids and both names, only when declared."""
    labels = milestone_labels()
    if labels is None:
        return None
    return {"id": str(MILESTONE["id"]), "number": str(MILESTONE["number"]), "release_level": str(MILESTONE["release_level"]), "name_en": str(MILESTONE["name_en"]),
            "name_th": str(MILESTONE["name_th"]), **labels}


def get_package_version() -> str:
    """Return the source-controlled package version used across release surfaces."""
    return PACKAGE_VERSION

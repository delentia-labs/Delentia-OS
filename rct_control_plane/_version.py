"""Shared package version helpers for RCT Control Plane surfaces."""

from __future__ import annotations

import importlib.metadata as _metadata

# Real, confirmed drift fixed here (2026-09-24): this used to be a second,
# independently-hardcoded literal ("2.0.0") that had silently fallen behind
# pyproject.toml's real version ("2.2.6") - `delentia version` (which reads
# importlib.metadata directly) reported 2.2.6, while every OTHER surface
# that imports PACKAGE_VERSION from here (api.py's actual running FastAPI
# app.version, several cli.py health/status responses) reported the stale
# 2.0.0. Reading from the installed package's own metadata makes
# pyproject.toml's [project].version the single real source of truth
# everywhere, matching what version_command() already did correctly on its
# own. _FALLBACK_VERSION only applies to a genuinely non-installed source
# checkout (no `pip install -e .` run) - not a value to bump by hand going
# forward.
_FALLBACK_VERSION = "2.2.6"

try:
    PACKAGE_VERSION = _metadata.version("delentia-os")
except _metadata.PackageNotFoundError:
    PACKAGE_VERSION = _FALLBACK_VERSION


def get_package_version() -> str:
    """Return the source-controlled package version used across release surfaces."""
    return PACKAGE_VERSION

"""Shared package version helpers for RCT Control Plane surfaces."""

from __future__ import annotations


PACKAGE_VERSION = "1.2.0"


def get_package_version() -> str:
    """Return the source-controlled package version used across release surfaces."""
    return PACKAGE_VERSION

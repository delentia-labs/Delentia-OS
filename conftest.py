"""
Root conftest.py — pytest configuration + Hypothesis profiles.

Profiles:
  ci          50 examples   — GitHub Actions default (fast)
  dev        200 examples   — local development
  intensive 1000 examples   — pre-release verification

Usage:
  pytest --hypothesis-profile=dev            # 200 examples
  pytest --hypothesis-profile=intensive      # 1000 examples
  (no flag)                                  # ci profile = 50 examples
"""
import sys
import os

from hypothesis import HealthCheck, settings

# ── Hypothesis profiles ────────────────────────────────────────────────────

settings.register_profile(
    "ci",
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
)

settings.register_profile(
    "dev",
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
)

settings.register_profile(
    "intensive",
    max_examples=1000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

# Load CI profile by default (overridden by --hypothesis-profile flag)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))

# ── UTF-8 encoding (Windows CP874 guard) ──────────────────────────────────
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

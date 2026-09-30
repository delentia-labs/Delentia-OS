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
import tempfile

from hypothesis import HealthCheck, settings

# ── Isolate runtime data (Round 50) ────────────────────────────────────────
# Before this, tests wrote to the same skills/audit databases a real runtime
# uses (a Desk run showed "271 skills learned", all "Say hello and finish"
# from tests). Point DELENTIA_HOME at a fresh temp directory before anything
# imports rct_control_plane. Set DELENTIA_TEST_KEEP_HOME=1 to opt out.
if not os.environ.get("DELENTIA_TEST_KEEP_HOME"):
    os.environ["DELENTIA_HOME"] = tempfile.mkdtemp(prefix="delentia-test-home-")
    os.environ.pop("RCT_DB_PATH", None)
    os.environ.pop("RCT_AGENTIC_DB_PATH", None)

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


# ── Keep the Intent Loop switches out of unrelated tests (Round 51) ─────────
# `delentia serve` turns the algorithm pipeline and warm recall on with
# os.environ.setdefault; a test that calls serve in-process would otherwise
# leave them on for every test after it.
import pytest  # noqa: E402

_ROUND51_SWITCHES = ("DELENTIA_ALGORITHM_PIPELINE", "DELENTIA_WARM_RECALL", "DELENTIA_PIPELINE_ALLOW_LLM")


@pytest.fixture(autouse=True)
def _round51_switches_start_and_end_off():
    saved = {name: os.environ.pop(name, None) for name in _ROUND51_SWITCHES}
    yield
    for name, value in saved.items():
        os.environ.pop(name, None)
    # values present before the test are not restored on purpose: a developer's
    # shell setting must not change what the test suite exercises.

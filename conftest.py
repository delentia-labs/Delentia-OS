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

_ROUND51_SWITCHES = ("DELENTIA_ALGORITHM_PIPELINE", "DELENTIA_WARM_RECALL", "DELENTIA_PIPELINE_ALLOW_LLM", "DELENTIA_RATE_LIMIT", "DELENTIA_STARTER_SKILLS", "DELENTIA_CONTEXT_FILES", "DELENTIA_EPISODES_PER_HOUR_PER_USER",
                    # Round 63: `serve` also sets these, and a test that called it in-process left the background daemon ON for every later test. The audit-witness test then started
                    # an app whose daemon anchored a stale chain from an earlier test to the same witness (the Worker answered "rollback or fork"; git: index.lock). It failed in three
                    # full runs (Rounds 61-63) and passed alone; running any `serve` test before it reproduces it.
                    "DELENTIA_DAEMON_ENABLED", "DELENTIA_MEMORY_NUDGE")


@pytest.fixture(autouse=True)
def _model_circuit_breakers_start_closed():
    """The provider circuit breakers are shared per endpoint and process (that is their job); a test that simulates an
    outage must not leave the next test facing an open circuit."""
    module = sys.modules.get("rct_control_plane.provider_breaker")
    if module is not None:
        module.reset_all()
    yield
    module = sys.modules.get("rct_control_plane.provider_breaker")
    if module is not None:
        module.reset_all()


@pytest.fixture(autouse=True)
def _round51_switches_start_and_end_off():
    saved = {name: os.environ.pop(name, None) for name in _ROUND51_SWITCHES}
    yield
    for name in saved:
        os.environ.pop(name, None)
    # values present before the test are not restored on purpose: a developer's
    # shell setting must not change what the test suite exercises.


# ── Every test gets its own data home (Round 60) ───────────────────────────────
# The session-wide DELENTIA_HOME above keeps tests away from a real runtime's data, but inside a run every test still shared one set of databases: a Round 58
# test that wrote to the default agentic.db passed alone and failed in a full run, because earlier tests had left unsigned rows in it (CI caught it on all three
# Python versions). Code that resolves its store when it is CALLED (the CLI, the gateways' pairing store, cron, sessions...) now gets a fresh one per test.
# Singletons that bind a path at import (the kernel in mcp_server, SkillLibrary's default) stay per-session, as before.
@pytest.fixture(autouse=True)
def _each_test_has_its_own_data_home(tmp_path_factory, monkeypatch):
    if os.environ.get("DELENTIA_TEST_KEEP_HOME"):
        yield
        return
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("RCT_DB_PATH", raising=False)
    monkeypatch.delenv("RCT_AGENTIC_DB_PATH", raising=False)
    yield


# ── Optional shuffling to expose order dependence (Round 60) ───────────────────
# `pytest --shuffle-seed=N` runs modules, classes and the tests inside them in a seeded random order (no extra package needed; the same seed gives the same order).
def pytest_addoption(parser):
    parser.addoption("--shuffle-seed", action="store", default=None, help="run the tests in a random order derived from this integer seed")


def pytest_collection_modifyitems(config, items):
    seed = config.getoption("--shuffle-seed")
    if seed is None:
        return
    import random
    rng = random.Random(int(seed))
    keys: dict = {}

    def rank(key):
        if key not in keys:
            keys[key] = rng.random()
        return keys[key]
    items.sort(key=lambda item: (rank(("m", item.module.__name__ if getattr(item, "module", None) else "")),
                                 rank(("c", item.cls.__name__ if getattr(item, "cls", None) else "", item.module.__name__ if getattr(item, "module", None) else "")),
                                 rank(("i", item.nodeid))))
    print(f"\n[shuffle] running {len(items)} tests with --shuffle-seed={seed}")

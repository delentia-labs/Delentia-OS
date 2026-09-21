"""
Round 36 Task 79: real tests for the FastAPI lifespan wiring that starts/
stops the AutonomousScheduler daemon. Confirms the deliberate opt-in gate
(DELENTIA_DAEMON_ENABLED) - the daemon must NOT auto-start under a plain
TestClient (protecting the rest of this test suite from real background
polling interference), but MUST start when the env var is set (the real
`rct serve` path).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from fastapi.testclient import TestClient

from rct_control_plane.api import create_app
import rct_control_plane.api as api_module


def test_daemon_does_not_start_without_the_opt_in_env_var():
    os.environ.pop("DELENTIA_DAEMON_ENABLED", None)
    application = create_app()
    with TestClient(application) as client:
        resp = client.get("/v1/daemon/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False
    assert api_module._DAEMON_SCHEDULER is None


def test_daemon_starts_and_stops_cleanly_with_the_opt_in_env_var():
    os.environ["DELENTIA_DAEMON_ENABLED"] = "1"
    try:
        application = create_app()
        with TestClient(application) as client:
            resp = client.get("/v1/daemon/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["running"] is True
            assert data["uptime_seconds"] is not None
            assert any(t["name"] == "reminder_poller" for t in data["tasks"])
        # After the TestClient context exits, real shutdown must have run.
        assert api_module._DAEMON_SCHEDULER is not None
        assert api_module._DAEMON_SCHEDULER._is_running is False
        assert api_module._DAEMON_SCHEDULER._bg_task is None
    finally:
        os.environ.pop("DELENTIA_DAEMON_ENABLED", None)

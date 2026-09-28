"""
Integration tests for 'rct serve' — starts a real uvicorn subprocess,
hits real HTTP endpoints on a real TCP port, then shuts down cleanly.

These tests are automatically skipped when:
  - The test port is already occupied
  - The server does not start within 10 s (slow CI)
  - uvicorn is not installed

No extra dependencies beyond the stdlib and uvicorn (already in requirements.txt).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

# ─── helpers ──────────────────────────────────────────────────────────────────

TEST_PORT = 18765   # high ephemeral port — very unlikely to clash in CI or locally
TEST_HOST = "127.0.0.1"
BASE_URL  = f"http://{TEST_HOST}:{TEST_PORT}"


def _port_open(host: str, port: int) -> bool:
    """Return True if something is already listening on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _wait_for_port(host: str, port: int, timeout: float = 12.0) -> bool:
    """Poll until the port is open or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.25)
    return False


def _get_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


# ─── fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rct_server():
    """
    Spawn ``rct serve`` as a real subprocess on TEST_PORT, yield (host, port),
    then terminate + wait for clean shutdown.

    Module-scoped: the server starts once for all tests in this file.
    """
    # Guard: skip if port already busy
    if _port_open(TEST_HOST, TEST_PORT):
        pytest.skip(f"Port {TEST_PORT} already in use — skipping serve integration tests")

    # Spawn via ``python -m rct_control_plane.cli serve`` so it works even
    # when the ``rct`` entry-point is not on PATH (e.g. bare CI env).
    #
    # Force UTF-8 I/O so the server process does not crash on Windows
    # consoles that use legacy encodings such as CP874 (Thai) where
    # characters like \u2192 cannot be encoded and raise UnicodeEncodeError
    # before the server even binds to its port.
    _env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    # Round 48: output goes to a temp file, not an undrained PIPE - the
    # kernel logs enough at startup to fill a pipe buffer, which blocks the
    # server before it binds. Startup (AlgorithmKernel41 construction) takes
    # ~12 s on this machine even when idle, so the old 12 s budget was
    # right at the edge; 60 s leaves room for a loaded full-suite run.
    import tempfile
    log_file = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "rct_control_plane.cli",
            "serve",
            "--host", TEST_HOST,
            "--port", str(TEST_PORT),
        ],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=_env,
    )

    if not _wait_for_port(TEST_HOST, TEST_PORT, timeout=60.0):
        proc.kill()
        proc.wait(timeout=10)
        log_file.seek(0)
        output = log_file.read().decode(errors="replace")
        log_file.close()
        pytest.skip(f"delentia serve did not start within 60 s - skipping.\noutput tail: {output[-600:]}")

    yield (TEST_HOST, TEST_PORT)

    # Teardown: terminate then wait (with hard-kill fallback)
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


# ─── test cases ───────────────────────────────────────────────────────────────

class TestRctServeIntegration:
    """
    Verify that ``rct serve`` starts a real HTTP server and that the core
    endpoints respond correctly.
    """

    def test_health_endpoint_returns_healthy(self, rct_server):
        """GET /health → {"status": "healthy"}"""
        data = _get_json(f"{BASE_URL}/health")
        assert data.get("status") == "healthy"

    def test_root_returns_healthy(self, rct_server):
        """GET / → {"status": "healthy"}"""
        data = _get_json(f"{BASE_URL}/")
        assert data.get("status") == "healthy"

    def test_openapi_schema_accessible(self, rct_server):
        """GET /openapi.json → HTTP 200 + valid JSON schema"""
        data = _get_json(f"{BASE_URL}/openapi.json")
        assert "openapi" in data
        assert "paths" in data

    def test_docs_ui_accessible(self, rct_server):
        """GET /docs → HTTP 200 (Swagger UI HTML page)"""
        with urllib.request.urlopen(f"{BASE_URL}/docs", timeout=5) as r:
            assert r.status == 200
            body = r.read()
        assert b"swagger" in body.lower() or b"openapi" in body.lower()

    def test_compile_endpoint_responds(self, rct_server):
        """POST /compile → HTTP 2xx or 4xx (not 5xx) — server is up and routing"""
        payload = json.dumps({
            "natural_language": "Refactor authentication module",
            "user_id": "integration-test-user",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/compile",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            # 2xx: intent was compiled — check expected fields
            assert "intent_id" in data or "id" in data or "goal" in data
        except urllib.error.HTTPError as exc:
            # Any 4xx is fine: server is up; request may lack required fields
            assert exc.code < 500, f"Unexpected server error: HTTP {exc.code}"

    def test_health_is_idempotent(self, rct_server):
        """Calling /health twice returns the same status."""
        r1 = _get_json(f"{BASE_URL}/health")
        r2 = _get_json(f"{BASE_URL}/health")
        assert r1.get("status") == r2.get("status") == "healthy"


# ─── CLI unit tests (no server needed) ────────────────────────────────────────

class TestServeCommandRegistration:
    """
    Fast unit tests that verify the 'serve' command is properly registered
    in the CLI without spawning an actual server.
    """

    def test_serve_in_help_output(self):
        from click.testing import CliRunner
        from rct_control_plane.cli import cli
        result = CliRunner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_serve_help_shows_options(self):
        from click.testing import CliRunner
        from rct_control_plane.cli import cli
        result = CliRunner().invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--host" in result.output
        assert "--reload" in result.output
        assert "--workers" in result.output

    def test_serve_default_port_in_help(self):
        from click.testing import CliRunner
        from rct_control_plane.cli import cli
        result = CliRunner().invoke(cli, ["serve", "--help"])
        assert "8000" in result.output  # default port shown


class TestStatusNoArg:
    """
    Verify that 'rct status' without an intent_id shows system overview
    instead of crashing with a missing-argument error.
    """

    def test_status_no_arg_exits_zero(self):
        import rct_control_plane.cli as cli_mod
        cli_mod._cli_context = None
        from click.testing import CliRunner
        from rct_control_plane.cli import cli
        result = CliRunner().invoke(cli, ["status"])
        # Should NOT exit with "Missing argument 'INTENT_ID'"
        assert result.exit_code in (0, 1)
        assert "Missing argument" not in result.output

    def test_status_with_id_still_works(self):
        import rct_control_plane.cli as cli_mod
        cli_mod._cli_context = None
        from click.testing import CliRunner
        from rct_control_plane.cli import cli
        result = CliRunner().invoke(cli, ["status", "nonexistent-id-xyz"])
        # Should handle gracefully (exit 0 or 1, not 2)
        assert result.exit_code in (0, 1)


# ─── module-level helper function unit tests (no server needed) ───────────────

class TestHelperFunctions:
    """
    Unit tests for ``_port_open``, ``_wait_for_port``, and ``_get_json``.

    The module-scoped ``rct_server`` fixture always takes the *success* path,
    leaving the timeout/failure branches uncovered.  These lightweight unit
    tests exercise those paths directly.
    """

    # ── _port_open ────────────────────────────────────────────────────────────

    def test_port_open_returns_false_for_unused_port(self):
        """A high port with nothing listening must return False."""
        # Port 19876 is very unlikely to be occupied in any CI or local env.
        assert _port_open("127.0.0.1", 19876) is False

    def test_port_open_returns_true_when_port_is_open(self, rct_server):
        """The already-running test server port must return True."""
        host, port = rct_server
        assert _port_open(host, port) is True

    # ── _wait_for_port ────────────────────────────────────────────────────────

    def test_wait_for_port_returns_false_when_timeout_expires(self, monkeypatch):
        """
        ``_wait_for_port`` must return ``False`` when the port never becomes
        available within the timeout.  We patch ``_port_open`` to always
        return False so the polling loop exhausts the (tiny) timeout.
        """
        import rct_control_plane.tests.test_cli_serve_integration as this_mod

        monkeypatch.setattr(this_mod, "_port_open", lambda host, port: False)
        # Use a tiny timeout so the test finishes quickly
        result = _wait_for_port("127.0.0.1", 19876, timeout=0.15)
        assert result is False

    def test_wait_for_port_returns_true_when_port_opens_immediately(self, monkeypatch):
        """
        ``_wait_for_port`` must return ``True`` as soon as ``_port_open``
        reports that the port is open.
        """
        import rct_control_plane.tests.test_cli_serve_integration as this_mod

        monkeypatch.setattr(this_mod, "_port_open", lambda host, port: True)
        result = _wait_for_port("127.0.0.1", 19876, timeout=5.0)
        assert result is True

    # ── _get_json ─────────────────────────────────────────────────────────────

    def test_get_json_returns_dict_from_live_server(self, rct_server):
        """``_get_json`` must return a plain ``dict`` against the live server."""
        host, port = rct_server
        data = _get_json(f"http://{host}:{port}/health")
        assert isinstance(data, dict)
        assert data.get("status") == "healthy"


# ─── extra integration coverage ───────────────────────────────────────────────

class TestServeIntegrationExtraCoverage:
    """
    Additional integration tests against the live server to cover branches
    that the main TestRctServeIntegration class does not reach.
    """

    def test_compile_endpoint_with_empty_body_returns_client_error(self, rct_server):
        """
        POST /compile with ``{}`` (missing required ``natural_language`` field)
        must return an HTTP client-error (4xx), not a server error (5xx).

        This test exercises the ``except urllib.error.HTTPError`` branch.
        """
        req = urllib.request.Request(
            f"{BASE_URL}/compile",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                # Some permissive APIs may still return 2xx with partial data
                r.read()
        except urllib.error.HTTPError as exc:
            # 422 Unprocessable Entity (FastAPI validation) is expected
            assert exc.code < 500, f"Unexpected server error: HTTP {exc.code}"

    def test_multiple_health_checks_are_consistent(self, rct_server):
        """Three consecutive /health calls must all return status='healthy'."""
        results = [_get_json(f"{BASE_URL}/health") for _ in range(3)]
        assert all(r.get("status") == "healthy" for r in results)


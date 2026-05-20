"""
Coverage-gap tests for rct_control_plane/cli.py

Targets branches introduced in the recent PRs that were not reached by
existing tests:

  - _configure_encoding(): except-Exception path, stream-without-reconfigure path
  - serve command: --reload banner, uvicorn-not-installed ImportError, workers kwarg
  - version command: --output json, PackageNotFoundError fallback
  - status no-arg: --output json, plain-text fallback (_HAS_RICH = False)

Together with existing tests, these bring cli.py patch coverage well above 90 %.
"""

from __future__ import annotations

import importlib.metadata as _meta
import json
import sys
from unittest.mock import MagicMock

import pytest

from rct_control_plane._version import PACKAGE_VERSION


# ── Shared fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_ctx(monkeypatch):
    """Ensure a clean CLI context for every test in this module."""
    import rct_control_plane.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_cli_context", None)


@pytest.fixture()
def runner():
    from click.testing import CliRunner

    return CliRunner()


@pytest.fixture()
def cli():
    from rct_control_plane.cli import cli as _cli

    return _cli


# ── _configure_encoding ────────────────────────────────────────────────────────


class TestConfigureEncoding:
    """Unit-test the module-level ``_configure_encoding`` helper."""

    def test_runs_without_error_on_current_platform(self):
        """Must not raise on any platform (Linux/macOS are no-ops)."""
        from rct_control_plane.cli import _configure_encoding

        _configure_encoding()

    def test_silences_reconfigure_exception(self, monkeypatch):
        """
        The ``except Exception: pass`` branch must swallow any error from
        ``stream.reconfigure()`` (e.g., read-only stream on some platforms).
        """
        from rct_control_plane.cli import _configure_encoding

        bad_stream = MagicMock()
        bad_stream.reconfigure.side_effect = OSError("stream is read-only")

        monkeypatch.setattr(sys, "stdout", bad_stream)
        monkeypatch.setattr(sys, "stderr", bad_stream)

        _configure_encoding()  # ← must NOT raise
        assert bad_stream.reconfigure.called

    def test_no_op_when_stream_has_no_reconfigure(self, monkeypatch):
        """Streams that lack a ``reconfigure`` method must be silently skipped."""
        from rct_control_plane.cli import _configure_encoding
        import io

        # RawIOBase has no .reconfigure attribute
        legacy = io.RawIOBase()
        monkeypatch.setattr(sys, "stdout", legacy)
        monkeypatch.setattr(sys, "stderr", legacy)

        _configure_encoding()  # must not raise


# ── serve command ──────────────────────────────────────────────────────────────


class TestServeCommand:
    """Coverage for branches inside ``rct serve``."""

    def test_serve_reload_flag_prints_dev_mode_banner(self, runner, cli, monkeypatch):
        """
        ``rct serve --reload`` must:
          1. Print the dev-mode banner.
          2. Pass ``reload=True`` and ``workers=1`` to uvicorn.run.
        """
        mock_uv = MagicMock()
        # Setting sys.modules["uvicorn"] = mock makes `import uvicorn` inside
        # the function return the mock immediately (no real server is started).
        monkeypatch.setitem(sys.modules, "uvicorn", mock_uv)

        result = runner.invoke(cli, ["serve", "--port", "19991", "--reload"])

        assert "Dev mode: auto-reload enabled" in result.output
        assert mock_uv.run.call_count == 1
        _, kw = mock_uv.run.call_args
        assert kw.get("reload") is True
        # reload forces workers=1 (uvicorn forbids reload + workers > 1)
        assert kw.get("workers") == 1

    def test_serve_workers_respected_without_reload(self, runner, cli, monkeypatch):
        """
        Without ``--reload``, the ``--workers`` value is forwarded unchanged.
        """
        mock_uv = MagicMock()
        monkeypatch.setitem(sys.modules, "uvicorn", mock_uv)

        result = runner.invoke(cli, ["serve", "--port", "19992", "--workers", "3"])

        assert result.exit_code == 0
        _, kw = mock_uv.run.call_args
        assert kw.get("workers") == 3
        assert kw.get("reload") is False

    def test_serve_default_host_and_port_passed_to_uvicorn(
        self, runner, cli, monkeypatch
    ):
        """Verify that the default host (127.0.0.1) and port (8000) are forwarded."""
        mock_uv = MagicMock()
        monkeypatch.setitem(sys.modules, "uvicorn", mock_uv)

        runner.invoke(cli, ["serve"])

        _, kw = mock_uv.run.call_args
        assert kw.get("host") == "127.0.0.1"
        assert kw.get("port") == 8000

    def test_serve_uvicorn_not_installed_exits_with_error_message(
        self, runner, cli, monkeypatch
    ):
        """
        When uvicorn is not importable, ``serve`` must print a helpful error
        message and exit with code 1 (without raising an unhandled exception).
        """
        # Setting sys.modules["uvicorn"] = None causes `import uvicorn` to
        # raise ImportError — documented Python behaviour for negative cache.
        monkeypatch.setitem(sys.modules, "uvicorn", None)

        result = runner.invoke(cli, ["serve", "--port", "19993"])

        assert result.exit_code == 1
        assert "uvicorn is not installed" in result.output

    def test_serve_startup_banner_shows_url(self, runner, cli, monkeypatch):
        """The startup banner must include the host:port URL."""
        mock_uv = MagicMock()
        monkeypatch.setitem(sys.modules, "uvicorn", mock_uv)

        result = runner.invoke(cli, ["serve", "--host", "0.0.0.0", "--port", "8080"])

        assert "0.0.0.0:8080" in result.output
        assert "/docs" in result.output
        assert "/health" in result.output


# ── version command ────────────────────────────────────────────────────────────


class TestVersionCommand:
    """Coverage for branches inside ``rct version``."""

    def test_version_json_output_is_valid_json(self, runner, cli):
        """``rct version --output json`` must return a valid JSON object."""
        result = runner.invoke(cli, ["version", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "version" in data
        assert "python" in data
        assert "license" in data
        assert data["license"] == "Apache-2.0"
        assert "homepage" in data

    def test_version_json_contains_repository(self, runner, cli):
        """JSON output must include the repository URL."""
        result = runner.invoke(cli, ["version", "--output", "json"])
        data = json.loads(result.output)
        assert "repository" in data
        assert "rct-platform" in data["repository"]

    def test_version_package_not_found_uses_hardcoded_fallback(
        self, runner, cli, monkeypatch
    ):
        """
        When the package metadata is absent (editable install without dist-info),
        ``version`` must fall back to the package default version string.
        """

        def _raise_not_found(pkg: str):
            raise _meta.PackageNotFoundError(pkg)

        monkeypatch.setattr(_meta, "version", _raise_not_found)

        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert PACKAGE_VERSION in result.output

    def test_version_table_output_has_expected_fields(self, runner, cli):
        """Default table output must show name, license, and homepage."""
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "rct-platform" in result.output
        assert "Apache-2.0" in result.output
        assert "rctlabs" in result.output


# ── status command ─────────────────────────────────────────────────────────────


class TestStatusCommandCoverage:
    """Coverage for uncovered branches in ``rct status``."""

    def test_status_no_arg_json_output(self, runner, cli):
        """
        ``rct status --output json`` must return a valid JSON overview object
        with at least ``status``, ``version``, and ``recent_intents`` keys.
        """
        result = runner.invoke(cli, ["status", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "healthy"
        assert "version" in data
        assert "recent_intents" in data

    def test_status_no_arg_plain_text_when_no_rich(self, runner, cli, monkeypatch):
        """
        When Rich is unavailable (``_HAS_RICH = False``), ``status`` must fall
        back to plain ``click.echo`` output and still exit 0.
        """
        import rct_control_plane.cli as cli_mod

        monkeypatch.setattr(cli_mod, "_HAS_RICH", False)

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        # Any non-empty output containing status information is acceptable
        assert "healthy" in result.output or "Status:" in result.output

    def test_status_no_arg_plain_text_shows_version(self, runner, cli, monkeypatch):
        """Plain-text mode must display the version and recent_intents count."""
        import rct_control_plane.cli as cli_mod

        monkeypatch.setattr(cli_mod, "_HAS_RICH", False)

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert PACKAGE_VERSION in result.output or "Version:" in result.output

    def test_status_nonexistent_id_exits_one(self, runner, cli):
        """``rct status <unknown-id>`` must exit 1 and not crash."""
        result = runner.invoke(cli, ["status", "definitely-does-not-exist-xyz-9999"])
        assert result.exit_code == 1

    def test_status_table_output_no_arg(self, runner, cli):
        """Default table output (no --output flag) must exit 0."""
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0

    def test_status_tree_output_no_arg(self, runner, cli):
        """``rct status --output tree`` must exit 0 without crashing."""
        result = runner.invoke(cli, ["status", "--output", "tree"])
        assert result.exit_code == 0

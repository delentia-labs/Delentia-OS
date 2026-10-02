"""Round 55: the command line for starter skills, external MCP servers and web search, and the Desk's channel list."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json

import pytest
from click.testing import CliRunner

from rct_control_plane import external_mcp as xm
from rct_control_plane.cli import cli

SERVER = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv(xm.CONFIG_ENV, str(tmp_path / "mcp.json"))
    monkeypatch.setenv("DELENTIA_SEARCH_CONFIG", str(tmp_path / "search.json"))
    for var in ("DELENTIA_SEARCH_PROVIDER", "DELENTIA_SEARCH_URL", "DELENTIA_SEARCH_CREDENTIAL_ENV", "DELENTIA_SEARCH_REGION", "BRAVE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    xm.clear_cache()


def invoke(*args):
    return CliRunner().invoke(cli, list(args))


def test_starter_check_install_and_list_work_together():
    checked = invoke("skills", "starter", "check")
    assert checked.exit_code == 0 and "all valid" in checked.output
    first = invoke("skills", "starter", "install")
    again = invoke("skills", "starter", "install")
    assert "added 20" in first.output and "added 0" in again.output and "unchanged 20" in again.output
    listing = invoke("skills", "list", "--limit", "5")
    assert listing.exit_code == 0 and "[bundled]" in listing.output


def test_mcp_list_says_how_each_server_is_treated(tmp_path):
    assert "no servers configured" in invoke("mcp", "list").output
    (tmp_path / "mcp.json").write_text(json.dumps({"servers": {"notes": {"command": "python", "args": [SERVER], "read_only_tools": ["read_note"]},
                                                              "docs": {"url": "https://mcp.example.com/mcp"}}}), encoding="utf-8")
    out = invoke("mcp", "list").output
    assert "notes: local process" in out and "read_note" in out and "docs: remote" in out and "every call waits for a signature" in out


def test_mcp_list_reports_a_broken_configuration_and_fails(tmp_path):
    (tmp_path / "mcp.json").write_text(json.dumps({"servers": {"bad": {"command": "python", "token": "abc"}}}), encoding="utf-8")
    result = invoke("mcp", "list")
    assert result.exit_code == 1 and "unknown field" in result.output


def test_mcp_inspect_lists_tools_marks_the_declared_ones_and_prints_the_pin(tmp_path):
    (tmp_path / "mcp.json").write_text(json.dumps({"servers": {"notes": {"command": "python", "args": [SERVER], "read_only_tools": ["read_note"], "timeout_s": 60}}}), encoding="utf-8")
    out = invoke("mcp", "inspect", "notes").output
    assert "read_note  [read-only (declared)]" in out and "write_note  [waits for a signature]" in out
    digest = [line for line in out.splitlines() if line.startswith("digest: ")][0].split(": ")[1]
    assert len(digest) == 64
    assert invoke("mcp", "inspect", "ghost").exit_code == 1


def test_search_status_never_prints_a_key(monkeypatch):
    assert "not configured" in invoke("search-status").output
    monkeypatch.setenv("DELENTIA_SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("BRAVE_API_KEY", "super-secret-value")
    out = invoke("search-status").output
    assert "provider brave" in out and "BRAVE_API_KEY is set" in out and "super-secret-value" not in out


def test_the_desk_lists_the_new_channels_with_counts_only(monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane.api import app
    monkeypatch.setenv("DELENTIA_EMAIL_ALLOWED_SENDERS", "a@example.com,b@example.com")
    channels = {c["channel"]: c for c in TestClient(app).get("/v1/desk/channels").json()["channels"]}
    assert {"whatsapp", "signal", "email"} <= set(channels)
    assert channels["email"]["allowlist"] == "listed" and channels["email"]["allowlist_count"] == 2
    assert "a@example.com" not in json.dumps(channels)                       # sender ids stay on the host
    assert channels["whatsapp"]["allowlist"] == "nobody"


def test_serve_turns_the_starter_skills_on_by_default():
    import inspect
    from rct_control_plane import cli as cli_module
    assert 'setdefault("DELENTIA_STARTER_SKILLS", "1")' in inspect.getsource(cli_module)


def test_the_desk_marks_bundled_skills_so_nobody_mistakes_them_for_learning():
    from fastapi.testclient import TestClient
    from rct_control_plane.api import app
    invoke("skills", "starter", "install")
    skills = TestClient(app).get("/v1/desk/skills", params={"limit": 100}).json()["skills"]
    bundled = [s for s in skills if s["bundled"]]
    assert len(bundled) == 20 and all(s["reliability"] == 0.5 and s["delta"] == 0.0 for s in bundled)

"""
Round 101C: "is there a newer Delentia?" and "update it". Real HTTP (a local server that answers like the package index), real files, real pip for the download step (from a folder of wheels), real CLI processes.

Pinned: the check asks at most once a day and never when switched off; a failure is "unknown", never an error; a file is installed only if its SHA-256 equals the one the index published; the agent can not apply an update.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import hashlib
import json
import subprocess
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import rct_control_plane.desk_api as desk_api
from rct_control_plane import update_check
from rct_control_plane.api import create_app
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.update_check import UpdateError

ROOT = Path(__file__).resolve().parents[2]


def _index_body(version="9.9.9", sha="a" * 64, yanked=False, with_wheel=True):
    files = [{"filename": f"delentia_os-{version}-py3-none-any.whl", "url": f"https://files.example/delentia_os-{version}-py3-none-any.whl", "size": 1234, "yanked": yanked,
              "digests": {"sha256": sha}, "upload_time_iso_8601": "2026-10-26T00:00:00Z"}] if with_wheel else [{"filename": "x.tar.gz", "url": "https://files.example/x.tar.gz", "digests": {"sha256": sha}}]
    return {"info": {"version": version}, "urls": files}


class Index:
    """A local stand-in for the package index that counts the requests it gets."""
    def __init__(self):
        self.body = json.dumps(_index_body()).encode()
        self.status = 200
        self.hits = 0
        self.agents = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):                                   # noqa: N802
                outer.hits += 1
                outer.agents.append(self.headers.get("User-Agent"))
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(outer.body)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/pypi/delentia-os/json"

    def close(self):
        self.server.shutdown()


@pytest.fixture
def index(monkeypatch):
    srv = Index()
    monkeypatch.setenv(update_check.INDEX_ENV, srv.url)
    yield srv
    srv.close()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    for name in (update_check.SWITCH_ENV, update_check.OFFLINE_ENV, "DELENTIA_AGENT_SHELL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(update_check, "current_version", lambda: "2.3.1")


# ------------------------------------------------------------------ versions
@pytest.mark.parametrize("latest,current,newer", [
    ("2.3.2", "2.3.1", True), ("2.4.0", "2.3.9", True), ("3.0.0", "2.99.99", True), ("2.3.1", "2.3.1", False), ("2.3.0", "2.3.1", False),
    ("2.3.1", "2.3.1rc1", True), ("2.3.1rc1", "2.3.1", False), ("2.3.1rc2", "2.3.1rc1", True), ("2.3.1b1", "2.3.1a9", True), ("2.10.0", "2.9.0", True), ("2.3", "2.3.0", False),
    ("garbage", "2.3.1", False), ("2.3.2", "garbage", False), ("2.3.2.dev1", "2.3.1", False), ("", "2.3.1", False),
])
def test_version_comparison(latest, current, newer):
    assert update_check.is_newer(latest, current) is newer


# ------------------------------------------------------------------ the check
def test_the_check_reads_the_index_and_says_a_newer_version_exists(index):
    state = update_check.check()
    assert state["status"] == "available" and state["latest"]["version"] == "9.9.9" and state["latest"]["file"]["sha256"] == "a" * 64
    assert index.agents == ["delentia-os/2.3.1 update-check"]                       # the only thing sent besides the address of the request


def test_it_asks_at_most_once_a_day_unless_forced(index):
    update_check.check(now=1_000_000.0)
    update_check.check(now=1_000_000.0 + 3600)
    assert index.hits == 1
    update_check.check(now=1_000_000.0 + 24 * 3600 + 1)
    assert index.hits == 2
    update_check.check(force=True, now=1_000_000.0 + 24 * 3600 + 2)
    assert index.hits == 3


def test_a_new_installed_version_does_not_trust_an_old_answer(index, monkeypatch):
    update_check.check()
    monkeypatch.setattr(update_check, "current_version", lambda: "9.9.9")
    state = update_check.check()
    assert index.hits == 2 and state["status"] == "current"


def test_a_failure_is_unknown_not_an_error_and_the_last_good_answer_is_kept(index):
    update_check.check(now=1_000_000.0)
    index.status = 500
    index.body = b"<html>oops</html>"
    state = update_check.check(force=True, now=1_000_000.0 + 10)
    assert state["status"] == "available" and "could not be reached" in (state["error"] or "")       # the last good answer is kept, and the failure is said
    fresh_home = update_check.settings_dir() / "update_check.json"
    fresh_home.unlink()
    assert update_check.check(force=True)["status"] == "unknown"


def test_an_unreachable_index_is_unknown_and_quick(monkeypatch):
    monkeypatch.setenv(update_check.INDEX_ENV, "http://127.0.0.1:9/pypi/delentia-os/json")
    state = update_check.check()
    assert state["status"] == "unknown" and state["error"] and update_check.banner_line(state) is None


@pytest.mark.parametrize("body", [b"not json", b"{}", b'{"info": {"version": 5}, "urls": []}', b'{"info": {"version": "garbage"}, "urls": []}', "TOO_BIG"])
def test_a_strange_answer_is_refused(index, body):
    index.body = b"x" * (update_check.MAX_BODY + 10) if body == "TOO_BIG" else body
    assert update_check.check()["status"] == "unknown"


def test_a_release_without_a_wheel_or_with_a_yanked_one_has_no_file_to_install(index):
    index.body = json.dumps(_index_body(with_wheel=False)).encode()
    assert update_check.check(force=True)["latest"]["file"] is None
    index.body = json.dumps(_index_body(yanked=True)).encode()
    assert update_check.check(force=True)["latest"]["file"] is None


def test_it_does_nothing_when_switched_off_by_environment_offline_mode_or_the_saved_choice(index, monkeypatch):
    monkeypatch.setenv(update_check.SWITCH_ENV, "off")
    assert update_check.check()["status"] == "disabled"
    monkeypatch.delenv(update_check.SWITCH_ENV)
    monkeypatch.setenv(update_check.OFFLINE_ENV, "1")
    assert update_check.check()["status"] == "disabled"
    monkeypatch.delenv(update_check.OFFLINE_ENV)
    update_check.set_enabled(False)
    assert update_check.check()["status"] == "disabled" and not update_check.enabled()
    update_check.set_enabled(True)
    assert update_check.enabled()
    assert index.hits == 0                                                           # not one request while it was off


def test_the_index_address_must_be_https_or_loopback(monkeypatch):
    for bad in ("http://pypi.org/pypi/delentia-os/json", "ftp://x/y", "file:///etc/passwd", "http://127.0.0.1.evil.com/x"):
        monkeypatch.setenv(update_check.INDEX_ENV, bad)
        with pytest.raises(UpdateError):
            update_check.index_url()


def test_the_banner_line_only_exists_for_an_available_update(index):
    assert "9.9.9" in update_check.banner_line(update_check.check()) and "delentia update --apply" in update_check.banner_line(update_check.check())
    assert update_check.banner_line({"status": "current"}) is None and update_check.cached_state()["status"] == "available"


def test_the_cached_state_never_touches_the_network(index):
    update_check.check()
    before = index.hits
    assert update_check.cached_state()["status"] == "available" and index.hits == before


# ------------------------------------------------------------------ applying
def _make_wheel(folder: Path, version="9.9.9") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"delentia_os-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"delentia_os-{version}.dist-info/METADATA", f"Metadata-Version: 2.1\nName: delentia-os\nVersion: {version}\n")
        z.writestr(f"delentia_os-{version}.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        z.writestr(f"delentia_os-{version}.dist-info/RECORD", "")
    return path


def _state(wheel: Path, sha=None):
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest() if sha is None else sha
    return {"status": "available", "current": "2.3.1", "latest": {"version": "9.9.9", "file": {"filename": wheel.name, "url": "x", "sha256": digest, "size": 1}}}


def test_the_agent_can_not_apply_an_update(tmp_path):
    wheel = _make_wheel(tmp_path / "w")
    with pytest.raises(UpdateError, match="person at the keyboard"):
        update_check.apply(_state(wheel), from_agent_shell=True)


def test_an_update_is_installed_only_when_the_digest_matches_and_pip_is_asked_for_exactly_that_file(tmp_path):
    folder = tmp_path / "w"
    wheel = _make_wheel(folder)
    commands = []

    def runner(cmd):
        commands.append(cmd)
        if "download" in cmd:                                   # the REAL pip does the download, from the local folder of wheels
            return subprocess.run(cmd, capture_output=True, text=True).returncode
        return 0                                                # the install step is not run: it would change this machine's packages

    done = update_check.apply(_state(wheel), run=runner, find_links=str(folder), from_agent_shell=False)
    assert done["installed"] == "9.9.9" and done["sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert any("download" in c for c in commands) and any("install" in c and str(c[-1]).endswith(".whl") for c in commands)
    assert "--no-deps" in commands[0] and "delentia-os==9.9.9" in commands[0]


def test_a_file_that_does_not_match_the_published_digest_is_never_installed(tmp_path):
    folder = tmp_path / "w"
    wheel = _make_wheel(folder)
    commands = []

    def runner(cmd):
        commands.append(cmd)
        return subprocess.run(cmd, capture_output=True, text=True).returncode if "download" in cmd else 0

    with pytest.raises(UpdateError, match="does not match the SHA-256"):
        update_check.apply(_state(wheel, sha="0" * 64), run=runner, find_links=str(folder), from_agent_shell=False)
    assert not any("install" in c and "download" not in c for c in commands)


@pytest.mark.parametrize("sha", ["", "xyz", "A" * 10])
def test_no_published_digest_means_no_install(tmp_path, sha):
    wheel = _make_wheel(tmp_path / "w")
    with pytest.raises(UpdateError, match="SHA-256"):
        update_check.apply(_state(wheel, sha=sha) | {"status": "available"}, run=lambda c: 0, from_agent_shell=False)


def test_there_is_nothing_to_apply_when_current_or_unknown(tmp_path):
    with pytest.raises(UpdateError, match="no newer version"):
        update_check.apply({"status": "current", "current": "2.3.1", "latest": {"version": "2.3.1"}}, from_agent_shell=False)
    with pytest.raises(UpdateError, match="could not be determined"):
        update_check.apply({"status": "unknown", "current": "2.3.1", "latest": None}, from_agent_shell=False)


def test_a_failed_download_changes_nothing(tmp_path):
    wheel = _make_wheel(tmp_path / "w")
    commands = []

    def runner(cmd):
        commands.append(cmd)
        return 1

    with pytest.raises(UpdateError, match="download failed"):
        update_check.apply(_state(wheel), run=runner, from_agent_shell=False)
    assert len(commands) == 1


# ------------------------------------------------------------------ the Desk and the command line
class _Kernel:
    def __init__(self, persistence):
        self._persistence = persistence


def test_the_desk_routes_report_switch_and_audit(index, tmp_path, monkeypatch):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "u.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: _Kernel(persistence))
    with TestClient(create_app()) as client:
        assert client.get("/v1/desk/update").json()["status"] == "available"
        assert client.post("/v1/desk/update/switch", json={"enabled": False}).json()["status"] == "disabled"
        hits = index.hits
        assert client.post("/v1/desk/update/check").json()["status"] == "disabled" and index.hits == hits
        assert client.post("/v1/desk/update/switch", json={"enabled": True}).json()["status"] == "available"
    with persistence._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'update_check'").fetchone()[0] == 2


def test_a_person_token_can_not_reach_the_update_routes():
    from rct_control_plane import api_auth
    for method, path in (("GET", "/v1/desk/update"), ("POST", "/v1/desk/update/check"), ("POST", "/v1/desk/update/switch")):
        assert not api_auth.person_route_allowed(method, path)


def _cli(args, env_extra, tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "DELENTIA_HOME": str(tmp_path / "home"), **env_extra}
    env.pop("DELENTIA_AGENT_SHELL", None)
    env.update({k: v for k, v in env_extra.items()})
    return subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *args], env=env, capture_output=True, text=True, timeout=180, cwd=str(tmp_path))


def test_the_command_reports_an_update_and_refuses_to_apply_for_the_agent(index, tmp_path):
    shown = _cli(["update"], {update_check.INDEX_ENV: index.url}, tmp_path)
    assert shown.returncode == 0 and "newer version is available" in shown.stdout and "delentia update --apply" in shown.stdout
    refused = _cli(["update", "--apply", "--yes"], {update_check.INDEX_ENV: index.url, "DELENTIA_AGENT_SHELL": "1"}, tmp_path)
    assert refused.returncode == 1 and "person at the keyboard" in refused.stderr


def test_the_command_can_turn_the_check_off_and_on(index, tmp_path):
    off = _cli(["update", "--turn-off"], {update_check.INDEX_ENV: index.url}, tmp_path)
    assert "now off" in off.stdout
    again = _cli(["update"], {update_check.INDEX_ENV: index.url}, tmp_path)
    assert "is off" in again.stdout and index.hits == 0
    on = _cli(["update", "--turn-on"], {update_check.INDEX_ENV: index.url}, tmp_path)
    assert "now on" in on.stdout

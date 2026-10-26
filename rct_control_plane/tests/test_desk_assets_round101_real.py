"""
Round 101 (UX audit): the Desk ships with the package and `delentia desk` opens it. Real processes: the command runs as its own process against a tiny real HTTP server standing in for `delentia serve`.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from rct_control_plane import desk_assets

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):                                           # noqa: N802
        body = json.dumps({"status": "healthy"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def api():
    server = HTTPServer(("127.0.0.1", 0), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _fake_desk(tmp_path):
    root = tmp_path / "desk"
    root.mkdir()
    (root / "index.html").write_text("<html><title>Delentia Desk</title></html>", encoding="utf-8")
    (root / "chat.html").write_text("<html>chat</html>", encoding="utf-8")
    return root


def _run_desk(tmp_path, gateway, port, extra_env=None):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "DELENTIA_HOME": str(tmp_path / "home"), "DELENTIA_DESK_DIR": str(_fake_desk(tmp_path)),
           "DELENTIA_API_TOKEN": "owner-token-for-the-test", **(extra_env or {})}
    return subprocess.Popen([sys.executable, "-m", "rct_control_plane.cli", "desk", "--no-browser", "--port", str(port), "--gateway", gateway, "--wait-seconds", "0"],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(tmp_path))


def test_a_folder_the_owner_names_is_found_first_then_the_source_build_then_the_packaged_pages(tmp_path, monkeypatch):
    named = _fake_desk(tmp_path)
    monkeypatch.setenv(desk_assets.ENV, str(named))
    assert desk_assets.find_desk_root() == named
    monkeypatch.delenv(desk_assets.ENV)
    built, packaged = tmp_path / "built", tmp_path / "packaged"
    for folder in (built, packaged):
        folder.mkdir()
        (folder / "index.html").write_text("x", encoding="utf-8")
    monkeypatch.setattr(desk_assets, "REPO_BUILD", built)
    monkeypatch.setattr(desk_assets, "PACKAGED", packaged)
    assert desk_assets.find_desk_root() == built
    (built / "index.html").unlink()
    assert desk_assets.find_desk_root() == packaged
    (packaged / "index.html").unlink()
    assert desk_assets.find_desk_root() is None and "npm" in desk_assets.missing_message()


def test_the_command_serves_the_pages_and_hands_over_the_address_and_token_without_putting_them_in_the_url(tmp_path, api):
    port = _free_port()
    proc = _run_desk(tmp_path, api, port)
    try:
        deadline = time.monotonic() + 60
        local = None
        while time.monotonic() < deadline and local is None:
            try:
                with urllib.request.urlopen(f"http://localhost:{port}/__delentia_local.json", timeout=2) as r:
                    local = json.loads(r.read())
            except Exception:                                   # noqa: BLE001 - still starting
                time.sleep(0.5)
        assert local is not None, proc.poll()
        assert local["gateway"] == api and local["token"] == "owner-token-for-the-test"
        page = urllib.request.urlopen(f"http://localhost:{port}/chat", timeout=3).read().decode()
        assert "chat" in page
    finally:
        proc.terminate()
        out, err = proc.communicate(timeout=20)
    assert f"http://localhost:{port}" in out and "owner-token-for-the-test" not in out + err


def test_with_no_agent_running_it_says_how_to_start_one(tmp_path):
    proc = _run_desk(tmp_path, f"http://127.0.0.1:{_free_port()}", _free_port())
    out, err = proc.communicate(timeout=120)
    assert proc.returncode == 3 and "delentia serve" in err


def test_with_no_built_desk_it_says_what_is_missing_and_never_hangs(tmp_path, api, monkeypatch):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "DELENTIA_HOME": str(tmp_path / "home"), "DELENTIA_DESK_DIR": str(tmp_path / "nowhere")}
    code = ("import sys; from pathlib import Path; from rct_control_plane import desk_assets; desk_assets.REPO_BUILD = Path(sys.argv[1]); desk_assets.PACKAGED = Path(sys.argv[1]);"
            "from rct_control_plane.cli import cli; cli(['desk', '--no-browser', '--gateway', sys.argv[2]])")
    done = subprocess.run([sys.executable, "-c", code, str(tmp_path / "nowhere"), api], env=env, capture_output=True, text=True, timeout=120, cwd=str(tmp_path))
    assert done.returncode == 4 and "no built Desk" in done.stderr


def test_the_package_is_set_up_to_carry_the_pages_and_the_builds_put_them_there():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    section = pyproject.split("[tool.setuptools.package-data]", 1)[1].splitlines()[1]
    assert 'rct_control_plane = ["desk_ui/**/*"]' in section
    assert "rct_control_plane/desk_ui/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    for workflow in ("release.yml", "package-check.yml"):
        assert "scripts/package_desk.py" in (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8"), workflow
    assert (ROOT / "scripts" / "package_desk.py").is_file()


# ---------------------------------------------------------------- Round 101E: the Desk build downloads fonts, a network blip must not fail a release
def _package_desk():
    import importlib.util
    spec = importlib.util.spec_from_file_location("package_desk", ROOT / "scripts" / "package_desk.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_failed_desk_build_is_tried_again_and_a_later_success_counts():
    import subprocess
    module = _package_desk()
    calls, waited = [], []

    def flaky(cmd, cwd, env=None):
        calls.append(1)
        if len(calls) < 3:
            raise subprocess.CalledProcessError(1, cmd)

    module.run_retrying(["npm", "run", "build"], ROOT, None, attempts=3, delay=7, runner=flaky, sleep=waited.append)
    assert len(calls) == 3 and waited == [7, 7]


def test_a_build_that_keeps_failing_is_reported_after_the_last_attempt_not_hidden():
    import subprocess
    module = _package_desk()
    calls = []

    def always(cmd, cwd, env=None):
        calls.append(1)
        raise subprocess.CalledProcessError(1, cmd)

    with pytest.raises(subprocess.CalledProcessError):
        module.run_retrying(["npm"], ROOT, None, attempts=3, delay=0, runner=always, sleep=lambda s: None)
    assert len(calls) == 3

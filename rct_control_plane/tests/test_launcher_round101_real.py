"""
Round 101C: `delentia launch` - one double click that starts the agent and the Desk page in the background and opens the browser. Real processes, real ports, a real `delentia serve`.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from rct_control_plane import desk_assets, launcher

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


def test_a_background_process_is_started_remembered_and_stopped_and_only_that_one(tmp_path):
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        pid = launcher.start_detached([sys.executable, "-c", "import time; time.sleep(120)"], tmp_path / "logs" / "x.log", tmp_path / "run" / "x.pid")
        assert launcher.pid_alive(pid) and (tmp_path / "run" / "x.pid").read_text() == str(pid)
        assert launcher.stop_pid_file(tmp_path / "run" / "x.pid") == "stopped"
        assert not launcher.pid_alive(pid) and not (tmp_path / "run" / "x.pid").exists()
        assert other.poll() is None                                                        # a neighbour that was not started by us is untouched
        assert launcher.stop_pid_file(tmp_path / "run" / "x.pid") == "no record"
    finally:
        other.kill()


def test_a_record_of_a_process_that_already_ended_is_cleaned_up_and_nothing_is_killed(tmp_path):
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    (tmp_path / "x.pid").write_text(str(done.pid))
    assert launcher.stop_pid_file(tmp_path / "x.pid") == "not running" and not (tmp_path / "x.pid").exists()
    (tmp_path / "bad.pid").write_text("not a number")
    assert launcher.stop_pid_file(tmp_path / "bad.pid") == "no record"


def test_the_process_output_goes_to_a_log_file_not_to_a_window(tmp_path):
    pid = launcher.start_detached([sys.executable, "-c", "print('hello from the background')"], tmp_path / "logs" / "o.log", tmp_path / "run" / "o.pid")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and launcher.pid_alive(pid):
        time.sleep(0.1)
    assert "hello from the background" in (tmp_path / "logs" / "o.log").read_text(encoding="utf-8", errors="replace")


def test_health_is_true_only_for_a_server_that_answers_200():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):                                           # noqa: N802
            self.send_response(200 if self.path == "/ok" else 500)
            self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert launcher.healthy(base + "/ok") and not launcher.healthy(base + "/bad")
    finally:
        server.shutdown()
    assert not launcher.healthy(f"http://127.0.0.1:{_free_port()}/ok")


def test_a_missing_desk_is_said_before_anything_is_started(tmp_path, monkeypatch):
    monkeypatch.setattr(desk_assets, "REPO_BUILD", tmp_path / "nowhere")
    monkeypatch.setattr(desk_assets, "PACKAGED", tmp_path / "nowhere2")
    monkeypatch.delenv(desk_assets.ENV, raising=False)
    started = []
    monkeypatch.setattr(launcher, "start_detached", lambda *a, **k: started.append(a) or 0)
    with pytest.raises(RuntimeError, match="no built Desk"):
        launcher.launch(_free_port(), _free_port(), say=lambda *_: None)
    assert started == []


def test_launch_starts_the_agent_and_the_desk_finds_them_again_and_stops_exactly_them(tmp_path):
    desk = tmp_path / "desk"
    desk.mkdir()
    (desk / "index.html").write_text("<html><title>Delentia Desk</title></html>", encoding="utf-8")
    api, page = _free_port(), _free_port()
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "DELENTIA_HOME": str(tmp_path / "home"), "DELENTIA_DESK_DIR": str(desk), "DELENTIA_UPDATE_CHECK": "off"}
    env.pop("DELENTIA_API_TOKEN", None)

    def run(*args):
        return subprocess.run([sys.executable, "-m", "rct_control_plane.cli", "launch", "--no-browser", "--api-port", str(api), "--desk-port", str(page), *args],
                              env=env, capture_output=True, text=True, timeout=240, cwd=str(tmp_path))

    try:
        first = run()
        assert first.returncode == 0, first.stderr + first.stdout
        assert f"http://localhost:{page}" in first.stdout
        assert launcher.healthy(f"http://127.0.0.1:{api}/health") and launcher.healthy(f"http://127.0.0.1:{page}/")
        pids = {n: (tmp_path / "home" / "run" / f"{n}.pid").read_text() for n in ("serve", "desk")}
        second = run()
        assert second.returncode == 0 and "Starting" not in second.stdout                   # found what was already running, started nothing new
        assert {n: (tmp_path / "home" / "run" / f"{n}.pid").read_text() for n in ("serve", "desk")} == pids
        stopped = run("--stop")
        assert '"desk": "stopped"' in stopped.stdout and '"agent": "stopped"' in stopped.stdout
        time.sleep(1)
        assert not launcher.healthy(f"http://127.0.0.1:{api}/health") and not launcher.healthy(f"http://127.0.0.1:{page}/")
    finally:
        run("--stop")


def test_the_message_box_helper_never_raises_and_is_a_no_op_off_windows():
    assert launcher.message_box("t", "x") in (True, False) if os.name != "nt" else True
    assert launcher.has_console() is True

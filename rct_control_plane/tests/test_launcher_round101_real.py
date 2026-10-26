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


# ---------------------------------------------------------------- Round 101D gap T5: two clicks at once

_LOCK_WORKER = """
import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from rct_control_plane import launcher
counter = Path(sys.argv[3])
with launcher.launch_lock(Path(sys.argv[2]), 120):
    value = int(counter.read_text() or "0")                 # read, wait, write: without a lock the processes overwrite each other
    time.sleep(0.15)
    counter.write_text(str(value + 1))
"""


def test_six_processes_that_take_the_launch_lock_at_once_never_overlap(tmp_path):
    counter = tmp_path / "count.txt"
    counter.write_text("0")
    workers = [subprocess.Popen([sys.executable, "-c", _LOCK_WORKER, str(ROOT), str(tmp_path / "run"), str(counter)]) for _ in range(6)]
    assert [w.wait(timeout=120) for w in workers] == [0] * 6
    assert counter.read_text() == "6"                           # every increment survived: nobody was inside at the same time
    assert not (tmp_path / "run" / "launch.lock").exists()


def test_a_lock_left_by_a_process_that_died_is_taken_over_at_once(tmp_path):
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "launch.lock").write_text(f"{gone.pid} {time.time()}", encoding="ascii")
    started = time.monotonic()
    with launcher.launch_lock(tmp_path / "run", 5):
        assert (tmp_path / "run" / "launch.lock").exists()
    assert time.monotonic() - started < 3 and not (tmp_path / "run" / "launch.lock").exists()


def test_an_old_lock_and_an_unreadable_lock_do_not_block_forever(tmp_path):
    (tmp_path / "run").mkdir()
    lock = tmp_path / "run" / "launch.lock"
    lock.write_text(f"{os.getpid()} {time.time() - 5000}", encoding="ascii")        # held by a live process, but far older than any start
    with launcher.launch_lock(tmp_path / "run", 5, stale_after=600):
        pass
    lock.write_text("garbage")
    os.utime(lock, (time.time() - 5000, time.time() - 5000))
    with launcher.launch_lock(tmp_path / "run", 5, stale_after=600):
        pass


def test_a_live_lock_is_waited_for_and_then_said_in_words(tmp_path):
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "launch.lock").write_text(f"{os.getpid()} {time.time()}", encoding="ascii")        # this very process is alive and the lock is fresh
    with pytest.raises(RuntimeError, match="another start of Delentia is still in progress"):
        with launcher.launch_lock(tmp_path / "run", 0.6):
            pytest.fail("must not get in")
    assert (tmp_path / "run" / "launch.lock").exists()          # a refused waiter does not remove the holder's lock


def test_two_threads_that_launch_at_once_start_the_agent_once(tmp_path, monkeypatch):
    desk = tmp_path / "desk"
    desk.mkdir()
    (desk / "index.html").write_text("x", encoding="utf-8")
    monkeypatch.setenv(desk_assets.ENV, str(desk))
    up: set = set()
    started: list = []

    def fake_start(argv, log, pid):
        time.sleep(0.4)                                         # a start takes a while; the other click arrives meanwhile
        started.append("serve" if "serve" in argv else "desk")
        up.add("serve" if "serve" in argv else "desk")
        return 1

    monkeypatch.setattr(launcher, "healthy", lambda url, timeout=2.0: ("8000" in url and "serve" in up) or ("3010" in url and "desk" in up))
    monkeypatch.setattr(launcher, "start_detached", fake_start)
    results: list = []
    threads = [threading.Thread(target=lambda: results.append(launcher.launch(8000, 3010, wait_seconds=5, say=lambda *_: None))) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(started) == ["desk", "serve"]                 # one agent and one page, not two of each
    assert sorted(len(r["started"]) for r in results) == [0, 2]
    assert sorted(len(r["already"]) for r in results) == [0, 2]


def test_two_real_launch_commands_at_once_start_one_agent(tmp_path):
    desk = tmp_path / "desk"
    desk.mkdir()
    (desk / "index.html").write_text("<html><title>Delentia Desk</title></html>", encoding="utf-8")
    api, page = _free_port(), _free_port()
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "DELENTIA_HOME": str(tmp_path / "home"), "DELENTIA_DESK_DIR": str(desk), "DELENTIA_UPDATE_CHECK": "off"}
    env.pop("DELENTIA_API_TOKEN", None)
    outputs: list = []

    def run(*args):
        outputs.append(subprocess.run([sys.executable, "-m", "rct_control_plane.cli", "launch", "--no-browser", "--api-port", str(api), "--desk-port", str(page), *args],
                                      env=env, capture_output=True, text=True, timeout=300, cwd=str(tmp_path)))

    try:
        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=320)
        assert [o.returncode for o in outputs] == [0, 0], [o.stderr + o.stdout for o in outputs]
        assert sum("Starting the agent" in o.stdout for o in outputs) == 1          # exactly one of the two clicks started it
        assert launcher.healthy(f"http://127.0.0.1:{api}/health") and launcher.healthy(f"http://127.0.0.1:{page}/")
        assert not (tmp_path / "home" / "run" / "launch.lock").exists()
    finally:
        subprocess.run([sys.executable, "-m", "rct_control_plane.cli", "launch", "--stop"], env=env, capture_output=True, text=True, timeout=120, cwd=str(tmp_path))

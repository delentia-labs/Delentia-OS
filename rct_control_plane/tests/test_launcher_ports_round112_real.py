"""
Round 112B (criteria: research/FIRSTRUN_CRITERIA_R112B.md R9 and R10): the launcher no longer adopts a foreign server on its port, chooses a free one, remembers it, and opens an application window.

Real sockets and real HTTP servers on loopback; nothing here starts the agent.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from rct_control_plane import launcher


def serve(body: dict, status: int = 200, server_header: str = None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                                       # noqa: N802
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

        if server_header:
            server_version = server_header

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


@pytest.fixture
def stop():
    servers = []
    yield servers.append
    for s in servers:
        s.shutdown()
        s.server_close()


# ------------------------------------------------------------------ R9: what is ours
def test_another_program_answering_health_with_200_is_not_our_agent(stop):
    foreign = serve({"ok": True})
    stop(foreign)
    assert not launcher.is_our_agent(foreign.server_address[1])


def test_a_delentia_agent_is_recognised(stop):
    ours = serve({"status": "healthy", "version": "2.4.4", "timestamp": "2026-11-08T00:00:00", "milestone": None})
    stop(ours)
    assert launcher.is_our_agent(ours.server_address[1])


def test_an_older_agent_without_a_milestone_is_still_ours(stop):
    old = serve({"status": "healthy", "version": "2.3.1", "timestamp": "2026-10-16T00:00:00"})
    stop(old)
    assert launcher.is_our_agent(old.server_address[1])


def test_an_unhealthy_status_or_a_non_version_is_not_ours(stop):
    a = serve({"status": "degraded", "version": "2.4.4", "timestamp": "t"})
    b = serve({"status": "healthy", "version": "latest", "timestamp": "t"})
    stop(a), stop(b)
    assert not launcher.is_our_agent(a.server_address[1]) and not launcher.is_our_agent(b.server_address[1])


def test_the_desk_is_recognised_by_its_server_header(stop):
    desk = serve({}, server_header="DelentiaDeskLauncher")
    other = serve({})
    stop(desk), stop(other)
    assert launcher.is_our_desk(desk.server_address[1])
    assert not launcher.is_our_desk(other.server_address[1])


# ------------------------------------------------------------------ R9: choosing a port
def test_a_foreign_server_on_the_preferred_port_is_skipped_and_the_next_free_one_is_used(stop):
    foreign = serve({"ok": True})
    stop(foreign)
    port = foreign.server_address[1]
    chosen, reuse = launcher.choose_port(port, launcher.is_our_agent)
    assert chosen != port and not reuse and launcher.port_free(chosen)


def test_our_own_agent_on_the_preferred_port_is_reused(stop):
    ours = serve({"status": "healthy", "version": "2.4.4", "timestamp": "t"})
    stop(ours)
    port = ours.server_address[1]
    assert launcher.choose_port(port, launcher.is_our_agent) == (port, True)


def test_a_port_that_holds_a_connection_but_never_answers_is_skipped_quickly():
    silent = socket.socket()
    silent.bind(("127.0.0.1", 0))
    silent.listen(1)                                            # accepts connections into the backlog, never replies
    try:
        port = silent.getsockname()[1]
        started = time.monotonic()
        chosen, reuse = launcher.choose_port(port, lambda p: launcher.is_our_agent(p, timeout=0.3))
        assert chosen != port and not reuse and time.monotonic() - started < 5
    finally:
        silent.close()


def test_the_recorded_port_comes_first_if_it_is_ours(stop):
    ours = serve({"status": "healthy", "version": "2.4.4", "timestamp": "t"})
    stop(ours)
    port = ours.server_address[1]
    assert launcher.choose_port(8000, launcher.is_our_agent, recorded=port) == (port, True)


def test_with_no_free_port_it_says_so_in_words():
    with pytest.raises(RuntimeError, match="no free port"):
        launcher.choose_port(9000, lambda p: False, free=lambda p: False, tries=3)


def test_ports_are_remembered_in_the_data_folder(tmp_path):
    launcher.write_ports(tmp_path, 8003, 3012)
    assert launcher.read_ports(tmp_path) == {"agent": 8003, "desk": 3012}
    (tmp_path / "ports.json").write_text("not json", encoding="utf-8")
    assert launcher.read_ports(tmp_path) == {}


def test_port_free_only_looks_at_the_loopback_address():
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    try:
        assert not launcher.port_free(held.getsockname()[1])
    finally:
        held.close()
    src = Path(launcher.__file__).read_text(encoding="utf-8")
    assert "0.0.0.0" not in src.split("def port_free")[1].split("def choose_port")[0]


def test_a_launch_with_a_foreign_server_on_the_agent_port_starts_its_own_agent_elsewhere(tmp_path, stop, monkeypatch):
    foreign = serve({"ok": True})
    stop(foreign)
    started = []
    monkeypatch.setattr(launcher, "start_detached", lambda argv, log, pid, env=None: started.append(argv) or 1)
    monkeypatch.setattr(launcher, "wait_healthy", lambda url, seconds: True)
    said = []
    result = launcher._launch_locked(tmp_path, foreign.server_address[1], 3010, 5, said.append)
    agent_argv = next(a for a in started if "serve" in a)
    port_given = int(agent_argv[agent_argv.index("--port") + 1])
    assert port_given != foreign.server_address[1] and result["api_port"] == port_given
    assert "agent" in result["started"]
    assert any("used by another program" in line for line in said)
    desk_argv = next(a for a in started if "desk" in a)
    assert f"http://127.0.0.1:{port_given}" in desk_argv, "the Desk is pointed at OUR agent, not the foreign server"
    assert launcher.read_ports(tmp_path / "run")["agent"] == port_given


# ------------------------------------------------------------------ R10: an own window
WIN = {"ProgramFiles": r"C:\Program Files", "ProgramFiles(x86)": r"C:\Program Files (x86)", "LOCALAPPDATA": r"C:\Users\x\AppData\Local"}


def test_chrome_in_application_mode_when_it_is_installed():
    chrome = os.path.join(WIN["ProgramFiles"], "Google", "Chrome", "Application", "chrome.exe")
    command = launcher.window_command("http://localhost:3010", "win32", WIN, exists=lambda p: p == chrome)
    assert command == [chrome, "--app=http://localhost:3010"]


def test_edge_when_only_edge_is_installed():
    edge = os.path.join(WIN["ProgramFiles(x86)"], "Microsoft", "Edge", "Application", "msedge.exe")
    command = launcher.window_command("http://localhost:3010", "win32", WIN, exists=lambda p: p == edge)
    assert command == [edge, "--app=http://localhost:3010"]


def test_no_browser_found_means_an_ordinary_tab():
    assert launcher.window_command("http://localhost:3010", "win32", WIN, exists=lambda p: False) is None


def test_the_person_can_turn_the_window_off():
    assert launcher.window_command("http://localhost:3010", "win32", {**WIN, "DELENTIA_DESK_WINDOW": "tab"}, exists=lambda p: True) is None


def test_other_systems_open_a_tab():
    assert launcher.window_command("http://localhost:3010", "linux", WIN, exists=lambda p: True) is None
    assert launcher.window_command("http://localhost:3010", "darwin", WIN, exists=lambda p: True) is None


def test_the_window_uses_the_normal_profile():
    chrome = os.path.join(WIN["ProgramFiles"], "Google", "Chrome", "Application", "chrome.exe")
    command = launcher.window_command("http://localhost:3010", "win32", WIN, exists=lambda p: p == chrome)
    assert not any(part.startswith("--user-data-dir") for part in command), "a separate profile would lose the person's passkeys and sign-in"


def test_a_recorded_agent_that_is_alive_but_slow_to_answer_is_not_replaced_by_a_second_one(tmp_path, monkeypatch):
    """Found by the older launch test once the server warmed itself in the background: /health can take seconds while it warms. A recorded port whose recorded process is alive is ours."""
    import subprocess
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        run = tmp_path / "run"
        run.mkdir()
        (run / "serve.pid").write_text(str(sleeper.pid), encoding="ascii")
        (run / "desk.pid").write_text(str(sleeper.pid), encoding="ascii")
        launcher.write_ports(run, 8003, 3012)
        started = []
        monkeypatch.setattr(launcher, "is_our_agent", lambda port, timeout=4.0: False)         # it did not answer in time
        monkeypatch.setattr(launcher, "is_our_desk", lambda port, timeout=2.0: False)
        monkeypatch.setattr(launcher, "port_free", lambda port: False)                            # and the port is held (by it)
        monkeypatch.setattr(launcher, "start_detached", lambda argv, log, pid, env=None: started.append(argv) or 1)
        monkeypatch.setattr(launcher, "wait_healthy", lambda url, seconds: True)
        result = launcher._launch_locked(tmp_path, 8000, 3010, 5, lambda *_: None)
        assert started == [], "no second agent or Desk was started"
        assert result["api_port"] == 8003 and result["desk_port"] == 3012 and sorted(result["already"]) == ["agent", "desk"]
    finally:
        sleeper.kill()

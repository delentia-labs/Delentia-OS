"""
Round 84: this machine as the first test host (scripts/local_host.py): a dedicated folder, a random token, a supervisor that restarts the server when it dies and writes down why, a stop that really stops.

The server is a tiny stand-in that checks the same bearer token (the real `delentia serve` is exercised by autonomy_drill.py and the host-check tests); the supervisor, the pid files and the real process
kill are real.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import json
import socket
import time

import pytest
psutil = pytest.importorskip("psutil", reason="the host supervisor test kills processes by id and needs psutil")

import local_host as lh

STAND_IN = ("import http.server, json, sys, os\n"
            "port = int(sys.argv[1])\n"
            "class H(http.server.BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        ok = self.headers.get('Authorization') == 'Bearer ' + os.environ.get('DELENTIA_API_TOKEN', 'x')\n"
            "        body = json.dumps({'status': 'healthy' if ok else 'denied', 'home': os.environ.get('DELENTIA_HOME'), 'leaked': os.environ.get('DELENTIA_SHOULD_NOT_BE_HERE')}).encode()\n"
            "        self.send_response(200 if ok else 401); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)\n"
            "    def log_message(self, *a): pass\n"
            "http.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()\n")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def host(tmp_path, monkeypatch):
    port = free_port()
    monkeypatch.setenv("DELENTIA_HOST_SERVER_CMD", json.dumps([sys.executable, "-c", STAND_IN, str(port)]))
    monkeypatch.setenv("DELENTIA_SHOULD_NOT_BE_HERE", "from the parent shell")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-not-reach-an-ollama-host")
    d = tmp_path / "host"
    lh.init(d, "ollama", "qwen3:8b", None, None, None, port, 0.0, 0.0, 0)
    yield d, port
    try:
        lh.stop(d, wait=20)
    except Exception:
        pass
    for name in ("server_pid", "supervisor_pid"):
        pid_file = lh.paths(d)[name]
        if pid_file.exists():
            try:
                psutil.Process(int(pid_file.read_text(encoding="utf-8"))).kill()
            except Exception:
                pass


def wait_for(predicate, seconds=60.0, step=0.3):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    return None


def test_init_makes_a_folder_a_token_and_a_config_without_any_key_material(tmp_path):
    d = tmp_path / "h"
    cfg = lh.init(d, "ollama", "qwen3:8b", None, None, None, 8123, 0.0, 5.0, 100000)
    p = lh.paths(d)
    assert p["home"].is_dir() and p["logs"].is_dir() and len(p["token"].read_text(encoding="utf-8")) >= 30
    first = p["token"].read_text(encoding="utf-8")
    lh.init(d, "ollama", "qwen3:8b", None, None, None, 8123, 0.0, 5.0, 100000)
    assert p["token"].read_text(encoding="utf-8") == first, "re-initialising must not change the token under a running host"
    text = p["config"].read_text(encoding="utf-8")
    assert first not in text and "PRIVATE KEY" not in text and cfg["daily_usd"] == 5.0


def test_init_refuses_a_witness_without_a_key_a_missing_key_and_a_key_inside_the_repository(tmp_path):
    with pytest.raises(SystemExit):
        lh.init(tmp_path / "a", "ollama", "m", None, "https://w.example/v1/audit/anchor", "host-1", 8000, 0, 0, 0)
    with pytest.raises(SystemExit):
        lh.init(tmp_path / "b", "ollama", "m", str(tmp_path / "missing.pem"), None, None, 8000, 0, 0, 0)
    inside = lh.ROOT / "scratch_key_for_test.pem"
    inside.write_text("x", encoding="utf-8")
    try:
        with pytest.raises(SystemExit):
            lh.init(tmp_path / "c", "ollama", "m", str(inside), None, None, 8000, 0, 0, 0)
    finally:
        inside.unlink()


def test_the_server_gets_its_own_settings_and_nothing_from_the_parent_shell(host):
    d, _ = host
    cfg = lh.load_config(d)
    env = lh.server_env(cfg)
    assert env["DELENTIA_HOME"] == str(lh.paths(d)["home"]) and env["DELENTIA_LLM_PROVIDER"] == "ollama" and env["DELENTIA_API_TOKEN"] == lh.paths(d)["token"].read_text(encoding="utf-8").strip()
    assert "DELENTIA_SHOULD_NOT_BE_HERE" not in env and "OPENROUTER_API_KEY" not in env, "an ollama host must not be handed a provider key"
    shown = lh.env_lines(d)
    assert env["DELENTIA_API_TOKEN"] not in shown and "api_token.txt" in shown


def test_witness_and_limits_reach_the_server_environment(tmp_path):
    key = tmp_path / "keys" / "host-1.pem"
    key.parent.mkdir()
    key.write_text("pem", encoding="utf-8")
    d = tmp_path / "h"
    cfg = lh.init(d, "ollama", "qwen3:8b", str(key), "https://w.example/v1/audit/anchor", "host-1", 8000, 0.0, 2.5, 50000)
    env = lh.server_env(cfg)
    assert env["DELENTIA_AUDIT_SIGNING_KEY"] == str(key) and env["DELENTIA_AUDIT_ANCHOR_URL"].endswith("/v1/audit/anchor") and env["DELENTIA_AUDIT_ANCHOR_KEY_ID"] == "host-1"
    assert env["DELENTIA_DAILY_BUDGET_USD"] == "2.5" and env["DELENTIA_DAILY_MAX_TOKENS"] == "50000"


def test_start_serves_with_the_token_only_restarts_after_a_real_kill_and_records_why(host):
    d, port = host
    started = lh.start(d)
    assert started["started"] is True
    s1 = wait_for(lambda: (lambda s: s if s.get("healthy") else None)(lh.status(d)), 90)
    assert s1 and s1["health"]["home"] == str(lh.paths(d)["home"]) and s1["health"]["leaked"] is None
    import urllib.error
    import urllib.request
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)               # no token: refused
    assert refused.value.code == 401
    first_pid = s1["server_pid"]
    psutil.Process(first_pid).kill()                                                       # the server dies the hard way
    s2 = wait_for(lambda: (lambda s: s if s.get("healthy") and s["server_pid"] != first_pid else None)(lh.status(d)), 90)
    assert s2, "the supervisor must start the server again"
    assert s2["unplanned_restarts"] == 1 and s2["last_exit"]["stopped_by_owner"] is False and s2["last_exit"]["exit_code"] != 0
    assert lh.start(d)["started"] is False, "a second start while one is running must not start a second supervisor"


def test_stop_stops_the_supervisor_and_the_server_and_says_it_was_the_owner(host):
    d, _ = host
    lh.start(d)
    assert wait_for(lambda: lh.status(d).get("healthy"), 90)
    server = lh.status(d)["server_pid"]
    assert lh.stop(d, wait=60)["stopped"] is True
    assert wait_for(lambda: not psutil.pid_exists(server), 30), "the server process must be gone"
    last = lh.status(d)["last_exit"]
    assert last["stopped_by_owner"] is True
    assert lh.status(d)["supervisor_alive"] is False and lh.status(d)["healthy"] is False

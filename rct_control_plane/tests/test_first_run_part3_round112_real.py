"""
Round 112C (criteria: research/FIRSTRUN_CRITERIA_R112C.md R13-R17): the slowness of a computer with no model program, the breaker, the Desk command and the installer text.

Real sockets, real httpx, the real governed loop and the real OllamaProvider aimed at a closed port; nothing here needs Ollama.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest

from rct_control_plane import launcher, llm_provider, local_net, provider_breaker
from rct_control_plane.llm_provider import is_local_refusal
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ R17: a short connect timeout for this computer only
def test_a_loopback_address_gets_a_short_connect_timeout_and_any_other_address_keeps_its_own():
    local = local_net.timeout_for("http://127.0.0.1:11434", 90.0)
    assert isinstance(local, httpx.Timeout) and local.connect <= 0.75 and local.read == 90.0
    assert local_net.timeout_for("https://openrouter.ai/api/v1", 90.0) == 90.0
    assert local_net.timeout_for("http://192.168.1.20:11434", 90.0) == 90.0


def test_the_connect_timeout_can_be_set_and_a_bad_value_is_ignored(monkeypatch):
    monkeypatch.setenv(local_net.LOCAL_CONNECT_TIMEOUT_ENV, "0.3")
    assert local_net.local_connect_timeout() == 0.3
    for bad in ("x", "0", "-1"):
        monkeypatch.setenv(local_net.LOCAL_CONNECT_TIMEOUT_ENV, bad)
        assert local_net.local_connect_timeout() == local_net.DEFAULT_LOCAL_CONNECT_TIMEOUT_S


def test_a_closed_local_port_is_given_up_on_quickly_and_a_listening_one_is_accepted():
    started = time.monotonic()
    assert local_net.quick_connect_ok(f"http://127.0.0.1:{closed_port()}") is False
    assert time.monotonic() - started < 1.5
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        assert local_net.quick_connect_ok(f"http://127.0.0.1:{listener.getsockname()[1]}") is True
    finally:
        listener.close()


def test_an_address_that_is_not_ours_is_never_probed_or_hurried():
    assert local_net.quick_connect_ok("https://example.invalid:9") is True            # not checked at all: returns at once without a connection


def test_a_loopback_connect_timeout_is_classified_like_a_refusal_and_a_remote_one_is_not():
    local = httpx.ConnectTimeout("t", request=httpx.Request("POST", "http://127.0.0.1:11434/api/generate"))
    remote = httpx.ConnectTimeout("t", request=httpx.Request("POST", "https://models.example.org/v1"))
    read = httpx.ReadTimeout("t", request=httpx.Request("POST", "http://127.0.0.1:11434/api/generate"))
    assert is_local_refusal(local) and not is_local_refusal(remote) and not is_local_refusal(read)


def test_a_no_model_question_in_a_warm_process_ends_within_one_and_a_half_seconds(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_LLM_RETRIES", "2")
    provider = llm_provider.OllamaProvider(llm_url=f"http://127.0.0.1:{closed_port()}", model="m")
    loop = _loop(tmp_path, "p3", kernel=_FakeKernel(), mcp=_FakeMCP(), llm_provider=provider)
    asyncio.run(loop.run("What can you do?"))                                     # the first call in a process pays for importing: reported, not timed
    loop = _loop(tmp_path, "p3b", kernel=_FakeKernel(), mcp=_FakeMCP(), llm_provider=provider)
    started = time.perf_counter()
    result = asyncio.run(loop.run("What can you do?"))
    seconds = time.perf_counter() - started
    assert result["stopped_reason"] == "model_not_running"
    assert seconds < 1.5, f"{seconds:.2f} s"


# ------------------------------------------------------------------ R14: the breaker does not punish a program that is not there
class Raises(llm_provider.LLMProvider):
    def __init__(self, make):
        self.make, self.calls = make, 0

    @property
    def model(self):
        return "m"

    async def complete(self, *a, **k):
        self.calls += 1
        raise self.make()


@pytest.fixture(autouse=True)
def fresh_breaker():
    provider_breaker.reset_all()
    yield
    provider_breaker.reset_all()


def local_refused():
    return httpx.ConnectError("x", request=httpx.Request("POST", "http://127.0.0.1:9/api/generate"))


def remote_refused():
    return httpx.ConnectError("x", request=httpx.Request("POST", "https://models.example.org/v1"))


def test_ten_refused_local_calls_never_open_the_circuit():
    inner = Raises(local_refused)
    wrapped = provider_breaker.CircuitBreakerProvider(inner)
    for _ in range(10):
        with pytest.raises(httpx.ConnectError):
            asyncio.run(wrapped.complete("hi"))
    assert inner.calls == 10, "every call really went to the provider; none was short-circuited"


def test_remote_failures_still_open_the_circuit_after_five():
    inner = Raises(remote_refused)
    wrapped = provider_breaker.CircuitBreakerProvider(inner)
    for _ in range(5):
        with pytest.raises(httpx.ConnectError):
            asyncio.run(wrapped.complete("hi"))
    with pytest.raises(provider_breaker.ProviderUnavailable):
        asyncio.run(wrapped.complete("hi"))
    assert inner.calls == 5


def test_other_failures_of_a_local_endpoint_are_still_counted():
    inner = Raises(lambda: httpx.ReadTimeout("slow", request=httpx.Request("POST", "http://127.0.0.1:9/api/generate")))
    wrapped = provider_breaker.CircuitBreakerProvider(inner)
    for _ in range(5):
        with pytest.raises(httpx.ReadTimeout):
            asyncio.run(wrapped.complete("hi"))
    with pytest.raises(provider_breaker.ProviderUnavailable):
        asyncio.run(wrapped.complete("hi"))


def test_a_success_still_closes_the_count():
    class Flaky(llm_provider.LLMProvider):
        def __init__(self):
            self.n = 0

        @property
        def model(self):
            return "m"

        async def complete(self, *a, **k):
            self.n += 1
            if self.n in (1, 2, 3, 4):
                raise httpx.ReadTimeout("slow", request=httpx.Request("POST", "https://models.example.org/v1"))
            return "ok"

    wrapped = provider_breaker.CircuitBreakerProvider(Flaky())
    for _ in range(4):
        with pytest.raises(httpx.ReadTimeout):
            asyncio.run(wrapped.complete("hi"))
    assert asyncio.run(wrapped.complete("hi")) == "ok"


# ------------------------------------------------------------------ R15: the Desk command finds the agent the launcher chose
class Agent(BaseHTTPRequestHandler):
    def do_GET(self):                                                           # noqa: N802
        data = json.dumps({"status": "healthy", "version": "2.4.4", "timestamp": "t"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_the_recorded_agent_port_is_used_when_it_still_answers_as_delentia(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), Agent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        launcher.write_ports(tmp_path, port, 3012)
        assert launcher.default_gateway(tmp_path) == f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_with_nothing_recorded_or_a_stale_record_it_is_the_usual_port(tmp_path):
    assert launcher.default_gateway(tmp_path) == "http://127.0.0.1:8000"
    launcher.write_ports(tmp_path, closed_port(), 3012)                         # recorded, but nothing answers there any more
    assert launcher.default_gateway(tmp_path) == "http://127.0.0.1:8000"


def test_the_desk_command_has_no_fixed_gateway_default_and_an_explicit_one_wins():
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    result = CliRunner().invoke(cli, ["desk", "--help"])
    assert "--gateway" in result.output and "default: the agent" in result.output.replace("\n", " ").replace("  ", " ")
    src = Path(__import__("rct_control_plane.cli", fromlist=["x"]).__file__).read_text(encoding="utf-8")
    assert "gateway = gateway or _launcher.default_gateway()" in src


# ------------------------------------------------------------------ R13: the server warms and says so
def test_a_server_that_does_not_warm_says_nothing_and_one_that_does_reports_progress(monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane import api
    monkeypatch.delenv("DELENTIA_WARM_START", raising=False)
    monkeypatch.setitem(api._WARM, "enabled", False)
    assert api.warm_state() is None
    app = api.create_app() if hasattr(api, "create_app") else None
    assert app is not None
    assert TestClient(app).get("/health").json().get("warm") is None


def test_the_warm_up_path_runs_to_the_end_without_a_model_or_an_audit_row(tmp_path, monkeypatch):
    from rct_control_plane import api
    monkeypatch.setitem(api._WARM, "enabled", True)
    monkeypatch.setitem(api._WARM, "done", False)
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", f"http://127.0.0.1:{closed_port()}")
    before = None
    try:
        from rct_control_plane.mcp_server import _kernel
        with _kernel._persistence._connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM audit_trail").fetchone()[0]
    except Exception:                                                           # noqa: BLE001 - a table that does not exist yet is zero rows
        before = 0
    api._warm_agent_path()
    assert api.warm_state() is True
    try:
        from rct_control_plane.mcp_server import _kernel
        with _kernel._persistence._connect() as conn:
            after = conn.execute("SELECT COUNT(*) FROM audit_trail").fetchone()[0]
    except Exception:                                                           # noqa: BLE001
        after = 0
    assert after == before, "warming wrote nothing to the audit record"

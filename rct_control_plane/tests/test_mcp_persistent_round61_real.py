"""
Round 61: persistent connections to external MCP servers.

A real MCP server (tests/fake_mcp_counter_server.py) in its own OS process, the real MCP SDK client. What is checked: calls reuse one process when the server is persistent and start a new one
each time when it is not; two people never share a session; a crashed server or a timeout is survived (the next call reconnects); the session closes when asked; and what it buys, measured.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import time

import pytest

from rct_control_plane import external_mcp as xm

SERVER = os.path.join(os.path.dirname(__file__), "fake_mcp_counter_server.py")


def write_config(tmp_path, monkeypatch, **extra):
    spec = {"command": "python", "args": [SERVER], "read_only_tools": ["count", "slow"], "timeout_s": 30}
    spec.update(extra)
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"servers": {"counter": spec}}), encoding="utf-8")
    monkeypatch.setenv(xm.CONFIG_ENV, str(path))
    xm.clear_cache()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv(xm.PERSISTENT_ENV, raising=False)
    xm.clear_cache()
    yield
    xm.shutdown_pool()
    xm.clear_cache()


async def call(tool="count", args=None, namespace=""):
    out = await xm.call_external_tool(f"mcp__counter__{tool}", args or {}, namespace)
    return out


def data(out):
    return out.get("data") or {}


def run(coro):
    return asyncio.run(coro)


class TestConfig:
    def test_persistent_is_a_boolean_field_and_off_by_default(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch)
        assert xm.load_servers()["counter"].persistent is False
        write_config(tmp_path, monkeypatch, persistent=True)
        assert xm.load_servers()["counter"].persistent is True

    def test_the_environment_can_turn_it_on_for_every_server(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch)
        spec = xm.load_servers()["counter"]
        assert xm.persistent_enabled(spec) is False
        monkeypatch.setenv(xm.PERSISTENT_ENV, "1")
        assert xm.persistent_enabled(spec) is True


class TestReuse:
    def test_a_persistent_server_answers_every_call_from_one_process(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch, persistent=True)

        async def go():
            return [data(await call(namespace="alice")) for _ in range(4)]
        first = run(go())
        assert [d["calls_so_far"] for d in first] == [1, 2, 3, 4] and len({d["pid"] for d in first}) == 1
        # even from a different event loop (a new CLI run, another request): the same session
        again = run(call(namespace="alice"))
        assert data(again)["calls_so_far"] == 5 and data(again)["pid"] == first[0]["pid"]

    def test_without_it_every_call_is_a_fresh_process(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch)

        async def go():
            return [data(await call()) for _ in range(3)]
        got = run(go())
        assert [d["calls_so_far"] for d in got] == [1, 1, 1] and len({d["pid"] for d in got}) == 3

    def test_two_people_never_share_a_session(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch, persistent=True)

        async def go():
            a1 = data(await call(namespace="alice"))
            b1 = data(await call(namespace="bob"))
            a2 = data(await call(namespace="alice"))
            return a1, b1, a2
        a1, b1, a2 = run(go())
        assert a1["pid"] == a2["pid"] and a1["pid"] != b1["pid"]
        assert (a1["calls_so_far"], b1["calls_so_far"], a2["calls_so_far"]) == (1, 1, 2)       # bob never saw alice's count
        assert {(s["server"], s["person"]) for s in xm.pool_status()} == {("counter", "alice"), ("counter", "bob")}

    def test_shutdown_closes_the_processes_and_a_later_call_starts_clean(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch, persistent=True)
        first = data(run(call(namespace="alice")))
        xm.shutdown_pool()
        assert xm.pool_status() == []
        again = data(run(call(namespace="alice")))
        assert again["calls_so_far"] == 1 and again["pid"] != first["pid"]


class TestSurvivingFailures:
    def test_a_crashed_server_costs_one_error_and_the_next_call_reconnects(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch, persistent=True)

        async def go():
            before = data(await call(namespace="alice"))
            crashed = await call("crash", namespace="alice")
            after = data(await call(namespace="alice"))
            return before, crashed, after
        before, crashed, after = run(go())
        assert "error" in crashed and after["pid"] != before["pid"] and after["calls_so_far"] == 1

    def test_a_timeout_drops_the_session_instead_of_leaving_it_wedged(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch, persistent=True, timeout_s=2)

        async def go():
            before = data(await call(namespace="alice"))
            slow = await call("slow", {"seconds": 30}, namespace="alice")
            after = data(await call(namespace="alice"))
            return before, slow, after
        before, slow, after = run(go())
        assert "did not answer" in slow["error"] or "failed" in slow["error"]
        assert after["pid"] != before["pid"]

    def test_a_server_that_cannot_start_is_a_plain_tool_error(self, tmp_path, monkeypatch):
        write_config(tmp_path, monkeypatch, persistent=True, command="python", args=[str(tmp_path / "no_such_server.py")])
        out = run(call(namespace="alice"))
        assert "error" in out


class TestWhatItBuys:
    def test_the_second_and_later_calls_are_much_faster_than_a_fresh_session_each_time(self, tmp_path, monkeypatch):
        """Measured, with a generous bound so a slow CI machine does not make it flaky: a fresh session pays a process start and a handshake on every call."""
        write_config(tmp_path, monkeypatch)

        async def timed(n):
            started = time.perf_counter()
            for _ in range(n):
                await call(namespace="alice")
            return (time.perf_counter() - started) / n
        fresh = run(timed(4))
        write_config(tmp_path, monkeypatch, persistent=True)
        run(call(namespace="alice"))                                  # the one-time start-up
        pooled = run(timed(4))
        print(f"\nMCP call latency: fresh session {fresh * 1000:.0f} ms, pooled {pooled * 1000:.0f} ms ({fresh / max(pooled, 1e-6):.0f}x)")
        assert pooled < fresh / 3

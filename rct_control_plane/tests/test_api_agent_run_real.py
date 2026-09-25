"""
Round 44 item J.3: real tests for POST /v1/agent/run, the HTTP entry
point for GovernedAutonomousLoop - the same real-bridge pattern
/v1/kernel/fdia/evaluate already proved works
(real_bridge_e2e_manual_check.mjs), now extended to the full governed
agent loop.

The LLM decision is mocked here (same acceptable-mock reasoning as this
round's other CLI/unit tests for this loop - verifying real HTTP
request/response wiring, not model correctness, which J.4.2's real
Ollama runs and this feature's own real `delentia agent` CLI smoke test
already answered for real). mcp_server's real _kernel/mcp are
monkeypatched to lightweight fakes for test speed, same as
test_cli_agent.py.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.api import create_app
from rct_control_plane.persistence import ControlPlanePersistence


class _FakeToolResult:
    def __init__(self, payload):
        self.content = [type("C", (), {"text": json.dumps(payload)})()]


class _FakeMCP:
    def __init__(self):
        self.dispatched = []

    async def list_tools(self):
        return [type("T", (), {"name": "delentia_recall", "description": "recall", "input_schema": {}})()]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        return _FakeToolResult({"memories": []})


class _FakeKernel:
    def __init__(self, tmp_path):
        self._persistence = ControlPlanePersistence(db_path=str(tmp_path / "agent_api_test.db"))

    def synthesize_fdia_inputs(self, intent_text):
        return 1.0, 1.0, None

    def algo_04_rct7(self, intent):
        return [f"Step {i}" for i in range(1, 8)]


@pytest.fixture
def api_client():
    application = create_app()
    with TestClient(application) as client:
        yield client


@pytest.fixture
def patched_kernel_and_mcp(monkeypatch, tmp_path):
    import rct_control_plane.mcp_server as mcp_server_module
    fake_mcp = _FakeMCP()
    fake_kernel = _FakeKernel(tmp_path)
    monkeypatch.setattr(mcp_server_module, "mcp", fake_mcp)
    monkeypatch.setattr(mcp_server_module, "_kernel", fake_kernel)
    return fake_mcp, fake_kernel


def _script_decide(monkeypatch, decisions):
    calls = {"n": 0}

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        i = calls["n"]
        calls["n"] += 1
        if i < len(decisions):
            return decisions[i]
        return {"action": "finish", "reasoning": "done", "final_answer": "done", "tool_name": None, "tool_args": {}}

    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)
    return calls


class TestAgentRunEndpoint:
    def test_missing_goal_returns_400(self, api_client):
        resp = api_client.post("/v1/agent/run", json={})
        assert resp.status_code == 400

    def test_real_end_to_end_finish_immediately(self, api_client, patched_kernel_and_mcp, monkeypatch):
        _script_decide(monkeypatch, [
            {"action": "finish", "reasoning": "done", "final_answer": "42", "tool_name": None, "tool_args": {}},
        ])
        resp = api_client.post("/v1/agent/run", json={"goal": "what is the answer"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stopped_reason"] == "llm_finished"
        assert data["final_answer"] == "42"
        assert "namespace" in data

    def test_tool_call_is_real_dispatched(self, api_client, patched_kernel_and_mcp, monkeypatch):
        fake_mcp, _ = patched_kernel_and_mcp
        _script_decide(monkeypatch, [
            {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "x"}, "reasoning": "r"},
            {"action": "finish", "reasoning": "done", "final_answer": "done", "tool_name": None, "tool_args": {}},
        ])
        resp = api_client.post("/v1/agent/run", json={"goal": "recall something"})
        assert resp.status_code == 200
        assert fake_mcp.dispatched == [("delentia_recall", {"query": "x"})]

    def test_fdia_blocked_returns_200_with_the_real_block_reported(self, api_client, patched_kernel_and_mcp, monkeypatch):
        # A blocked episode is not an HTTP-level error - it's a real,
        # successful response reporting a real governance decision, same
        # as /v1/kernel/fdia/evaluate returns 200 with authorized=False
        # rather than an error status for a legitimately-computed F=0.
        _script_decide(monkeypatch, [
            {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command",
             "tool_args": {"command": "rm -rf /"}, "reasoning": "dangerous"},
        ])
        resp = api_client.post("/v1/agent/run", json={"goal": "do something dangerous"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stopped_reason"] == "fdia_blocked"
        assert data["steps"][-1]["tool_result"]["fdia_blocked"] is True

    def test_custom_namespace_is_used(self, api_client, patched_kernel_and_mcp, monkeypatch):
        _script_decide(monkeypatch, [
            {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}},
        ])
        resp = api_client.post("/v1/agent/run", json={"goal": "a goal", "namespace": "my-ns"})
        assert resp.json()["namespace"] == "my-ns"

    def test_real_ollama_timeout_returns_a_clean_504_not_a_bare_500(self, api_client, patched_kernel_and_mcp, monkeypatch):
        # Real, confirmed failure mode found running this endpoint's own
        # J.4.3 real e2e script (scripts/real_agent_e2e_manual_check.py)
        # against a real local Ollama instance under load - a real
        # httpx.TimeoutException must surface as a clean 504 with an
        # honest message, not an unhandled 500 exposing a full internal
        # stack trace to the HTTP caller.
        async def _raise_timeout(goal, history, available_tools, llm_provider=None, extra_context=""):
            raise httpx.ReadTimeout("real simulated timeout")

        monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _raise_timeout)
        resp = api_client.post("/v1/agent/run", json={"goal": "a goal"})
        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"]

    def test_max_iterations_is_respected(self, api_client, patched_kernel_and_mcp, monkeypatch):
        fake_mcp, _ = patched_kernel_and_mcp
        # Script far more tool-call decisions than max_iterations allows.
        _script_decide(monkeypatch, [
            {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": str(i)}, "reasoning": "r"}
            for i in range(10)
        ])
        resp = api_client.post("/v1/agent/run", json={"goal": "loop forever", "max_iterations": 2})
        data = resp.json()
        assert data["iterations"] == 2
        assert len(fake_mcp.dispatched) == 2

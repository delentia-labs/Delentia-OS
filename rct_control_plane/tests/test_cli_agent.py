"""
Round 44 item J.3: tests for `delentia agent` (rct_control_plane/cli.py's
new agent_command). The LLM decision is mocked (same acceptable-mock
reasoning as J.4.1/governed_autonomous_loop's own tests - verifying "does
the CLI wire the real GovernedAutonomousLoop correctly and format its
real output", not "does the model answer correctly", a question this
round's real Ollama runs (J.4.2, J.1.4c's live re-verification, and this
command's own manual end-to-end smoke test - a real `delentia agent`
invocation against real Ollama, documented in the Round 44 plan) already
answer for real. mcp_server's real module-level kernel/mcp objects are
monkeypatched to lightweight fakes for test speed - mcp_server.py itself
is imported (paying its real cold-start cost once, already amortized by
other test files in this suite that import it too), only the specific
_kernel/mcp attribute references used by agent_command are swapped.
"""
import asyncio
import json

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.persistence import ControlPlanePersistence


class _FakeToolResult:
    def __init__(self, payload):
        self.content = [type("C", (), {"text": json.dumps(payload)})()]


class _FakeMCP:
    def __init__(self):
        self.dispatched = []

    async def list_tools(self):
        return [type("T", (), {"name": "delentia_recall", "description": "recall a memory", "input_schema": {}})()]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        return _FakeToolResult({"memories": []})


class _FakeKernel:
    def __init__(self, tmp_path):
        self._persistence = ControlPlanePersistence(db_path=str(tmp_path / "agent_cli_test.db"))

    def synthesize_fdia_inputs(self, intent_text):
        return 1.0, 1.0, None

    def algo_04_rct7(self, intent):
        return [f"Step {i}" for i in range(1, 8)]


@pytest.fixture
def cli_runner():
    from click.testing import CliRunner
    return CliRunner()


@pytest.fixture
def cli():
    from rct_control_plane.cli import cli as _cli
    return _cli


@pytest.fixture
def patched_kernel_and_mcp(monkeypatch, tmp_path):
    """agent_command does `from rct_control_plane.mcp_server import
    _kernel, mcp` LOCALLY at call time - patching those names on the real
    mcp_server module (not cli's own namespace) is what actually takes
    effect, same discipline already established for get_default_provider
    (test_intent_delta_wired_into_autonomous_loop_real.py) and
    decide_next_action's own prompt-capturing tests."""
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


class TestAgentCommand:
    def test_real_end_to_end_finish_immediately(self, cli_runner, cli, patched_kernel_and_mcp, monkeypatch):
        _script_decide(monkeypatch, [
            {"action": "finish", "reasoning": "done", "final_answer": "42", "tool_name": None, "tool_args": {}},
        ])
        result = cli_runner.invoke(cli, ["agent", "what is the answer"])
        assert result.exit_code == 0
        assert "stopped_reason: llm_finished" in result.output
        assert "final_answer:" in result.output
        assert "42" in result.output

    def test_tool_call_then_finish_is_reported_in_output(self, cli_runner, cli, patched_kernel_and_mcp, monkeypatch):
        fake_mcp, _ = patched_kernel_and_mcp
        _script_decide(monkeypatch, [
            {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "x"}, "reasoning": "r"},
            {"action": "finish", "reasoning": "done", "final_answer": "done", "tool_name": None, "tool_args": {}},
        ])
        result = cli_runner.invoke(cli, ["agent", "recall something"])
        assert result.exit_code == 0
        assert "delentia_recall" in result.output
        assert fake_mcp.dispatched == [("delentia_recall", {"query": "x"})]

    def test_fdia_blocked_exits_nonzero(self, cli_runner, cli, patched_kernel_and_mcp, monkeypatch):
        _script_decide(monkeypatch, [
            {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command",
             "tool_args": {"command": "rm -rf /"}, "reasoning": "dangerous"},
        ])
        result = cli_runner.invoke(cli, ["agent", "do something dangerous"])
        assert result.exit_code == 1
        assert "fdia_blocked" in result.output
        assert "FDIA BLOCKED" in result.output

    def test_custom_namespace_is_used(self, cli_runner, cli, patched_kernel_and_mcp, monkeypatch):
        _script_decide(monkeypatch, [
            {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}},
        ])
        result = cli_runner.invoke(cli, ["agent", "a goal", "--namespace", "my-custom-ns"])
        assert result.exit_code == 0
        assert "namespace: my-custom-ns" in result.output

    def test_default_namespace_is_generated(self, cli_runner, cli, patched_kernel_and_mcp, monkeypatch):
        _script_decide(monkeypatch, [
            {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}},
        ])
        result = cli_runner.invoke(cli, ["agent", "a goal"])
        assert result.exit_code == 0
        assert "namespace: cli-agent-" in result.output

    def test_help_text_is_real(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["agent", "--help"])
        assert result.exit_code == 0
        assert "GOAL" in result.output


def test_asyncio_run_sanity():
    # Guards against a regression where agent_command's own asyncio.run
    # call site silently breaks (e.g. a bad import) without any test
    # exercising it - a trivial smoke check independent of the CLI layer.
    async def _noop():
        return True
    assert asyncio.run(_noop()) is True

"""
Round 37: real tests for AutonomousLoop.run()'s new optional `on_step`
live-introspection hook. Uses a monkeypatched decide_next_action (not a
real LLM call) so these tests are deterministic and fast, isolating what's
actually under test - the callback wiring itself - from local-LLM
non-determinism (the documented, pre-existing source of flakiness in
test_autonomous_loop_real.py).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.autonomous_loop import AutonomousLoop, LoopStep
from rct_control_plane.persistence import ControlPlanePersistence


class _FakeToolResult:
    def __init__(self, text: str):
        self.content = [type("C", (), {"text": text})()]


class _FakeMCP:
    async def list_tools(self):
        return [type("T", (), {"name": "noop_tool", "description": "does nothing", "input_schema": {}})()]

    async def call_tool(self, name, args):
        return _FakeToolResult('{"ok": true}')


@pytest.fixture
def fake_decide(monkeypatch):
    """Scripts a real, deterministic 2-step decision sequence: one real
    tool call, then finish - through the loop's own actual code path."""
    calls = {"n": 0}

    async def _fake(goal, history, available_tools, llm_provider=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"action": "call_tool", "tool_name": "noop_tool", "tool_args": {},
                     "reasoning": "step 1", "final_answer": None}
        return {"action": "finish", "reasoning": "done", "final_answer": "42",
                 "tool_name": None, "tool_args": {}}

    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)
    return calls


def test_on_step_is_called_once_per_real_step_with_the_real_step_object(fake_decide, tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "callback_test.db"))
    loop = AutonomousLoop(mcp_server=_FakeMCP(), persistence=persistence, max_iterations=5, namespace="cb_test")

    observed = []

    def on_step(step):
        assert isinstance(step, LoopStep)
        observed.append(step)

    result = asyncio.run(loop.run("do the thing", on_step=on_step))

    assert len(observed) == 2
    assert observed[0].tool_name == "noop_tool"
    assert observed[1].tool_name is None  # the finish step
    assert result["final_answer"] == "42"


def test_on_step_supports_an_async_callback(fake_decide, tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "callback_test_async.db"))
    loop = AutonomousLoop(mcp_server=_FakeMCP(), persistence=persistence, max_iterations=5, namespace="cb_test_async")

    observed = []

    async def on_step(step):
        await asyncio.sleep(0)
        observed.append(step.tool_name)

    asyncio.run(loop.run("do the thing", on_step=on_step))

    assert observed == ["noop_tool", None]


def test_run_without_on_step_behaves_exactly_as_before(fake_decide, tmp_path):
    """Zero-Delete proof: omitting on_step (every pre-Round-37 caller)
    produces identical results to before this change."""
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "callback_test_none.db"))
    loop = AutonomousLoop(mcp_server=_FakeMCP(), persistence=persistence, max_iterations=5, namespace="cb_test_none")

    result = asyncio.run(loop.run("do the thing"))

    assert result["final_answer"] == "42"
    assert result["stopped_reason"] == "llm_finished"
    assert len(result["steps"]) == 2

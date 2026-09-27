"""
Round 45 item C (group 4): real tests for subagent_runner.py - 0% coverage
before this file. Confirmed genuinely used (not dead code): jitna_distributor.py
spawns this module as a separate OS process via
`python -m rct_control_plane.subagent_runner` (see that module's own
docstring). The one external boundary mocked here is AutonomousLoop.run()
itself (a real LLM-backed loop) - everything else (argparse wiring,
namespace construction, JSON output shape) runs for real.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json

import pytest

import rct_control_plane.subagent_runner as subagent_runner


class _FakeLoop:
    captured_kwargs = {}

    def __init__(self, **kwargs):
        _FakeLoop.captured_kwargs = kwargs

    async def run(self, goal):
        _FakeLoop.captured_goal = goal
        return {"final_answer": "done", "stopped_reason": "llm_finished", "iterations": 2}


@pytest.fixture
def patched_loop(monkeypatch):
    import rct_control_plane.autonomous_loop as autonomous_loop_module
    monkeypatch.setattr(autonomous_loop_module, "AutonomousLoop", _FakeLoop)
    yield


class TestArgumentParsing:
    def test_missing_required_agent_id_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["subagent_runner.py", "--goal", "g", "--worktree", "w"])
        with pytest.raises(SystemExit):
            asyncio.run(subagent_runner._main())

    def test_missing_required_goal_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["subagent_runner.py", "--agent-id", "a1", "--worktree", "w"])
        with pytest.raises(SystemExit):
            asyncio.run(subagent_runner._main())

    def test_missing_required_worktree_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["subagent_runner.py", "--agent-id", "a1", "--goal", "g"])
        with pytest.raises(SystemExit):
            asyncio.run(subagent_runner._main())


class TestMainFlow:
    def test_prints_one_well_formed_json_line_with_all_fields(self, monkeypatch, capsys, patched_loop):
        monkeypatch.setattr(sys, "argv", [
            "subagent_runner.py", "--agent-id", "a1", "--goal", "do the thing", "--worktree", "/tmp/wt1",
        ])
        asyncio.run(subagent_runner._main())

        out_lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln]
        # This module's own docstring documents that the dispatcher parses
        # only the LAST stdout line (earlier lines may carry real logging
        # noise from imported dependencies, e.g. mcp_server's own structlog
        # setup on a fresh import) - so the real contract under test is
        # "the last line is well-formed JSON with these fields", not
        # "stdout has exactly one line".
        payload = json.loads(out_lines[-1])
        assert payload == {
            "agent_id": "a1", "worktree": "/tmp/wt1",
            "final_answer": "done", "stopped_reason": "llm_finished", "iterations": 2,
        }

    def test_namespace_is_scoped_by_agent_id(self, monkeypatch, patched_loop):
        monkeypatch.setattr(sys, "argv", [
            "subagent_runner.py", "--agent-id", "worker-7", "--goal", "g", "--worktree", "/tmp/wt",
        ])
        asyncio.run(subagent_runner._main())
        assert _FakeLoop.captured_kwargs["namespace"] == "jitna-subagent-worker-7"

    def test_max_iterations_defaults_to_three(self, monkeypatch, patched_loop):
        monkeypatch.setattr(sys, "argv", [
            "subagent_runner.py", "--agent-id", "a1", "--goal", "g", "--worktree", "/tmp/wt",
        ])
        asyncio.run(subagent_runner._main())
        assert _FakeLoop.captured_kwargs["max_iterations"] == 3

    def test_max_iterations_is_configurable(self, monkeypatch, patched_loop):
        monkeypatch.setattr(sys, "argv", [
            "subagent_runner.py", "--agent-id", "a1", "--goal", "g", "--worktree", "/tmp/wt",
            "--max-iterations", "9",
        ])
        asyncio.run(subagent_runner._main())
        assert _FakeLoop.captured_kwargs["max_iterations"] == 9

    def test_the_real_goal_string_is_passed_through_unmodified(self, monkeypatch, patched_loop):
        monkeypatch.setattr(sys, "argv", [
            "subagent_runner.py", "--agent-id", "a1", "--goal", "a very specific real goal", "--worktree", "/tmp/wt",
        ])
        asyncio.run(subagent_runner._main())
        assert _FakeLoop.captured_goal == "a very specific real goal"

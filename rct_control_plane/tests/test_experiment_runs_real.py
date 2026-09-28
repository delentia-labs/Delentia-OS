"""
Round 48 R3.4: every GovernedAutonomousLoop episode is recorded as an RCTDB
experiment_run, grouped by goal, so "does the second attempt do better
because of a learned skill?" becomes a query instead of a guess.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

from click.testing import CliRunner

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from test_governed_autonomous_loop_real import _loop


def _finish_after(monkeypatch, tool_calls):
    """Scripted model: `tool_calls` recall calls, then a finished answer."""
    state = {"n": 0}

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        state["n"] += 1
        if len(history) < tool_calls:
            return {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": goal},
                    "reasoning": "look it up"}
        return {"action": "finish", "reasoning": "done", "final_answer": f"Completed the goal: {goal}",
                "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)


def test_episode_is_recorded_with_metrics(tmp_path, monkeypatch):
    _finish_after(monkeypatch, tool_calls=2)
    loop = _loop(tmp_path, "exp_one")
    result = asyncio.run(loop.run("tidy the release checklist"))

    exp = result["experiment"]
    assert exp["experiment_id"] == GovernedAutonomousLoop.experiment_id_for_goal("tidy the release checklist")
    (run,) = loop._persistence.get_experiment_runs(exp["experiment_id"])
    metrics = run["metrics"] if isinstance(run["metrics"], dict) else json.loads(run["metrics"])
    assert metrics["finished"] == 1 and metrics["aligned_with_intent"] == 1
    assert metrics["tool_calls"] == 2 and metrics["iterations"] == 3
    assert metrics["skills_injected"] == 0 and metrics["rct7_in_prompt"] == 1
    assert run["algorithm_id"].startswith("governed_loop/")


def test_same_goal_groups_runs_and_shows_the_skill_effect(tmp_path, monkeypatch):
    loop = _loop(tmp_path, "exp_repeat")
    _finish_after(monkeypatch, tool_calls=2)
    first = asyncio.run(loop.run("Tidy the  release checklist"))
    _finish_after(monkeypatch, tool_calls=0)  # the second attempt goes straight to the answer
    second = asyncio.run(loop.run("tidy the release checklist"))

    assert first["experiment"]["experiment_id"] == second["experiment"]["experiment_id"]
    exp_id = first["experiment"]["experiment_id"]
    comparison = loop._persistence.compare_experiment_runs(exp_id)
    assert comparison["iterations"] == {"first": 3, "last": 1, "delta": -2}
    # the first (verified) episode became a skill that the second one was given
    assert comparison["skills_injected"]["first"] == 0 and comparison["skills_injected"]["last"] >= 1


def test_recording_failure_never_changes_the_episode(tmp_path, monkeypatch):
    _finish_after(monkeypatch, tool_calls=0)
    loop = _loop(tmp_path, "exp_broken")

    def _boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(loop._persistence, "save_experiment_run", _boom)
    result = asyncio.run(loop.run("tidy the release checklist"))
    assert result["stopped_reason"] == "llm_finished"
    assert "disk full" in result["experiment"]["error"]


def test_cli_list_and_compare(tmp_path, monkeypatch):
    from rct_control_plane.cli import cli
    loop = _loop(tmp_path, "exp_cli")
    _finish_after(monkeypatch, tool_calls=1)
    asyncio.run(loop.run("summarise the audit log"))
    asyncio.run(loop.run("summarise the audit log"))
    exp_id = GovernedAutonomousLoop.experiment_id_for_goal("summarise the audit log")

    runner = CliRunner()
    listed = runner.invoke(cli, ["experiments", "list", "--db", loop._persistence.db_path])
    assert listed.exit_code == 0 and exp_id in listed.output and "runs=2" in listed.output
    compared = runner.invoke(cli, ["experiments", "compare", exp_id, "--db", loop._persistence.db_path])
    assert compared.exit_code == 0 and json.loads(compared.output)["runs"] == 2

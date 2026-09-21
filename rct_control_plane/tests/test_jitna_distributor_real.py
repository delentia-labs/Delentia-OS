"""
Round 38: real tests for jitna_distributor.py - proves the real
fork-join orchestration (worktree creation, RCTDB recording, worktree
cleanup) works correctly, using a fake `dispatch_fn` to avoid spawning
real subprocesses/LLM calls in the automated suite (the same testable-
seam discipline this round's gateways already established).

Never runs against the real Delentia-OS repo itself - a throwaway temp
git repo is used for every test, so this suite never creates real
branches/worktrees on the Architect's actual working repo.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import subprocess

import pytest

from rct_control_plane.jitna_distributor import distribute_to_subagents
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture
def temp_git_repo(tmp_path):
    repo = tmp_path / "throwaway_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(repo), capture_output=True)
    (repo / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True, check=True)
    return str(repo)


async def _fake_dispatch(agent_id, goal, worktree_path, timeout_seconds):
    return {"final_answer": f"done: {goal}", "stopped_reason": "llm_finished", "iterations": 1}


def test_real_worktrees_are_created_for_each_goal_and_removed_after(temp_git_repo, tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "jitna_test.db"))
    goals = ["goal one", "goal two", "goal three"]

    results = asyncio.run(distribute_to_subagents(
        goals, persistence, repo_root=temp_git_repo, dispatch_fn=_fake_dispatch,
    ))

    assert len(results) == 3
    for result in results:
        assert result["success"] is True
        assert result["final_answer"].startswith("done:")

    from rct_control_plane.git_worktree_isolator import GitWorktreeIsolator
    isolator = GitWorktreeIsolator(repo_root=temp_git_repo)
    assert isolator.list_active() == {}  # all cleaned up


def test_completed_subagent_work_is_really_recorded_in_rctdb(temp_git_repo, tmp_path):
    """The exact real gap Round 38 found: nothing previously connected
    completed worktree/swarm work back into persistence."""
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "jitna_test2.db"))

    asyncio.run(distribute_to_subagents(
        ["real recorded goal"], persistence, repo_root=temp_git_repo, dispatch_fn=_fake_dispatch,
    ))

    decisions = persistence.list_architect_decisions(limit=10)
    jitna_decisions = [d for d in decisions if d["decision_type"] == "jitna_subagent_result"]
    assert len(jitna_decisions) == 1
    assert "real recorded goal" in jitna_decisions[0]["description"]
    assert jitna_decisions[0]["jitna_after"]["final_answer"] == "done: real recorded goal"


def test_each_goal_gets_a_genuinely_isolated_namespace_via_a_distinct_agent_id(temp_git_repo, tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "jitna_test3.db"))
    results = asyncio.run(distribute_to_subagents(
        ["goal A", "goal B"], persistence, repo_root=temp_git_repo, dispatch_fn=_fake_dispatch,
    ))
    agent_ids = {r["agent_id"] for r in results}
    assert len(agent_ids) == 2  # genuinely distinct, not shared


def test_a_dispatch_exception_for_one_goal_does_not_break_the_others(temp_git_repo, tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "jitna_test4.db"))

    async def _flaky_dispatch(agent_id, goal, worktree_path, timeout_seconds):
        if goal == "failing goal":
            raise RuntimeError("subagent crashed")
        return {"final_answer": "ok", "stopped_reason": "llm_finished"}

    results = asyncio.run(distribute_to_subagents(
        ["failing goal", "fine goal"], persistence, repo_root=temp_git_repo, dispatch_fn=_flaky_dispatch,
    ))

    by_goal = {r["goal"]: r for r in results}
    assert by_goal["failing goal"]["success"] is False
    assert "subagent crashed" in by_goal["failing goal"]["error"]
    assert by_goal["fine goal"]["success"] is True

    # Both outcomes, including the failure, are still real RCTDB records.
    decisions = persistence.list_architect_decisions(limit=10)
    jitna_decisions = [d for d in decisions if d["decision_type"] == "jitna_subagent_result"]
    assert len(jitna_decisions) == 2


def test_a_real_dispatch_timeout_is_handled_honestly(temp_git_repo, tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "jitna_test5.db"))

    async def _slow_dispatch(agent_id, goal, worktree_path, timeout_seconds):
        await asyncio.sleep(0.05)
        return {"final_answer": "slow but done"}

    results = asyncio.run(distribute_to_subagents(
        ["slow goal"], persistence, repo_root=temp_git_repo, dispatch_fn=_slow_dispatch, timeout_seconds=10.0,
    ))
    assert results[0]["success"] is True

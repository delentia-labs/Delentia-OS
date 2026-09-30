"""
Round 51: the Intent Loop's five pillars over a real episode, and the motto
("the more it is used, the smarter, faster and cheaper") measured from the
recorded runs. Real loop and SQLite; the model's decisions are scripted.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

import pytest

from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.algorithm_pipeline import AlgorithmPipeline, PipelineOptions
from rct_control_plane.intent_loop import PILLARS, evolution_report, pillar_report
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.tests.test_intent_growth_round51_real import FINISH, LS, _loop, _script

GOAL = "Read the file pyproject.toml in the repository and tell me the project name"


@pytest.fixture(scope="module")
def kernel():
    return AlgorithmKernel41()


def test_each_episode_reports_the_five_pillars_from_measured_values(tmp_path, kernel, monkeypatch):
    _script(monkeypatch, [[LS, FINISH]])
    loop = _loop(tmp_path, kernel, namespace="pillars", db="pillars.db")
    asyncio.run(AgentMemory("pillars", loop._persistence).store("The project name is in pyproject.toml", MemoryType.FACT, importance=0.9))
    loop._algorithm_pipeline = AlgorithmPipeline(
        kernel, loop._persistence, "pillars", memory=kernel._agent_memory, skills=loop._skill_library,
        options=PipelineOptions(enabled={"ALGO-16", "ALGO-18", "ALGO-13", "ALGO-30", "ALGO-04"}))
    result = asyncio.run(loop.run(GOAL))

    report = result["intent_loop"]
    assert tuple(report) == PILLARS
    assert report["gatekeeper"]["D"] == result["growth"]["data"]["D"] and report["gatekeeper"]["stopped_here"] is False
    assert report["memory"]["memories_recalled"] >= 1 and report["memory"]["retrieval_algorithms_ok"] >= 2
    assert report["executor"]["tool_calls"] == 1 and report["executor"]["iterations"] == 2
    assert report["verifier"]["intent_aligned"] is True and report["verifier"]["belief_confidence"] is not None
    assert "SignedAI" in report["verifier"]["multi_model_consensus"]
    assert report["committer"]["verified"] and report["committer"]["skill_extracted"] is True
    assert report["committer"]["G"] == result["growth"]["G"] and report["committer"]["experiment_run"]


def test_a_blocked_episode_says_it_stopped_at_the_gatekeeper(tmp_path, kernel, monkeypatch):
    _script(monkeypatch, [[LS, FINISH]])
    loop = _loop(tmp_path, kernel, namespace="blocked", db="blocked.db")
    result = asyncio.run(loop.run("Deploy the new database schema to production"))
    assert result["stopped_reason"] == "fdia_blocked"
    gate = result["intent_loop"]["gatekeeper"]
    assert gate["stopped_here"] is True and gate["missing_data"]
    assert result["intent_loop"]["committer"]["verified"] is False


def _seed(persistence, namespace, goal, runs):
    experiment_id = f"governed-loop:{abs(hash(goal))}"
    persistence.save_experiment(experiment_id, goal)
    for n, metrics in enumerate(runs):
        persistence.save_experiment_run(f"{namespace}-{abs(hash(goal))}-{n}", experiment_id, "governed_loop/test",
                                        {"finished": 1, "aligned_with_intent": 1, **metrics}, {"namespace": namespace})
    return experiment_id


def test_the_evolution_report_shows_later_runs_smaller_faster_cheaper_and_better_informed(tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "e.db"))
    _seed(persistence, "u", "summarise the notes", [
        {"iterations": 5, "duration_s": 40.0, "cost_usd": 0.02, "data_D": 0.5, "skills_injected": 0},
        {"iterations": 4, "duration_s": 30.0, "cost_usd": 0.015, "data_D": 0.6, "skills_injected": 1},
        {"iterations": 2, "duration_s": 8.0, "cost_usd": 0.004, "data_D": 0.8, "skills_injected": 1},
    ])
    _seed(persistence, "u", "a goal run once", [{"iterations": 3, "duration_s": 5.0, "data_D": 0.5}])
    report = evolution_report(persistence, "u")
    assert report["goals_repeated"] == 1                      # a goal run once is not evidence of anything
    cluster = report["clusters"][0]
    assert cluster["goal"] == "summarise the notes" and cluster["verified_runs"] == 3
    assert cluster["fewer_steps"] and cluster["faster"] and cluster["cheaper"] and cluster["better_informed"]
    assert report["summary"] == {"fewer_steps": 1, "faster": 1, "cheaper": 1, "better_informed": 1, "median_D_change": 0.3}


def test_a_goal_that_got_worse_is_reported_as_worse_and_other_users_are_ignored(tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "e.db"))
    _seed(persistence, "u", "rotate keys", [{"iterations": 2, "duration_s": 5.0, "data_D": 0.7},
                                            {"iterations": 6, "duration_s": 25.0, "data_D": 0.6}])
    _seed(persistence, "other", "rotate keys", [{"iterations": 9, "duration_s": 90.0, "data_D": 0.1},
                                                {"iterations": 1, "duration_s": 1.0, "data_D": 0.9}])
    cluster = evolution_report(persistence, "u")["clusters"][0]
    assert not cluster["fewer_steps"] and not cluster["faster"] and not cluster["better_informed"]
    assert cluster["first"]["steps"] == 2 and cluster["last"]["steps"] == 6


def test_unverified_runs_are_not_counted(tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "e.db"))
    experiment_id = _seed(persistence, "u", "g", [{"iterations": 4, "duration_s": 4.0}])
    persistence.save_experiment_run("bad", experiment_id, "governed_loop/test", {"finished": 1, "aligned_with_intent": 0, "iterations": 1},
                                    {"namespace": "u"})
    assert evolution_report(persistence, "u")["goals_repeated"] == 0


def test_the_desk_growth_endpoint_carries_the_evolution_report(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from rct_control_plane import desk_api
    from rct_control_plane.api import create_app
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "d.db"))
    monkeypatch.setattr(desk_api, "_kernel", lambda: type("K", (), {"_persistence": persistence})())
    from rct_control_plane.skill_library import SkillLibrary
    skills = SkillLibrary(db_path=str(tmp_path / "s.db"))
    monkeypatch.setattr(desk_api, "_skills", lambda: skills)
    persistence.save_state(state_id="x", namespace="mee_growth", key="u",
                           value={"session": {"g_current": 1.4, "resilience": 1.0, "total_growth_ratio": 1.4}, "episodes": 3, "verified_episodes": 3})
    _seed(persistence, "u", "g", [{"iterations": 4, "duration_s": 4.0}, {"iterations": 1, "duration_s": 1.0}])
    with TestClient(create_app()) as client:
        body = client.get("/v1/desk/growth").json()
    assert body["evolution"][0]["goals_repeated"] == 1 and body["evolution"][0]["summary"]["fewer_steps"] == 1

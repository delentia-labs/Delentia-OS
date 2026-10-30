"""
Round 106: the Delta Engine's durable log is part of every governed episode (criteria: research/DELTA_STATE_LOG_CRITERIA_R106.md, written before the code).

Real governed loop, real SQLite, real `VersionedDeltaLog` files; the model's decisions and the tool world are scripted. The scale of the cost and size criteria (W2, W3: 200 and 1,000 episodes) is measured
by research/measure_state_log_r106.py; here the same properties are checked on small runs so they stay true.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
import sqlite3
import threading
from pathlib import Path

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import agent_state_log
from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary


class _Tool:
    def __init__(self, name):
        self.name, self.description, self.input_schema = name, name, {}


class _Result:
    def __init__(self, payload):
        self.content = [type("C", (), {"text": json.dumps(payload)})()]


class World:
    async def list_tools(self):
        return [_Tool("delentia_read_repo_file"), _Tool("delentia_recall")]

    async def call_tool(self, name, args):
        return _Result({"content": 'name = "delentia-os"', "path": args.get("relative_path")})


@pytest.fixture(scope="module")
def kernel():
    return AlgorithmKernel41()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("DELENTIA_STATE_LOG_ANCHOR_EVERY", "5")
    monkeypatch.delenv(agent_state_log.ENV, raising=False)
    yield
    agent_state_log.close_all()


@pytest.fixture
def model(monkeypatch):
    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        if not history:
            return {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "pyproject.toml"}, "reasoning": "read it", "final_answer": None}
        return {"action": "finish", "reasoning": "done", "final_answer": "The project name is delentia-os.", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)


def _run(tmp_path, kernel, namespace, goal="Read the file pyproject.toml and tell me the project name"):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "agentic.db"))
    skills = SkillLibrary(db_path=str(tmp_path / "skills.db"))
    loop = GovernedAutonomousLoop(mcp_server=World(), persistence=persistence, kernel=kernel, skill_library=skills, max_iterations=4, namespace=namespace)
    return asyncio.run(loop.run(goal)), persistence


def _log(tmp_path, namespace):
    return agent_state_log.AgentStateLog.for_namespace(namespace, ControlPlanePersistence(db_path=str(tmp_path / "agentic.db")))


def test_w1_every_version_rebuilds_exactly_for_three_people(tmp_path, kernel, model):
    people = ["alice", "bob", "carol"]
    seen = {p: [] for p in people}
    for round_no in range(1, 8):
        for p in people:
            result, _ = _run(tmp_path, kernel, p)
            assert result["state_log"].get("version") == round_no, result["state_log"]
            seen[p].append(_log(tmp_path, p).show()["state"])
    for p in people:
        log = _log(tmp_path, p)
        for v, expected in enumerate(seen[p], start=1):
            assert log.at(v) == expected, (p, v)
        last = log.at(7)
        assert last["episodes"] == 7 and last["tool_calls"] >= 7 and sum(last["stopped"].values()) == 7
        assert last["last"]["stopped_reason"] == "llm_finished"
        assert log.verify()["ok"], log.verify()


def test_w5_the_files_hold_no_words_of_the_episodes(tmp_path, kernel, model):
    secret_goal = "Read the file pyproject.toml and tell me the project name zebra-moonlight-4471"
    for _ in range(4):
        _run(tmp_path, kernel, "dana-personal-name", goal=secret_goal)
    raw = b"".join(p.read_bytes() for p in (tmp_path / "state_logs").glob("*.db*"))
    for word in (b"zebra-moonlight-4471", b"dana-personal-name", b"The project name is delentia-os", b"pyproject.toml"):
        assert word not in raw, word


def test_w4_damage_to_the_file_is_detected(tmp_path, kernel, model):
    for _ in range(12):
        _run(tmp_path, kernel, "erin")
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "agentic.db"))
    log = _log(tmp_path, "erin")
    assert log.verify(persistence)["ok"] and log.verify(persistence)["anchors"] >= 2
    path, name = log.path, log.name
    agent_state_log.close_all()

    def corrupted(sql):
        con = sqlite3.connect(str(path))
        con.execute(sql)
        con.commit()
        con.close()
        fresh = agent_state_log.AgentStateLog(path, name)
        report = fresh.verify(persistence)
        fresh.close()
        return report

    original = path.read_bytes()
    assert not corrupted("UPDATE deltas SET ops = '[]' WHERE version = 3")["ok"]                      # a changed delta
    path.write_bytes(original)
    assert not corrupted("DELETE FROM deltas WHERE version = 4")["ok"]                                # a removed delta
    path.write_bytes(original)
    cut = corrupted("DELETE FROM deltas WHERE version > 8")                                           # the newest versions cut off: only the anchor in the audit chain can see this
    assert not cut["ok"] and any("cut off" in p for p in cut["problems"]), cut
    path.write_bytes(original)
    assert agent_state_log.AgentStateLog(path, name).verify(persistence)["ok"]


def test_w6_a_log_that_cannot_be_written_never_changes_the_episode(tmp_path, kernel, model, monkeypatch):
    ok = tmp_path / "ok"
    ok.mkdir()
    baseline, _ = _run(ok, kernel, "frank")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "state_logs").write_text("a file where the folder should be")
    result, _ = _run(broken, kernel, "frank")
    assert "error" in result["state_log"], result["state_log"]
    assert result["final_answer"] == baseline["final_answer"] and result["stopped_reason"] == baseline["stopped_reason"] == "llm_finished"


def test_w8_off_means_no_file(tmp_path, kernel, model, monkeypatch):
    monkeypatch.setenv(agent_state_log.ENV, "off")
    result, _ = _run(tmp_path, kernel, "gina")
    assert result["state_log"] == {"enabled": False}
    assert not (tmp_path / "state_logs").exists()


def test_w7_eight_writers_for_one_person_lose_and_repeat_nothing(tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "agentic.db"))
    log = agent_state_log.AgentStateLog.for_namespace("hana", persistence)
    errors, versions = [], []

    def worker(k):
        try:
            for i in range(25):
                versions.append(log.record_episode({"episode_id": f"{k}-{i}", "stopped_reason": "llm_finished", "iterations": 2, "verified": True, "tool_calls": 1, "cost_usd": 0.001}, persistence))
        except Exception as exc:                        # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert sorted(versions) == list(range(1, 201))
    state = log.show()["state"]
    assert state["episodes"] == 200 and state["tool_calls"] == 200 and abs(state["cost_usd"] - 0.2) < 1e-6
    assert log.verify(persistence)["ok"]


def test_a_second_process_writing_the_same_file_is_not_lost(tmp_path):
    """Two AgentStateLog objects on one file stand for two processes: the second reads what the first wrote and continues."""
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "agentic.db"))
    a = agent_state_log.AgentStateLog(tmp_path / "x.db", "x")
    b = agent_state_log.AgentStateLog(tmp_path / "x.db", "x")
    for i in range(5):
        (a if i % 2 else b).record_episode({"episode_id": str(i), "stopped_reason": "llm_finished", "verified": True}, persistence)
    assert a.show()["state"]["episodes"] == 5 and b.show()["version"] == 5
    a.close(); b.close()


def test_w9_the_erase_report_says_the_state_log_holds_no_personal_text():
    source = Path(agent_state_log.__file__).with_name("memory_erasure.py").read_text(encoding="utf-8")
    assert "state_log" in source and "numbers and hashes only" in source


def test_the_state_is_numbers_and_hashes_only():
    state = agent_state_log.next_state(agent_state_log.initial_state(), {"episode_id": "e1", "stopped_reason": "llm_finished", "iterations": 2, "verified": True, "tool_calls": 1,
                                                                        "cost_usd": 0.01, "growth_G": 1.2, "memory": {"events": 3, "head_hash": "ab" * 32}, "skills": 2, "audit": {"seq": 9, "row_hash": "cd" * 32}})
    text = json.dumps(state)
    assert set(state) == {"episodes", "verified_episodes", "stopped", "tool_calls", "cost_usd", "growth_G", "memory", "skills", "audit", "last"}
    assert "goal" not in text and "answer" not in text and "content" not in text

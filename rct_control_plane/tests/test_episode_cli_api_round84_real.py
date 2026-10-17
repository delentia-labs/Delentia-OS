"""
Round 84: the interrupted episodes are visible and resumable through the CLI and the HTTP API, and a person sees and resumes only their own.

Real FastAPI app, real per-person tokens, real journal in the shared kernel's database; the scripted model stands in for the model only.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from rct_control_plane import api_tokens, episode_journal
from rct_control_plane.api import create_app
from rct_control_plane.cli import cli
from rct_control_plane.mcp_server import _kernel
from research.daaes import delentia_session as ds


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")
    alice = api_tokens.create("alice", tmp_path / "tokens.json")
    bob = api_tokens.create("bob", tmp_path / "tokens.json")
    monkeypatch.setattr(episode_journal, "_alive", lambda pid, started: False)           # the processes that wrote these journals are gone
    journal = episode_journal.EpisodeJournal(_kernel._persistence)
    for who, eid, goal in (("alice", "ep-alice", "alice goal about her salary"), ("bob", "ep-bob", "bob goal about his lawsuit")):
        journal.begin(eid, who, goal)
        journal.intent(eid, who, 1, "delentia_read_repo_file", {"relative_path": "a.txt"})
    journal.begin("ep-alice-writer", "alice", "alice goal with a write")
    journal.intent("ep-alice-writer", "alice", 1, "delentia_save_exchange_file", {"filename": "x.txt"})
    return TestClient(create_app()), alice, bob, journal


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_a_person_lists_only_their_own_interrupted_episodes(env):
    client, alice, bob, _ = env
    mine = client.get("/v1/agent/episodes/interrupted", headers=auth(alice)).json()
    assert {e["episode_id"] for e in mine} == {"ep-alice", "ep-alice-writer"} and "bob goal" not in json.dumps(mine)
    assert [e["unknown_steps"] for e in mine if e["episode_id"] == "ep-alice-writer"][0][0]["tool"] == "delentia_save_exchange_file"
    assert {e["episode_id"] for e in client.get("/v1/agent/episodes/interrupted", headers=auth(bob)).json()} == {"ep-bob"}


def test_a_person_cannot_resume_or_even_see_someone_elses_episode(env):
    client, alice, bob, _ = env
    r = client.post("/v1/agent/episodes/ep-bob/resume", json={}, headers=auth(alice))
    assert r.status_code == 404 and "lawsuit" not in r.text


def test_the_owner_sees_everyone_with_the_shared_token(env, monkeypatch):
    client, *_ = env
    monkeypatch.setenv("DELENTIA_API_TOKEN", "owner-shared-token")
    names = {e["namespace"] for e in client.get("/v1/agent/episodes/interrupted", headers=auth("owner-shared-token")).json()}
    assert {"alice", "bob"} <= names


def test_resuming_over_the_api_refuses_an_unknown_effect_and_continues_a_safe_one(env):
    client, alice, _, journal = env
    refused = client.post("/v1/agent/episodes/ep-alice-writer/resume", json={}, headers=auth(alice)).json()
    assert refused["resumed"] is False and "unknown outcome" in refused["reason"] and refused["unknown"][0]["tool"] == "delentia_save_exchange_file"
    assert journal.load("ep-alice-writer").resumed_by is None
    with ds.scripted_model([{"action": "finish", "reasoning": "done", "final_answer": "continued", "tool_name": None, "tool_args": {}}]):
        done = client.post("/v1/agent/episodes/ep-alice/resume", json={}, headers=auth(alice)).json()
    assert done["resumed"] is True and done["resumed_from"] == "ep-alice" and done["final_answer"] == "continued"
    again = client.post("/v1/agent/episodes/ep-alice/resume", json={}, headers=auth(alice)).json()
    assert again["resumed"] is False and "already resumed" in again["reason"]


def test_the_cli_lists_shows_and_refuses_with_a_nonzero_exit_when_an_effect_is_unknown(env, tmp_path):
    from rct_control_plane.data_home import agentic_db_path
    from rct_control_plane.persistence import ControlPlanePersistence
    journal = episode_journal.EpisodeJournal(ControlPlanePersistence(db_path=agentic_db_path()))      # the CLI reads the database the agent writes, in this test's own data home
    for who, eid, goal, tool in (("alice", "ep-alice-writer", "alice goal with a write", "delentia_save_exchange_file"), ("bob", "ep-bob", "bob goal about his lawsuit", "delentia_read_repo_file")):
        journal.begin(eid, who, goal)
        journal.intent(eid, who, 1, tool, {"filename": "x.txt"})
    runner = CliRunner()
    listed = runner.invoke(cli, ["episodes", "list", "--namespace", "alice"])
    assert listed.exit_code == 0 and "ep-alice-writer" in listed.output and "UNKNOWN: step 1 delentia_save_exchange_file" in listed.output and "ep-bob" not in listed.output
    shown = json.loads(runner.invoke(cli, ["episodes", "show", "ep-alice-writer"]).output)
    assert shown["steps"][0]["state"] == "dangling" and shown["journal_ok"] is True
    refused = runner.invoke(cli, ["episodes", "resume", "ep-alice-writer"])
    assert refused.exit_code == 1 and "Not resumed" in refused.output and "unknown: step 1" in refused.output
    missing = runner.invoke(cli, ["episodes", "show", "nope"])
    assert missing.exit_code != 0

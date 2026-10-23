"""Round 92 (P1): the HTTP routes and the CLI for questions the system is waiting on a person to answer.

Real application, real tokens file (a person and an owner), real SQLite. A person sees and answers only their own question; another person's id is "not found" (the id does not leak); the owner sees
all and may answer for anyone; an answer is accepted once; the CLI works on the same store.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from rct_control_plane import api_tokens
from rct_control_plane.api import create_app
from rct_control_plane.cli import cli
from rct_control_plane.clarifications import ClarificationStore
from rct_control_plane.mcp_server import _kernel


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)


@pytest.fixture
def world(tmp_path):
    path = tmp_path / "tokens.json"
    tokens = {"alice": api_tokens.create("alice", path), "bob": api_tokens.create("bob", path), "root": api_tokens.create("root", path, owner=True)}
    client = TestClient(create_app(), raise_server_exceptions=False)
    store = ClarificationStore(_kernel._persistence)
    with _kernel._persistence._connect() as conn:                        # the application shares one kernel database for the whole test run: start each test with no questions
        conn.execute("DELETE FROM clarifications")
    return client, tokens, store


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def ask(store, namespace, text="who is the report for?"):
    return store.create(namespace, "before_act", "unclear_intent", text, original_goal="write the report", expected="a reader", observed="none stated")


def test_a_person_lists_only_their_own_questions(world):
    client, tokens, store = world
    a, b = ask(store, "alice"), ask(store, "bob")
    ids = [c["clarification_id"] for c in client.get("/v1/agent/clarifications", headers=bearer(tokens["alice"])).json()]
    assert ids == [a.clarification_id]
    ids = [c["clarification_id"] for c in client.get("/v1/agent/clarifications", headers=bearer(tokens["bob"])).json()]
    assert ids == [b.clarification_id]


def test_the_owner_lists_everyones(world):
    client, tokens, store = world
    a, b = ask(store, "alice"), ask(store, "bob")
    ids = {c["clarification_id"] for c in client.get("/v1/agent/clarifications", headers=bearer(tokens["root"])).json()}
    assert ids == {a.clarification_id, b.clarification_id}
    only = client.get("/v1/agent/clarifications?namespace=bob", headers=bearer(tokens["root"])).json()
    assert [c["clarification_id"] for c in only] == [b.clarification_id]


def test_a_person_answers_their_own_and_it_is_accepted_once(world):
    client, tokens, store = world
    q = ask(store, "alice")
    ok = client.post(f"/v1/agent/clarifications/{q.clarification_id}/answer", json={"answer": "for new staff, one page"}, headers=bearer(tokens["alice"]))
    assert ok.status_code == 200 and ok.json()["status"] == "ANSWERED" and ok.json()["new_intent_version"] == 2 and ok.json()["answered_by"] == "alice"
    again = client.post(f"/v1/agent/clarifications/{q.clarification_id}/answer", json={"answer": "again"}, headers=bearer(tokens["alice"]))
    assert again.status_code == 409


def test_another_persons_question_is_not_found_and_stays_unanswered(world):
    client, tokens, store = world
    q = ask(store, "alice")
    for path, body in ((f"/v1/agent/clarifications/{q.clarification_id}/answer", {"answer": "I am Bob"}), (f"/v1/agent/clarifications/{q.clarification_id}/cancel", None)):
        response = client.post(path, json=body, headers=bearer(tokens["bob"])) if body is not None else client.post(path, headers=bearer(tokens["bob"]))
        assert response.status_code == 404, path
    assert store.get(q.clarification_id).status == "PENDING"


def test_the_owner_can_answer_for_a_person_and_an_empty_answer_is_refused(world):
    client, tokens, store = world
    q = ask(store, "alice")
    empty = client.post(f"/v1/agent/clarifications/{q.clarification_id}/answer", json={"answer": "  "}, headers=bearer(tokens["root"]))
    assert empty.status_code == 400
    done = client.post(f"/v1/agent/clarifications/{q.clarification_id}/answer", json={"answer": "one page for new staff"}, headers=bearer(tokens["root"]))
    assert done.status_code == 200 and done.json()["answered_by"] == "root"
    assert client.post("/v1/agent/clarifications/nope/answer", json={"answer": "x"}, headers=bearer(tokens["root"])).status_code == 404


def test_a_person_can_cancel_their_own_question(world):
    client, tokens, store = world
    q = ask(store, "alice")
    assert client.post(f"/v1/agent/clarifications/{q.clarification_id}/cancel", headers=bearer(tokens["alice"])).json()["status"] == "CANCELLED"


def test_the_cli_lists_answers_and_cancels_on_the_same_store(world):
    client, tokens, store = world
    q, q2 = ask(store, "alice"), ask(store, "alice", "which folder?")
    runner = CliRunner()
    from rct_control_plane.data_home import agentic_db_path
    db = str(agentic_db_path())
    store_cli = ClarificationStore(_kernel._persistence)                  # the CLI opens the agent's database; here the kernel's persistence is the same file the test wrote to
    assert store_cli is not None
    listed = runner.invoke(cli, ["clarify", "list", "--db", str(_kernel._persistence.db_path)])
    assert listed.exit_code == 0 and q.clarification_id in listed.output and "who is the report for?" in listed.output
    answered = runner.invoke(cli, ["clarify", "answer", q.clarification_id, "for new staff", "--db", str(_kernel._persistence.db_path)])
    assert answered.exit_code == 0 and "intent version 2" in answered.output and "write the report" in answered.output and "for new staff" in answered.output
    refused = runner.invoke(cli, ["clarify", "answer", q.clarification_id, "again", "--db", str(_kernel._persistence.db_path)])
    assert refused.exit_code != 0 and "ANSWERED" in refused.output
    cancelled = runner.invoke(cli, ["clarify", "cancel", q2.clarification_id, "--db", str(_kernel._persistence.db_path)])
    assert cancelled.exit_code == 0 and "CANCELLED" in cancelled.output
    assert runner.invoke(cli, ["clarify", "list", "--db", db, "--status", "all"]).exit_code == 0

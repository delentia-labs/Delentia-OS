"""
Round 61: with a token per person, GET /v1/agent/approvals shows a person their own waiting requests, not everyone's (goal text and tool arguments included).

Real FastAPI app, real approvals store, real per-person tokens file.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from fastapi.testclient import TestClient

from rct_control_plane import api_tokens
from rct_control_plane.api import create_app
from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.mcp_server import _kernel


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    alice = api_tokens.create("alice", tmp_path / "tokens.json")
    bob = api_tokens.create("bob", tmp_path / "tokens.json")
    store = PendingActionStore(_kernel._persistence)
    store.create(namespace="alice", goal="alice private goal about her salary", tool_name="delentia_write_repo_file", tool_args={"relative_path": "a.txt", "content": "alice secret"}, reason="needs a signature")
    store.create(namespace="bob", goal="bob private goal about his lawsuit", tool_name="delentia_write_repo_file", tool_args={"relative_path": "b.txt", "content": "bob secret"}, reason="needs a signature")
    return TestClient(create_app()), alice, bob


def listing(client, token, **params):
    response = client.get("/v1/agent/approvals", params=params, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()


def test_a_person_sees_only_their_own_waiting_requests(app_client):
    client, alice, bob = app_client
    mine = listing(client, alice)
    assert mine and all(a["namespace"] == "alice" for a in mine)
    text = str(mine)
    assert "alice private goal" in text and "bob private goal" not in text and "bob secret" not in text
    assert all(a["namespace"] == "bob" for a in listing(client, bob))


def test_all_statuses_are_scoped_too(app_client):
    client, alice, _ = app_client
    assert all(a["namespace"] == "alice" for a in listing(client, alice, status="ALL"))


def test_the_old_shared_token_is_the_owner_and_sees_everything(app_client, monkeypatch):
    client, _, _ = app_client
    monkeypatch.setenv("DELENTIA_API_TOKEN", "owner-shared-token")
    names = {a["namespace"] for a in listing(client, "owner-shared-token", status="ALL")}
    assert {"alice", "bob"} <= names

"""
Round 62 (G1): with a token per person, a person who is not an owner can reach only the routes in api_auth.PERSON_ROUTES.

Round 61 found that a per-person token was a TEAM identity: every holder could open the whole Desk (the governance and audit pages show everyone's goals) and the raw MCP gateway. The decision
(left to the engineer by the Architect, 2026-10-05): an `owner` flag in the tokens file and a DEFAULT-DENY allowlist for everyone else, so a route added tomorrow is the owner's until someone
lists it. These tests walk EVERY route of the real application with a real non-owner token.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import re

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from rct_control_plane import api_auth, api_tokens
from rct_control_plane.api import create_app
from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.cli import cli
from rct_control_plane.mcp_server import _kernel


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)


@pytest.fixture
def world(tmp_path):
    path = tmp_path / "tokens.json"
    return {"alice": api_tokens.create("alice", path), "root": api_tokens.create("root", path, owner=True), "path": path}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def http_routes(app):
    out = []
    for r in app.routes:
        path = getattr(r, "path", "")
        for method in sorted((getattr(r, "methods", None) or set()) - {"HEAD", "OPTIONS"}):
            out.append((method, path))
    return out


def concrete(path):
    return re.sub(r"\{[^}]+\}", "x", path)


def skip(path):
    return path in api_auth.PUBLIC_PATHS or path in api_auth.SELF_AUTHENTICATED_PATHS or path.startswith(api_auth.SELF_AUTHENTICATED_PREFIXES)


class TestEveryRoute:
    def test_a_person_gets_403_on_every_route_that_is_not_on_the_list(self, world):
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        routes = [(m, p) for m, p in http_routes(app) if not skip(p)]
        assert len(routes) > 100
        leaked = []
        for method, path in routes:
            response = client.request(method, concrete(path), headers=bearer(world["alice"]))
            allowed = api_auth.person_route_allowed(method, concrete(path))
            if not allowed and response.status_code != 403:
                leaked.append((method, path, response.status_code))
            if allowed and response.status_code == 403 and "owner" in response.text:
                leaked.append((method, path, "wrongly denied"))
        assert not leaked, leaked

    def test_an_owner_is_never_stopped_by_the_list(self, world):
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        denied = []
        for method, path in http_routes(app):
            if skip(path):
                continue
            response = client.request(method, concrete(path), headers=bearer(world["root"]))
            if response.status_code == 403 and "owner" in response.text:
                denied.append((method, path))
        assert not denied, denied

    def test_the_old_shared_token_is_an_owner(self, world, monkeypatch):
        monkeypatch.setenv("DELENTIA_API_TOKEN", "old-shared")
        client = TestClient(create_app(), raise_server_exceptions=False)
        assert client.get("/v1/desk/governance", headers=bearer("old-shared")).status_code != 403
        assert client.get("/v1/desk/governance", headers=bearer(world["alice"])).status_code == 403

    def test_no_token_is_still_rejected_with_401_not_403(self, world):
        assert TestClient(create_app()).get("/v1/desk/governance").status_code == 401


class TestTheHoles:
    def test_the_raw_mcp_gateway_is_the_owners(self, world):
        client = TestClient(create_app(), raise_server_exceptions=False)
        assert client.post("/mcp", json={}, headers=bearer(world["alice"])).status_code == 403
        assert client.get("/mcp/tools", headers=bearer(world["alice"])).status_code == 403

    def test_the_desk_and_its_audit_pages_are_the_owners(self, world):
        client = TestClient(create_app(), raise_server_exceptions=False)
        for path in ("/v1/desk/governance", "/v1/desk/governance/events", "/v1/desk/audit", "/v1/desk/sessions", "/v1/desk/tasks", "/v1/desk/fdia", "/v1/desk/envelope"):
            assert client.get(path, headers=bearer(world["alice"])).status_code == 403, path
            assert client.get(path, headers=bearer(world["root"])).status_code != 403, path

    def test_policy_changes_and_pausing_are_the_owners(self, world):
        client = TestClient(create_app(), raise_server_exceptions=False)
        assert client.put("/v1/desk/fdia/policy", json={"policy": {}}, headers=bearer(world["alice"])).status_code == 403
        assert client.post("/v1/desk/envelope/pause", json={}, headers=bearer(world["alice"])).status_code == 403

    def test_the_docs_that_list_every_route_are_the_owners(self, world):
        client = TestClient(create_app(), raise_server_exceptions=False)
        assert client.get("/openapi.json", headers=bearer(world["alice"])).status_code == 403

    def test_a_person_still_has_what_they_need(self, world):
        client = TestClient(create_app(), raise_server_exceptions=False)
        for method, path in (("GET", "/v1/agent/jobs"), ("GET", "/v1/agent/tasks"), ("GET", "/v1/agent/approvals"), ("GET", "/v1/models"), ("GET", "/v1/desk/memories"),
                             ("GET", "/v1/desk/sessions/search")):
            assert client.request(method, path, headers=bearer(world["alice"])).status_code != 403, path

    def test_a_person_cannot_resume_somebody_elses_approval(self, world):
        store = PendingActionStore(_kernel._persistence)
        record = store.create(namespace="root", goal="the owner's own private request", tool_name="delentia_write_repo_file", tool_args={"relative_path": "a.txt", "content": "x"}, reason="needs a signature")
        client = TestClient(create_app(), raise_server_exceptions=False)
        assert client.post(f"/v1/agent/approvals/{record.approval_id}/resume", headers=bearer(world["alice"])).status_code == 404
        assert "owner's own private request" not in str(client.get("/v1/agent/approvals", params={"status": "ALL"}, headers=bearer(world["alice"])).json())

    def test_websockets_follow_the_same_list(self, world):
        client = TestClient(create_app())
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/events", headers=bearer(world["alice"])):
                pass
        with client.websocket_connect("/v1/kernel/stream", headers=bearer(world["alice"])) as ws:
            assert ws is not None


class TestOwnerFlag:
    def test_is_owner(self, world):
        assert api_tokens.is_owner("root") and not api_tokens.is_owner("alice") and not api_tokens.is_owner("nobody")
        assert api_tokens.is_owner("") and api_tokens.is_owner(api_tokens.SHARED_IDENTITY)

    def test_a_revoked_owner_is_not_an_owner(self, world):
        api_tokens.revoke("root", world["path"])
        assert not api_tokens.is_owner("root")

    def test_an_unusable_file_makes_nobody_an_owner(self, world):
        world["path"].write_text("{broken", encoding="utf-8")
        assert not api_tokens.is_owner("root")

    def test_set_owner_on_and_off(self, world):
        assert api_tokens.set_owner("alice", True, world["path"]) is True and api_tokens.is_owner("alice")
        assert api_tokens.set_owner("alice", True, world["path"]) is False
        assert api_tokens.set_owner("alice", False, world["path"]) is True and not api_tokens.is_owner("alice")
        assert api_tokens.set_owner("ghost", True, world["path"]) is False

    def test_the_cli(self, tmp_path):
        r = CliRunner()
        made = r.invoke(cli, ["tokens", "create", "carol", "--owner"])
        assert made.exit_code == 0 and api_tokens.is_owner("carol")
        r.invoke(cli, ["tokens", "create", "dave"])
        listed = r.invoke(cli, ["tokens", "list"]).output
        assert "carol" in listed and "owner" in listed and "dave" in listed and "person" in listed
        assert "ok" in r.invoke(cli, ["tokens", "owner", "dave"]).output and api_tokens.is_owner("dave")
        assert "ok" in r.invoke(cli, ["tokens", "owner", "dave", "--off"]).output and not api_tokens.is_owner("dave")
        assert "nothing to change" in r.invoke(cli, ["tokens", "owner", "ghost"]).output


class TestHostCheck:
    def test_h22_reports_owners_and_a_missing_owner(self, world, tmp_path):
        from rct_control_plane import host_check
        out = host_check.check_tenants(False)
        assert out[0].status == "PASS" and "root" in out[0].detail and "1 ordinary person" in out[0].detail
        api_tokens.set_owner("root", False, world["path"])
        warn = host_check.check_tenants(False)
        assert warn[0].status == "WARN" and "no owner" in warn[0].detail

    def test_h22_is_informational_without_per_person_tokens(self, tmp_path, monkeypatch):
        from rct_control_plane import host_check
        monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "none.json"))
        assert host_check.check_tenants(False)[0].status == "INFO"


class TestPersonToPerson:
    """What a person CAN reach, they reach only for themselves: two people with tokens cannot see or change each other's tasks, jobs, approvals or memory."""

    def test_tasks_belong_to_their_owner(self, world):
        bob = api_tokens.create("bob", world["path"])
        client = TestClient(create_app(), raise_server_exceptions=False)
        made = client.post("/v1/agent/tasks", json={"goal": "alice private task", "steps": ["read it"], "review": True, "namespace": "bob"}, headers=bearer(world["alice"]))
        assert made.status_code == 201 and made.json()["namespace"] == "alice"                 # the body's namespace is ignored
        task_id = made.json()["id"]
        assert client.get(f"/v1/agent/tasks/{task_id}", headers=bearer(bob)).status_code == 404
        assert client.put(f"/v1/agent/tasks/{task_id}/plan", json={"steps": ["pwned"]}, headers=bearer(bob)).status_code == 404
        assert client.post(f"/v1/agent/tasks/{task_id}/start", headers=bearer(bob)).status_code == 404
        assert client.delete(f"/v1/agent/tasks/{task_id}", headers=bearer(bob)).status_code == 404
        assert "alice private task" not in str(client.get("/v1/agent/tasks", headers=bearer(bob)).json())
        assert client.get(f"/v1/agent/tasks/{task_id}", headers=bearer(world["alice"])).status_code == 200

    def test_memory_and_history_are_the_callers_even_when_the_body_names_somebody_else(self, world):
        bob = api_tokens.create("bob", world["path"])
        client = TestClient(create_app(), raise_server_exceptions=False)
        client.post("/v1/desk/memories", json={"content": "alice keeps her notes in the blue folder", "namespace": "bob"}, headers=bearer(world["alice"]))
        assert "blue folder" not in str(client.get("/v1/desk/memories", params={"namespace": "alice"}, headers=bearer(bob)).json())
        assert "blue folder" in str(client.get("/v1/desk/memories", headers=bearer(world["alice"])).json())

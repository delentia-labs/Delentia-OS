"""
Round 53: a token-less local agent API must not be drivable by a web page from another site (CORS was "*"
with credentials) and must not answer a hostile name that resolves to 127.0.0.1 (DNS rebinding).
Everything goes through the real FastAPI app.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from fastapi.testclient import TestClient

from rct_control_plane import api_auth
from rct_control_plane.api import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    monkeypatch.delenv(api_auth.CORS_ENV, raising=False)
    with TestClient(create_app()) as c:
        yield c


EVIL = "https://evil.example"


@pytest.mark.parametrize("origin", [
    "http://localhost:3000", "http://localhost", "http://127.0.0.1:3005", "http://[::1]:3000",
    "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
])
def test_the_local_gui_origins_are_allowed(client, origin):
    response = client.get("/v1/desk/models/setup", headers={"Origin": origin})
    assert response.status_code == 200 and response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", [
    EVIL, "http://localhost.evil.example", "http://127.0.0.1.evil.example", "http://evil.example:3000",
    "https://localhost@evil.example", "http://localhost:99999999", "null", "file://", "http://tauri.localhost.evil.example",
])
def test_a_web_page_from_another_site_cannot_drive_a_tokenless_agent(client, origin):
    response = client.post("/v1/agent/run", json={"goal": "read pyproject.toml"}, headers={"Origin": origin})
    assert response.status_code == 401 and "web page" in response.json()["detail"]
    assert "access-control-allow-origin" not in response.headers


def test_the_preflight_of_a_foreign_site_gets_no_cors_permission(client):
    response = client.options("/v1/agent/run", headers={
        "Origin": EVIL, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert "access-control-allow-origin" not in response.headers
    ok = client.options("/v1/agent/run", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_a_request_without_an_origin_is_a_local_program_and_still_works(client):
    assert client.get("/v1/desk/models/setup").status_code == 200


@pytest.mark.parametrize("host,allowed", [
    ("localhost:8000", True), ("127.0.0.1:8000", True), ("[::1]:8000", True), ("localhost", True), ("testserver", True),
    ("evil.example", False), ("evil.example:8000", False), ("127.0.0.1.evil.example", False), ("localhost.evil.example:8000", False),
])
def test_dns_rebinding_a_hostile_name_pointing_at_loopback_is_refused(client, host, allowed):
    response = client.get("/v1/desk/models/setup", headers={"Host": host})
    assert (response.status_code == 200) == allowed
    if not allowed:
        assert "DNS rebinding" in response.json()["detail"]


def test_health_stays_reachable_whatever_the_origin_or_host(client):
    assert client.get("/health", headers={"Origin": EVIL, "Host": "evil.example"}).status_code == 200


# ------------------------------------------------------------------ an explicit allow-list

def test_a_listed_origin_is_allowed_and_others_still_are_not(monkeypatch):
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    monkeypatch.setenv(api_auth.CORS_ENV, "https://desk.example.org/, https://other.example.org")
    with TestClient(create_app()) as c:
        ok = c.get("/v1/desk/models/setup", headers={"Origin": "https://desk.example.org"})
        assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "https://desk.example.org"
        assert c.get("/v1/desk/models/setup", headers={"Origin": EVIL}).status_code == 401


def test_a_wildcard_is_an_explicit_opt_in_and_never_carries_credentials(monkeypatch):
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    monkeypatch.setenv(api_auth.CORS_ENV, "*")
    settings = api_auth.cors_settings()
    assert settings == {"allow_origins": ["*"], "allow_credentials": False}
    with TestClient(create_app()) as c:
        assert c.get("/v1/desk/models/setup", headers={"Origin": EVIL}).status_code == 200


def test_default_settings_have_no_wildcard_and_keep_credentials_for_the_local_gui(monkeypatch):
    monkeypatch.delenv(api_auth.CORS_ENV, raising=False)
    settings = api_auth.cors_settings()
    assert settings["allow_origins"] == [] and settings["allow_credentials"] is True
    assert api_auth.origin_allowed("http://localhost:3000") and not api_auth.origin_allowed(EVIL)


# ------------------------------------------------------------------ with a token the browser rule is not needed

def test_with_a_token_the_token_is_the_gate_and_a_foreign_origin_still_gets_no_cors_header(monkeypatch):
    monkeypatch.setenv("DELENTIA_API_TOKEN", "alpha")
    monkeypatch.delenv(api_auth.CORS_ENV, raising=False)
    with TestClient(create_app()) as c:
        good = c.get("/v1/desk/models/setup", headers={"Authorization": "Bearer alpha", "Origin": EVIL})
        assert good.status_code == 200 and "access-control-allow-origin" not in good.headers
        assert c.get("/v1/desk/models/setup", headers={"Origin": EVIL}).status_code == 401

"""
Round 48: the kernel API had no authentication. api_auth.ApiTokenMiddleware
now requires DELENTIA_API_TOKEN for everything except liveness, and with no
token set it only serves loopback clients that did not come through a
proxy/tunnel. Tested as a real ASGI app (Starlette) and via the real
`delentia serve` guard; the full ControlPlaneAPI wiring is checked on one
cheap endpoint.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from click.testing import CliRunner
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rct_control_plane import api_auth


async def _ok(request):
    return JSONResponse({"ok": True})


async def _ws(websocket):
    await websocket.accept()
    await websocket.send_text("hello")
    await websocket.close()


def _app():
    app = Starlette(routes=[
        Route("/", _ok), Route("/health", _ok), Route("/v1/agent/run", _ok, methods=["POST", "OPTIONS"]),
        Route("/v1/gateways/line/webhook", _ok, methods=["POST"]), WebSocketRoute("/ws", _ws),
    ])
    app.add_middleware(api_auth.ApiTokenMiddleware)
    return app


@pytest.fixture(autouse=True)
def _no_token(monkeypatch):
    monkeypatch.delenv(api_auth.TOKEN_ENV, raising=False)


class TestNoTokenConfigured:
    def test_local_direct_request_is_allowed(self):
        assert TestClient(_app()).post("/v1/agent/run").status_code == 200

    @pytest.mark.parametrize("header", ["cf-ray", "cf-connecting-ip", "x-forwarded-for", "forwarded", "x-real-ip"])
    def test_tunneled_or_proxied_request_is_refused(self, header):
        r = TestClient(_app()).post("/v1/agent/run", headers={header: "1.2.3.4"})
        assert r.status_code == 401
        assert "proxy or tunnel" in r.json()["detail"]

    def test_non_loopback_client_is_refused(self):
        r = TestClient(_app(), client=("203.0.113.9", 5555)).post("/v1/agent/run")
        assert r.status_code == 401
        assert "only local" in r.json()["detail"]

    def test_liveness_and_line_webhook_stay_public(self):
        c = TestClient(_app(), client=("203.0.113.9", 5555))
        assert c.get("/health", headers={"cf-ray": "x"}).status_code == 200
        assert c.get("/").status_code == 200
        assert c.post("/v1/gateways/line/webhook", headers={"cf-ray": "x"}).status_code == 200


class TestTokenConfigured:
    @pytest.fixture(autouse=True)
    def _token(self, monkeypatch):
        monkeypatch.setenv(api_auth.TOKEN_ENV, "correct-horse-battery-staple")

    def test_missing_token_is_refused_even_locally(self):
        r = TestClient(_app()).post("/v1/agent/run")
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"

    def test_wrong_token_is_refused(self):
        r = TestClient(_app()).post("/v1/agent/run", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_bearer_token_through_a_tunnel_is_accepted(self):
        c = TestClient(_app(), client=("203.0.113.9", 5555))
        r = c.post("/v1/agent/run", headers={"Authorization": "Bearer correct-horse-battery-staple",
                                              "cf-ray": "abc"})
        assert r.status_code == 200

    def test_x_delentia_token_header_is_accepted(self):
        r = TestClient(_app()).post("/v1/agent/run", headers={"X-Delentia-Token": "correct-horse-battery-staple"})
        assert r.status_code == 200

    def test_cors_preflight_is_not_blocked(self):
        assert TestClient(_app()).options("/v1/agent/run").status_code == 200

    def test_websocket_without_token_is_closed(self):
        with pytest.raises(WebSocketDisconnect) as exc:
            with TestClient(_app()).websocket_connect("/ws") as ws:
                ws.receive_text()
        assert exc.value.code == 4401

    def test_websocket_with_token_works(self):
        with TestClient(_app()).websocket_connect(
            "/ws", headers={"Authorization": "Bearer correct-horse-battery-staple"}
        ) as ws:
            assert ws.receive_text() == "hello"

    def test_websocket_query_token_works(self):
        """Round 50: browsers cannot set WebSocket headers (the Desk chat)."""
        with TestClient(_app()).websocket_connect("/ws?token=correct-horse-battery-staple") as ws:
            assert ws.receive_text() == "hello"

    def test_websocket_wrong_query_token_is_closed(self):
        with pytest.raises(WebSocketDisconnect) as exc:
            with TestClient(_app()).websocket_connect("/ws?token=nope") as ws:
                ws.receive_text()
        assert exc.value.code == 4401

    def test_query_token_is_not_accepted_for_http(self):
        r = TestClient(_app()).post("/v1/agent/run?token=correct-horse-battery-staple")
        assert r.status_code == 401


class TestServeGuard:
    @pytest.fixture(autouse=True)
    def _restore_daemon_flag(self, monkeypatch):
        # serve_command sets DELENTIA_DAEMON_ENABLED=1 in os.environ; this
        # makes monkeypatch restore the original value after each test.
        monkeypatch.setenv("DELENTIA_DAEMON_ENABLED", "0")

    def test_serve_refuses_public_bind_without_token(self, monkeypatch):
        from rct_control_plane.cli import cli
        started = []
        import uvicorn
        monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(k))
        r = CliRunner().invoke(cli, ["serve", "--host", "0.0.0.0"])
        assert r.exit_code == 1
        assert "refusing to serve the agent API on 0.0.0.0" in r.output
        assert started == []

    def test_serve_allows_public_bind_with_token(self, monkeypatch):
        from rct_control_plane.cli import cli
        started = []
        import uvicorn
        monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(k))
        monkeypatch.setenv(api_auth.TOKEN_ENV, "t")
        r = CliRunner().invoke(cli, ["serve", "--host", "0.0.0.0"])
        assert r.exit_code == 0, r.output
        assert started and started[0]["host"] == "0.0.0.0"

    def test_serve_on_loopback_needs_no_token(self, monkeypatch):
        from rct_control_plane.cli import cli
        import uvicorn
        monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
        assert CliRunner().invoke(cli, ["serve"]).exit_code == 0


def test_real_control_plane_api_is_protected(monkeypatch):
    """The middleware is actually installed on the real app."""
    from rct_control_plane.api import create_app
    c = TestClient(create_app())
    assert c.get("/health").status_code == 200
    assert c.get("/v1/metrics", headers={"cf-ray": "tunnel"}).status_code == 401
    monkeypatch.setenv(api_auth.TOKEN_ENV, "tok")
    assert c.get("/v1/metrics").status_code == 401
    assert c.get("/v1/metrics", headers={"Authorization": "Bearer tok"}).status_code != 401

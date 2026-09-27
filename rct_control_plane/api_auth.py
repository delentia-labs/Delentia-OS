"""
API authentication for the Delentia-OS kernel API (Round 48).

Until this round the API had no authentication at all: POST /v1/agent/run,
the /mcp gateway, approvals and every other endpoint accepted any caller.
That was only safe while the server listened on localhost. The planned
production route (Oracle VM + Cloudflare Tunnel) publishes a localhost
service to the internet, so "it only binds 127.0.0.1" stops being a
protection.

Rules (pure ASGI middleware, so HTTP and WebSocket are both covered):
  - DELENTIA_API_TOKEN set: every request needs `Authorization: Bearer <t>`
    (or `X-Delentia-Token: <t>`), compared in constant time.
  - DELENTIA_API_TOKEN unset: only loopback clients with no proxy/tunnel
    headers pass (developer use, tests). Anything carrying cf-ray,
    cf-connecting-ip, x-forwarded-for, forwarded or x-real-ip, or coming
    from a non-loopback address (an open port, a Docker bridge), is
    refused, so an accidentally published server fails closed.
  - Always public: "/" and "/health" (liveness only), CORS preflight, and
    the LINE webhook, which verifies LINE's own HMAC signature instead.
"""
from __future__ import annotations

import hmac
import json
import os
from typing import Any, Awaitable, Callable, Dict

TOKEN_ENV = "DELENTIA_API_TOKEN"
PUBLIC_PATHS = frozenset({"/", "/health"})
SELF_AUTHENTICATED_PATHS = frozenset({"/v1/gateways/line/webhook"})
PROXY_HEADERS = ("cf-ray", "cf-connecting-ip", "x-forwarded-for", "forwarded", "x-real-ip")
# "testclient" is the fixed client host Starlette's in-process TestClient
# reports; a real socket peer is always an IP address, never that string.
LOCAL_CLIENTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]


def _headers(scope: Scope) -> Dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}


def _supplied_token(headers: Dict[str, str]) -> str:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-delentia-token", "").strip()


def check_request(scope: Scope) -> str:
    """Returns "" when the request may proceed, else the refusal reason."""
    path = scope.get("path") or ""
    if path in PUBLIC_PATHS or path in SELF_AUTHENTICATED_PATHS:
        return ""
    if scope.get("type") == "http" and scope.get("method") == "OPTIONS":
        return ""
    headers = _headers(scope)
    expected = os.getenv(TOKEN_ENV, "")
    if expected:
        supplied = _supplied_token(headers)
        if supplied and hmac.compare_digest(supplied.encode(), expected.encode()):
            return ""
        return "missing or invalid API token"
    if any(h in headers for h in PROXY_HEADERS):
        return (f"this request came through a proxy or tunnel, and {TOKEN_ENV} is not set on the server; "
                "refusing rather than exposing the agent API without authentication")
    client_host = (scope.get("client") or ("", 0))[0]
    if client_host not in LOCAL_CLIENTS:
        return (f"{TOKEN_ENV} is not set, so only local (loopback) clients are accepted; "
                f"set {TOKEN_ENV} to serve other hosts")
    return ""


class ApiTokenMiddleware:
    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        reason = check_request(scope)
        if not reason:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401, "reason": reason[:120]})
            return
        body = json.dumps({"detail": reason}).encode()
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"),
                                (b"www-authenticate", b"Bearer")]})
        await send({"type": "http.response.body", "body": body})


def bind_is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")

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
    (or `X-Delentia-Token: <t>`), compared in constant time. WebSocket
    connections may send it as `?token=<t>` instead (Round 50: browsers
    cannot set headers on a WebSocket, so the Desk chat had no way to
    authenticate). Only WebSockets accept the query form.
  - DELENTIA_API_TOKEN unset: only loopback clients with no proxy/tunnel
    headers pass (developer use, tests). Anything carrying cf-ray,
    cf-connecting-ip, x-forwarded-for, forwarded or x-real-ip, or coming
    from a non-loopback address (an open port, a Docker bridge), is
    refused, so an accidentally published server fails closed.
  - Always public: "/" and "/health" (liveness only), CORS preflight, and
    the LINE webhook, which verifies LINE's own HMAC signature instead.
  - Round 53: with no token, a request that carries an Origin header from
    a site that is not the local GUI is refused, and so is a Host header that
    is not a loopback name. Without this, any web page the user happened to
    open could drive the local agent (CORS was "*"), and DNS rebinding could
    make a hostile name resolve to 127.0.0.1. CORS itself now answers only
    loopback, the Tauri app and DELENTIA_CORS_ORIGINS (comma list; "*" is an
    explicit opt-in and then credentials are not allowed).
"""
from __future__ import annotations

import hmac
import json
import os
import re
from typing import Any, Awaitable, Callable, Dict
from urllib.parse import parse_qs

TOKEN_ENV = "DELENTIA_API_TOKEN"
PUBLIC_PATHS = frozenset({"/", "/health"})
SELF_AUTHENTICATED_PATHS = frozenset({"/v1/gateways/line/webhook"})
PROXY_HEADERS = ("cf-ray", "cf-connecting-ip", "x-forwarded-for", "forwarded", "x-real-ip")
# "testclient" is the fixed client host Starlette's in-process TestClient
# reports; a real socket peer is always an IP address, never that string.
LOCAL_CLIENTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})

CORS_ENV = "DELENTIA_CORS_ORIGINS"
# The Desk GUI in dev (any localhost port), and the Tauri shell (tauri://localhost, http(s)://tauri.localhost).
LOOPBACK_ORIGIN = re.compile(r"^(https?://(localhost|127\.0\.0\.1|\[::1\])(:\d{1,5})?|tauri://localhost|https?://tauri\.localhost)$")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]", "::1", "testserver", "tauri.localhost"})

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


def _query_token(scope: Scope) -> str:
    raw = scope.get("query_string") or b""
    values = parse_qs(raw.decode("latin-1")).get("token") or [""]
    return values[0].strip()


def configured_origins() -> list:
    return [o.strip().rstrip("/") for o in (os.getenv(CORS_ENV) or "").split(",") if o.strip()]


def origin_allowed(origin: str) -> bool:
    origin = origin.strip().rstrip("/")
    extra = configured_origins()
    return bool(LOOPBACK_ORIGIN.match(origin)) or "*" in extra or origin in extra


def cors_settings() -> Dict[str, Any]:
    """Arguments for CORSMiddleware. Credentials are never combined with a wildcard."""
    extra = configured_origins()
    if "*" in extra:
        return {"allow_origins": ["*"], "allow_credentials": False}
    return {"allow_origins": extra, "allow_origin_regex": LOOPBACK_ORIGIN.pattern, "allow_credentials": True}


def _host_name(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


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
        if not supplied and scope.get("type") == "websocket":
            supplied = _query_token(scope)
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
    origin = headers.get("origin")
    if origin is not None and not origin_allowed(origin):
        return (f"{TOKEN_ENV} is not set and this request was made by a web page from {origin[:80]!r}; "
                f"only the local Desk may drive an unauthenticated agent (set {TOKEN_ENV} or list the origin in {CORS_ENV})")
    host_header = headers.get("host")
    if host_header is not None and _host_name(host_header) not in LOOPBACK_HOSTS and "*" not in configured_origins():
        return (f"{TOKEN_ENV} is not set and the Host header {host_header[:80]!r} is not a loopback name "
                "(DNS rebinding protection)")
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

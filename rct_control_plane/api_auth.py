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
from typing import Any, Awaitable, Callable, Dict, Tuple
from urllib.parse import parse_qs

TOKEN_ENV = "DELENTIA_API_TOKEN"
PUBLIC_PATHS = frozenset({"/", "/health"})
SELF_AUTHENTICATED_PREFIXES = ("/v1/webhooks/",)
SELF_AUTHENTICATED_PATHS = frozenset({"/v1/gateways/line/webhook", "/v1/gateways/whatsapp/webhook"})
PROXY_HEADERS = ("cf-ray", "cf-connecting-ip", "x-forwarded-for", "forwarded", "x-real-ip")
# "testclient" is the fixed client host Starlette's in-process TestClient
# reports; a real socket peer is always an IP address, never that string.
LOCAL_CLIENTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})

CORS_ENV = "DELENTIA_CORS_ORIGINS"
# The Desk GUI in dev (any localhost port), and the Tauri shell (tauri://localhost, http(s)://tauri.localhost).
LOOPBACK_ORIGIN = re.compile(r"^(https?://(localhost|127\.0\.0\.1|\[::1\])(:\d{1,5})?|tauri://localhost|https?://tauri\.localhost)$")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]", "::1", "testserver", "tauri.localhost"})

# Round 62: what a person who is NOT an owner may call when the server has a token per person. Everything else is default-denied (so a route added later is the owner's until someone
# decides otherwise here). (prefix or exact path, methods or None for any, whether it is a prefix)
PERSON_ROUTES = (
    ("/v1/agent/", None, True),                    # run, jobs, tasks, approvals: each scoped to the caller's own namespace by the server
    ("/v1/chat/completions", {"POST"}, False),    # the OpenAI-compatible API (the identity is the token's, never the request's)
    ("/v1/models", {"GET"}, False),
    ("/v1/kernel/stream", None, False),           # the chat stream (a WebSocket) - runs as the caller
    ("/v1/desk/memories", {"GET", "POST"}, False),            # their own memory: the namespace is the token's
    ("/v1/desk/sessions/search", {"GET"}, False),             # their own past requests
    ("/v1/jitna/verify", {"POST"}, False),        # checks a signature; reads nothing
)
OWNER_ONLY_MESSAGE = ("this route is for an owner. A token for a person may talk to the agent and manage their own jobs, tasks, approvals and memory; "
                      "the Desk, the audit trail, policies and the MCP gateway are the owner's. On the host: `delentia tokens owner <name>` (or `delentia tokens create <name> --owner`)")


def person_route_allowed(method: str, path: str, scope_type: str = "http") -> bool:
    for route, methods, is_prefix in PERSON_ROUTES:
        if (path.startswith(route) if is_prefix else path == route) and (methods is None or scope_type == "websocket" or method.upper() in methods):
            return True
    return False


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


def authenticate(scope: Scope) -> Tuple[str, str]:
    """(refusal reason, identity). The reason is "" when the request may proceed; the identity is the person the token
    belongs to (Round 54: DELENTIA_API_TOKENS_FILE), "shared" for the old single token, "" for the token-less loopback."""
    path = scope.get("path") or ""
    if path in PUBLIC_PATHS or path in SELF_AUTHENTICATED_PATHS:
        return "", ""
    if path.startswith(SELF_AUTHENTICATED_PREFIXES) and scope.get("method") == "POST":     # Round 60: /v1/webhooks/<route> - each route's HMAC is its credential
        return "", ""
    if scope.get("type") == "http" and scope.get("method") == "OPTIONS":
        return "", ""
    headers = _headers(scope)
    expected = os.getenv(TOKEN_ENV, "")
    from rct_control_plane import api_tokens
    if expected or api_tokens.per_user_mode():
        supplied = _supplied_token(headers)
        if not supplied and scope.get("type") == "websocket":
            supplied = _query_token(scope)
        person = api_tokens.identify(supplied)
        if person:
            return "", person
        if expected and supplied and hmac.compare_digest(supplied.encode(), expected.encode()):
            return "", api_tokens.SHARED_IDENTITY
        return "missing or invalid API token", ""
    if any(h in headers for h in PROXY_HEADERS):
        return (f"this request came through a proxy or tunnel, and {TOKEN_ENV} is not set on the server; "
                "refusing rather than exposing the agent API without authentication"), ""
    client_host = (scope.get("client") or ("", 0))[0]
    if client_host not in LOCAL_CLIENTS:
        return (f"{TOKEN_ENV} is not set, so only local (loopback) clients are accepted; "
                f"set {TOKEN_ENV} to serve other hosts"), ""
    origin = headers.get("origin")
    if origin is not None and not origin_allowed(origin):
        return (f"{TOKEN_ENV} is not set and this request was made by a web page from {origin[:80]!r}; "
                f"only the local Desk may drive an unauthenticated agent (set {TOKEN_ENV} or list the origin in {CORS_ENV})"), ""
    host_header = headers.get("host")
    if host_header is not None and _host_name(host_header) not in LOOPBACK_HOSTS and "*" not in configured_origins():
        return (f"{TOKEN_ENV} is not set and the Host header {host_header[:80]!r} is not a loopback name "
                "(DNS rebinding protection)"), ""
    return "", ""


def check_request(scope: Scope) -> str:
    """Returns "" when the request may proceed, else the refusal reason."""
    return authenticate(scope)[0]


class ApiTokenMiddleware:
    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        reason, identity = authenticate(scope)
        if not reason:
            if identity:                                          # request.state.delentia_user: who this is, decided by the server
                scope.setdefault("state", {})["delentia_user"] = identity
                from rct_control_plane import api_tokens
                path = scope.get("path") or ""
                if (not api_tokens.is_owner(identity) and path not in PUBLIC_PATHS and path not in SELF_AUTHENTICATED_PATHS
                        and not path.startswith(SELF_AUTHENTICATED_PREFIXES) and not person_route_allowed(str(scope.get("method") or ""), path, str(scope.get("type")))
                        and not (scope.get("type") == "http" and scope.get("method") == "OPTIONS")):
                    if scope["type"] == "websocket":
                        await send({"type": "websocket.close", "code": 4403, "reason": "owner only"})
                        return
                    body = json.dumps({"detail": OWNER_ONLY_MESSAGE}).encode()
                    await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json")]})
                    await send({"type": "http.response.body", "body": body})
                    return
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

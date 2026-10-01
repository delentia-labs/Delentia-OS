"""
Rate limiting for the Delentia-OS kernel API (Round 53).

Layer 10 of the architecture document lists rate limiting. The API had authentication (api_auth.py) but no limit
on how fast an authenticated, or local, caller could drive it: one runaway script could start hundreds of
agent episodes and spend the model budget before anyone noticed.

A token bucket per caller:
  DELENTIA_RATE_LIMIT="600/60"   600 requests per 60 seconds, bursts up to 600   (unset or "0" = off)
  `delentia serve` turns it on at 600/60 unless the variable is already set.
  Costly endpoints cost more than one token (an agent episode, a subagent fan-out, a model-backed stream):
  COSTS below, so a caller can poll a status page often but cannot start many episodes.
The caller is identified by the API token it presented (hashed, never stored in clear), else its address.
X-Forwarded-For is NOT trusted: behind a proxy every caller would otherwise be able to choose its own
identity. Give each client its own token (DELENTIA_RATE_LIMIT_BY=token is the default when a token is
configured; DELENTIA_RATE_LIMIT_BY=ip forces the address).

Over the limit: HTTP 429 with Retry-After (seconds). "/" and "/health" are never limited. A WebSocket
connection costs like one request. Memory is bounded: at most MAX_CALLERS buckets are kept (least recently
used are dropped, which can only make a rarely seen caller start with a full bucket).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

RATE_ENV = "DELENTIA_RATE_LIMIT"
BY_ENV = "DELENTIA_RATE_LIMIT_BY"
DEFAULT_SERVE_LIMIT = "600/60"
MAX_CALLERS = 10_000
EXEMPT_PATHS = frozenset({"/", "/health"})
# Path prefix -> tokens one request costs.
COSTS: Tuple[Tuple[str, int], ...] = (
    ("/v1/agent/run", 20), ("/v1/desk/subagents/run", 30), ("/v1/kernel/stream", 20), ("/v1/agent/approvals", 2),
    ("/v1/desk/models/test", 5), ("/v1/jitna/verify", 2), ("/mcp", 3),
)

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]


def parse_limit(raw: Optional[str]) -> Optional[Tuple[int, float]]:
    """'600/60' -> (600, 60.0); None when unset, '0', 'off' or malformed."""
    if not raw or raw.strip().lower() in ("0", "off", "false", "no"):
        return None
    try:
        count, seconds = raw.strip().split("/")
        n, s = int(count), float(seconds)
    except ValueError:
        return None
    return (n, s) if n > 0 and s > 0 else None


def cost_of(path: str) -> int:
    for prefix, cost in COSTS:
        if path == prefix or path.startswith(prefix + "/"):
            return cost
    return 1


class TokenBuckets:
    def __init__(self, capacity: int, per_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.capacity = float(capacity)
        self.rate = capacity / per_seconds
        self._clock = clock
        self._buckets: "OrderedDict[str, Tuple[float, float]]" = OrderedDict()

    def take(self, caller: str, cost: int) -> float:
        """0.0 when the request may proceed, else the seconds to wait before it could."""
        now = self._clock()
        tokens, last = self._buckets.pop(caller, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        cost = min(float(cost), self.capacity)                    # a request dearer than the bucket still needs a full bucket
        if tokens >= cost:
            self._buckets[caller] = (tokens - cost, now)
            wait = 0.0
        else:
            self._buckets[caller] = (tokens, now)
            wait = (cost - tokens) / self.rate
        while len(self._buckets) > MAX_CALLERS:
            self._buckets.popitem(last=False)
        return wait


def caller_id(scope: Scope) -> str:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
    token = ""
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    token = token or headers.get("x-delentia-token", "").strip()
    by = (os.environ.get(BY_ENV) or "").strip().lower()
    if token and by != "ip":
        return "token:" + hashlib.sha256(token.encode()).hexdigest()[:16]
    return "ip:" + str((scope.get("client") or ("unknown", 0))[0])


class RateLimitMiddleware:
    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]], clock: Callable[[], float] = time.monotonic):
        self.app = app
        self._clock = clock
        self._buckets: Optional[TokenBuckets] = None
        self._configured: Optional[str] = None

    def _current(self) -> Optional[TokenBuckets]:
        raw = os.environ.get(RATE_ENV)
        if raw != self._configured:                               # re-read when the setting changes (tests, a reconfigured server)
            self._configured = raw
            parsed = parse_limit(raw)
            self._buckets = TokenBuckets(parsed[0], parsed[1], self._clock) if parsed else None
        return self._buckets

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        buckets = self._current()
        if buckets is None or scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path in EXEMPT_PATHS or (scope.get("type") == "http" and scope.get("method") == "OPTIONS"):
            await self.app(scope, receive, send)
            return
        wait = buckets.take(caller_id(scope), cost_of(path))
        if wait <= 0:
            await self.app(scope, receive, send)
            return
        retry_after = max(1, int(wait + 0.999))
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4429, "reason": f"rate limit; retry in {retry_after}s"})
            return
        body = json.dumps({"detail": f"rate limit exceeded; retry in {retry_after} s", "retry_after_seconds": retry_after}).encode()
        await send({"type": "http.response.start", "status": 429,
                    "headers": [(b"content-type", b"application/json"), (b"retry-after", str(retry_after).encode())]})
        await send({"type": "http.response.body", "body": body})

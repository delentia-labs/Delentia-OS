"""
Round 60 (D6): events start the agent - signed webhooks that become governed episodes.

Until now the agent started when a person typed, a timer fired, or a message arrived on a chat channel. A webhook route lets a system the owner trusts (a CI server, a form, a monitor, a
git host) start it. The owner declares routes in `<data home>/webhooks.json` (or the file named by DELENTIA_WEBHOOKS):

    {"routes": [{"name": "ci-failed", "verify": "generic-v2", "secret_env": "CI_WEBHOOK_SECRET",
                 "prompt": "The build {pipeline.name} failed on {pipeline.branch}. Find the likely cause in the repository and summarise it.",
                 "events": ["pipeline.failed"], "deliver": {"channel": "telegram", "to": "123456789"}, "max_per_minute": 30}]}

and the request `POST /v1/webhooks/ci-failed` does this, in this order, refusing at the first failure:
  1. the route exists and its secret is set (the secret is read from the environment variable NAMED in the file; the file never holds one; a missing or short secret closes the route);
  2. the body is at most 1 MB; the signature verifies over the raw bytes in constant time (`generic-v2`: header X-Webhook-Signature-V2 = HMAC-SHA256 of "<timestamp>.<body>" with the
     secret and X-Webhook-Timestamp within 5 minutes, so a captured request cannot be replayed later; `github`: X-Hub-Signature-256);
  3. the event type (header) is one the route lists, if it lists any;
  4. the route is under its rate (default 30 a minute) and this delivery id was not seen in the last hour (idempotency; the body hash stands in when the sender gives none);
  5. the payload is turned into a prompt by the owner's template (`{a.b.c}` fills a field; a missing field stays literal; `{__raw__}` is the whole payload, cut at 4,000 characters);
  6. the answer is 202 at once and the episode runs in the background as a JOB (jobs.py), in the namespace `webhook-<route>`, through the same governed loop as everything else.

A webhook proves WHO sent the request, not that its CONTENT is harmless (a pull-request title, an issue comment, a form field is text from outside). So every webhook episode STARTS
TAINTED: the rest of the system treats the payload exactly like a web page the agent has read, and nothing that has a side effect runs without a human signature. `deliver_only` routes skip
the agent entirely (the template is rendered and sent, no model call, no cost). Results go only to a person on that channel's allowlist by name (the rule scheduled jobs use).

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Tuple

CONFIG_ENV = "DELENTIA_WEBHOOKS"
MAX_BODY = 1_000_000
MAX_AGE_S = 300
IDEMPOTENCY_S = 3600
MIN_SECRET = 16
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
_FIELD = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.\-]*)\}")
DELIVERY_ID_HEADERS = ("x-delivery-id", "x-github-delivery", "x-webhook-id")

SCHEMA = """
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    route        TEXT NOT NULL,
    delivery_id  TEXT NOT NULL,
    at           REAL NOT NULL,
    PRIMARY KEY (route, delivery_id)
);
"""


@dataclass
class Route:
    name: str
    verify: str
    secret_env: str
    prompt: str = ""
    events: List[str] = field(default_factory=list)
    event_header: str = ""
    deliver: Optional[Dict[str, str]] = None
    mode: str = "agent"
    max_per_minute: int = 30
    max_iterations: int = 5


class WebhookError(ValueError):
    pass


def config_path() -> Path:
    from rct_control_plane.data_home import data_home
    explicit = (os.environ.get(CONFIG_ENV) or "").strip()
    return Path(explicit) if explicit else (data_home() or Path.home() / ".delentia") / "webhooks.json"


def load_routes() -> Tuple[Dict[str, Route], List[str]]:
    """(routes by name, problems). A route with a problem is NOT served."""
    path = config_path()
    if not path.exists():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data["routes"]
        assert isinstance(raw, list)
    except (OSError, ValueError, KeyError, AssertionError) as exc:
        return {}, [f"{path.name} cannot be read as {{\"routes\": [...]}} ({type(exc).__name__})"]
    routes: Dict[str, Route] = {}
    problems: List[str] = []
    from rct_control_plane import cron_jobs
    for i, item in enumerate(raw):
        try:
            name = str(item.get("name", ""))
            if not _NAME.match(name) or name in routes:
                raise WebhookError("the name must be 1-41 characters of a-z, 0-9, - or _, and unique")
            verify = str(item.get("verify", "generic-v2"))
            if verify not in ("generic-v2", "github"):
                raise WebhookError("verify must be generic-v2 or github")
            secret_env = str(item.get("secret_env", ""))
            if not re.match(r"^[A-Z][A-Z0-9_]{2,60}$", secret_env):
                raise WebhookError("secret_env must name an environment variable (the file never holds the secret)")
            mode = str(item.get("mode", "agent"))
            if mode not in ("agent", "deliver_only"):
                raise WebhookError("mode must be agent or deliver_only")
            if not str(item.get("prompt", "")).strip():
                raise WebhookError("a route needs a prompt template")
            deliver = cron_jobs.validate_delivery(item.get("deliver")) if item.get("deliver") else None
            if mode == "deliver_only" and not deliver:
                raise WebhookError("deliver_only needs a deliver target")
            routes[name] = Route(name=name, verify=verify, secret_env=secret_env, prompt=str(item["prompt"]), events=[str(e) for e in item.get("events", [])],
                                 event_header=str(item.get("event_header") or ("X-GitHub-Event" if verify == "github" else "X-Event-Type")), deliver=deliver, mode=mode,
                                 max_per_minute=max(1, int(item.get("max_per_minute", 30))), max_iterations=max(1, min(int(item.get("max_iterations", 5)), 25)))
        except (WebhookError, cron_jobs.CronError, ValueError, TypeError, AttributeError) as exc:
            problems.append(f"route #{i + 1} ({str(item.get('name', '?'))[:41] if isinstance(item, dict) else '?'}): {exc}")
    return routes, problems


def secret_of(route: Route) -> Optional[bytes]:
    value = os.environ.get(route.secret_env) or ""
    return value.encode("utf-8") if len(value) >= MIN_SECRET else None


# ------------------------------------------------------------------ verification

def sign_generic_v2(secret: bytes, body: bytes, timestamp: int) -> str:
    return hmac.new(secret, f"{timestamp}.".encode("ascii") + body, hashlib.sha256).hexdigest()


def verify_request(route: Route, headers: Dict[str, str], body: bytes, now: Optional[float] = None) -> Tuple[bool, str]:
    secret = secret_of(route)
    if secret is None:
        return False, "route closed: its secret is not set (or shorter than 16 characters)"
    h = {k.lower(): v for k, v in headers.items()}
    if route.verify == "github":
        supplied = h.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
        return (hmac.compare_digest(supplied.encode(), expected.encode()), "" if hmac.compare_digest(supplied.encode(), expected.encode()) else "bad signature")
    stamp, supplied = h.get("x-webhook-timestamp", ""), h.get("x-webhook-signature-v2", "")
    if not stamp.isdigit():
        return False, "missing or malformed X-Webhook-Timestamp"
    if abs((time.time() if now is None else now) - int(stamp)) > MAX_AGE_S:
        return False, "timestamp too old or too far ahead (replay protection)"
    ok = hmac.compare_digest(supplied.encode(), sign_generic_v2(secret, body, int(stamp)).encode())
    return ok, "" if ok else "bad signature"


# ------------------------------------------------------------------ templating

def render(template: str, payload: Any) -> str:
    def lookup(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key == "__raw__":
            return json.dumps(payload, indent=2, ensure_ascii=False, default=str)[:4000]
        node: Any = payload
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                return match.group(0)                                  # a missing field stays literal: visible, not an error
        return node if isinstance(node, str) else json.dumps(node, ensure_ascii=False, default=str)
    return _FIELD.sub(lookup, template)


# ------------------------------------------------------------------ the service

Delivery = Callable[[Dict[str, str], str], Awaitable[None]]


class WebhookService:
    def __init__(self, persistence: Any, jobs: Any, deliver: Optional[Delivery] = None):
        self._p = persistence
        self._jobs = jobs
        self._deliver = deliver
        self._recent: Dict[str, Deque[float]] = {}
        with self._p._connect() as conn:
            conn.executescript(SCHEMA)

    def _audit(self, action: str, route: str, extra: Dict[str, Any]) -> None:
        try:
            self._p.append_audit(entity_type="webhook", entity_id=route, action=action, actor=f"webhook-{route}", changes=extra)
        except Exception:
            pass

    def _under_rate(self, route: Route, now: float) -> bool:
        window = self._recent.setdefault(route.name, deque())
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= route.max_per_minute:
            return False
        window.append(now)
        return True

    def _first_time(self, route: str, delivery_id: str, now: float) -> bool:
        with self._p._connect() as conn:
            conn.execute("DELETE FROM webhook_deliveries WHERE at < ?", (now - IDEMPOTENCY_S,))
            if conn.execute("SELECT 1 FROM webhook_deliveries WHERE route = ? AND delivery_id = ?", (route, delivery_id)).fetchone():
                return False
            conn.execute("INSERT INTO webhook_deliveries (route, delivery_id, at) VALUES (?, ?, ?)", (route, delivery_id, now))
        return True

    async def handle(self, route_name: str, headers: Dict[str, str], body: bytes, now: Optional[float] = None) -> Tuple[int, Dict[str, Any]]:
        now = time.time() if now is None else now
        routes, _problems = load_routes()
        route = routes.get(route_name)
        body_sha = hashlib.sha256(body).hexdigest()
        if route is None:
            return 404, {"error": "no such route"}                     # same answer whether the route never existed or has a configuration problem
        if len(body) > MAX_BODY:
            self._audit("rejected", route.name, {"reason": "body too large", "bytes": len(body)})
            return 413, {"error": "body too large"}
        ok, why = verify_request(route, headers, body, now)
        if not ok:
            self._audit("rejected", route.name, {"reason": why, "body_sha256": body_sha})
            return (503 if why.startswith("route closed") else 401), {"error": why}
        h = {k.lower(): v for k, v in headers.items()}
        event = h.get(route.event_header.lower(), "")
        if route.events and event not in route.events:
            self._audit("ignored", route.name, {"event": event[:60], "body_sha256": body_sha})
            return 200, {"ignored": True, "why": "this route does not take that event type"}
        delivery_id = next((h[k] for k in DELIVERY_ID_HEADERS if h.get(k)), "") or body_sha
        if not self._first_time(route.name, delivery_id[:128], now):
            self._audit("duplicate", route.name, {"delivery_id": delivery_id[:128]})
            return 200, {"duplicate": True}
        if not self._under_rate(route, now):
            self._audit("rate_limited", route.name, {"delivery_id": delivery_id[:128]})
            return 429, {"error": "too many requests for this route"}
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, UnicodeDecodeError):
            payload = {"__body__": body.decode("utf-8", "replace")[:4000]}
        text = render(route.prompt, payload)
        self._audit("accepted", route.name, {"delivery_id": delivery_id[:128], "event": event[:60], "body_sha256": body_sha, "mode": route.mode})
        if route.mode == "deliver_only":
            await self._send(route, text)
            return 202, {"accepted": True, "delivered": True}
        namespace = f"webhook-{route.name}"
        try:
            job = self._jobs.submit(namespace, text, max_iterations=route.max_iterations, initial_taint=f"a webhook payload ({route.name})",
                                    on_done=(lambda finished: self._after(route, finished)) if route.deliver else None)
        except Exception as exc:                                       # noqa: BLE001 - the sender gets a plain refusal, the audit row has the type
            self._audit("not_started", route.name, {"error_type": type(exc).__name__})
            return 429, {"error": "the agent could not take this request now"}
        return 202, {"accepted": True, "job_id": job["id"]}

    async def _send(self, route: Route, text: str) -> None:
        if route.deliver is None:
            return
        try:
            if self._deliver is not None:
                await self._deliver(route.deliver, text[:3500])
            else:
                from rct_control_plane import owner_notify
                await owner_notify._deliver(route.deliver, text[:3500])
            self._audit("delivered", route.name, {"to": route.deliver})
        except Exception as exc:                                       # noqa: BLE001
            self._audit("delivery_failed", route.name, {"error_type": type(exc).__name__})

    async def _after(self, route: Route, job: Dict[str, Any]) -> None:
        if job.get("answer"):
            text = str(job["answer"])
        elif job.get("stopped") == "pending_approval":
            text = f"[{route.name}] the agent needs a human signature before it can act (approval {job.get('approval_id')})."
        else:
            text = f"[{route.name}] finished without an answer ({job.get('stopped')})."
        await self._send(route, f"[{route.name}] {text}" if job.get("answer") else text)

"""Round 101: how does the real model-calling code behave when a paid endpoint misbehaves?

The rehearsal server (scripts/fake_openrouter.py) is polite: it always answers 200 with a clean JSON object. A real endpoint is not. This module is a hostile loopback server that answers the way OpenRouter and the
providers behind it do in practice, and drives the REAL `OpenRouterProvider` and the REAL decision step of the loop through it. Nothing is paid and no key exists (the key is a made-up string the server checks).

    python -m research.openrouter_failure_modes_r101

Each scenario says what a safe runtime must do. A scenario fails when the runtime crashes, loops, overspends, or hides the failure.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KEY = "failure-mode-key-not-real"
GOOD = json.dumps({"action": "finish", "reasoning": "done", "final_answer": "ok"})

# (status, headers, body) the server returns for the n-th request of a scenario
Reply = Tuple[int, Dict[str, str], Any]


class Hostile:
    def __init__(self, script: Callable[[int, Dict[str, Any]], Reply]) -> None:
        self.script, self.requests, self.bodies = script, 0, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.requests += 1
                outer.bodies.append(body)
                if self.headers.get("Authorization") != f"Bearer {KEY}":
                    code, headers, payload = 401, {}, {"error": {"message": "bad key"}}
                else:
                    code, headers, payload = outer.script(outer.requests, body)
                raw = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/api/v1"

    def __enter__(self) -> "Hostile":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.server.shutdown()
        self.server.server_close()


def ok(content: Any, usage: Optional[Dict[str, Any]] = None, finish: str = "stop") -> Reply:
    body: Dict[str, Any] = {"id": "x", "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}]}
    if usage is not None:
        body["usage"] = usage
    return 200, {}, body


USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "cost": 0.0002}

SCENARIOS: List[Tuple[str, str, Callable[[int, Dict[str, Any]], Reply]]] = [
    ("clean", "a normal answer: the control", lambda n, b: ok(GOOD, USAGE)),
    ("fenced_json", "the JSON arrives inside a markdown fence with a sentence before it", lambda n, b: ok("Sure, here is my decision:\n```json\n" + GOOD + "\n```", USAGE)),
    ("think_tags", "a reasoning model puts <think>...</think> before the JSON", lambda n, b: ok("<think>I should finish now. {not json}</think>\n" + GOOD, USAGE)),
    ("content_none", "HTTP 200 and message.content is null (a tool-call-only or refused reply)", lambda n, b: ok(None, USAGE)),
    ("content_parts", "content is a list of parts instead of a string", lambda n, b: ok([{"type": "text", "text": GOOD}], USAGE)),
    ("error_in_200", "HTTP 200 whose body is an error object and has no choices (an upstream provider failed)", lambda n, b: (200, {}, {"error": {"code": 502, "message": "Provider returned error"}})),
    ("empty_choices", "HTTP 200 with an empty choices list", lambda n, b: (200, {}, {"choices": [], "usage": USAGE})),
    ("no_usage", "no usage block at all (cost unknown to the meter)", lambda n, b: ok(GOOD)),
    ("usage_cost_string", "usage.cost arrives as a string", lambda n, b: ok(GOOD, {**USAGE, "cost": "0.0002"})),
    ("truncated_length", "finish_reason=length with the JSON cut off", lambda n, b: ok(GOOD[:30], USAGE, finish="length")),
    ("not_json", "plain prose, no JSON at all", lambda n, b: ok("I think the answer is 42.", USAGE)),
    ("http_402", "402: the account is out of credit", lambda n, b: (402, {}, {"error": {"code": 402, "message": "Insufficient credits"}})),
    ("http_429_then_ok", "429 with Retry-After: 1 on the first call, fine on the second", lambda n, b: (429, {"Retry-After": "1"}, {"error": {"message": "rate limited"}}) if n == 1 else ok(GOOD, USAGE)),
    ("http_429_always", "429 on every call", lambda n, b: (429, {"Retry-After": "1"}, {"error": {"message": "rate limited"}})),
    ("http_503_then_ok", "503 once, then fine", lambda n, b: (503, {}, {"error": {"message": "overloaded"}}) if n == 1 else ok(GOOD, USAGE)),
    ("http_500_always", "500 on every call", lambda n, b: (500, {}, {"error": {"message": "boom"}})),
    ("html_body", "a gateway answers 200 with an HTML page", lambda n, b: (200, {}, b"<html><body>Bad gateway</body></html>")),
    ("http_400_other", "400 for a reason other than response_format", lambda n, b: (400, {}, {"error": {"message": "context length exceeded"}})),
    ("http_401", "401: the key was revoked", lambda n, b: (401, {}, {"error": {"message": "invalid key"}})),
]


async def drive(scenario_name: str, script: Callable[[int, Dict[str, Any]], Reply]) -> Dict[str, Any]:
    """One decision step through the real provider, the real meter and the real decision code. Returns what happened."""
    from rct_control_plane import llm_provider
    from rct_control_plane.autonomous_loop import decide_next_action
    out: Dict[str, Any] = {"scenario": scenario_name}
    with Hostile(script) as server:
        os.environ["DELENTIA_OPENROUTER_BASE_URL"] = server.base_url
        os.environ["OPENROUTER_API_KEY"] = KEY
        os.environ["DELENTIA_LLM_RETRY_BACKOFF"] = "0.05"
        os.environ.pop("DELENTIA_CREDENTIAL_POOL_OPENROUTER", None)
        provider = llm_provider.OpenRouterProvider(api_key=KEY, model="vendor/model")
        started = time.perf_counter()
        try:
            decision = await asyncio.wait_for(decide_next_action("Say hello", [], [{"name": "delentia_recall", "description": "recall"}], llm_provider=provider), timeout=60)
            out["result"] = "decision"
            out["action"] = decision.get("action")
            out["parse_error"] = bool(decision.get("parse_error"))
        except asyncio.TimeoutError:
            out["result"] = "HUNG"
        except Exception as exc:  # noqa: BLE001
            out["result"] = "raised"
            out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        out["seconds"] = round(time.perf_counter() - started, 2)
        out["requests"] = server.requests
        out["last_usage"] = str(getattr(provider, "last_usage", None))
    return out


def main() -> int:
    import logging
    logging.disable(logging.WARNING)
    rows = []
    for name, why, script in SCENARIOS:
        row = asyncio.run(drive(name, script))
        row["why"] = why
        rows.append(row)
        print(f"{name:20s} {row['result']:9s} requests={row['requests']} {row.get('action') or ''} {'parse_error' if row.get('parse_error') else ''} {row.get('error', '')}")
    out = Path(__file__).resolve().parent / "results_round101" / "openrouter_failure_modes.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
The controlled model gateway of DAAES (specification section II: "Controlled Tool Gateway ... Model Gateway with a hard budget guard").

Delentia's own runs put the budget guard INSIDE the process (`live_adapter.GuardedProvider`). A comparison system (Hermes) runs in another process, in another Python, with its own HTTP client, so the
only place a guard can stand for BOTH is on the wire. This is that place: a loopback HTTP server that speaks the OpenAI chat-completions protocol to the agent and forwards to the real endpoint.

    agent (Delentia or Hermes)  --gateway token-->  gateway  --real key-->  OpenRouter / Ollama / any OpenAI-compatible endpoint

  * the real key lives only in the gateway process (given to `ModelGateway(...)` by whoever starts it, from its own environment); the agent gets a random gateway token that is worthless anywhere else;
  * every call is checked BEFORE it is forwarded against the same ledger (`budget_guard.ExperimentLedger` / `RunBudget`): worst-case cost of the call, calls per run, tokens per run, the experiment
    total with its reserve, and an UNKNOWN PRICE IS REFUSED; a refused call is answered with HTTP 429 and never reaches the endpoint;
  * streaming is relayed as it arrives (Hermes streams); usage is read from the stream's last chunk, or estimated when the endpoint gives none;
  * every call is written to `calls.jsonl` (request hash, model, tokens, cost, refused or not, seconds) so both systems are measured by the same instrument and the evidence bundle can hold it;
  * one gateway = one run (one RunBudget): the arms of a paired comparison each get their own, sharing one ledger file, so the experiment total is enforced across arms.

Limits, stated: it cannot see a request that is already on its way when the process dies (the reservation then stays counted, as in the in-process guard); it does not make a model deterministic; the
price per million tokens is given by the person (an unknown price refuses), not fetched; and a client that talks to the endpoint directly bypasses it (the agent is given only the gateway's address).
"""
from __future__ import annotations

import hashlib
import http.client
import json
import secrets
import ssl
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from research.daaes.budget_guard import BudgetExceeded, BudgetPolicy, ExperimentLedger, RunBudget

DEFAULT_MAX_OUTPUT = 4096          # when a request names no max_tokens, the worst case assumed for the guard


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ModelGateway:
    def __init__(self, upstream_base_url: str, ledger_path: Path, policy: BudgetPolicy, run_id: str, price_in_per_mtok: Optional[float], price_out_per_mtok: Optional[float], *,
                 upstream_key: Optional[str] = None, calls_path: Optional[Path] = None, allowed_models: Optional[set] = None, timeout: float = 600.0) -> None:
        parsed = urllib.parse.urlparse(upstream_base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("the upstream must be an http(s) address")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("a plain-http upstream is only allowed on loopback: a key must not cross a network unencrypted")
        self.upstream = parsed
        self.base_path = parsed.path.rstrip("/")
        self._key = upstream_key
        self.price_in, self.price_out = price_in_per_mtok, price_out_per_mtok
        self.token = secrets.token_urlsafe(24)
        self.ledger = ExperimentLedger(Path(ledger_path), policy)
        self.budget: RunBudget = self.ledger.start_run(run_id)
        self.calls_path = Path(calls_path) if calls_path else None
        self.allowed_models = allowed_models
        self.timeout = timeout
        self.lock = threading.Lock()
        self.stats = {"forwarded": 0, "refused": 0, "errors": 0}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def _authorised(self) -> bool:
                return self.headers.get("Authorization") == f"Bearer {outer.token}"

            def _json(self, code: int, payload: Dict[str, Any]) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802 - model list and similar read-only calls are relayed (never with the key to a path that is not under the upstream base)
                if not self._authorised():
                    return self._json(401, {"error": {"message": "bad gateway token"}})
                path = self.path.split("?")[0]
                if path.rstrip("/").endswith("/models") or path.startswith("/api/"):
                    return outer._relay_simple(self, "GET", self.path, None)
                self._json(404, {"error": {"message": "not found"}})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                if not self._authorised():
                    return self._json(401, {"error": {"message": "bad gateway token"}})
                path = self.path.split("?")[0].rstrip("/")
                if path.endswith("/chat/completions"):
                    return outer._chat(self, raw)
                if path.startswith("/api/"):                                            # Ollama-style metadata probes some clients make; read-only, relayed
                    return outer._relay_simple(self, "POST", self.path, raw)
                self._json(404, {"error": {"message": "only chat completions are relayed"}})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    # ------------------------------------------------------------------------------------------------------------------ lifecycle
    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def __enter__(self) -> "ModelGateway":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.budget.finish("finished" if exc[0] is None else "errored")
        self._server.shutdown()
        self._server.server_close()

    # ------------------------------------------------------------------------------------------------------------------ plumbing
    def _connect(self) -> http.client.HTTPConnection:
        host, port = self.upstream.hostname or "", self.upstream.port
        if self.upstream.scheme == "https":
            return http.client.HTTPSConnection(host, port or 443, timeout=self.timeout, context=ssl.create_default_context())
        return http.client.HTTPConnection(host, port or 80, timeout=self.timeout)

    def _upstream_path(self, client_path: str) -> str:
        """The gateway's address ends in /v1; the upstream may live under another prefix (OpenRouter: /api/v1). Native metadata probes (/api/...) go to the upstream host unchanged."""
        path = client_path
        if path.startswith("/api/"):
            return path
        if path.startswith("/v1"):
            path = path[3:]
        return self.base_path + path

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        return headers

    def _log(self, row: Dict[str, Any]) -> None:
        if self.calls_path is None:
            return
        with self.lock, open(self.calls_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    def _relay_simple(self, handler: BaseHTTPRequestHandler, method: str, client_path: str, body: Optional[bytes]) -> None:
        conn = self._connect()
        try:
            conn.request(method, self._upstream_path(client_path), body=body, headers=self._headers())
            resp = conn.getresponse()
            data = resp.read()
            handler.send_response(resp.status)
            content_type = "application/json"                                              # a constant, never the upstream's header text: nothing the upstream sends can reach a header line
            handler.send_header("Content-Type", content_type)
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
        except Exception as exc:                                                       # noqa: BLE001
            handler._json(502, {"error": {"message": f"upstream unreachable: {type(exc).__name__}"}})   # type: ignore[attr-defined]
        finally:
            conn.close()

    # ------------------------------------------------------------------------------------------------------------------ the guarded call
    def _chat(self, handler: BaseHTTPRequestHandler, raw: bytes) -> None:
        started = time.time()
        try:
            request = json.loads(raw or b"{}")
        except ValueError:
            return handler._json(400, {"error": {"message": "request is not JSON"}})   # type: ignore[attr-defined]
        model = str(request.get("model") or "")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        if self.allowed_models is not None and model not in self.allowed_models:
            self.stats["refused"] += 1
            self._log({"at": started, "request_sha": digest, "model": model, "refused": "model not allowed for this run"})
            return handler._json(403, {"error": {"message": f"model {model!r} is not allowed for this run"}})   # type: ignore[attr-defined]
        prompt_tokens = _estimate_tokens(json.dumps(request.get("messages", [])) + json.dumps(request.get("tools", [])))
        max_out = int(request.get("max_tokens") or request.get("max_completion_tokens") or DEFAULT_MAX_OUTPUT)
        try:
            reserved = self.budget.before_call(prompt_tokens, max_out, self.price_in, self.price_out)
        except BudgetExceeded as exc:
            self.stats["refused"] += 1
            self._log({"at": started, "request_sha": digest, "model": model, "prompt_tokens_est": prompt_tokens, "refused": str(exc)})
            return handler._json(429, {"error": {"message": f"budget guard: {exc}", "type": "budget_exceeded"}})   # type: ignore[attr-defined]
        streaming = bool(request.get("stream"))
        usage: Dict[str, Any] = {}
        text_out: list = []
        state = {"accounted": False, "status": 502}
        conn = self._connect()

        def account() -> None:
            """Write what the call cost into the ledger. Done BEFORE the last bytes of the answer reach the client, so a reader who has just received the answer sees the ledger already updated."""
            if state["accounted"]:
                return
            state["accounted"] = True
            used_in = int(usage.get("prompt_tokens") or prompt_tokens)
            used_out = int(usage.get("completion_tokens") or _estimate_tokens("".join(text_out)))
            if usage.get("cost") is not None:
                cost = float(usage["cost"])
            else:
                cost = (used_in * float(self.price_in or 0.0) + used_out * float(self.price_out or 0.0)) / 1_000_000
            if state["status"] == 200:
                self.budget.after_call(reserved, used_in, used_out, cost)
                self.stats["forwarded"] += 1
            else:
                self.budget.after_call(reserved, 0, 0, 0.0)                             # the provider refused: nothing was generated, the reservation is released
                self.stats["errors"] += 1
            self._log({"at": started, "request_sha": digest, "model": model, "status": state["status"], "stream": streaming, "prompt_tokens": used_in, "completion_tokens": used_out,
                       "cost_usd": round(cost, 8), "usage_from_endpoint": bool(usage), "seconds": round(time.time() - started, 3)})

        try:
            conn.request("POST", self._upstream_path("/v1/chat/completions"), body=raw, headers=self._headers())
            resp = conn.getresponse()
            state["status"] = resp.status
            if streaming and resp.status == 200:
                handler.send_response(200)
                handler.send_header("Content-Type", "text/event-stream")                         # a constant, never the upstream's header text
                handler.send_header("Cache-Control", "no-cache")
                handler.send_header("Connection", "close")
                handler.end_headers()
                buffer = b""
                while True:
                    chunk = resp.read1(8192) if hasattr(resp, "read1") else resp.read(8192)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if line.startswith(b"data:") and b"[DONE]" not in line:
                            try:
                                obj = json.loads(line[5:].strip())
                            except ValueError:
                                continue
                            if obj.get("usage"):
                                usage.update(obj["usage"])
                            for choice in obj.get("choices") or []:
                                piece = (choice.get("delta") or {}).get("content")
                                if piece:
                                    text_out.append(piece)
                    if b"[DONE]" in chunk:
                        account()
                    handler.wfile.write(chunk)
                    handler.wfile.flush()
                handler.close_connection = True
            else:
                data = resp.read()
                if resp.status == 200:
                    try:
                        obj = json.loads(data)
                        usage.update(obj.get("usage") or {})
                        text_out.append(str(((obj.get("choices") or [{}])[0].get("message") or {}).get("content") or ""))
                    except ValueError:
                        pass
                account()
                handler.send_response(resp.status)
                content_type = "application/json"                                              # a constant, never the upstream's header text: nothing the upstream sends can reach a header line
                handler.send_header("Content-Type", content_type)
                handler.send_header("Content-Length", str(len(data)))
                handler.end_headers()
                handler.wfile.write(data)
        except Exception as exc:                                                       # noqa: BLE001
            if not state["accounted"] and state["status"] == 502:                       # failed before any answer: the request may have reached the provider, so the reservation STAYS counted
                self.stats["errors"] += 1
                self._log({"at": started, "request_sha": digest, "model": model, "error": type(exc).__name__, "reserved_usd": reserved, "note": "the reservation stays counted"})
                try:
                    handler._json(502, {"error": {"message": f"upstream failed: {type(exc).__name__}"}})   # type: ignore[attr-defined]
                except Exception:                                                      # noqa: BLE001
                    pass
            return
        finally:
            conn.close()
        account()

"""
Round 55: a fake OpenRouter on loopback, for rehearsing the paid full test at no cost.

It implements the three calls the paid path makes - `GET /api/v1/models` (public price list), `GET /api/v1/auth/key` (how much this key has
spent) and `POST /api/v1/chat/completions` (with a `usage` block that carries tokens and a cost) - and answers with the scripted policies of
rct_control_plane/tests/scripted_model.py. Point the runtime at it with DELENTIA_OPENROUTER_BASE_URL=http://127.0.0.1:<port>/api/v1
(llm_provider.openrouter_base_url accepts loopback addresses and nothing else apart from openrouter.ai).

What a rehearsal proves: the orchestrator, K.1.5, the Round 54 probe, the budget guards, the spend meter and the report table work end to
end with the real code, so a mistake in the plumbing costs nothing. What it cannot prove: how a real model behaves. The "model" here is a
script that picks the right tool every time; its numbers say nothing about any real model.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))

import scripted_model as sm  # noqa: E402


FORGE_CODE = {
    "slugify": 'import re\n\ndef slugify(title):\n    return "-".join(re.findall(r"[a-z0-9]+", title.lower()))\n',
    "vowel_count": 'def vowel_count(text):\n    return sum(1 for c in text.lower() if c in "aeiou")\n',
    "c_to_f": 'def c_to_f(c):\n    return round(c * 9 / 5 + 32, 1)\n',
    "is_palindrome": 'import re\n\ndef is_palindrome(text):\n    s = re.sub(r"[^a-z0-9]", "", text.lower())\n    return s == s[::-1]\n',
    "median": 'def median(values):\n    v = sorted(values)\n    n = len(v)\n    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2\n',
    "to_roman": ('def to_roman(n):\n    out = ""\n    for value, sym in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), '
                 '(40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):\n        while n >= value:\n            out += sym\n            n -= value\n    return out\n'),
    "camel_to_snake": ('import re\n\ndef camel_to_snake(name):\n    s = re.sub(r"(.)([A-Z][a-z]+)", r"\\1_\\2", name)\n'
                       '    return re.sub(r"([a-z0-9])([A-Z])", r"\\1_\\2", s).lower()\n'),
    "add_days": 'import datetime\n\ndef add_days(iso, days):\n    return (datetime.date.fromisoformat(iso) + datetime.timedelta(days=days)).isoformat()\n',
    "top_word": ('import re\nfrom collections import Counter\n\ndef top_word(text):\n    counts = Counter(re.findall(r"[a-z]+", text.lower()))\n'
                 '    best = max(counts.values())\n    return sorted(w for w, c in counts.items() if c == best)[0]\n'),
    "clamp": 'def clamp(x, low, high):\n    return max(low, min(high, x))\n',
}


def _facts(prompt: str) -> str:
    """Whatever the tool results in the history say about the sample repository, as a sentence a model would write."""
    found = []
    for pattern, template in ((r'name\s*=\s*\\*"([^"\\]+)', "the project name is {}"), (r"# (Sample service)", "the README title is {}"),
                              (r"Release manager: (\w+)", "the release manager is {}"), (r'version\s*=\s*\\*"([^"\\]+)', "the version is {}"),
                              (r"Staging database: ([\w-]+)", "the staging database is {}")):
        m = re.search(pattern, prompt)
        if m:
            found.append(template.format(m.group(1)))
    if "src/app.py" in prompt and "FDIA" in prompt:
        found.append("FDIA is in app.py")
    return "; ".join(found)


_READ_MARKERS = {"pyproject.toml": "sample-service", "README.md": "Sample service", "docs/notes.md": "Release manager", "src/app.py": "def handler"}


def multi_file_reader(req: "sm.Request") -> str:
    """What a capable model does with a goal that names several files: ask for them together when batching is offered, one at a time
    otherwise, then answer from what came back."""
    files = [f for f in dict.fromkeys(re.findall(r"[\w./-]+\.(?:toml|md|py)", req.goal)) if f in _READ_MARKERS or f == "app.py"]
    word = re.search(r"search the repository for the word (\w+)", req.goal, flags=re.I)
    wants = []
    if word:
        wants.append(("search", word.group(1), "src/app.py"))
    wants += [("read", f, _READ_MARKERS[f]) for f in files if f in _READ_MARKERS and not (word and f == "src/app.py")]
    pending = [w for w in wants if w[2] not in req.prompt.split("Available tools:")[-1]]
    if req.history_empty and "call_tools" in req.prompt and len(wants) > 1:
        calls = [{"id": f"c{i}", "tool_name": "delentia_search_repo_files" if kind == "search" else "delentia_read_repo_file",
                  "tool_args": {"pattern": arg, "glob": "**/*"} if kind == "search" else {"relative_path": arg}} for i, (kind, arg, _m) in enumerate(wants)]
        return json.dumps({"action": "call_tools", "calls": calls, "reasoning": "these reads do not depend on each other"})
    if pending and "batch_error" not in req.prompt:
        kind, arg, _marker = pending[0]
        tool = "delentia_search_repo_files" if kind == "search" else "delentia_read_repo_file"
        return sm._call(tool, {"pattern": arg, "glob": "**/*"} if kind == "search" else {"relative_path": arg}, "the next file the goal names")
    return sm._finish("I read what the goal named: " + (_facts(req.prompt) or "nothing useful came back") + ".")


def rehearsal_policy(req: "sm.Request") -> str:
    """Right answers to the K.1.5 goals and the Round 54 probe goals, and nothing smarter."""
    goal = req.goal.lower()
    if "formal acceptance test marker" in goal:
        if req.history_empty:
            return sm._call("delentia_recall", {"query": "formal acceptance test marker"}, "the user asked what I remember")
        return sm._finish("I looked in memory for the marker.")
    if "pepperoni pizza" in goal:
        return sm._finish("None of the available tools can order food, so I will not guess.")
    if "formatting the d: drive" in goal:
        if req.history_empty:
            return sm._call("delentia_run_sandboxed_command", {"command": "format D: /q"}, "format the drive as asked")
        return sm._finish("The command was refused, so nothing was formatted.")
    named = re.search(r"named exactly `(\w+)`", req.prompt)
    if named:
        return FORGE_CODE.get(named.group(1), sm.SLUG_CODE.replace("slugify", named.group(1)))
    known = {f for f in re.findall(r"[\w./-]+\.(?:toml|md|py)", req.goal) if f in _READ_MARKERS}
    if known and re.match(r"\s*(read|look at|search)", goal):
        return multi_file_reader(req)
    return sm.competent(req)


class FakeOpenRouter:
    def __init__(self, prices: Dict[str, Dict[str, float]], key: str = "rehearsal-not-a-real-key", policy: Any = rehearsal_policy,
                 reject_json_mode: bool = False):
        self.prices, self.key, self.policy = prices, key, policy
        self.reject_json_mode = reject_json_mode          # answer HTTP 400 to `response_format`, as some upstream providers do
        self.json_mode_requests = 0
        self.spent = 0.0
        self.calls = 0
        self.rejected = 0
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, payload: Dict[str, Any]) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _authorised(self) -> bool:
                return self.headers.get("Authorization") == f"Bearer {outer.key}"

            def do_GET(self) -> None:  # noqa: N802
                path = self.path.split("?")[0].rstrip("/")
                if path.endswith("/models"):                 # public, like the real list
                    return self._send(200, {"data": [{"id": m, "pricing": {"prompt": str(p["in"] / 1e6), "completion": str(p["out"] / 1e6)}}
                                                     for m, p in outer.prices.items()]})
                if path.endswith("/auth/key"):
                    if not self._authorised():
                        outer.rejected += 1
                        return self._send(401, {"error": "bad key"})
                    return self._send(200, {"data": {"usage": round(outer.spent, 8), "limit": None}})
                self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")      # always drain the request first
                if not self.path.split("?")[0].rstrip("/").endswith("/chat/completions"):
                    return self._send(404, {"error": "not found"})
                if not self._authorised():
                    outer.rejected += 1
                    return self._send(401, {"error": "bad key"})
                model = body.get("model", "")
                if "response_format" in body:
                    outer.json_mode_requests += 1
                    if outer.reject_json_mode:
                        return self._send(400, {"error": {"message": "response_format is not supported by this provider"}})
                if model not in outer.prices:
                    return self._send(404, {"error": f"no such model {model}"})
                messages = body.get("messages") or []
                prompt = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") != "system")
                system = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
                content = outer.policy(sm.Request(prompt, system, body))
                p_tokens, c_tokens = max(1, len(prompt + system) // 4), max(1, len(content) // 4)
                price = outer.prices[model]
                cost = p_tokens * price["in"] / 1e6 + c_tokens * price["out"] / 1e6
                with outer._lock:
                    outer.spent += cost
                    outer.calls += 1
                self._send(200, {"id": "rehearsal", "object": "chat.completion", "model": model,
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                                 "usage": {"prompt_tokens": p_tokens, "completion_tokens": c_tokens, "total_tokens": p_tokens + c_tokens, "cost": cost}})

            def log_message(self, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/api/v1"

    def __enter__(self) -> "FakeOpenRouter":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()


def start(prices: Optional[Dict[str, Dict[str, float]]] = None) -> FakeOpenRouter:
    return FakeOpenRouter(prices or {"rehearsal/model": {"in": 0.2, "out": 0.8}})

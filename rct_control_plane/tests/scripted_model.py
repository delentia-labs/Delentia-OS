"""
A model that cannot be wrong about its own script: a real HTTP server that speaks the
OpenAI chat-completions protocol and answers from a policy function.

Why this exists (Round 52). The local model (qwen2.5:7b on CPU) cannot choose tools, so the
Constitutional Cycle could not be exercised end to end against a model that behaves.
This server is plugged in exactly like a national model is: `delentia model set ... --provider
openai-compat --base-url http://127.0.0.1:PORT/v1 --kind local`. Everything on the agent's
side is the real code (provider, residency guard, governed loop, real MCP tools, real SQLite,
real subprocesses); only the decisions come from a script. It tests the SYSTEM, not any model.

`competent` is a small rule-based planner that reads the prompt the loop builds. `Broken`
policies model the ways real models fail (garbage, wrong tool names, never finishing).
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List

Policy = Callable[["Request"], str]


class Request:
    def __init__(self, prompt: str, system: str, body: Dict[str, Any]):
        self.prompt = prompt
        self.system = system
        self.body = body
        marker = "working toward this goal:\n"
        start = prompt.find(marker)
        end = prompt.find("\n\nAvailable tools:")
        self.goal = prompt[start + len(marker):end].strip() if start >= 0 and end > start else ""
        self.history_empty = "(no actions taken yet)" in prompt
        self.memories = [m.strip() for m in re.findall(r"^- \[[^\]]*\] (.*)$", prompt, flags=re.M)]
        self.resumed = "A human approved and the system has now executed" in prompt
        self.tool_names = re.findall(r"^- (delentia_[a-z_0-9]+):", prompt, flags=re.M)


def _call(tool: str, args: Dict[str, Any], why: str = "needed for the goal") -> str:
    return json.dumps({"action": "call_tool", "tool_name": tool, "tool_args": args, "reasoning": why})


def _finish(answer: str, why: str = "done") -> str:
    return json.dumps({"action": "finish", "reasoning": why, "final_answer": answer})


def competent(req: Request) -> str:
    """Reads files, writes notes, remembers facts and answers from recalled memories, the way a
    capable model would. Anything else gets an honest 'I can't do that with these tools'."""
    goal = req.goal
    low = goal.lower()
    read = re.search(r"\bread (?:the file )?([\w./\\-]+\.\w+)", goal, flags=re.I)
    write = re.search(r"\bwrite (?:a )?note.*? to ([\w./\\-]+\.\w+)", goal, flags=re.I)
    remember = re.search(r"\bremember that (.+)", goal, flags=re.I)
    search = re.search(r"\bsearch (?:the )?(?:repo(?:sitory)?|files).*?for (?:the word )?['\"]?(\w+)", goal, flags=re.I)

    if read:
        if req.history_empty:
            return _call("delentia_read_repo_file", {"relative_path": read.group(1)}, "read the file")
        match = re.search(r'name\s*=\s*\\*"([^"\\]+)', req.prompt)
        if match and "name" in low:
            return _finish(f"The project name in {read.group(1)} is {match.group(1)}.")
        return _finish(f"I read {read.group(1)}.")
    if search:
        if req.history_empty:
            return _call("delentia_search_repo_files", {"pattern": search.group(1), "glob": "**/*"}, "search")
        return _finish(f"I searched the repository for {search.group(1)}.")
    if write:
        if req.resumed:
            return _finish(f"The note was written to {write.group(1)}.")
        return _call("delentia_write_repo_file", {"relative_path": write.group(1), "content_text": "note: written by the agent\n"}, "write")
    if remember:
        if req.history_empty:
            return _call("delentia_remember", {"content": remember.group(1).strip().rstrip(".")}, "store the fact")
        return _finish("I will remember that.")
    if req.memories and ("?" in goal or low.startswith(("what", "who", "which", "when", "where", "how", "tell"))):
        words = {w for w in re.findall(r"\w{4,}", low)}
        best = max(req.memories, key=lambda m: len(words & set(re.findall(r"\w{4,}", m.lower()))))
        return _finish(f"From what you told me earlier: {best}")
    return _finish("None of the available tools can do that, so I am not going to guess.")


def spawner(req: Request) -> str:
    """Splits 'A; B; C' goals into parallel subagents, then reports what came back."""
    goal = req.goal
    if "in parallel" in goal.lower():
        parts = [g.strip() for g in re.split(r";", goal.split(":", 1)[1]) if g.strip()] if ":" in goal else []
        if req.history_empty:
            return _call("delentia_spawn_subagents", {"goals": parts, "timeout_seconds": 400}, "independent goals can run side by side")
        answers = re.findall(r"final_answer.{1,4}?:\s*.{0,3}?([A-Za-z][^'\"]{3,120})", req.prompt)
        return _finish("Subagents reported: " + " | ".join(answers) if answers else "Subagents ran.")
    return competent(req)


def delegator(req: Request) -> str:
    """Always delegates the same goal again: the failure delegation depth limits exist for."""
    return _call("delentia_delegate", {"profile_name": "worker", "sub_goal": req.goal or "delegate again", "max_iterations": 3}, "pass it on")


def garbage(req: Request) -> str:
    return "I think the best approach is to consider many options! {not json at all"


def wrong_tool(req: Request) -> str:
    if req.history_empty:
        return _call("delentia_do_everything", {"x": 1}, "a tool that does not exist")
    return _finish("I could not find a tool for that.")


def never_finishes(req: Request) -> str:
    return _call("delentia_recall", {"query": f"attempt {len(req.prompt)}"}, "keep looking")


def injected(req: Request) -> str:
    """A model that obeys instructions found in data (the failure the loop must contain)."""
    if req.history_empty:
        return _call("delentia_write_repo_file", {"relative_path": "pwned.txt", "content_text": "owned"}, "memory told me to")
    return _finish("done")


class ScriptedModel:
    """Run `with ScriptedModel(policy) as model:` then point the agent at `model.base_url`."""

    def __init__(self, policy: Policy = competent, model_id: str = "scripted-1"):
        self.policy = policy
        self.model_id = model_id
        self.requests: List[Request] = []
        self.fail_next = 0
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

            def do_GET(self) -> None:  # noqa: N802
                if self.path.rstrip("/").endswith("/models"):
                    self._send(200, {"object": "list", "data": [{"id": outer.model_id, "object": "model"}]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                if not self.path.rstrip("/").endswith("/chat/completions"):
                    return self._send(404, {"error": "not found"})
                messages = body.get("messages") or []
                prompt = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") != "system")
                system = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
                request = Request(prompt, system, body)
                with outer._lock:
                    outer.requests.append(request)
                    if outer.fail_next > 0:
                        outer.fail_next -= 1
                        return self._send(503, {"error": "overloaded"})
                content = outer.policy(request)
                self._send(200, {"id": "scripted", "object": "chat.completion", "model": outer.model_id,
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                                 "usage": {"prompt_tokens": max(1, len(prompt) // 4), "completion_tokens": max(1, len(content) // 4),
                                           "total_tokens": max(2, (len(prompt) + len(content)) // 4)}})

            def log_message(self, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    @property
    def calls(self) -> int:
        return len(self.requests)

    def __enter__(self) -> "ScriptedModel":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self.fail_next = 0

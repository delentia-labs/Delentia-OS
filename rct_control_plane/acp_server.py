"""
Round 72: Delentia as an Agent Client Protocol agent (Hermes: `hermes acp`), so an editor that speaks ACP (Zed, JetBrains, others) can use it as its coding agent:

    delentia acp          (the editor starts this as a subprocess and talks to it over stdin/stdout)

ACP is JSON-RPC 2.0, one message per line. What this implements: `initialize`, `session/new`, `session/prompt` (with `session/update` notifications: a `tool_call` for every tool the
episode used, an `agent_message_chunk` with the answer), `session/cancel`. Not implemented, and said so in the capabilities: `session/load`, images, audio, embedded context, and the
client's file-system and terminal methods (the agent uses its own tools, through the gate).

What the protocol does NOT change:
  * every prompt is one episode of the governed loop (`agent_factory.build_governed_loop`), like the CLI, the API and the chat channels: GUARD, THINK, ROUTE, ACT with the FDIA gate and the
    owner's policy, the taint gate, RECORD in the audit chain;
  * an action that needs a human signature STOPS the episode and says so in the answer, with the approval id. An editor's "allow" button is not a signature: the key of an approver is on
    another device (`delentia approvals sign`), so `session/request_permission` is never used to authorise anything;
  * the editor is the person at the keyboard: it runs as the owner's namespace (DELENTIA_ACP_NAMESPACE, else the Desk's), like the CLI. It is NOT given a say over what the agent may do;
  * MCP servers listed by the editor in `session/new` are IGNORED: starting a program an editor names would be running a command that did not come from the owner's configuration
    (external servers come only from ~/.delentia/mcp_servers.json, through the same gate);
  * the working directory the editor reports is recorded, not obeyed: the agent's file tools stay inside DELENTIA_REPO_ROOT.
Nothing is written to stdout except protocol messages (logs go to stderr), because the editor reads stdout as JSON.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

PROTOCOL_VERSION = 1
ENV_NAMESPACE = "DELENTIA_ACP_NAMESPACE"
ENV_MAX_ITERATIONS = "DELENTIA_ACP_MAX_ITERATIONS"
ENV_MAX_SECONDS = "DELENTIA_ACP_MAX_SECONDS"
_RESULT_PREVIEW = 1500
_KINDS = (("write", "edit"), ("patch", "edit"), ("read", "read"), ("list", "read"), ("search", "search"), ("grep", "search"), ("recall", "search"),
          ("crawl", "fetch"), ("browse", "fetch"), ("web", "fetch"), ("sandbox", "execute"), ("shell", "execute"), ("run", "execute"), ("think", "think"))
_STOP = {"guard_blocked": "refusal", "max_iterations": "max_turn_requests", "cancelled": "cancelled"}


def tool_kind(name: str) -> str:
    low = (name or "").lower()
    return next((kind for word, kind in _KINDS if word in low), "other")


def _text(value: Any, limit: int = _RESULT_PREVIEW) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + " ..."


class AcpError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class AcpServer:
    """One connection. `read_line` returns the next line ('' at end of input); `write` sends one message (a dict) to the editor."""

    def __init__(self, read_line: Callable[[], Awaitable[str]], write: Callable[[Dict[str, Any]], None], *, kernel: Any = None, mcp_server: Any = None,
                 loop_factory: Optional[Callable[..., Any]] = None, namespace: Optional[str] = None) -> None:
        self._read, self._write = read_line, write
        self._kernel, self._mcp = kernel, mcp_server
        self._factory = loop_factory
        self.namespace = namespace or os.environ.get(ENV_NAMESPACE) or os.environ.get("DELENTIA_DESK_NAMESPACE", "desk")
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._tasks: set = set()
        self._initialized = False
        self._client: Dict[str, str] = {}

    # ---- plumbing ----------------------------------------------------------------------------------------------------------------------------------------
    def _reply(self, request_id: Any, result: Any) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _error(self, request_id: Any, code: int, message: str) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def _update(self, session_id: str, update: Dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": update}})

    async def serve(self) -> None:
        while True:
            line = await self._read()
            if line == "":
                break
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                self._error(None, -32700, "parse error")
                continue
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                self._error(message.get("id") if isinstance(message, dict) else None, -32600, "invalid request")
                continue
            if "method" not in message:                                    # a response to something we sent: we send no requests, so there is nothing to match
                continue
            task = asyncio.create_task(self._handle(message))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _handle(self, message: Dict[str, Any]) -> None:
        method, request_id, params = message.get("method"), message.get("id"), message.get("params") or {}
        is_request = "id" in message
        try:
            handler = {"initialize": self._initialize, "session/new": self._session_new, "session/prompt": self._session_prompt, "session/cancel": self._session_cancel}.get(str(method))
            if handler is None:
                if is_request:
                    self._error(request_id, -32601, f"method not supported: {method}")
                return
            if not isinstance(params, dict):
                raise AcpError(-32602, "params must be an object")
            result = await handler(params)
            if is_request:
                self._reply(request_id, result)
        except asyncio.CancelledError:
            raise
        except AcpError as exc:
            if is_request:
                self._error(request_id, exc.code, exc.message)
        except Exception as exc:                                           # noqa: BLE001 - one bad request must not take the connection down
            print(f"acp: {method} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            if is_request:
                self._error(request_id, -32603, f"internal error ({type(exc).__name__})")

    # ---- methods -----------------------------------------------------------------------------------------------------------------------------------------
    async def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._initialized = True
        client: Dict[str, Any] = params["clientInfo"] if isinstance(params.get("clientInfo"), dict) else {}
        self._client = {"name": _text(client.get("name") or "", 80), "version": _text(client.get("version") or "", 40)}
        from rct_control_plane._version import PACKAGE_VERSION
        return {"protocolVersion": PROTOCOL_VERSION,
                "agentCapabilities": {"loadSession": False, "promptCapabilities": {"image": False, "audio": False, "embeddedContext": False}, "mcpCapabilities": {"http": False, "sse": False}},
                "agentInfo": {"name": "delentia", "title": "Delentia (governed agent)", "version": PACKAGE_VERSION},
                "authMethods": []}

    async def _session_new(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._initialized:
            raise AcpError(-32600, "call initialize first")
        session_id = "sess_" + uuid.uuid4().hex[:16]
        cwd = _text(params.get("cwd") or "", 300)
        ignored = len(params.get("mcpServers") or []) if isinstance(params.get("mcpServers"), list) else 0
        self.sessions[session_id] = {"cwd": cwd, "running": None, "ignored_mcp_servers": ignored}
        kernel = self._get_kernel()                                         # ~2 s, in this thread on purpose: importing numpy from a worker thread while another thread waits on stdin hung on Windows
        try:
            kernel._persistence.append_audit(entity_type="acp_session", entity_id=session_id, action="opened", actor=self.namespace,
                                             changes={"client": self._client, "cwd": cwd, "mcp_servers_ignored": ignored})
        except Exception:                                                  # noqa: BLE001 - the audit row must not stop a session from opening
            pass
        return {"sessionId": session_id}

    async def _session_cancel(self, params: Dict[str, Any]) -> None:
        session = self.sessions.get(str(params.get("sessionId")))
        if session and session["running"] is not None:
            session["running"].cancel()
        return None

    def _get_kernel(self) -> Any:
        if self._kernel is None:
            from rct_control_plane.mcp_server import _kernel
            self._kernel = _kernel
        return self._kernel

    def _get_mcp(self) -> Any:
        if self._mcp is None:
            from rct_control_plane.mcp_server import mcp
            self._mcp = mcp
        return self._mcp

    @staticmethod
    def _prompt_text(blocks: Any) -> str:
        parts: List[str] = []
        skipped = 0
        for block in blocks if isinstance(blocks, list) else []:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                skipped += 1
        if skipped:
            parts.append(f"[{skipped} attachment(s) of a kind this agent does not read were left out]")
        return "\n".join(parts).strip()

    async def _session_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(params.get("sessionId") or "")
        session = self.sessions.get(session_id)
        if session is None:
            raise AcpError(-32602, "unknown sessionId")
        goal = self._prompt_text(params.get("prompt"))
        if not goal:
            raise AcpError(-32602, "the prompt has no text")
        if session["running"] is not None:
            raise AcpError(-32602, "a prompt is already running in this session; cancel it first")
        kernel = self._get_kernel()
        from rct_control_plane import chat_commands
        if goal.startswith("/"):                                           # the same read-only slash commands as the chat channels
            answer = await asyncio.to_thread(chat_commands.handle, kernel, "acp", "owner", self.namespace, goal)
            if answer is not None:
                self._update(session_id, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": answer}})
                return {"stopReason": "end_turn"}
        task = asyncio.current_task()
        session["running"] = task
        try:
            return await self._run_episode(session_id, goal, kernel)
        except asyncio.CancelledError:                                     # session/cancel (or the connection closing): the turn ends with the cancelled stop reason
            if task is not None and hasattr(task, "uncancel"):
                task.uncancel()
            return {"stopReason": "cancelled"}
        finally:
            session["running"] = None

    async def _run_episode(self, session_id: str, goal: str, kernel: Any) -> Dict[str, Any]:
        from rct_control_plane.agent_factory import build_governed_loop
        factory = self._factory or build_governed_loop
        max_iterations = int(os.environ.get(ENV_MAX_ITERATIONS, "5"))
        max_seconds = float(os.environ.get(ENV_MAX_SECONDS, "600"))
        loop = factory(kernel, self.namespace, max_iterations=max_iterations, max_seconds=max_seconds, mcp_server=self._get_mcp())

        async def on_step(step: Any) -> None:
            tool = getattr(step, "tool_name", None)
            if not tool:
                return
            result = getattr(step, "tool_result", None)
            status, note = "completed", ""
            if isinstance(result, dict):
                if result.get("fdia_blocked"):
                    status, note = "failed", f"Blocked by the FDIA gate (F = {result.get('F')}): {result.get('reason')}"
                elif result.get("pending_approval"):
                    status, note = "failed", f"Waiting for a human signature: {result.get('reason') or 'this action needs an approver'}. Nothing was run."
                elif result.get("notary_unavailable"):
                    status, note = "failed", "Not run: the notary could not record it (fail closed)."
                elif "did_you_mean" in result:
                    status, note = "failed", f"No tool named {tool}; close names: {', '.join(result['did_you_mean']) or '-'}"
                elif result.get("error"):
                    status = "failed"
            call_id = f"call_{uuid.uuid4().hex[:10]}"
            self._update(session_id, {"sessionUpdate": "tool_call", "toolCallId": call_id, "name": tool, "title": f"{tool}", "kind": tool_kind(str(tool)), "status": status,
                                      "rawInput": getattr(step, "tool_args", {}) or {},
                                      "content": [{"type": "content", "content": {"type": "text", "text": note or _text(result)}}]})

        result = dict(await loop.run(goal, on_step=on_step))
        stopped = str(result.get("stopped_reason") or "")
        answer = str(result.get("final_answer") or "")
        extra = ""
        if result.get("approval_id") or stopped == "pending_approval":
            extra = (f"\n\nThis needs a human signature (approval {result.get('approval_id') or '?'}). An editor's button cannot give it: sign on the approver's own device with "
                     "`delentia approvals sign`, then `delentia approvals approve`.")
        elif stopped == "llm_error":
            extra = "\n\nThe model could not be reached. Check `delentia model show`."
        elif stopped in ("paused", "daily_limit", "stuck_repeating", "notary_unavailable"):
            extra = f"\n\nThe episode stopped: {stopped}."
        if answer or extra:
            self._update(session_id, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": (answer + extra).strip()}})
        return {"stopReason": _STOP.get(stopped, "end_turn")}


def stdio_server(**kwargs: Any) -> AcpServer:
    """A server wired to this process's stdin/stdout: UTF-8, one JSON object per line, nothing else on stdout."""
    # The editor reads stdout as JSON. Libraries the kernel loads (logging, rich, loguru) print there while it starts, and some of them hold the file descriptor, not `sys.stdout`: so
    # file descriptor 1 itself is pointed at stderr, and the protocol gets a private duplicate of the real stdout that nothing else knows about.
    sys.stdout.flush()
    stdout = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    async def read_line_in_a_thread() -> str:
        raw = await asyncio.to_thread(sys.stdin.buffer.readline)
        return raw.decode("utf-8", errors="replace") if raw else ""

    read_line = read_line_in_a_thread
    if os.name == "nt":
        # On Windows a thread blocked in a read of the stdin pipe makes the FIRST import of numpy or pyarrow in this process wait until the pipe closes (measured: 19 s and 24 s, i.e. until the
        # other end of the pipe went away), and the agent imports them the first time a tool needs them. So nothing waits in a read: the event loop asks the pipe how many bytes are there
        # (PeekNamedPipe) and reads only those.
        try:
            import msvcrt

            import _winapi
            handle = msvcrt.get_osfhandle(0)
            _winapi.PeekNamedPipe(handle, 0)                                  # raises unless stdin is a pipe
            pending = bytearray()

            async def read_line_by_peeking() -> str:
                while True:
                    cut = pending.find(b"\n")
                    if cut >= 0:
                        line = bytes(pending[:cut + 1])
                        del pending[:cut + 1]
                        return line.decode("utf-8", errors="replace")
                    try:
                        available = int(_winapi.PeekNamedPipe(handle, 0)[0])
                    except OSError:                                           # the editor closed its end
                        rest = bytes(pending)
                        pending.clear()
                        return rest.decode("utf-8", errors="replace")
                    if available:
                        pending.extend(os.read(0, min(available, 1 << 16)))
                    else:
                        await asyncio.sleep(0.02)
            read_line = read_line_by_peeking
        except (OSError, ImportError, AttributeError):
            pass                                                              # stdin is a file or a console: the thread reader above

    def write(message: Dict[str, Any]) -> None:
        stdout.write((json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
        stdout.flush()
    return AcpServer(read_line, write, **kwargs)


def main() -> int:
    asyncio.run(stdio_server().serve())
    return 0

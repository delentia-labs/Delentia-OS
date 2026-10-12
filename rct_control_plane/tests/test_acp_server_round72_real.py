"""
Round 72: `delentia acp` (acp_server.py). The main test starts the real command as a subprocess and talks to it the way an editor does: one JSON-RPC message per line over stdin/stdout, with a
scripted model behind a real HTTP endpoint, the real governed loop and real tools. The protocol corners (cancel, a second prompt, the order of calls, parse errors) are tested in-process.
What must hold besides the protocol: stdout carries nothing but protocol messages; a write that needs a signature is NOT run and the editor is told to sign elsewhere; the MCP servers an editor
lists are ignored; every session leaves an audit row.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import queue
import sqlite3
import subprocess
import threading
import time

import pytest

import scripted_model as sm
from rct_control_plane import acp_server
from rct_control_plane.model_config import save_model_selection


# ---- the real command over real pipes ----------------------------------------------------------------------------------------------------------------------

class Editor:
    """A minimal ACP client: sends a request, collects notifications until the response with that id arrives."""

    def __init__(self, env, cwd):
        self.proc = subprocess.Popen([sys.executable, "-m", "rct_control_plane.cli", "acp"], cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.lines: "queue.Queue[bytes]" = queue.Queue()
        self.raw = []
        threading.Thread(target=self._pump, daemon=True).start()
        self.next_id = 0

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(b"")

    def send(self, obj):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def request(self, method, params, timeout=180):
        self.next_id += 1
        mid = self.next_id
        self.send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        updates = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self.lines.get(timeout=1)
            except queue.Empty:
                continue
            assert line != b"", "the agent closed stdout"
            self.raw.append(line)
            message = json.loads(line)                                         # EVERY line on stdout must be JSON: the editor parses it all
            assert message.get("jsonrpc") == "2.0"
            if message.get("id") == mid:
                return message, updates
            if message.get("method") == "session/update":
                updates.append(message["params"]["update"])
        raise AssertionError(f"no answer to {method} in {timeout} s")

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=20)
        except Exception:                                                       # noqa: BLE001
            self.proc.kill()


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    work = tmp_path_factory.mktemp("acp")
    repo = work / "repo"
    (repo / "notes").mkdir(parents=True)
    (repo / "report.txt").write_text("Quarterly total: 41,250 baht\n", encoding="utf-8")
    with sm.ScriptedModel(sm.competent) as model:
        config = work / "model.json"
        save_model_selection("openai-compat", model.model_id, path=config, endpoint={"base_url": model.base_url, "kind": "local", "region": "", "operator": "scripted-acp-test"})
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DELENTIA_HOME": str(work / "home"), "DELENTIA_REPO_ROOT": str(repo), "DELENTIA_MODEL_CONFIG": str(config),
               "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": model.model_id, "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_MEMORY_EMBED": "off",
               "USERPROFILE": str(work / "home"), "HOME": str(work / "home"), "DELENTIA_DESK_NAMESPACE": "desk"}
        for name in ("DELENTIA_API_TOKEN", "DELENTIA_API_TOKENS_FILE", "DELENTIA_FDIA_POLICY", "DELENTIA_NOTARY_URL"):
            env.pop(name, None)
        editor = Editor(env, str(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))))
        yield editor, repo, work
        editor.close()


def test_the_real_command_speaks_the_protocol_and_runs_governed_episodes(world):
    editor, repo, work = world
    reply, _ = editor.request("initialize", {"protocolVersion": 1, "clientInfo": {"name": "test-editor", "version": "1"}, "clientCapabilities": {}}, timeout=180)
    result = reply["result"]
    assert result["protocolVersion"] == 1 and result["authMethods"] == [] and result["agentInfo"]["name"] == "delentia"
    caps = result["agentCapabilities"]
    assert caps["loadSession"] is False and caps["promptCapabilities"] == {"image": False, "audio": False, "embeddedContext": False}

    new, _ = editor.request("session/new", {"cwd": str(repo), "mcpServers": [{"name": "evil", "command": "calc.exe", "args": [], "env": []}]})
    session = new["result"]["sessionId"]
    assert session.startswith("sess_")

    # a read: a tool_call update (kind read, completed) with the file's text, then the answer
    done, updates = editor.request("session/prompt", {"sessionId": session, "prompt": [{"type": "text", "text": "Read the file report.txt and tell me the quarterly total"}]})
    assert done["result"]["stopReason"] == "end_turn"
    calls = [u for u in updates if u["sessionUpdate"] == "tool_call"]
    assert calls and calls[0]["name"] == "delentia_read_repo_file" and calls[0]["kind"] == "read" and calls[0]["status"] == "completed"
    assert "41,250" in json.dumps(calls[0]["content"], ensure_ascii=False)
    assert any(u["sessionUpdate"] == "agent_message_chunk" and u["content"]["type"] == "text" for u in updates)

    # a write: not run, and the editor is told that a button cannot sign
    done, updates = editor.request("session/prompt", {"sessionId": session, "prompt": [{"type": "text", "text": "Write a note to notes/out.txt"}]})
    failed = [u for u in updates if u["sessionUpdate"] == "tool_call" and u["status"] == "failed"]
    assert failed and "human signature" in json.dumps(failed[0]["content"])
    message = " ".join(u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk")
    assert "approvals sign" in message and not (repo / "notes" / "out.txt").exists()

    # a slash command is answered without a model call; an unknown method is an error; a bad line is a parse error
    done, updates = editor.request("session/prompt", {"sessionId": session, "prompt": [{"type": "text", "text": "/help"}]})
    assert done["result"]["stopReason"] == "end_turn" and any("/status" in u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk")
    err, _ = editor.request("fs/read_text_file", {"path": "/etc/passwd"})
    assert err["error"]["code"] == -32601
    editor.proc.stdin.write(b"this is not json\n")
    editor.proc.stdin.flush()
    parse = json.loads(editor.lines.get(timeout=30))
    assert parse["error"]["code"] == -32700 and parse["id"] is None

    # the audit row says what was ignored
    with sqlite3.connect(str(work / "home" / "agentic.db")) as conn:
        rows = [json.loads(r[0]) for r in conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'acp_session'")]
    assert rows and rows[0]["mcp_servers_ignored"] == 1 and rows[0]["client"]["name"] == "test-editor"


# ---- the protocol corners, in-process -----------------------------------------------------------------------------------------------------------------------

class Wire:
    def __init__(self):
        self.inbox: "asyncio.Queue[str]" = asyncio.Queue()
        self.out = []

    async def read(self):
        return await self.inbox.get()

    def write(self, message):
        self.out.append(message)

    def feed(self, obj):
        self.inbox.put_nowait(json.dumps(obj) + "\n")

    async def until(self, predicate, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            for m in self.out:
                if predicate(m):
                    return m
            await asyncio.sleep(0.02)
        raise AssertionError(f"not seen: {self.out}")


class FakeKernel:
    class _P:
        def append_audit(self, **kw):
            pass
    _persistence = _P()


class SlowLoop:
    async def run(self, goal, on_step=None):
        await asyncio.sleep(60)
        return {"stopped_reason": "finished", "final_answer": "never"}


class QuickLoop:
    def __init__(self, stopped="finished", answer="done", approval=None):
        self.result = {"stopped_reason": stopped, "final_answer": answer, "approval_id": approval}

    async def run(self, goal, on_step=None):
        return dict(self.result)


def _server(wire, factory):
    return acp_server.AcpServer(wire.read, wire.write, kernel=FakeKernel(), mcp_server=object(), loop_factory=factory, namespace="desk")


async def _open(wire):
    wire.feed({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}})
    await wire.until(lambda m: m.get("id") == 1)
    wire.feed({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": "/x", "mcpServers": []}})
    return (await wire.until(lambda m: m.get("id") == 2))["result"]["sessionId"]


def test_cancel_ends_the_turn_with_the_cancelled_stop_reason_and_a_second_prompt_is_refused():
    async def go():
        wire = Wire()
        server = _server(wire, lambda *a, **k: SlowLoop())
        runner = asyncio.create_task(server.serve())
        session = await _open(wire)
        wire.feed({"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": session, "prompt": [{"type": "text", "text": "go"}]}})
        await asyncio.sleep(0.3)
        wire.feed({"jsonrpc": "2.0", "id": 4, "method": "session/prompt", "params": {"sessionId": session, "prompt": [{"type": "text", "text": "again"}]}})
        refused = await wire.until(lambda m: m.get("id") == 4)
        assert refused["error"]["code"] == -32602 and "already running" in refused["error"]["message"]
        wire.feed({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session}})
        done = await wire.until(lambda m: m.get("id") == 3)
        assert done["result"] == {"stopReason": "cancelled"}
        wire.inbox.put_nowait("")
        await runner
    asyncio.run(go())


def test_order_of_calls_unknown_sessions_empty_prompts_and_stop_reasons():
    async def go():
        wire = Wire()
        stops = iter([QuickLoop("guard_blocked", "refused"), QuickLoop("max_iterations", "tired"), QuickLoop("pending_approval", "", approval="apr_1")])
        server = _server(wire, lambda *a, **k: next(stops))
        runner = asyncio.create_task(server.serve())
        wire.feed({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": "/x", "mcpServers": []}})
        assert (await wire.until(lambda m: m.get("id") == 1))["error"]["code"] == -32600               # initialize first
        session = await _open(wire)
        wire.feed({"jsonrpc": "2.0", "id": 5, "method": "session/prompt", "params": {"sessionId": "sess_nope", "prompt": [{"type": "text", "text": "x"}]}})
        assert (await wire.until(lambda m: m.get("id") == 5))["error"]["code"] == -32602
        wire.feed({"jsonrpc": "2.0", "id": 6, "method": "session/prompt", "params": {"sessionId": session, "prompt": []}})
        assert (await wire.until(lambda m: m.get("id") == 6))["error"]["code"] == -32602
        for n, expected in ((7, "refusal"), (8, "max_turn_requests"), (9, "end_turn")):
            wire.feed({"jsonrpc": "2.0", "id": n, "method": "session/prompt", "params": {"sessionId": session, "prompt": [{"type": "text", "text": "do it"}, {"type": "image", "data": "x", "mimeType": "image/png"}]}})
            assert (await wire.until(lambda m, n=n: m.get("id") == n))["result"]["stopReason"] == expected
        said = " ".join(m["params"]["update"]["content"]["text"] for m in wire.out if m.get("method") == "session/update")
        assert "apr_1" in said and "cannot give it" in said                                              # a pending approval names the id and says a button is not a signature
        wire.inbox.put_nowait("")
        await runner
    asyncio.run(go())


def test_a_tool_is_given_a_kind_the_editor_understands():
    assert acp_server.tool_kind("delentia_read_repo_file") == "read" and acp_server.tool_kind("delentia_write_repo_file") == "edit"
    assert acp_server.tool_kind("delentia_search_repo_files") == "search" and acp_server.tool_kind("delentia_crawl_url") == "fetch"
    assert acp_server.tool_kind("delentia_sandbox_shell") == "execute" and acp_server.tool_kind("something_else") == "other"


def test_the_governance_page_describes_acp_sessions_credential_moves_and_replacements_in_words():
    from rct_control_plane import governance_view as gv
    assert "ACP session" in gv.summarise("acp_session", "opened", {"client": {"name": "zed"}, "mcp_servers_ignored": 2}) and "2 MCP server" in gv.summarise("acp_session", "opened", {"client": {"name": "zed"}, "mcp_servers_ignored": 2})
    text = gv.summarise("credential_pool", "cooldown", {"provider": "openrouter", "label": "OPENROUTER_API_KEY", "status": 429, "seconds": 300})
    assert "OPENROUTER_API_KEY" in text and "429" in text and "300" in text
    assert "replaced by mem_b" in gv.summarise("memory_replaced", "replaced", {"old_id": "mem_a", "new_id": "mem_b", "pin_moved": False})
    assert gv.CATEGORY_OF["acp_session"] == "identity" and gv.CATEGORY_OF["credential_pool"] == "models" and gv.CATEGORY_OF["memory_replaced"] == "memory"

"""
Round 73: does `delentia acp` interoperate with a protocol implementation that is NOT ours? The official Agent Client Protocol Python SDK (`pip install agent-client-protocol`) plays the editor: it starts
`delentia acp` as a subprocess, negotiates, opens a session, sends prompts and receives the typed `session/update` notifications through the SDK's own validation (pydantic models generated from the
protocol schema). If our messages were malformed the SDK would reject them. The model behind the agent is a scripted one over HTTP; everything else is real.

Run it with the SDK's interpreter (an isolated venv is best), giving the main interpreter that has Delentia's dependencies:

    C:\\Users\\whale\\acpenv\\Scripts\\python.exe scripts\\acp_interop_check.py --main-python python
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))

import acp  # noqa: E402
from acp import text_block  # noqa: E402
from acp.schema import AgentMessageChunk, ToolCallStart  # noqa: E402


class Editor(acp.Client):
    """What an editor does: it listens. It never answers a permission request with 'allow' (the agent never sends one)."""

    def __init__(self) -> None:
        self.updates: List[Any] = []
        self.permission_requests = 0

    def on_connect(self, conn: Any) -> None:
        self.conn = conn

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        self.updates.append(update)

    async def request_permission(self, *args: Any, **kwargs: Any) -> Any:
        self.permission_requests += 1
        raise acp.RequestError.method_not_found("session/request_permission")


async def main(main_python: str) -> int:
    import scripted_model as sm
    work = Path(tempfile.mkdtemp(prefix="acp-interop-"))
    repo = work / "repo"
    (repo / "notes").mkdir(parents=True)
    (repo / "report.txt").write_text("Quarterly total: 41,250 baht\n", encoding="utf-8")
    results: List[tuple] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, bool(ok)))
        print(f"  {'OK ' if ok else 'NO '} {name}  {detail}"[:200], flush=True)

    with sm.ScriptedModel(sm.competent) as model:
        config = work / "model.json"
        code = ("import sys; sys.path.insert(0, r'%s'); from rct_control_plane.model_config import save_model_selection; "
                "import pathlib; save_model_selection('openai-compat', %r, path=pathlib.Path(%r), endpoint={'base_url': %r, 'kind': 'local', 'region': '', 'operator': 'scripted-interop'})"
                % (str(ROOT), model.model_id, str(config), model.base_url))
        subprocess.run([main_python, "-c", code], check=True, capture_output=True)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DELENTIA_HOME": str(work / "home"), "DELENTIA_REPO_ROOT": str(repo), "DELENTIA_MODEL_CONFIG": str(config),
               "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": model.model_id, "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_MEMORY_EMBED": "off",
               "USERPROFILE": str(work / "home"), "HOME": str(work / "home")}
        editor = Editor()
        print(f"agent-client-protocol SDK {__import__('importlib.metadata', fromlist=['version']).version('agent-client-protocol')}; protocol version {acp.PROTOCOL_VERSION}", flush=True)
        async with acp.spawn_agent_process(editor, main_python, "-m", "rct_control_plane.cli", "acp", env=env, cwd=str(ROOT)) as (conn, _proc):
            init = await asyncio.wait_for(conn.initialize(protocol_version=acp.PROTOCOL_VERSION), 120)
            check("initialize is accepted by the SDK's own validation", init.protocol_version == acp.PROTOCOL_VERSION and init.agent_info is not None, f"agent {init.agent_info.name} {init.agent_info.version}")
            caps = init.agent_capabilities
            check("the capabilities say what is not supported", caps is not None and not caps.load_session and not caps.prompt_capabilities.image)
            session = await asyncio.wait_for(conn.new_session(cwd=str(repo), mcp_servers=[]), 120)
            check("session/new returns a session id", bool(session.session_id))
            reply = await asyncio.wait_for(conn.prompt(prompt=[text_block("Read the file report.txt and tell me the quarterly total")], session_id=session.session_id), 300)
            check("a read prompt ends with end_turn", reply.stop_reason == "end_turn", str(reply.stop_reason))
            calls = [u for u in editor.updates if isinstance(u, ToolCallStart)]
            said = " ".join(getattr(u.content, "text", "") for u in editor.updates if isinstance(u, AgentMessageChunk))
            check("the tool call arrives as a typed ToolCallStart (kind read, completed) with the file text", bool(calls) and calls[0].kind == "read" and str(calls[0].status) == "completed" and "41,250" in json.dumps([c.model_dump(mode="json") for c in calls], ensure_ascii=False))
            check("the answer arrives as an agent message chunk", "report.txt" in said, said[:60])
            editor.updates.clear()
            reply = await asyncio.wait_for(conn.prompt(prompt=[text_block("Write a note to notes/out.txt")], session_id=session.session_id), 300)
            failed = [u for u in editor.updates if isinstance(u, ToolCallStart) and str(u.status) == "failed"]
            said = " ".join(getattr(u.content, "text", "") for u in editor.updates if isinstance(u, AgentMessageChunk))
            check("a write that needs a signature is reported as failed and nothing is written", bool(failed) and "approvals sign" in said and not (repo / "notes" / "out.txt").exists())
            check("the agent never asked the editor for permission", editor.permission_requests == 0)
            # the SDK cancels a running prompt with session/cancel; an idle cancel must be harmless
            await conn.cancel(session_id=session.session_id)
            reply = await asyncio.wait_for(conn.prompt(prompt=[text_block("/help")], session_id=session.session_id), 120)
            check("the connection still works after a cancel", reply.stop_reason == "end_turn")
    ok = all(r[1] for r in results)
    print(f"\n{sum(1 for r in results if r[1])}/{len(results)} interoperability checks hold", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--main-python", default="python", help="the interpreter that has Delentia's dependencies")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.main_python)))

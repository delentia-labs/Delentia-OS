"""Does the model see mcp__notes__write_note in the W12 menu? Builds the real tool list (the runtime's tools + the external 'notes' server used by W12) and ranks it
with the real tool_menu code for the real W12 goal. Calls no model, spends nothing. Run with the Delentia-OS repository first on the path."""
import asyncio, json, os, sys, tempfile
from pathlib import Path

REPO = r"C:\Users\whale\Delentia\Delentia-OS"
sys.path.insert(0, REPO)
sys.path.insert(0, REPO + r"\rct_control_plane\tests")
home = Path(tempfile.mkdtemp(prefix="w12menu_"))
os.environ["DELENTIA_HOME"] = str(home)
from research import live_workflows as lw
from rct_control_plane import external_mcp as xm
from rct_control_plane import tool_menu
from rct_control_plane.mcp_server import mcp

server = Path(REPO) / "rct_control_plane" / "tests" / "fake_mcp_server.py"
config = home / "w12_mcp_servers.json"
config.write_text(json.dumps({"servers": {"notes": {"command": sys.executable, "args": [str(server)], "env_vars": ["FAKE_NOTES_FILE"],
                                                    "read_only_tools": ["read_note", "fetch_page"], "timeout_s": 90}}}), encoding="utf-8")
os.environ[xm.CONFIG_ENV] = str(config)
os.environ["FAKE_NOTES_FILE"] = str(home / "notes.txt")
xm.clear_cache()
wrapped = xm.maybe_wrap(mcp, "owner-w12")
tools = asyncio.run(wrapped.list_tools())
tools = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools if t]
names = [t["name"] for t in tools]
print("total tools offered to the ranker:", len(tools))
print("external tools present:", [n for n in names if n.startswith("mcp__")])
for t in tools:
    if t["name"].startswith("mcp__"):
        print("  ", t["name"], "|", (t.get("description") or "")[:120])
print("ranked_enabled (env unset):", tool_menu.ranked_enabled(), "| top_k:", tool_menu.top_k())
shown = tool_menu.rank_tools(lw.W12_GOAL, tools, tool_menu.top_k())
print("menu shown to the model for the W12 goal (%d tools):" % len(shown))
for t in shown:
    print("  ", t["name"])
print("mcp__notes__write_note in the menu:", any(t["name"] == "mcp__notes__write_note" for t in shown))
print("W12 goal:", lw.W12_GOAL)
xm.shutdown_pool()

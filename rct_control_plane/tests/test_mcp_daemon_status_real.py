"""Round 36: real test for the delentia_daemon_status MCP tool."""
import asyncio
import json
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.mcp_server import mcp


def test_daemon_status_tool_is_registered_and_honestly_reports_not_running():
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert "delentia_daemon_status" in names

    result = asyncio.run(mcp.call_tool("delentia_daemon_status", {}))
    data = json.loads(result.content[0].text)
    # mcp_server.py's process doesn't run rct serve's lifespan, so this
    # must honestly report not-running rather than fabricating a status.
    assert data["running"] is False
    assert data["tasks"] == []

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
    # NOTE: `tasks` is NOT asserted empty here - api.py's _DAEMON_SCHEDULER
    # global is deliberately left set (not reset to None) after a real
    # start/stop cycle elsewhere in the same test process (see
    # test_api_daemon_lifespan_real.py's own assertion that it stays
    # non-None post-shutdown), so `tasks` may legitimately list that
    # scheduler's registered tasks even while genuinely not running. The
    # real, order-independent contract this test verifies is `running`.
    assert data["running"] is False
    assert isinstance(data["tasks"], list)

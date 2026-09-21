"""Round 38: real test for the delentia_compress_intent_delta MCP tool."""
import sys, os, json, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.mcp_server import mcp


def test_compress_intent_delta_tool_is_registered_and_works_for_real():
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert "delentia_compress_intent_delta" in names

    result = asyncio.run(mcp.call_tool("delentia_compress_intent_delta", {
        "prior_intent_state": {"intent": "deploy", "status": "pending"},
        "current_intent_state": {"intent": "deploy", "status": "done"},
    }))
    data = json.loads(result.content[0].text)
    assert data["op_count"] >= 1
    assert "byte_reduction_pct" in data
    assert data["old_state_tokens_approx"] is not None

"""
Real, in-process MCP client/server round-trip test — Round 21 Phase 2
Task 4. Uses mcp>=2.0's real MCPServer API (FastMCP was renamed to
MCPServer in mcp 2.x; verified by direct inspection of the installed
package before writing this test, not assumed from older docs).
"""
import asyncio
import json
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.mcp_server import mcp


def test_process_intent_tool_is_registered():
    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "delentia_process_intent" in tool_names


def test_process_intent_tool_real_call():
    result = asyncio.run(mcp.call_tool("delentia_process_intent", {"intent": "document this function"}))
    # Real observed shape (mcp 2.x): CallToolResult with .content[0].text
    # holding the JSON-serialized real dict the tool function returned.
    assert result.is_error is False
    payload = json.loads(result.content[0].text)
    assert payload["intent"] == "document this function"
    assert payload["phase_1_ingestion"]["jitna_signed"] is True
    assert payload["phase_1_ingestion"]["jitna_verified"] is True
    assert "jitna_packet_id" in payload["phase_1_ingestion"]
    assert payload["phase_3_4_routing_and_execution"]["path"] == "fast"


def test_assemble_nodes_mcp_tool():
    result = asyncio.run(mcp.call_tool("delentia_assemble_nodes", {
        "query": "graph stats check", "node_names": ["algo_17_graph_traversal"],
    }))
    payload = json.loads(result.content[0].text)
    assert "answer" in payload

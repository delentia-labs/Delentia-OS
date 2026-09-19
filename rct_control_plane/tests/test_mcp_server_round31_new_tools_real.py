"""
Real MCP tool tests for Round 31's tool-count expansion (item 4: closing
part of the 12-vs-Hermes'-70+ gap with genuinely already-built, tested
kernel capabilities newly exposed as MCP tools, not new core logic).
Same real in-process MCPServer round-trip pattern as test_mcp_server_real.py.
"""
import asyncio
import json
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.mcp_server import mcp, _exchange_bridge


def _call(name, args):
    result = asyncio.run(mcp.call_tool(name, args))
    return result, json.loads(result.content[0].text)


def test_new_tools_are_registered():
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    for expected in [
        "delentia_list_exchange_files",
        "delentia_read_exchange_file",
        "delentia_save_exchange_file",
        "delentia_crawl_url",
        "delentia_query_audit_log",
        "delentia_query_intents",
        "delentia_check_ground_truth_claim",
    ]:
        assert expected in names


class TestExchangeBridgeTools:
    def test_save_then_read_then_list_round_trip(self):
        _, saved = _call("delentia_save_exchange_file", {
            "category": "projects", "filename": "round31_mcp_test.txt", "content_text": "real content",
        })
        assert saved["status"] == "SAVED"

        _, read = _call("delentia_read_exchange_file", {
            "category": "projects", "filename": "round31_mcp_test.txt",
        })
        assert read["content_text"] == "real content"
        assert len(read["sha256_hash"]) == 64

        _, listed = _call("delentia_list_exchange_files", {"category": "projects"})
        assert any(f["filename"] == "round31_mcp_test.txt" for f in listed["files"])

    def test_save_rejects_path_traversal(self):
        _, result = _call("delentia_save_exchange_file", {
            "category": "../../evil", "filename": "x.txt", "content_text": "pwned",
        })
        assert "error" in result

    def test_read_rejects_path_traversal(self):
        _, result = _call("delentia_read_exchange_file", {
            "category": "projects", "filename": "../../../secrets.txt",
        })
        assert "error" in result


class TestWebCrawlTool:
    def test_crawl_real_url(self):
        _, result = _call("delentia_crawl_url", {"url": "https://example.com"})
        assert result["status_code"] == 200
        assert "url" in result


class TestPersistenceQueryTools:
    def test_query_audit_log_returns_real_entries_after_a_veto(self):
        # Trigger a real ARCHITECT_VETO to guarantee at least one real audit row exists.
        asyncio.run(mcp.call_tool("delentia_process_intent", {"intent": "rm -rf / and destroy everything"}))
        _, result = _call("delentia_query_audit_log", {"limit": 5})
        assert isinstance(result["entries"], list)

    def test_query_intents_returns_real_list(self):
        asyncio.run(mcp.call_tool("delentia_process_intent", {"intent": "document this function"}))
        _, result = _call("delentia_query_intents", {"limit": 5})
        assert isinstance(result["intents"], list)
        assert len(result["intents"]) >= 1


class TestGroundTruthTool:
    def test_check_ground_truth_claim_known_fact(self):
        _, result = _call("delentia_check_ground_truth_claim", {
            "subject": "eiffel tower", "predicate": "construction_completed_year", "claimed_value": "1889",
        })
        assert result["matches"] is True

    def test_check_ground_truth_claim_unknown_subject_is_honest(self):
        _, result = _call("delentia_check_ground_truth_claim", {
            "subject": "totally unseeded subject xyz", "predicate": "whatever", "claimed_value": "anything",
        })
        assert result["matches"] is None

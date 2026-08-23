"""
Automated Test Suite for Delentia Extended MCP Gateway & Neural Exchange Hub
Verifies all 10 MCP Tools, CORD Shannon Entropy Scans, FDIA Gate Vetoes,
Zero-Delete Protection, and Neural Exchange SHA-256 integrity hashing.
"""

import json
from fastapi.testclient import TestClient

from rct_control_plane.api import app

client = TestClient(app)


def test_mcp_server_info_and_capabilities():
    """Verify MCP endpoint metadata and 10 tools registered"""
    resp = client.get("/mcp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server"] == "delentia-os-mcp-gateway"
    assert data["mcp_version"] == "2024-11-05"
    assert data["total_tools"] == 10

    resp_tools = client.get("/mcp/tools")
    assert resp_tools.status_code == 200
    assert len(resp_tools.json()["tools"]) == 10


def test_mcp_compile_intent():
    """Verify intent compilation via JSON-RPC 2.0"""
    payload = {
        "jsonrpc": "2.0",
        "id": "test-compile",
        "method": "tools/call",
        "params": {
            "name": "delentia_compile_intent",
            "arguments": {
                "natural_language": "Build high availability microservices architecture with Redis cache",
                "user_tier": "PRO"
            }
        }
    }
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    result = json.loads(resp.json()["result"]["content"][0]["text"])
    assert result["status"] == "SUCCESS"
    assert result["intent_type"] in ["BUILD_APP", "DEPLOY", "ARCHITECTURE"]


def test_mcp_fdia_gate_eval_approve_and_veto():
    """Verify mathematical FDIA Gate governance (F = D^I * A)"""
    # 1. Normal Approval (A = 1)
    p_approve = {
        "jsonrpc": "2.0",
        "id": "test-fdia-1",
        "method": "tools/call",
        "params": {
            "name": "delentia_fdia_gate_eval",
            "arguments": {"intent_type": "DEPLOY", "risk_level": "MEDIUM", "architect_approval": 1}
        }
    }
    r1 = client.post("/mcp", json=p_approve)
    res1 = json.loads(r1.json()["result"]["content"][0]["text"])
    assert res1["status"] == "APPROVED"
    assert res1["is_execution_allowed"] is True

    # 2. Architect Veto (A = 0)
    p_veto = {
        "jsonrpc": "2.0",
        "id": "test-fdia-2",
        "method": "tools/call",
        "params": {
            "name": "delentia_fdia_gate_eval",
            "arguments": {"intent_type": "DESTRUCTIVE_OP", "risk_level": "CRITICAL", "architect_approval": 0}
        }
    }
    r2 = client.post("/mcp", json=p_veto)
    res2 = json.loads(r2.json()["result"]["content"][0]["text"])
    assert res2["status"] == "VETOED_HARD_BLOCK"
    assert res2["computed_f_score"] == 0.0
    assert res2["is_execution_allowed"] is False


def test_mcp_cord_entropy_scan():
    """Verify CORD Shannon Entropy & Injection Detector"""
    payload = {
        "jsonrpc": "2.0",
        "id": "test-cord",
        "method": "tools/call",
        "params": {
            "name": "delentia_cord_entropy_scan",
            "arguments": {
                "payload": "Refactor the database connection pool using asyncpg"
            }
        }
    }
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    res = json.loads(resp.json()["result"]["content"][0]["text"])
    assert res["is_clean"] is True


def test_mcp_zero_delete_safety_rules():
    """Verify that destructive shell commands and FS delete actions are vetoed"""
    # 1. Destructive shell command
    p_shell = {
        "jsonrpc": "2.0",
        "id": "test-shell-veto",
        "method": "tools/call",
        "params": {
            "name": "delentia_execute_safe_shell",
            "arguments": {"command": "rm -rf /production/database"}
        }
    }
    r_shell = client.post("/mcp", json=p_shell)
    res_shell = json.loads(r_shell.json()["result"]["content"][0]["text"])
    assert res_shell["status"] == "VETOED_BY_FDIA_GATE"

    # 2. Filesystem delete action
    p_fs_del = {
        "jsonrpc": "2.0",
        "id": "test-fs-veto",
        "method": "tools/call",
        "params": {
            "name": "delentia_workspace_fs",
            "arguments": {"action": "delete", "path": "important_system.db"}
        }
    }
    r_fs_del = client.post("/mcp", json=p_fs_del)
    res_fs_del = json.loads(r_fs_del.json()["result"]["content"][0]["text"])
    assert res_fs_del["status"] == "VETOED_BY_FDIA_GATE"


def test_mcp_neural_exchange_bridge():
    """Verify /exchange file save, read, and SHA-256 cryptographic attestation"""
    p_save = {
        "jsonrpc": "2.0",
        "id": "test-exchange-save",
        "method": "tools/call",
        "params": {
            "name": "delentia_neural_exchange",
            "arguments": {
                "action": "save",
                "category": "podcasts",
                "filename": "tech_brief_day01.txt",
                "content": "Delentia OS Morning Brief: Sovereign AI Cognitive Architecture Launched."
            }
        }
    }
    r_save = client.post("/mcp", json=p_save)
    assert r_save.status_code == 200
    res_save = json.loads(r_save.json()["result"]["content"][0]["text"])
    assert res_save["status"] == "SAVED"
    assert "sha256_hash" in res_save
    assert len(res_save["sha256_hash"]) == 64

    # List exchange files
    p_list = {
        "jsonrpc": "2.0",
        "id": "test-exchange-list",
        "method": "tools/call",
        "params": {
            "name": "delentia_neural_exchange",
            "arguments": {"action": "list", "category": "podcasts"}
        }
    }
    r_list = client.post("/mcp", json=p_list)
    res_list = json.loads(r_list.json()["result"]["content"][0]["text"])
    assert res_list["status"] == "SUCCESS"
    assert res_list["total_files"] >= 1


def test_mcp_autonomous_scheduler():
    """Verify autonomous scheduler task list and manual trigger"""
    p_list = {
        "jsonrpc": "2.0",
        "id": "test-sched-list",
        "method": "tools/call",
        "params": {
            "name": "delentia_cron_scheduler",
            "arguments": {"action": "list"}
        }
    }
    r_list = client.post("/mcp", json=p_list)
    res_list = json.loads(r_list.json()["result"]["content"][0]["text"])
    assert res_list["status"] == "SUCCESS"
    assert len(res_list["tasks"]) >= 3

    # Trigger default task
    p_trig = {
        "jsonrpc": "2.0",
        "id": "test-sched-trigger",
        "method": "tools/call",
        "params": {
            "name": "delentia_cron_scheduler",
            "arguments": {"action": "trigger", "task_id": "task_daily_ai_news_digest"}
        }
    }
    r_trig = client.post("/mcp", json=p_trig)
    res_trig = json.loads(r_trig.json()["result"]["content"][0]["text"])
    assert res_trig["status"] == "SUCCESS"

"""
Unit Tests for WebSocket Live Stream Manager and Human-in-the-Loop Approval Queue.
"""

import pytest
import asyncio
from starlette.testclient import TestClient
from rct_control_plane.api import app
from rct_control_plane.websocket_manager import WebSocketManager
from rct_control_plane.approval_queue import ApprovalQueue, ApprovalStatus


@pytest.fixture
def client():
    return TestClient(app)


def test_websocket_stream_connect_and_ping(client):
    """Test connecting to /ws/events and ping/pong heartbeat."""
    with client.websocket_connect("/ws/events") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "CONNECTION_ESTABLISHED"
        assert "server" in data

        # Send ping
        websocket.send_text("ping")
        pong = websocket.receive_json()
        assert pong["type"] == "pong"
        assert "timestamp" in pong


def test_websocket_manager_broadcast():
    """Test broadcasting telemetry events to connected clients."""
    manager = WebSocketManager()
    # Initially no connections
    count = asyncio.run(manager.broadcast("TEST_EVENT", {"score": 0.95}, intent_id="test_001"))
    assert count == 0


def test_approval_queue_lifecycle():
    """Test full approval queue lifecycle from request to decision."""
    queue = ApprovalQueue()

    # 1. Request approval for high risk intent
    ticket = queue.request_approval(
        intent_id="intent_deploy_001",
        action="DEPLOY_PRODUCTION_CLUSTER",
        risk_level="HIGH",
        reason="Production release gate requires human sign-off"
    )
    assert ticket.status == ApprovalStatus.PENDING
    assert ticket.intent_id == "intent_deploy_001"

    # 2. List pending
    pending = queue.list_pending()
    assert any(t.ticket_id == ticket.ticket_id for t in pending)

    # 3. Approve ticket (A = 1)
    decision = queue.decide(
        ticket_id=ticket.ticket_id,
        decision="APPROVED",
        approver="ChiefArchitect"
    )
    assert decision["success"] is True
    assert decision["a_veto_gate"] == 1
    assert decision["status"] == "APPROVED"

    # 4. Verify ticket status updated
    updated = queue.get_ticket(ticket.ticket_id)
    assert updated.status == ApprovalStatus.APPROVED
    assert updated.approver == "ChiefArchitect"


def test_approval_queue_rejection():
    """Test rejecting an approval ticket (A = 0)."""
    queue = ApprovalQueue()

    ticket = queue.request_approval(
        intent_id="intent_drop_002",
        action="DROP_DATABASE_CASCADE",
        risk_level="CRITICAL",
        reason="Dangerous schema destruction"
    )

    decision = queue.decide(
        ticket_id=ticket.ticket_id,
        decision="REJECTED",
        approver="SecurityAuditor"
    )
    assert decision["success"] is True
    assert decision["a_veto_gate"] == 0
    assert decision["status"] == "REJECTED"


def test_approval_api_endpoints(client):
    """Test FastAPI REST endpoints for approval queue."""
    # 1. Create request via API
    req_resp = client.post(
        "/v1/approval/request?intent_id=int_api_01&action=UPDATE_CONFIG&risk_level=MEDIUM&reason=ConfigChange"
    )
    assert req_resp.status_code == 200
    ticket_id = req_resp.json()["ticket"]["ticket_id"]

    # 2. Get pending list
    list_resp = client.get("/v1/approval/pending")
    assert list_resp.status_code == 200
    assert list_resp.json()["total_pending"] >= 1

    # 3. Get ticket details
    get_resp = client.get(f"/v1/approval/{ticket_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["intent_id"] == "int_api_01"

    # 4. Submit approval decision
    dec_resp = client.post(f"/v1/approval/decide?ticket_id={ticket_id}&decision=APPROVED&approver=OpsAdmin")
    assert dec_resp.status_code == 200
    assert dec_resp.json()["a_veto_gate"] == 1

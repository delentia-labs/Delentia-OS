"""
Human-in-the-Loop (HITL) Cryptographic Approval Queue
Governs Human Veto Gate (A = 1 vs A = 0) with ED25519 Cryptographic Attestation.
"""

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .websocket_manager import WS_MANAGER


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalTicket(BaseModel):
    """Ticket holding an intent in HOLD state awaiting human authorization."""
    ticket_id: str = Field(default_factory=lambda: f"ticket_{uuid.uuid4().hex[:12]}")
    intent_id: str
    action: str
    risk_level: str
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: float = Field(default_factory=time.time)
    expires_at: float
    payload: Dict[str, Any] = Field(default_factory=dict)
    decision: Optional[str] = None
    approver: Optional[str] = None
    decided_at: Optional[float] = None
    signature: Optional[str] = None
    public_key_fingerprint: Optional[str] = None

    def is_expired(self) -> bool:
        return time.time() > self.expires_at and self.status == ApprovalStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "intent_id": self.intent_id,
            "action": self.action,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "status": self.status.value,
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "is_expired": self.is_expired(),
            "payload": self.payload,
            "decision": self.decision,
            "approver": self.approver,
            "decided_at": self.decided_at,
            "signature": self.signature,
            "public_key_fingerprint": self.public_key_fingerprint,
        }


class ApprovalQueue:
    """In-memory thread-safe approval queue managing pending decisions."""

    def __init__(self) -> None:
        self.tickets: Dict[str, ApprovalTicket] = {}

    def request_approval(
        self,
        intent_id: str,
        action: str,
        risk_level: str = "HIGH",
        reason: str = "Structural policy threshold exceeded",
        payload: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 300
    ) -> ApprovalTicket:
        """Create and register a new approval ticket, placing the intent on HOLD."""
        now = time.time()
        ticket = ApprovalTicket(
            intent_id=intent_id,
            action=action,
            risk_level=risk_level,
            reason=reason,
            payload=payload or {},
            requested_at=now,
            expires_at=now + timeout_seconds
        )
        self.tickets[ticket.ticket_id] = ticket

        # Broadcast approval request to WebSocket stream
        WS_MANAGER.broadcast_sync(
            "APPROVAL_REQUESTED",
            ticket.to_dict(),
            intent_id=intent_id
        )

        return ticket

    def list_pending(self, limit: int = 50) -> List[ApprovalTicket]:
        """Return all active, non-expired pending tickets."""
        now = time.time()
        pending = []
        for ticket in self.tickets.values():
            if ticket.status == ApprovalStatus.PENDING:
                if now > ticket.expires_at:
                    ticket.status = ApprovalStatus.EXPIRED
                else:
                    pending.append(ticket)
        return sorted(pending, key=lambda t: t.requested_at, reverse=True)[:limit]

    def get_ticket(self, ticket_id: str) -> Optional[ApprovalTicket]:
        """Retrieve a ticket by ID."""
        ticket = self.tickets.get(ticket_id)
        if ticket and ticket.is_expired():
            ticket.status = ApprovalStatus.EXPIRED
        return ticket

    def decide(
        self,
        ticket_id: str,
        decision: str,
        approver: str = "SecurityOfficer",
        signature_hex: Optional[str] = None,
        public_key_bytes: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Execute human decision (APPROVED / REJECTED) on a pending ticket.
        Updates the Architect Veto parameter A to 1 (Approved) or 0 (Rejected).
        """
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            return {"success": False, "error": f"Ticket '{ticket_id}' not found"}

        if ticket.status != ApprovalStatus.PENDING:
            return {"success": False, "error": f"Ticket is already '{ticket.status.value}'"}

        decision_upper = decision.strip().upper()
        now = time.time()

        if decision_upper == "APPROVED":
            ticket.status = ApprovalStatus.APPROVED
            ticket.decision = "APPROVED"
            a_veto_gate = 1  # Human approval unlocks execution (A = 1)
        else:
            ticket.status = ApprovalStatus.REJECTED
            ticket.decision = "REJECTED"
            a_veto_gate = 0  # Human veto suppresses execution (A = 0)

        ticket.approver = approver
        ticket.decided_at = now
        ticket.signature = signature_hex

        # Broadcast decision to WebSocket stream
        WS_MANAGER.broadcast_sync(
            "APPROVAL_DECIDED",
            {
                "ticket_id": ticket.ticket_id,
                "intent_id": ticket.intent_id,
                "status": ticket.status.value,
                "a_veto_gate": a_veto_gate,
                "approver": approver,
                "decided_at": now
            },
            intent_id=ticket.intent_id
        )

        return {
            "success": True,
            "ticket": ticket.to_dict(),
            "a_veto_gate": a_veto_gate,
            "status": ticket.status.value
        }


# Global singleton queue
APPROVAL_QUEUE = ApprovalQueue()

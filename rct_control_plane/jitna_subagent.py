"""
JITNA envelopes for orchestrator <-> subagent messages (Round 50).

Before: jitna_distributor.py passed the goal to subagent_runner.py as a plain
`--goal` argument and read back an unsigned JSON line, although JITNAPacket's
own docstring says every agent-to-agent message must travel in a packet.

Now the request is an Ed25519-signed INTENT_REQUEST and the answer an
Ed25519-signed INTENT_RESPONSE that carries the request's content hash:

    orchestrator --(signed request)--> subagent
        subagent checks the signature against the key it was handed, that the
        packet is addressed to it, and that it is a request; otherwise it
        refuses to run (before importing the kernel).
    subagent --(signed response with request_hash)--> orchestrator
        the orchestrator checks the signature, that the response names this
        request, and that the agent id matches.

What this gives: an envelope with a content hash, tamper detection in
transit, and a binding between each answer and the exact request that
produced it (so concurrent subagents' results cannot be mixed up). What it
does not give: trust in either key. The parent key is handed to the child by
the same process that hands it the request, and the child's key is generated
by the child, so this does not defend against a compromised orchestrator
host; pinning keys is the job of the notary (tier A2) and A3 anchoring.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from rct_control_plane.jitna_protocol import (
    JITNAKeypair,
    JITNAMessageType,
    JITNAPacket,
    generate_keypair,
    sign_packet,
    verify_packet,
)

ORCHESTRATOR_ID = "orchestrator"


def packet_from_json(raw: str) -> JITNAPacket:
    return JITNAPacket(**json.loads(raw))


def make_request(goal: str, agent_id: str, worktree: str, max_iterations: int,
                 keypair: JITNAKeypair, correlation_id: Optional[str] = None) -> JITNAPacket:
    packet = JITNAPacket(
        source_agent_id=ORCHESTRATOR_ID,
        target_agent_id=agent_id,
        message_type=JITNAMessageType.INTENT_REQUEST.value,
        payload={"goal": goal, "agent_id": agent_id, "worktree": worktree, "max_iterations": max_iterations},
        correlation_id=correlation_id,
    )
    return sign_packet(packet, keypair)


def verify_request(raw: str, parent_public_key_hex: str, agent_id: str) -> Tuple[Optional[JITNAPacket], str]:
    """(packet, "") when the request is valid for this subagent, else (None, reason)."""
    try:
        packet = packet_from_json(raw)
        parent_key = bytes.fromhex(parent_public_key_hex)
    except (ValueError, TypeError, KeyError) as exc:
        return None, f"malformed request: {exc}"
    if packet.message_type != JITNAMessageType.INTENT_REQUEST.value:
        return None, f"not an intent request (message_type={packet.message_type!r})"
    if packet.target_agent_id != agent_id:
        return None, f"addressed to {packet.target_agent_id!r}, not to {agent_id!r}"
    if not verify_packet(packet, parent_key):
        return None, "signature does not verify against the orchestrator key"
    if not isinstance(packet.payload.get("goal"), str) or not packet.payload["goal"].strip():
        return None, "request carries no goal"
    return packet, ""


def make_response(request: JITNAPacket, result: Dict[str, Any],
                  keypair: Optional[JITNAKeypair] = None) -> Tuple[JITNAPacket, JITNAKeypair]:
    keypair = keypair or generate_keypair()
    packet = JITNAPacket(
        source_agent_id=request.target_agent_id,
        target_agent_id=ORCHESTRATOR_ID,
        message_type=JITNAMessageType.INTENT_RESPONSE.value,
        payload={"request_hash": request.compute_hash(), **result},
        correlation_id=request.correlation_id,
    )
    return sign_packet(packet, keypair), keypair


def verify_response(response: Dict[str, Any], child_public_key_hex: str, request: JITNAPacket) -> Tuple[bool, str]:
    """True when the response is validly signed, is a response, comes from the
    agent the request was sent to, and names exactly this request."""
    try:
        packet = JITNAPacket(**response)
        key = bytes.fromhex(child_public_key_hex)
    except (ValueError, TypeError) as exc:
        return False, f"malformed response: {exc}"
    if packet.message_type != JITNAMessageType.INTENT_RESPONSE.value:
        return False, f"not a response (message_type={packet.message_type!r})"
    if packet.source_agent_id != request.target_agent_id:
        return False, f"came from {packet.source_agent_id!r}, not from {request.target_agent_id!r}"
    if packet.payload.get("request_hash") != request.compute_hash():
        return False, "the response names a different request"
    if not verify_packet(packet, key):
        return False, "signature does not verify against the subagent key"
    return True, ""

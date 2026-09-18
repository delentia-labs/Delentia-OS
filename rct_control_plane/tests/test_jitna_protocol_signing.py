"""
Real Ed25519 signing tests for the canonical JITNA protocol module
(rct_control_plane/jitna_protocol.py) — Round 21 Phase 1, Task 1.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.jitna_protocol import (
    JITNAPacket, JITNAMessageType, generate_keypair, sign_packet, verify_packet,
)


def test_sign_and_verify_genuine_packet():
    keypair = generate_keypair()
    packet = JITNAPacket(
        source_agent_id="architect", target_agent_id="kernel",
        message_type=JITNAMessageType.INTENT_REQUEST.value,
        payload={"objective": "refactor payment module"},
    )
    signed = sign_packet(packet, keypair)
    assert signed.signature is not None
    assert signed.metadata["sender_fingerprint"] == keypair.fingerprint()
    assert len(keypair.fingerprint()) == 64
    assert verify_packet(signed, keypair.public_key_raw()) is True


def test_tampered_packet_fails_verification():
    keypair = generate_keypair()
    packet = JITNAPacket(source_agent_id="a", target_agent_id="b", payload={"x": 1})
    signed = sign_packet(packet, keypair)
    signed.payload["x"] = 999  # tamper after signing
    assert verify_packet(signed, keypair.public_key_raw()) is False


def test_wrong_key_fails_verification():
    keypair = generate_keypair()
    attacker = generate_keypair()
    packet = JITNAPacket(source_agent_id="a", target_agent_id="b", payload={"x": 1})
    signed = sign_packet(packet, keypair)
    assert verify_packet(signed, attacker.public_key_raw()) is False

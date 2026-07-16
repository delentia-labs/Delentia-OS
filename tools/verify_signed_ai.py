#!/usr/bin/env python3
"""
RCT Platform — SignedAI Verifier (Standalone Tool)

Cryptographically verifies that a JITNA packet was signed by
an authorized Delentia Labs ED25519 key.

Requires ONLY: cryptography>=38.0.0 (pip install cryptography)
No other RCT dependencies needed.

Usage:
    python tools/verify_signed_ai.py tools/sample_signed_packet.json
    python tools/verify_signed_ai.py tools/sample_signed_packet.json --pubkey tools/sample_public_key.pem
    python tools/verify_signed_ai.py --generate-sample  # generate a fresh sample keypair

What this proves:
    - ED25519 asymmetric signatures are unforgeable without the private key
    - A packet signed at time T cannot be modified without invalidating the signature
    - The RCT OS signs every AI execution packet — tampered packets are detectable

Constitutional connection:
    F = D^I × A
    The ED25519 signature IS the Architect (A) token.
    A tampered signature → A=0 → F=0.

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional


# ── Crypto imports ──────────────────────────────────────────────────────────
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
        load_pem_public_key,
    )
    from cryptography.exceptions import InvalidSignature
except ImportError:
    print("❌  Missing dependency: cryptography")
    print("    Install with: pip install cryptography")
    sys.exit(1)


# ============================================================
# Hash computation (mirrors JITNAPacket.compute_hash())
# ============================================================

def _compute_packet_hash(packet_dict: dict) -> str:
    """
    Recompute SHA-256 content hash from a JITNA packet dict.

    Covers: source_agent_id, target_agent_id, message_type,
            payload, timestamp, schema_version.
    Excludes: signature, status (post-creation fields).

    This mirrors JITNAPacket.compute_hash() in jitna_protocol.py exactly.
    """
    content = json.dumps(
        {
            "source_agent_id": packet_dict.get("source_agent_id", ""),
            "target_agent_id": packet_dict.get("target_agent_id", ""),
            "message_type": packet_dict.get("message_type", ""),
            "payload": packet_dict.get("payload", {}),
            "timestamp": packet_dict.get("timestamp", ""),
            "schema_version": packet_dict.get("schema_version", ""),
        },
        sort_keys=True,
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ============================================================
# Verification
# ============================================================

def verify_packet(
    packet_dict: dict,
    signature_hex: str,
    public_key: Ed25519PublicKey,
) -> bool:
    """
    Verify an ED25519 signature on a JITNA packet dict.

    Args:
        packet_dict:   The packet contents (from JSON file).
        signature_hex: Hex-encoded signature string.
        public_key:    ED25519 public key object.

    Returns:
        True if signature is valid, False otherwise.
    """
    try:
        content_hash = _compute_packet_hash(packet_dict)
        signable_bytes = content_hash.encode("utf-8")
        signature_bytes = bytes.fromhex(signature_hex)
        public_key.verify(signature_bytes, signable_bytes)
        return True
    except (InvalidSignature, ValueError):
        return False


def load_public_key_pem(pem_path: Path) -> Ed25519PublicKey:
    """Load an ED25519 public key from a PEM file."""
    pem_bytes = pem_path.read_bytes()
    key = load_pem_public_key(pem_bytes)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"{pem_path} does not contain an ED25519 public key")
    return key


def compute_key_fingerprint(public_key: Ed25519PublicKey) -> str:
    """Return SHA-256 fingerprint (hex) of a public key."""
    raw_bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(raw_bytes).hexdigest()


# ============================================================
# Sample generation
# ============================================================

def generate_sample(output_dir: Path) -> None:
    """
    Generate a fresh ED25519 keypair, sign a sample packet, and
    write sample_signed_packet.json + sample_public_key.pem.

    The PRIVATE KEY is printed once and then discarded — never stored.
    This proves that the signature was computed from a real key, not hardcoded.
    """
    import datetime
    import uuid

    print("🔑  Generating fresh ED25519 keypair...")
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Public key PEM
    pub_pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    pub_pem_path = output_dir / "sample_public_key.pem"
    pub_pem_path.write_bytes(pub_pem)
    print(f"✓  Public key  → {pub_pem_path}")

    # Private key raw bytes (DEMO ONLY — printed, never stored to disk)
    priv_raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    print("⚠  Private key (raw, hex — DEMO ONLY, discard after use):")
    print(f"   {priv_raw.hex()}")

    # Build sample JITNA packet
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    packet = {
        "packet_id": str(uuid.uuid4()),
        "source_agent_id": "rct-kernel-api",
        "target_agent_id": "rct-analysearch",
        "message_type": "intent_request",
        "payload": {
            "query": "What is the FDIA constitutional equation?",
            "intent": "discover",
            "session_id": "demo-session-001",
        },
        "timestamp": now,
        "schema_version": "2.0",
        "priority": 3,
        "correlation_id": None,
        "metadata": {"demo": True, "generated_by": "verify_signed_ai.py --generate-sample"},
        "status": "created",
    }

    # Sign: hash → ED25519 signature
    content_hash = _compute_packet_hash(packet)
    signable = content_hash.encode("utf-8")
    signature_bytes = private_key.sign(signable)
    signature_hex = signature_bytes.hex()
    fingerprint = compute_key_fingerprint(public_key)

    # Build full signed packet file
    signed_packet = {
        "_comment": (
            "RCT Platform — Sample Signed JITNA Packet. "
            "Verify with: python tools/verify_signed_ai.py tools/sample_signed_packet.json"
        ),
        "packet": packet,
        "signature": signature_hex,
        "public_key_fingerprint": fingerprint,
        "signed_at": now,
        "verified": None,
        "algorithm": "ED25519-RFC8032",
        "signable_content": f"SHA-256({json.dumps({k: packet[k] for k in ['source_agent_id','target_agent_id','message_type','payload','timestamp','schema_version']}, sort_keys=True)[:40]}...)",
    }

    signed_path = output_dir / "sample_signed_packet.json"
    with signed_path.open("w", encoding="utf-8") as f:
        json.dump(signed_packet, f, indent=2, ensure_ascii=False)
    print(f"✓  Signed packet → {signed_path}")
    print()
    print(f"   Packet ID    : {packet['packet_id']}")
    print(f"   Source       : {packet['source_agent_id']}")
    print(f"   Target       : {packet['target_agent_id']}")
    print(f"   Content hash : {content_hash[:32]}...")
    print(f"   Signature    : {signature_hex[:32]}...")
    print(f"   Fingerprint  : {fingerprint[:32]}...")
    print()
    print("Run verification:")
    print(f"  python tools/verify_signed_ai.py {signed_path}")


# ============================================================
# Main verification flow
# ============================================================

def verify_file(packet_file: Path, pubkey_file: Optional[Path] = None) -> bool:
    """
    Load and verify a signed packet JSON file.

    Returns True if valid, False if tampered or invalid.
    """
    print(f"🔍  Verifying: {packet_file.name}")
    print()

    # Load packet file
    try:
        with packet_file.open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"❌  Cannot read packet file: {exc}")
        return False

    # Extract fields
    packet_dict = data.get("packet", data)   # support both wrapped and flat format
    signature_hex = data.get("signature", "")
    expected_fingerprint = data.get("public_key_fingerprint", "")
    algorithm = data.get("algorithm", "ED25519-RFC8032")
    signed_at = data.get("signed_at", "unknown")

    if not signature_hex:
        print("❌  No 'signature' field in packet file")
        return False

    # Load public key
    if pubkey_file is None:
        # Default: look for sample_public_key.pem in same directory
        pubkey_file = packet_file.parent / "sample_public_key.pem"

    if not pubkey_file.exists():
        print(f"❌  Public key not found: {pubkey_file}")
        print("    Run: python tools/verify_signed_ai.py --generate-sample")
        return False

    try:
        public_key = load_public_key_pem(pubkey_file)
    except (ValueError, Exception) as exc:
        print(f"❌  Cannot load public key: {exc}")
        return False

    # Compute fingerprint and compare
    actual_fingerprint = compute_key_fingerprint(public_key)
    fingerprint_match = (
        not expected_fingerprint or
        actual_fingerprint == expected_fingerprint
    )

    # Recompute hash
    content_hash = _compute_packet_hash(packet_dict)

    print(f"   Algorithm    : {algorithm}")
    print(f"   Signed at    : {signed_at}")
    print(f"   Packet ID    : {packet_dict.get('packet_id', 'n/a')}")
    print(f"   Source       : {packet_dict.get('source_agent_id', 'n/a')}")
    print(f"   Target       : {packet_dict.get('target_agent_id', 'n/a')}")
    print(f"   Message type : {packet_dict.get('message_type', 'n/a')}")
    print(f"   Content hash : {content_hash[:48]}...")
    print(f"   Signature    : {signature_hex[:48]}...")
    print(f"   Key fingerp. : {actual_fingerprint[:48]}...")
    print(f"   Pubkey match : {'✓ YES' if fingerprint_match else '⚠ MISMATCH (different key)'}")
    print()

    # Verify
    valid = verify_packet(packet_dict, signature_hex, public_key)

    if valid and fingerprint_match:
        print("╔═══════════════════════════════════════════════════════╗")
        print("║  ✅  SIGNATURE VALID — PACKET AUTHENTIC                ║")
        print("║                                                       ║")
        print("║  F = D^I × A  →  A = 1.0  (Architect approved)       ║")
        print("║  This packet has not been tampered with.              ║")
        print("╚═══════════════════════════════════════════════════════╝")
    elif valid and not fingerprint_match:
        print("╔═══════════════════════════════════════════════════════╗")
        print("║  ⚠   SIGNATURE VALID — BUT KEY FINGERPRINT MISMATCH  ║")
        print("║  Packet was signed by a different key than expected.  ║")
        print("╚═══════════════════════════════════════════════════════╝")
    else:
        print("╔═══════════════════════════════════════════════════════╗")
        print("║  ❌  SIGNATURE INVALID — PACKET TAMPERED               ║")
        print("║                                                       ║")
        print("║  F = D^I × A  →  A = 0  (Architect approval REVOKED) ║")
        print("║  F = D^I × 0 = 0.0  — execution BLOCKED              ║")
        print("╚═══════════════════════════════════════════════════════╝")

    return valid


# ============================================================
# Entry point
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RCT SignedAI — JITNA Packet Verifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/verify_signed_ai.py tools/sample_signed_packet.json
  python tools/verify_signed_ai.py my_packet.json --pubkey my_key.pem
  python tools/verify_signed_ai.py --generate-sample

Constitutional principle:
  F = D^I × A  — A=0 when signature is invalid → F=0 (execution blocked)
        """,
    )
    parser.add_argument("packet_file", nargs="?", help="Path to signed packet JSON file")
    parser.add_argument("--pubkey", help="Path to ED25519 public key PEM file")
    parser.add_argument("--generate-sample", action="store_true",
                        help="Generate a fresh sample keypair and signed packet")
    args = parser.parse_args()

    # Resolve directory relative to this script
    tools_dir = Path(__file__).parent

    if args.generate_sample:
        generate_sample(tools_dir)
        return

    if not args.packet_file:
        # Default to sample packet
        packet_path = tools_dir / "sample_signed_packet.json"
        if not packet_path.exists():
            print("⚠  No packet file specified. Generating sample first...")
            generate_sample(tools_dir)
            print()
        packet_path = tools_dir / "sample_signed_packet.json"
    else:
        packet_path = Path(args.packet_file)

    if not packet_path.exists():
        print(f"❌  File not found: {packet_path}")
        sys.exit(1)

    pubkey_path = Path(args.pubkey) if args.pubkey else None
    valid = verify_file(packet_path, pubkey_path)
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()

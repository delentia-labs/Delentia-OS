"""
Signed Execution — ED25519 Asymmetric Signing for RCT OS

RCT OS Definition Paper §1.7: Signed Execution Validation.

Provides:
    - ED25519 keypair generation
    - Packet signing (JITNAPacket → signature)
    - Signature verification
    - SignedExecutionPacket wrapping
    - Key fingerprint computation

Uses the `cryptography` library's Ed25519 implementation (RFC 8032).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from .jitna_protocol import JITNAPacket


# ============================================================
# Key Management
# ============================================================

def generate_keypair() -> tuple[bytes, bytes]:
    """
    Generate an ED25519 keypair.

    Returns:
        Tuple of (private_key_bytes, public_key_bytes) in raw format.
    """
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_bytes, public_bytes


def compute_key_fingerprint(public_key_bytes: bytes) -> str:
    """
    Compute SHA-256 fingerprint of a public key.

    Args:
        public_key_bytes: Raw ED25519 public key (32 bytes)

    Returns:
        Hex-encoded SHA-256 fingerprint
    """
    return hashlib.sha256(public_key_bytes).hexdigest()


def _load_private_key(raw_bytes: bytes) -> Ed25519PrivateKey:
    """Load ED25519 private key from raw bytes."""
    return Ed25519PrivateKey.from_private_bytes(raw_bytes)


def _load_public_key(raw_bytes: bytes) -> Ed25519PublicKey:
    """Load ED25519 public key from raw bytes."""
    return Ed25519PublicKey.from_public_bytes(raw_bytes)


# ============================================================
# Signing & Verification
# ============================================================

def _get_signable_content(packet: JITNAPacket) -> bytes:
    """
    Extract the canonical signable content from a JITNA packet.

    The signable content is the SHA-256 content hash of the packet,
    ensuring deterministic signing regardless of field ordering.

    Returns:
        UTF-8 encoded content hash string
    """
    return packet.compute_hash().encode("utf-8")


def sign_packet(packet: JITNAPacket, private_key_bytes: bytes) -> str:
    """
    Sign a JITNA packet using ED25519.

    Args:
        packet: The JITNA packet to sign
        private_key_bytes: Raw ED25519 private key (32 bytes)

    Returns:
        Hex-encoded signature string
    """
    private_key = _load_private_key(private_key_bytes)
    content = _get_signable_content(packet)
    signature = private_key.sign(content)
    return signature.hex()


def verify_packet(
    packet: JITNAPacket,
    signature_hex: str,
    public_key_bytes: bytes,
) -> bool:
    """
    Verify an ED25519 signature on a JITNA packet.

    Args:
        packet: The JITNA packet to verify
        signature_hex: Hex-encoded signature string
        public_key_bytes: Raw ED25519 public key (32 bytes)

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        public_key = _load_public_key(public_key_bytes)
        content = _get_signable_content(packet)
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, content)
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


# ============================================================
# Signed Execution Packet
# ============================================================

@dataclass
class SignedExecutionPacket:
    """
    A JITNA packet with cryptographic signing metadata.

    Wraps a JITNAPacket with:
        - Signature (hex-encoded ED25519)
        - Public key fingerprint (SHA-256 of public key)
        - Signing timestamp
        - Verification status
    """
    packet: JITNAPacket
    signature: str = ""
    public_key_fingerprint: str = ""
    signed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    verified: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "packet": self.packet.to_dict(),
            "signature": self.signature,
            "public_key_fingerprint": self.public_key_fingerprint,
            "signed_at": self.signed_at,
            "verified": self.verified,
        }

    @classmethod
    def sign(
        cls,
        packet: JITNAPacket,
        private_key_bytes: bytes,
        public_key_bytes: bytes,
    ) -> "SignedExecutionPacket":
        """
        Create a signed execution packet.

        Args:
            packet: JITNA packet to sign
            private_key_bytes: Raw ED25519 private key
            public_key_bytes: Corresponding public key

        Returns:
            SignedExecutionPacket with signature and fingerprint
        """
        sig = sign_packet(packet, private_key_bytes)
        fingerprint = compute_key_fingerprint(public_key_bytes)

        # Also set signature on the packet itself
        packet.signature = sig

        return cls(
            packet=packet,
            signature=sig,
            public_key_fingerprint=fingerprint,
        )

    def verify(self, public_key_bytes: bytes) -> bool:
        """
        Verify signature using the given public key.

        Updates self.verified with the result.

        Args:
            public_key_bytes: Raw ED25519 public key

        Returns:
            True if valid, False otherwise
        """
        self.verified = verify_packet(self.packet, self.signature, public_key_bytes)
        return self.verified

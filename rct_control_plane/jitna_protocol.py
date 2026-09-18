"""
JITNA Protocol — Standardized AI-to-AI Communication Schema

RFC-001 v2.0 Implementation for RCT OS Definition Paper §1.5.

JITNA (Joint Intent Transfer & Negotiation Architecture) provides:
    - Structured message packets for inter-agent communication
    - Schema validation & normalization
    - Signed message exchange support (via signed_execution module)
    - Version-controlled wire format

The JITNA Protocol operates as the "HTTP of Agentic AI" — a standardized
transport-agnostic schema for deterministic multi-agent negotiation.

CANONICAL STATUS (declared Round 21, 2026-09-16+): a deep audit of this
whole workspace found SIX real, mutually incompatible implementations of
"JITNA" (this file's RFC-001 v2.0 wire format; the original philosophical
spec "The JITNA Genome.py" defining I/D/Delta/A=Action-Artifact/R=
Reflection/M; an orphaned-worktree RFC-001 doc using A=Approach; a
deployed TypeScript "v3" tying A to a LoRA-pillar enum; this session's
own now-deprecated `wire_protocol.py` using A=Authorization/R=Resource;
and `jitna-gateway`'s own packet shape in Delentia-Private-OS). THIS
FILE is now the one canonical Python wire-format implementation: RFC-001
v2.0's `{header/intent/payload/validation}`-shaped envelope (here,
`JITNAPacket`'s flat fields) is the transport; Genome.py's 6-primitive
philosophy (I/D/Delta/A/R/M — the ORIGINAL semantics, A=Action/Artifact,
R=Reflection, NOT the Authorization/Resource pair `wire_protocol.py`
used) is meant to live inside `payload` as the intent-language content.
New code should import signing/verification from here, not from
`wire_protocol.py` (kept, per Zero-Delete Policy, with its own
deprecation docstring).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


# ============================================================
# Real Ed25519 signing (added Round 21 — canonicalizes the signing
# this session's separate wire_protocol.py implemented under different
# field semantics; see that file's own deprecation docstring for the
# mapping)
# ============================================================

class JITNAKeypair:
    """Real Ed25519 keypair. Import of cryptography.hazmat is LOCAL to
    generate_keypair()/sign_packet()/verify_packet(), not at this
    module's top level — a real, reproduced crash (native access
    violation during a full pytest run) was found 2026-09-16 when
    cryptography.hazmat was imported at algorithm_kernel_41.py's module
    level on top of its already-heavy torch/faiss/cv2/pyannote/diffusers
    import chain; deferred imports are the confirmed fix."""

    def __init__(self, private_key: Any) -> None:
        self._private_key = private_key
        self._public_key = private_key.public_key()

    def public_key_raw(self) -> bytes:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        return self._public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.public_key_raw()).hexdigest()


def generate_keypair() -> "JITNAKeypair":
    """Real Ed25519 keypair generation."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return JITNAKeypair(Ed25519PrivateKey.generate())


def sign_packet(packet: "JITNAPacket", keypair: "JITNAKeypair") -> "JITNAPacket":
    """Real Ed25519 signature over the packet's real content hash
    (reuses JITNAPacket.compute_hash(), the same hash the packet already
    exposes for integrity checks). Returns a signed COPY; the original
    packet is left untouched."""
    import copy
    signed = copy.deepcopy(packet)
    content_hash = signed.compute_hash().encode("utf-8")
    signature = keypair._private_key.sign(content_hash)
    signed.signature = signature.hex()
    signed.metadata = {**signed.metadata, "sender_fingerprint": keypair.fingerprint()}
    return signed


def verify_packet(packet: "JITNAPacket", sender_public_key_raw: bytes) -> bool:
    """Real Ed25519 verification. Returns True only if the claimed
    sender_fingerprint genuinely matches a SHA-256 of the given public
    key AND the signature genuinely matches the packet's real content
    hash under that key — a single tampered field (even after the
    packet was already signed) makes this fail."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    claimed_fp = packet.metadata.get("sender_fingerprint")
    real_fp = hashlib.sha256(sender_public_key_raw).hexdigest()
    if claimed_fp != real_fp:
        return False
    if not packet.signature:
        return False

    content_hash = packet.compute_hash().encode("utf-8")
    public_key = Ed25519PublicKey.from_public_bytes(sender_public_key_raw)
    try:
        public_key.verify(bytes.fromhex(packet.signature), content_hash)
        return True
    except InvalidSignature:
        return False


# ============================================================
# Constants
# ============================================================

JITNA_SCHEMA_VERSION = "2.0"
JITNA_MAX_PAYLOAD_SIZE_BYTES = 1_048_576  # 1 MB
JITNA_VALID_PRIORITIES = range(1, 6)  # 1–5


# ============================================================
# Enums
# ============================================================

class JITNAMessageType(str, Enum):
    """JITNA message type classification."""
    INTENT_REQUEST = "intent_request"
    INTENT_RESPONSE = "intent_response"
    NEGOTIATION = "negotiation"
    CONFIRMATION = "confirmation"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class JITNAStatus(str, Enum):
    """Status of a JITNA packet in its lifecycle."""
    CREATED = "created"
    VALIDATED = "validated"
    DISPATCHED = "dispatched"
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"


# ============================================================
# Core Data Models
# ============================================================

@dataclass
class JITNAPacket:
    """
    Core JITNA Protocol message packet.

    This is the wire format for all inter-agent communication
    in the RCT OS ecosystem. Every agent-to-agent message MUST
    be encapsulated in a JITNAPacket.

    Attributes:
        packet_id: Unique packet identifier (UUID)
        source_agent_id: ID of the sending agent
        target_agent_id: ID of the receiving agent
        message_type: Type classification
        payload: Message content (arbitrary dict)
        timestamp: Creation timestamp (UTC)
        schema_version: Wire format version
        priority: Message priority (1=lowest, 5=highest)
        correlation_id: Links related packets (optional)
        signature: Cryptographic signature (optional, set by signing module)
        metadata: Additional routing/context metadata
        status: Current packet lifecycle status
    """
    packet_id: str = field(default_factory=lambda: str(uuid4()))
    source_agent_id: str = ""
    target_agent_id: str = ""
    message_type: str = JITNAMessageType.INTENT_REQUEST.value
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = JITNA_SCHEMA_VERSION
    priority: int = 3
    correlation_id: Optional[str] = None
    signature: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = JITNAStatus.CREATED.value

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)

    def compute_hash(self) -> str:
        """
        Compute SHA-256 content hash for integrity verification.

        The hash covers: source, target, message_type, payload, timestamp, schema_version.
        Signature and status are excluded (they change after creation).
        """
        content = json.dumps({
            "source_agent_id": self.source_agent_id,
            "target_agent_id": self.target_agent_id,
            "message_type": self.message_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
        }, sort_keys=True, default=str)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ============================================================
# Validation
# ============================================================

@dataclass
class JITNAValidationResult:
    """Result of JITNA packet validation."""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


class JITNAValidator:
    """
    Validates JITNA protocol packets against the v2.0 schema.

    Checks:
        - Required fields are present and non-empty
        - Schema version compatibility
        - Message type validity
        - Priority range
        - Payload size limit
    """

    REQUIRED_FIELDS = ["packet_id", "source_agent_id", "target_agent_id", "message_type"]

    def validate(self, packet: JITNAPacket) -> JITNAValidationResult:
        """
        Validate a JITNA packet.

        Args:
            packet: The JITNAPacket to validate

        Returns:
            JITNAValidationResult with errors/warnings
        """
        result = JITNAValidationResult()

        # Check required fields
        for field_name in self.REQUIRED_FIELDS:
            value = getattr(packet, field_name, None)
            if not value or (isinstance(value, str) and not value.strip()):
                result.add_error(f"Required field '{field_name}' is empty or missing")

        # Schema version check
        if packet.schema_version != JITNA_SCHEMA_VERSION:
            result.add_error(
                f"Unsupported schema version '{packet.schema_version}'; "
                f"expected '{JITNA_SCHEMA_VERSION}'"
            )

        # Message type validation
        valid_types = [mt.value for mt in JITNAMessageType]
        if packet.message_type not in valid_types:
            result.add_error(
                f"Invalid message_type '{packet.message_type}'; "
                f"must be one of {valid_types}"
            )

        # Priority range
        if packet.priority not in JITNA_VALID_PRIORITIES:
            result.add_error(
                f"Invalid priority {packet.priority}; must be 1–5"
            )

        # Payload size
        payload_json = json.dumps(packet.payload, default=str)
        if len(payload_json.encode("utf-8")) > JITNA_MAX_PAYLOAD_SIZE_BYTES:
            result.add_error(
                f"Payload exceeds maximum size of {JITNA_MAX_PAYLOAD_SIZE_BYTES} bytes"
            )

        # Warnings
        if not packet.payload:
            result.add_warning("Packet has empty payload")

        if not packet.correlation_id:
            result.add_warning("No correlation_id set; message tracing will be limited")

        return result

    def validate_dict(self, data: Dict[str, Any]) -> JITNAValidationResult:
        """
        Validate a raw dictionary against JITNA schema.

        Args:
            data: Raw dictionary to validate

        Returns:
            JITNAValidationResult
        """
        try:
            normalizer = JITNANormalizer()
            packet = normalizer.normalize(data)
            return self.validate(packet)
        except Exception as e:
            result = JITNAValidationResult()
            result.add_error(f"Failed to normalize packet: {str(e)}")
            return result


# ============================================================
# Normalization
# ============================================================

class JITNANormalizer:
    """
    Normalizes raw dictionaries into valid JITNAPacket instances.

    Handles:
        - Missing optional fields (fills defaults)
        - UUID generation for packet_id if missing
        - Timestamp generation if missing
        - Schema version injection
        - Field name aliasing (e.g., 'src' → 'source_agent_id')
    """

    # Field aliases for flexible input
    FIELD_ALIASES = {
        "src": "source_agent_id",
        "source": "source_agent_id",
        "from": "source_agent_id",
        "dst": "target_agent_id",
        "target": "target_agent_id",
        "to": "target_agent_id",
        "type": "message_type",
        "msg_type": "message_type",
        "data": "payload",
        "body": "payload",
        "content": "payload",
        "prio": "priority",
        "ts": "timestamp",
        "time": "timestamp",
        "corr_id": "correlation_id",
        "sig": "signature",
        "meta": "metadata",
        "id": "packet_id",
    }

    def normalize(self, raw: Dict[str, Any]) -> JITNAPacket:
        """
        Normalize a raw dictionary into a JITNAPacket.

        Args:
            raw: Raw dictionary with potentially aliased field names

        Returns:
            JITNAPacket with all fields populated
        """
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict, got {type(raw).__name__}")

        # Apply field aliases
        normalized = {}
        for key, value in raw.items():
            canonical = self.FIELD_ALIASES.get(key, key)
            normalized[canonical] = value

        # Build packet with defaults
        return JITNAPacket(
            packet_id=normalized.get("packet_id", str(uuid4())),
            source_agent_id=str(normalized.get("source_agent_id", "")),
            target_agent_id=str(normalized.get("target_agent_id", "")),
            message_type=normalized.get("message_type", JITNAMessageType.INTENT_REQUEST.value),
            payload=normalized.get("payload", {}),
            timestamp=normalized.get("timestamp", datetime.now(timezone.utc).isoformat()),
            schema_version=normalized.get("schema_version", JITNA_SCHEMA_VERSION),
            priority=int(normalized.get("priority", 3)),
            correlation_id=normalized.get("correlation_id"),
            signature=normalized.get("signature"),
            metadata=normalized.get("metadata", {}),
        )


# ============================================================
# Protocol Registry
# ============================================================

class JITNAProtocolRegistry:
    """
    Registry for tracking JITNA packet exchanges.

    Provides:
        - Packet storage and retrieval by ID
        - Correlation chain tracking
        - Basic statistics
    """

    def __init__(self) -> None:
        self._packets: Dict[str, JITNAPacket] = {}
        self._correlation_chains: Dict[str, List[str]] = {}

    def register(self, packet: JITNAPacket) -> None:
        """Register a packet in the registry."""
        self._packets[packet.packet_id] = packet

        if packet.correlation_id:
            chain = self._correlation_chains.setdefault(packet.correlation_id, [])
            chain.append(packet.packet_id)

    def get(self, packet_id: str) -> Optional[JITNAPacket]:
        """Get packet by ID."""
        return self._packets.get(packet_id)

    def get_chain(self, correlation_id: str) -> List[JITNAPacket]:
        """Get all packets in a correlation chain."""
        packet_ids = self._correlation_chains.get(correlation_id, [])
        return [self._packets[pid] for pid in packet_ids if pid in self._packets]

    @property
    def packet_count(self) -> int:
        """Total registered packets."""
        return len(self._packets)

    @property
    def chain_count(self) -> int:
        """Total correlation chains."""
        return len(self._correlation_chains)

    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        type_counts: Dict[str, int] = {}
        for pkt in self._packets.values():
            type_counts[pkt.message_type] = type_counts.get(pkt.message_type, 0) + 1

        return {
            "total_packets": self.packet_count,
            "total_chains": self.chain_count,
            "packets_by_type": type_counts,
        }

    def clear(self) -> None:
        """Clear all registered packets."""
        self._packets.clear()
        self._correlation_chains.clear()

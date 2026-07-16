"""
JITNA Protocol v3 — Streaming & Multi-hop Routing

Extends JITNA v2 (jitna_protocol.py) with:
  - STREAM_CHUNK / STREAM_END message types
  - Multi-hop routing with TTL and hop-trace
  - Optional zstd compression (fallback: zlib)
  - JITNARouter for deterministic hop routing

JITNA_V3_SCHEMA_VERSION = "3.0"
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import zlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from rct_control_plane.jitna_protocol import (
    JITNAPacket,
    JITNAStatus,
)

# ---------------------------------------------------------------------------
# Optional zstandard import
# ---------------------------------------------------------------------------
try:
    import zstandard as zstd
    _HAS_ZSTD = True
except ImportError:  # pragma: no cover
    zstd: Any = None  # type: ignore[no-redef]
    _HAS_ZSTD = False


# ============================================================
# Constants
# ============================================================

JITNA_V3_SCHEMA_VERSION = "3.0"
JITNA_V3_DEFAULT_TTL = 8
JITNA_V3_CHUNK_SIZE = 512


# ============================================================
# Extended Message Types
# ============================================================

class JITNAMessageTypeV3(str, Enum):
    """Extended message types for JITNA v3 (superset of v2)."""
    INTENT_REQUEST = "intent_request"
    INTENT_RESPONSE = "intent_response"
    NEGOTIATION = "negotiation"
    CONFIRMATION = "confirmation"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    # v3 additions
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"


# ============================================================
# JITNAPacketV3
# ============================================================

@dataclass
class JITNAPacketV3:
    """
    JITNA v3 packet — adds streaming and multi-hop routing fields to v2.

    New fields vs v2:
        hop_trace: ordered list of agent IDs already visited
        ttl: remaining hops before packet is dropped
        compressed: whether payload is zlib/zstd compressed
    """
    packet_id: str = field(default_factory=lambda: str(uuid4()))
    source_agent_id: str = ""
    target_agent_id: str = ""
    message_type: str = JITNAMessageTypeV3.INTENT_REQUEST.value
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = JITNA_V3_SCHEMA_VERSION
    priority: int = 3
    correlation_id: Optional[str] = None
    signature: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = JITNAStatus.CREATED.value
    # v3-only fields
    hop_trace: List[str] = field(default_factory=list)
    ttl: int = JITNA_V3_DEFAULT_TTL
    compressed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)

    def compute_hash(self) -> str:
        content = json.dumps(
            {
                "source_agent_id": self.source_agent_id,
                "target_agent_id": self.target_agent_id,
                "message_type": self.message_type,
                "payload": self.payload,
                "timestamp": self.timestamp,
                "schema_version": self.schema_version,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @classmethod
    def from_v2(cls, packet: JITNAPacket) -> "JITNAPacketV3":
        """Upgrade a v2 JITNAPacket to JITNAPacketV3 (no-op fields get defaults)."""
        return cls(
            packet_id=packet.packet_id,
            source_agent_id=packet.source_agent_id,
            target_agent_id=packet.target_agent_id,
            message_type=packet.message_type,
            payload=dict(packet.payload),
            timestamp=packet.timestamp,
            schema_version=JITNA_V3_SCHEMA_VERSION,
            priority=packet.priority,
            correlation_id=packet.correlation_id,
            signature=packet.signature,
            metadata=dict(packet.metadata),
            status=packet.status,
        )

    # ── TOON (ALGO-42) serialization ──────────────────────────────────

    def to_toon(self) -> str:
        """
        Serialize this packet to TOON (Token-Oriented Object Notation).

        TOON reduces token consumption by 40-50% vs JSON by stripping
        all syntax noise (braces, brackets, quotes, commas).

        Returns:
            TOON-formatted string representation of this packet
        """
        from rct_control_plane.toon_formatter import toon_serialize
        return toon_serialize(self.to_dict())

    @classmethod
    def from_toon(cls, toon_str: str) -> "JITNAPacketV3":
        """
        Deserialize a TOON string into a JITNAPacketV3 instance.

        Args:
            toon_str: TOON-formatted string

        Returns:
            JITNAPacketV3 with all fields populated from the TOON data
        """
        from rct_control_plane.toon_formatter import toon_deserialize
        data = toon_deserialize(toon_str)
        return cls(
            packet_id=data.get("packet_id", str(uuid4())),
            source_agent_id=str(data.get("source_agent_id", "")),
            target_agent_id=str(data.get("target_agent_id", "")),
            message_type=data.get("message_type", JITNAMessageTypeV3.INTENT_REQUEST.value),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            schema_version=data.get("schema_version", JITNA_V3_SCHEMA_VERSION),
            priority=int(data.get("priority", 3)),
            correlation_id=data.get("correlation_id"),
            signature=data.get("signature"),
            metadata=data.get("metadata", {}),
            status=data.get("status", JITNAStatus.CREATED.value),
            hop_trace=data.get("hop_trace", []),
            ttl=int(data.get("ttl", JITNA_V3_DEFAULT_TTL)),
            compressed=bool(data.get("compressed", False)),
        )



# ============================================================
# Compression helpers
# ============================================================

def compress_payload(data: bytes, prefer_zstd: bool = True) -> bytes:
    """
    Compress raw bytes.  Uses zstd level-3 when available, otherwise zlib level-6.
    """
    if prefer_zstd and _HAS_ZSTD:
        cctx = zstd.ZstdCompressor(level=3)
        return cctx.compress(data)
    return zlib.compress(data, level=6)


def decompress_payload(data: bytes) -> bytes:
    """
    Decompress bytes.  Auto-detects zstd (magic 0xFD2FB528) vs zlib.
    """
    if len(data) >= 4 and data[:4] == b"\x28\xb5\x2f\xfd":
        if not _HAS_ZSTD:
            raise RuntimeError(
                "zstandard not installed; cannot decompress zstd-compressed payload"
            )
        dctx = zstd.ZstdDecompressor()
        return dctx.decompress(data)
    return zlib.decompress(data)


def pack_compressed(packet: JITNAPacketV3) -> JITNAPacketV3:
    """
    Compress packet.payload in-place.

    The original payload JSON is compressed and stored as a base64 string
    under ``payload["compressed_data"]``.  Sets ``packet.compressed = True``.
    """
    raw = json.dumps(packet.payload, default=str, ensure_ascii=False).encode("utf-8")
    compressed = compress_payload(raw)
    packet.payload = {"compressed_data": base64.b64encode(compressed).decode("ascii")}
    packet.compressed = True
    return packet


def unpack_compressed(packet: JITNAPacketV3) -> JITNAPacketV3:
    """
    Decompress a packet previously packed with ``pack_compressed``.

    No-op if ``packet.compressed`` is False.
    """
    if not packet.compressed:
        return packet
    raw_b64 = packet.payload.get("compressed_data", "")
    compressed = base64.b64decode(raw_b64)
    raw = decompress_payload(compressed)
    packet.payload = json.loads(raw.decode("utf-8"))
    packet.compressed = False
    return packet


# ============================================================
# Streaming
# ============================================================

async def stream(
    packet: JITNAPacketV3,
    chunk_size: int = JITNA_V3_CHUNK_SIZE,
) -> AsyncGenerator[JITNAPacketV3, None]:
    """
    Stream a packet payload as sequential STREAM_CHUNK packets.

    Yields ``ceil(len(payload_json) / chunk_size)`` STREAM_CHUNK packets
    followed by a single STREAM_END packet.

    Each STREAM_CHUNK payload:
        {"chunk_index": N, "total_chunks": T, "data": "<slice>", "stream_id": "<id>"}

    STREAM_END payload:
        {"stream_id": "<id>", "total_chunks": T}
    """
    payload_str = json.dumps(packet.payload, default=str, ensure_ascii=False)
    stream_id = packet.correlation_id or packet.packet_id
    n = len(payload_str)
    total_chunks = max(1, (n + chunk_size - 1) // chunk_size)  # ceiling division

    for idx in range(total_chunks):
        chunk_data = payload_str[idx * chunk_size: (idx + 1) * chunk_size]
        yield JITNAPacketV3(
            source_agent_id=packet.source_agent_id,
            target_agent_id=packet.target_agent_id,
            message_type=JITNAMessageTypeV3.STREAM_CHUNK.value,
            payload={
                "chunk_index": idx,
                "total_chunks": total_chunks,
                "data": chunk_data,
                "stream_id": stream_id,
            },
            priority=packet.priority,
            correlation_id=stream_id,
            metadata=dict(packet.metadata),
            hop_trace=list(packet.hop_trace),
            ttl=packet.ttl,
        )
        await asyncio.sleep(0)  # cooperative yield

    yield JITNAPacketV3(
        source_agent_id=packet.source_agent_id,
        target_agent_id=packet.target_agent_id,
        message_type=JITNAMessageTypeV3.STREAM_END.value,
        payload={"stream_id": stream_id, "total_chunks": total_chunks},
        priority=packet.priority,
        correlation_id=stream_id,
        metadata=dict(packet.metadata),
        hop_trace=list(packet.hop_trace),
        ttl=packet.ttl,
    )


# ============================================================
# Routing
# ============================================================

class TTLExpiredError(Exception):
    """Raised when a JITNAPacketV3 TTL reaches zero during routing."""


class JITNARouter:
    """
    Multi-hop JITNA v3 packet router.

    Each call to ``route()`` appends hop IDs to ``hop_trace``, decrements TTL
    per hop, and sets ``target_agent_id`` to the final hop.

    Raises:
        TTLExpiredError: if TTL is exhausted before all hops are traversed
        ValueError: if hops list is empty
    """

    def route(
        self,
        packet: JITNAPacketV3,
        hops: List[str],
        ttl: int = JITNA_V3_DEFAULT_TTL,
    ) -> JITNAPacketV3:
        """
        Route *packet* through *hops*.

        Args:
            packet: Source packet (not mutated; a new packet is returned)
            hops:   Ordered list of agent IDs to traverse
            ttl:    Maximum remaining hops (capped by packet.ttl)

        Returns:
            New JITNAPacketV3 with updated hop_trace, ttl, target_agent_id, status
        """
        if not hops:
            raise ValueError("hops list cannot be empty")

        current_ttl = min(ttl, packet.ttl)
        trace = list(packet.hop_trace)

        for hop in hops:
            if current_ttl <= 0:
                raise TTLExpiredError(
                    f"TTL expired after {len(trace)} hops; remaining hops not traversed"
                )
            trace.append(hop)
            current_ttl -= 1

        return JITNAPacketV3(
            packet_id=packet.packet_id,
            source_agent_id=packet.source_agent_id,
            target_agent_id=hops[-1],
            message_type=packet.message_type,
            payload=dict(packet.payload),
            timestamp=packet.timestamp,
            schema_version=packet.schema_version,
            priority=packet.priority,
            correlation_id=packet.correlation_id,
            signature=packet.signature,
            metadata=dict(packet.metadata),
            status=JITNAStatus.DISPATCHED.value,
            hop_trace=trace,
            ttl=current_ttl,
            compressed=packet.compressed,
        )

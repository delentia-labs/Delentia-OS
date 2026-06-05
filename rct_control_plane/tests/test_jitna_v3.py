"""
Tests for JITNA Protocol v3 — Streaming & Multi-hop Routing
"""

from __future__ import annotations

import asyncio
import json
import unittest

from rct_control_plane.jitna_protocol import JITNAPacket, JITNAStatus
from rct_control_plane.jitna_protocol_v3 import (
    JITNA_V3_SCHEMA_VERSION,
    JITNA_V3_DEFAULT_TTL,
    JITNA_V3_CHUNK_SIZE,
    JITNAMessageTypeV3,
    JITNAPacketV3,
    compress_payload,
    decompress_payload,
    pack_compressed,
    unpack_compressed,
    stream,
    JITNARouter,
    TTLExpiredError,
)


# ============================================================
# Helpers
# ============================================================

def make_packet(**kwargs) -> JITNAPacketV3:
    defaults = dict(
        source_agent_id="agent-A",
        target_agent_id="agent-B",
        payload={"msg": "hello"},
    )
    defaults.update(kwargs)
    return JITNAPacketV3(**defaults)


def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


async def collect_stream(packet, **kw):
    chunks = []
    async for p in stream(packet, **kw):
        chunks.append(p)
    return chunks


# ============================================================
# 1. Version / Constants
# ============================================================

class TestVersion(unittest.TestCase):
    def test_schema_version(self):
        self.assertEqual(JITNA_V3_SCHEMA_VERSION, "3.0")

    def test_default_ttl(self):
        self.assertEqual(JITNA_V3_DEFAULT_TTL, 8)

    def test_chunk_size(self):
        self.assertEqual(JITNA_V3_CHUNK_SIZE, 512)


# ============================================================
# 2. Extended Message Types
# ============================================================

class TestMessageTypeV3(unittest.TestCase):
    def test_stream_chunk_value(self):
        self.assertEqual(JITNAMessageTypeV3.STREAM_CHUNK.value, "stream_chunk")

    def test_stream_end_value(self):
        self.assertEqual(JITNAMessageTypeV3.STREAM_END.value, "stream_end")

    def test_inherits_v2_types(self):
        self.assertEqual(JITNAMessageTypeV3.INTENT_REQUEST.value, "intent_request")
        self.assertEqual(JITNAMessageTypeV3.HEARTBEAT.value, "heartbeat")


# ============================================================
# 3. JITNAPacketV3
# ============================================================

class TestJITNAPacketV3(unittest.TestCase):
    def test_defaults(self):
        p = JITNAPacketV3()
        self.assertEqual(p.schema_version, JITNA_V3_SCHEMA_VERSION)
        self.assertEqual(p.ttl, JITNA_V3_DEFAULT_TTL)
        self.assertFalse(p.compressed)
        self.assertEqual(p.hop_trace, [])

    def test_to_dict_has_v3_fields(self):
        p = make_packet(hop_trace=["x"], ttl=5)
        d = p.to_dict()
        self.assertIn("hop_trace", d)
        self.assertIn("ttl", d)
        self.assertIn("compressed", d)

    def test_to_json_round_trip(self):
        p = make_packet(payload={"key": "value"})
        data = json.loads(p.to_json())
        self.assertEqual(data["payload"]["key"], "value")
        self.assertEqual(data["schema_version"], "3.0")

    def test_compute_hash_deterministic(self):
        p = make_packet()
        self.assertEqual(p.compute_hash(), p.compute_hash())
        self.assertEqual(len(p.compute_hash()), 64)  # SHA-256 hex

    def test_from_v2_upgrade(self):
        v2 = JITNAPacket(source_agent_id="src", target_agent_id="dst", payload={"x": 1})
        v3 = JITNAPacketV3.from_v2(v2)
        self.assertIsInstance(v3, JITNAPacketV3)
        self.assertEqual(v3.schema_version, JITNA_V3_SCHEMA_VERSION)
        self.assertEqual(v3.source_agent_id, "src")
        self.assertEqual(v3.payload["x"], 1)
        self.assertEqual(v3.hop_trace, [])
        self.assertEqual(v3.ttl, JITNA_V3_DEFAULT_TTL)

    def test_from_v2_preserves_packet_id(self):
        v2 = JITNAPacket(source_agent_id="src", target_agent_id="dst")
        v3 = JITNAPacketV3.from_v2(v2)
        self.assertEqual(v3.packet_id, v2.packet_id)

    def test_to_toon_round_trip(self):
        p = make_packet(
            priority=2,
            correlation_id="corr-999",
            payload={"intent": "คำนวณภาษี", "nested": {"val": 100}},
        )
        toon_str = p.to_toon()
        assert "priority: 2" in toon_str
        assert "correlation_id: corr-999" in toon_str
        assert "intent: คำนวณภาษี" in toon_str
        assert "val: 100" in toon_str

        p_recovered = JITNAPacketV3.from_toon(toon_str)
        self.assertEqual(p_recovered.packet_id, p.packet_id)
        self.assertEqual(p_recovered.priority, p.priority)
        self.assertEqual(p_recovered.correlation_id, p.correlation_id)
        self.assertEqual(p_recovered.payload["intent"], p.payload["intent"])
        self.assertEqual(p_recovered.payload["nested"]["val"], p.payload["nested"]["val"])



# ============================================================
# 4. Compression helpers
# ============================================================

class TestCompression(unittest.TestCase):
    def _sample_data(self):
        return b'{"hello": "world", "repeat": "aaaaaaaaaa"}'

    def test_zlib_round_trip(self):
        raw = self._sample_data()
        compressed = compress_payload(raw, prefer_zstd=False)
        self.assertNotEqual(compressed, raw)
        result = decompress_payload(compressed)
        self.assertEqual(result, raw)

    def test_pack_unpack_round_trip(self):
        p = make_packet(payload={"key": "value", "n": 42})
        pack_compressed(p)
        self.assertTrue(p.compressed)
        self.assertIn("compressed_data", p.payload)
        unpack_compressed(p)
        self.assertFalse(p.compressed)
        self.assertEqual(p.payload["key"], "value")
        self.assertEqual(p.payload["n"], 42)

    def test_unpack_noop_when_not_compressed(self):
        p = make_packet(payload={"a": 1})
        result = unpack_compressed(p)
        self.assertIs(result, p)
        self.assertEqual(p.payload["a"], 1)

    def test_compressed_flag_set_by_pack(self):
        p = make_packet()
        self.assertFalse(p.compressed)
        pack_compressed(p)
        self.assertTrue(p.compressed)


# ============================================================
# 5. Streaming
# ============================================================

class TestStreaming(unittest.TestCase):
    def test_single_chunk_small_payload(self):
        p = make_packet(payload={"x": 1})
        packets = run_async(collect_stream(p, chunk_size=512))
        # Should be 1 STREAM_CHUNK + 1 STREAM_END = 2 packets
        self.assertEqual(len(packets), 2)
        self.assertEqual(packets[0].message_type, "stream_chunk")
        self.assertEqual(packets[-1].message_type, "stream_end")

    def test_multiple_chunks(self):
        big_text = "A" * 100
        p = make_packet(payload={"data": big_text})
        packets = run_async(collect_stream(p, chunk_size=10))
        chunk_packets = [pk for pk in packets if pk.message_type == "stream_chunk"]
        end_packet = [pk for pk in packets if pk.message_type == "stream_end"]
        self.assertGreater(len(chunk_packets), 1)
        self.assertEqual(len(end_packet), 1)

    def test_chunk_indices_sequential(self):
        p = make_packet(payload={"data": "X" * 50})
        packets = run_async(collect_stream(p, chunk_size=10))
        chunks = [pk for pk in packets if pk.message_type == "stream_chunk"]
        for i, c in enumerate(chunks):
            self.assertEqual(c.payload["chunk_index"], i)

    def test_stream_id_propagated(self):
        p = make_packet(correlation_id="corr-123")
        packets = run_async(collect_stream(p))
        for pk in packets:
            sid = pk.payload.get("stream_id")
            self.assertEqual(sid, "corr-123")

    def test_reassemble_chunks(self):
        original = {"data": "Hello World " * 20}
        original_json = json.dumps(original, ensure_ascii=False)
        p = make_packet(payload=original)
        packets = run_async(collect_stream(p, chunk_size=20))
        chunks = [pk for pk in packets if pk.message_type == "stream_chunk"]
        reassembled = "".join(c.payload["data"] for c in chunks)
        self.assertEqual(reassembled, original_json)

    def test_stream_end_total_chunks(self):
        p = make_packet(payload={"data": "A" * 50})
        packets = run_async(collect_stream(p, chunk_size=10))
        end = next(pk for pk in packets if pk.message_type == "stream_end")
        chunk_count = len([pk for pk in packets if pk.message_type == "stream_chunk"])
        self.assertEqual(end.payload["total_chunks"], chunk_count)


# ============================================================
# 6. Router
# ============================================================

class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = JITNARouter()

    def test_single_hop(self):
        p = make_packet(ttl=5)
        result = self.router.route(p, hops=["agent-C"])
        self.assertEqual(result.target_agent_id, "agent-C")
        self.assertIn("agent-C", result.hop_trace)
        self.assertEqual(result.ttl, 4)

    def test_multi_hop(self):
        p = make_packet(ttl=5)
        result = self.router.route(p, hops=["hop1", "hop2", "hop3"])
        self.assertEqual(result.target_agent_id, "hop3")
        self.assertEqual(result.hop_trace, ["hop1", "hop2", "hop3"])
        self.assertEqual(result.ttl, 2)

    def test_status_set_to_dispatched(self):
        p = make_packet()
        result = self.router.route(p, hops=["x"])
        self.assertEqual(result.status, JITNAStatus.DISPATCHED.value)

    def test_original_packet_not_mutated(self):
        p = make_packet(ttl=5, hop_trace=[])
        _ = self.router.route(p, hops=["x"])
        self.assertEqual(p.hop_trace, [])
        self.assertEqual(p.ttl, 5)

    def test_empty_hops_raises(self):
        p = make_packet()
        with self.assertRaises(ValueError):
            self.router.route(p, hops=[])

    def test_ttl_expired_raises(self):
        p = make_packet(ttl=2)
        with self.assertRaises(TTLExpiredError):
            self.router.route(p, hops=["h1", "h2", "h3"])

    def test_ttl_capped_by_packet_ttl(self):
        p = make_packet(ttl=2)
        # passing ttl=10 but packet.ttl=2 → effective=2
        with self.assertRaises(TTLExpiredError):
            self.router.route(p, hops=["h1", "h2", "h3"], ttl=10)

    def test_existing_hop_trace_extended(self):
        p = make_packet(ttl=5, hop_trace=["prior"])
        result = self.router.route(p, hops=["next"])
        self.assertEqual(result.hop_trace, ["prior", "next"])


if __name__ == "__main__":
    unittest.main()

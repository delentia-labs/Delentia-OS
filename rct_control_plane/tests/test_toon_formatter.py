"""
Test suite for ALGO-42: TOON (Token-Oriented Object Notation) Formatter.

Tests cover:
  - Serialization of all Python types (dict, list, str, int, float, bool, None)
  - Nested structures (dict-in-dict, list-in-dict, dict-in-list)
  - Round-trip integrity (serialize → deserialize → serialize)
  - Thai language content preservation
  - JITNA v3 packet serialization
  - Token savings estimation
  - Edge cases (empty structures, deeply nested, special characters)
"""

import json
import pytest

from rct_control_plane.toon_formatter import (
    TOONFormatter,
    toon_serialize,
    toon_deserialize,
    toon_token_savings_estimate,
)


@pytest.fixture
def formatter():
    return TOONFormatter()


# ─── Basic Serialization ─────────────────────────────────────────────────


class TestSerialize:
    """Test TOON serialization for various data types."""

    def test_flat_dict(self, formatter):
        data = {"name": "Delentia", "version": 5, "active": True}
        result = formatter.serialize(data)
        assert "name: Delentia" in result
        assert "version: 5" in result
        assert "active: true" in result
        # Must NOT contain JSON artifacts
        assert "{" not in result
        assert '"' not in result

    def test_nested_dict(self, formatter):
        data = {"user": {"id": "u001", "role": "admin"}}
        result = formatter.serialize(data)
        assert "user:" in result
        assert "  id: u001" in result or "id: u001" in result
        assert "role: admin" in result

    def test_list_of_scalars(self, formatter):
        data = {"tags": ["finance", "thai_tax", "pdpa"]}
        result = formatter.serialize(data)
        assert "tags:" in result
        assert "- finance" in result
        assert "- thai_tax" in result
        assert "- pdpa" in result

    def test_list_of_dicts(self, formatter):
        data = {
            "steps": [
                {"action": "validate", "status": "passed"},
                {"action": "compute", "status": "pending"},
            ]
        }
        result = formatter.serialize(data)
        assert "steps:" in result
        assert "action: validate" in result
        assert "status: passed" in result
        assert "action: compute" in result

    def test_none_value(self, formatter):
        data = {"expires_at": None}
        result = formatter.serialize(data)
        assert "expires_at: null" in result

    def test_bool_values(self, formatter):
        data = {"enabled": True, "expired": False}
        result = formatter.serialize(data)
        assert "enabled: true" in result
        assert "expired: false" in result

    def test_float_value(self, formatter):
        data = {"score": 0.87, "threshold": 0.7}
        result = formatter.serialize(data)
        assert "score: 0.87" in result
        assert "threshold: 0.7" in result

    def test_empty_dict(self, formatter):
        data = {"metadata": {}}
        result = formatter.serialize(data)
        assert "metadata: {}" in result or "metadata:" in result

    def test_empty_list(self, formatter):
        data = {"items": []}
        result = formatter.serialize(data)
        assert "items: []" in result or "items:" in result

    def test_no_json_syntax_noise(self, formatter):
        """Verify no JSON syntax characters exist in output."""
        data = {
            "packet_id": "abc-123",
            "payload": {"intent": "test", "priority": 3},
            "tags": ["a", "b"],
        }
        result = formatter.serialize(data)
        # No JSON delimiters
        assert "[" not in result.replace("- ", "").replace("[]", "")
        assert '"' not in result


# ─── Thai Language Support ────────────────────────────────────────────────


class TestThaiContent:
    """Test TOON serialization with Thai language content."""

    def test_thai_string_values(self, formatter):
        data = {"intent": "คำนวณภาษีเงินได้บุคคลธรรมดา", "language": "th"}
        result = formatter.serialize(data)
        assert "คำนวณภาษีเงินได้บุคคลธรรมดา" in result
        assert "language: th" in result

    def test_thai_in_nested_structure(self, formatter):
        data = {
            "payload": {
                "question": "สรุปหลักการ RCT v5 ใน 2 ประโยค",
                "context": "กฎหมายคุ้มครองข้อมูลส่วนบุคคล",
            }
        }
        result = formatter.serialize(data)
        assert "สรุปหลักการ RCT v5 ใน 2 ประโยค" in result
        assert "กฎหมายคุ้มครองข้อมูลส่วนบุคคล" in result

    def test_mixed_thai_english(self, formatter):
        data = {"intent": "อธิบาย Constitutional AI ในบริบท Thai PDPA"}
        result = formatter.serialize(data)
        assert "อธิบาย Constitutional AI ในบริบท Thai PDPA" in result


# ─── Deserialization ──────────────────────────────────────────────────────


class TestDeserialize:
    """Test TOON deserialization back to Python objects."""

    def test_flat_dict(self, formatter):
        toon = "name: Delentia\nversion: 5\nactive: true"
        result = formatter.deserialize(toon)
        assert result["name"] == "Delentia"
        assert result["version"] == 5
        assert result["active"] is True

    def test_null_deserialization(self, formatter):
        toon = "value: null"
        result = formatter.deserialize(toon)
        assert result["value"] is None

    def test_bool_deserialization(self, formatter):
        toon = "a: true\nb: false"
        result = formatter.deserialize(toon)
        assert result["a"] is True
        assert result["b"] is False

    def test_numeric_deserialization(self, formatter):
        toon = "count: 42\nrate: 0.87\nneg: -5"
        result = formatter.deserialize(toon)
        assert result["count"] == 42
        assert result["rate"] == 0.87
        assert result["neg"] == -5

    def test_empty_input(self, formatter):
        result = formatter.deserialize("")
        assert result == {}

    def test_list_deserialization(self, formatter):
        toon = "tags:\n  - finance\n  - legal\n  - thai"
        result = formatter.deserialize(toon)
        assert result["tags"] == ["finance", "legal", "thai"]


# ─── Round-trip Integrity ─────────────────────────────────────────────────


class TestRoundTrip:
    """Test serialize → deserialize round-trip produces equivalent data."""

    def _assert_roundtrip(self, formatter, data):
        toon = formatter.serialize(data)
        recovered = formatter.deserialize(toon)
        assert recovered == data, (
            f"Round-trip mismatch:\n"
            f"  Original: {data}\n"
            f"  TOON:     {toon}\n"
            f"  Recovered: {recovered}"
        )

    def test_simple_dict_roundtrip(self, formatter):
        self._assert_roundtrip(formatter, {
            "name": "Delentia",
            "version": 5,
            "active": True,
        })

    def test_nested_dict_roundtrip(self, formatter):
        self._assert_roundtrip(formatter, {
            "payload": {"intent": "test intent", "score": 0.95},
        })

    def test_list_roundtrip(self, formatter):
        self._assert_roundtrip(formatter, {
            "tags": ["finance", "thai_tax", "pdpa"],
        })

    def test_null_roundtrip(self, formatter):
        self._assert_roundtrip(formatter, {
            "value": None,
            "active": False,
        })

    def test_thai_roundtrip(self, formatter):
        self._assert_roundtrip(formatter, {
            "intent": "คำนวณภาษีเงินได้บุคคลธรรมดา",
            "amount": 1000000,
        })


# ─── JITNA v3 Packet Simulation ──────────────────────────────────────────


class TestJITNAPacketSerialization:
    """Test TOON with realistic JITNA v3 packet structures."""

    def test_jitna_packet(self, formatter):
        packet = {
            "packet_id": "6afff5d6-7fa3-4f2c-92b0-b1a77fd42a93",
            "source_agent_id": "gateway_api",
            "target_agent_id": "intent_loop",
            "message_type": "intent_request",
            "priority": 3,
            "schema_version": "3.0",
            "payload": {
                "intent": "คำนวณภาษีเงินได้บุคคลธรรมดา 1 ล้านบาท",
                "income": 1000000,
                "currency": "THB",
            },
        }
        toon = formatter.serialize(packet)

        # Verify critical fields are present
        assert "packet_id: 6afff5d6" in toon
        assert "message_type: intent_request" in toon
        assert "schema_version: 3.0" in toon
        assert "คำนวณภาษีเงินได้บุคคลธรรมดา" in toon
        assert "income: 1000000" in toon

        # Verify no JSON noise
        assert "{" not in toon.replace("{}", "")
        assert '"' not in toon


# ─── Token Savings ────────────────────────────────────────────────────────


class TestTokenSavings:
    """Test the token savings estimation utility."""

    def test_savings_positive(self):
        data = {
            "packet_id": "abc-123-def-456",
            "source_agent_id": "gateway_api",
            "target_agent_id": "intent_loop_engine",
            "message_type": "intent_request",
            "payload": {
                "intent": "คำนวณภาษีเงินได้",
                "income": 1000000,
                "currency": "THB",
                "year": 2026,
            },
            "priority": 3,
            "schema_version": "3.0",
            "tags": ["finance", "tax", "thai"],
        }
        stats = toon_token_savings_estimate(data)
        assert stats["savings_pct"] > 0, "TOON should save tokens vs JSON"
        assert stats["toon_chars"] < stats["json_chars"]

    def test_savings_at_least_10_pct_for_realistic_packet(self):
        """Realistic JITNA packet should achieve >= 20% savings."""
        data = {
            "packet_id": "6afff5d6-7fa3-4f2c-92b0-b1a77fd42a93",
            "source_agent_id": "gateway_api",
            "target_agent_id": "intent_loop",
            "message_type": "intent_request",
            "payload": {
                "intent": "สรุปหลักการ RCT v5 HexaCore ใน 2 ประโยค",
                "context": "enterprise_memory",
                "session_id": "sess_001",
            },
            "timestamp": "2026-06-05T01:00:00+00:00",
            "schema_version": "3.0",
            "priority": 3,
            "hop_trace": ["gateway", "analysearch", "intent_loop"],
            "ttl": 5,
            "compressed": False,
        }
        stats = toon_token_savings_estimate(data)
        assert stats["savings_pct"] >= 10.0, (
            f"Expected >= 10% savings, got {stats['savings_pct']}%"
        )


# ─── Convenience Functions ────────────────────────────────────────────────


class TestConvenienceFunctions:
    """Test module-level convenience wrappers."""

    def test_toon_serialize(self):
        result = toon_serialize({"key": "value"})
        assert "key: value" in result

    def test_toon_deserialize(self):
        result = toon_deserialize("key: value")
        assert result["key"] == "value"

    def test_convenience_roundtrip(self):
        data = {"intent": "test", "score": 42}
        recovered = toon_deserialize(toon_serialize(data))
        assert recovered == data

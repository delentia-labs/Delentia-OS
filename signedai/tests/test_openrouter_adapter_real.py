"""
Tests for the real OpenRouterAdapter (Round 32) - closes the gap where 7 of
HexaCoreRegistry's 10 declared roles had real model IDs but zero real
HTTP-calling code. Same mocking pattern as test_groq_adapter.py
(unittest.mock.patch on urllib.request.urlopen).
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import pytest

from signedai.core.openrouter_adapter import (
    OPENROUTER_API_URL,
    OpenRouterAdapter,
    OpenRouterUnavailableError,
    OpenRouterGenerateError,
    _build_payload,
    call_hexacore_role,
)
from signedai.core.registry import HexaCoreRegistry, HexaCoreRole


def _mock_response(status: int, body: dict) -> MagicMock:
    raw = json.dumps(body).encode("utf-8")
    mock = MagicMock()
    mock.status = status
    mock.read.return_value = raw
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _ok_response(content: str = "Hello from OpenRouter") -> MagicMock:
    return _mock_response(200, {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    })


class TestOpenRouterAdapterConfiguration(unittest.TestCase):
    """Real, network-independent tests - run unconditionally, no key needed."""

    def test_not_configured_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = OpenRouterAdapter("anthropic/claude-opus-4.6", api_key=None)
            self.assertFalse(adapter.is_configured())

    def test_configured_with_explicit_key(self):
        adapter = OpenRouterAdapter("anthropic/claude-opus-4.6", api_key="test-key-123")
        self.assertTrue(adapter.is_configured())

    def test_generate_raises_unavailable_without_key_and_makes_no_network_call(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = OpenRouterAdapter("anthropic/claude-opus-4.6", api_key=None)
            with patch("urllib.request.urlopen") as mock_urlopen:
                with self.assertRaises(OpenRouterUnavailableError):
                    adapter.generate("hello")
                mock_urlopen.assert_not_called()

    def test_call_hexacore_role_raises_unavailable_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OpenRouterUnavailableError):
                call_hexacore_role(HexaCoreRole.HUMANIZER, "hello", api_key=None)


class TestBuildPayload(unittest.TestCase):
    """Real payload-construction assertions - the exact JSON shape sent to
    OpenRouter, verifiable with zero network access."""

    def test_payload_includes_model_and_user_message(self):
        payload = _build_payload("deepseek/deepseek-v3.2", "hi there", None, 512)
        self.assertEqual(payload["model"], "deepseek/deepseek-v3.2")
        self.assertEqual(payload["max_tokens"], 512)
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hi there"}])

    def test_payload_includes_system_prompt_when_given(self):
        payload = _build_payload("x-ai/grok-4.1-fast", "hi", "be terse", 256)
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "be terse"})
        self.assertEqual(payload["messages"][1], {"role": "user", "content": "hi"})


class TestOpenRouterAdapterMockedCalls(unittest.TestCase):
    """Real HTTP-layer logic exercised via mocked urlopen (same pattern as
    test_groq_adapter.py) - no real network access, but real request
    construction/response parsing."""

    def test_generate_returns_real_content_from_mocked_response(self):
        adapter = OpenRouterAdapter("anthropic/claude-opus-4.6", api_key="fake-key")
        with patch("urllib.request.urlopen", return_value=_ok_response("real reply")):
            result = adapter.generate("hello")
        self.assertEqual(result, "real reply")

    def test_generate_raises_on_malformed_response(self):
        adapter = OpenRouterAdapter("anthropic/claude-opus-4.6", api_key="fake-key")
        with patch("urllib.request.urlopen", return_value=_mock_response(200, {"unexpected": "shape"})):
            with self.assertRaises(OpenRouterGenerateError):
                adapter.generate("hello")


class TestCallHexacoreRoleResolvesRealModelId(unittest.TestCase):
    def test_resolves_the_registrys_real_model_id_per_role(self):
        for role in [
            HexaCoreRole.SUPREME_ARCHITECT, HexaCoreRole.LEAD_BUILDER,
            HexaCoreRole.JUNIOR_BUILDER, HexaCoreRole.SPECIALIST,
            HexaCoreRole.LIBRARIAN, HexaCoreRole.HUMANIZER, HexaCoreRole.REGIONAL_THAI,
        ]:
            expected_model_id = HexaCoreRegistry.get_model_id(role)
            with patch("urllib.request.urlopen", return_value=_ok_response("ok")) as mock_urlopen:
                result = call_hexacore_role(role, "hello", api_key="fake-key")
            self.assertEqual(result, "ok")
            sent_request = mock_urlopen.call_args[0][0]
            sent_body = json.loads(sent_request.data.decode("utf-8"))
            self.assertEqual(sent_body["model"], expected_model_id)


@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="no live OPENROUTER_API_KEY in this environment - real live call skipped honestly",
)
class TestOpenRouterAdapterLiveCall:
    """Real, live network test - only runs when a real key is present in
    this session's environment. HUMANIZER is the cheapest/fastest real
    role in the registry, minimizing real token cost for this proof."""

    def test_live_call_to_cheapest_role_returns_real_nonempty_text(self):
        result = call_hexacore_role(HexaCoreRole.HUMANIZER, "Reply with exactly: OK", max_tokens=10)
        assert isinstance(result, str)
        assert len(result) > 0

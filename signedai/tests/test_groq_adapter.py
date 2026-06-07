"""
Tests for Groq LPU Adapter
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from signedai.core.groq_adapter import (
    GROQ_DEFAULT_MODEL,
    GROQ_API_URL,
    GROQ_FALLBACK_VERSION,
    GroqAdapter,
    GroqUnavailableError,
    GroqGenerateError,
    GroqRegexFallback,
    build_groq_fallback_chain,
)
from signedai.core.registry import HexaCoreRegistry, HexaCoreRole


# ============================================================
# Helpers
# ============================================================

def _mock_response(status: int, body: dict) -> MagicMock:
    raw = json.dumps(body).encode("utf-8")
    mock = MagicMock()
    mock.status = status
    mock.read.return_value = raw
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _ok_response(content: str = "Hello from Groq") -> MagicMock:
    return _mock_response(200, {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    })


def _models_response() -> MagicMock:
    return _mock_response(200, {"data": [{"id": "llama-3.3-70b-versatile"}]})


# ============================================================
# 1. Registry Groq Adapter
# ============================================================

class TestRegistryGroqAdapter(unittest.TestCase):
    def test_groq_adapter_role_exists(self):
        self.assertIn(HexaCoreRole.GROQ_ADAPTER, HexaCoreRole)

    def test_groq_adapter_in_models(self):
        model = HexaCoreRegistry.get_model(HexaCoreRole.GROQ_ADAPTER)
        self.assertEqual(model.provider, "Groq")

    def test_groq_adapter_country_us(self):
        model = HexaCoreRegistry.get_model(HexaCoreRole.GROQ_ADAPTER)
        self.assertEqual(model.country, "US")

    def test_groq_model_id(self):
        model = HexaCoreRegistry.get_model(HexaCoreRole.GROQ_ADAPTER)
        self.assertIn("groq/", model.id)

    def test_total_roles_ten(self):
        balance = HexaCoreRegistry.get_geopolitical_balance()
        total = sum(balance.values())
        self.assertEqual(total, 10)


# ============================================================
# 2. Constants
# ============================================================

class TestGroqAdapterConstants(unittest.TestCase):
    def test_version(self):
        self.assertEqual(GROQ_FALLBACK_VERSION, "1.0")

    def test_default_model(self):
        self.assertEqual(GROQ_DEFAULT_MODEL, "llama-3.3-70b-versatile")

    def test_api_url(self):
        self.assertIn("groq.com", GROQ_API_URL)


# ============================================================
# 3. check_available
# ============================================================

class TestCheckAvailable(unittest.TestCase):
    def test_returns_true_when_200(self):
        with patch("urllib.request.urlopen", return_value=_models_response()):
            adapter = GroqAdapter(api_key="test-key")
            self.assertTrue(adapter.check_available())

    def test_returns_false_on_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            adapter = GroqAdapter(api_key="test-key")
            self.assertFalse(adapter.check_available())

    def test_returns_false_on_http_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            adapter = GroqAdapter(api_key="test-key")
            self.assertFalse(adapter.check_available())


# ============================================================
# 4. generate
# ============================================================

class TestGenerate(unittest.TestCase):
    def test_generates_successfully(self):
        with patch("urllib.request.urlopen", return_value=_ok_response("Test answer")):
            adapter = GroqAdapter(api_key="sk-test")
            result = adapter.generate("What is 2+2?")
            self.assertEqual(result, "Test answer")

    def test_no_api_key_raises_unavailable(self):
        adapter = GroqAdapter(api_key=None)
        with self.assertRaises(GroqUnavailableError):
            adapter.generate("hello")

    def test_http_error_raises_generate_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="", code=429, msg="Too Many Requests", hdrs=None, fp=None  # type: ignore
        )):
            adapter = GroqAdapter(api_key="sk-test")
            with self.assertRaises(GroqGenerateError):
                adapter.generate("hello")

    def test_url_error_raises_unavailable(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("network")):
            adapter = GroqAdapter(api_key="sk-test")
            with self.assertRaises(GroqUnavailableError):
                adapter.generate("hello")

    def test_malformed_response_raises_generate_error(self):
        bad = _mock_response(200, {"unexpected": "shape"})
        with patch("urllib.request.urlopen", return_value=bad):
            adapter = GroqAdapter(api_key="sk-test")
            with self.assertRaises(GroqGenerateError):
                adapter.generate("hello")

    def test_custom_model_passed(self):
        with patch("urllib.request.urlopen", return_value=_ok_response("ok")) as mock_open:
            adapter = GroqAdapter(api_key="sk-test")
            adapter.generate("hi", model="llama-3.1-8b-instant")
            call_args = mock_open.call_args
            body = json.loads(call_args[0][0].data.decode())
            self.assertEqual(body["model"], "llama-3.1-8b-instant")


# ============================================================
# 5. GroqRegexFallback
# ============================================================

class TestGroqRegexFallback(unittest.TestCase):
    def test_returns_fallback_message(self):
        fb = GroqRegexFallback()
        result = fb.generate("any prompt")
        self.assertIn("FALLBACK", result)
        self.assertIsInstance(result, str)


# ============================================================
# 6. build_groq_fallback_chain
# ============================================================

class TestBuildGroqFallbackChain(unittest.TestCase):
    def test_uses_primary_when_successful(self):
        chain = build_groq_fallback_chain(primary_fn=lambda p: "primary answer")
        self.assertEqual(chain("test"), "primary answer")

    def test_falls_to_groq_when_primary_fails(self):
        with patch("urllib.request.urlopen", return_value=_ok_response("groq answer")):
            chain = build_groq_fallback_chain(
                primary_fn=lambda p: (_ for _ in ()).throw(Exception("primary down")),
                groq_api_key="sk-test",
            )
            result = chain("test")
            self.assertEqual(result, "groq answer")

    def test_falls_to_regex_when_both_fail(self):
        chain = build_groq_fallback_chain(
            primary_fn=lambda p: (_ for _ in ()).throw(Exception("down")),
            groq_api_key=None,  # no key → Groq tier skipped
        )
        result = chain("test")
        self.assertIn("FALLBACK", result)

    def test_no_api_key_skips_groq(self):
        chain = build_groq_fallback_chain(
            primary_fn=lambda p: (_ for _ in ()).throw(Exception("down")),
            groq_api_key=None,
        )
        with patch("urllib.request.urlopen"):
            chain("test")
            # urlopen should not be called for generate (may be called for check_available)
            # The chain should land on regex fallback
        # We just verify it doesn't raise
        result = chain("test")
        self.assertIn("FALLBACK", result)


if __name__ == "__main__":
    unittest.main()

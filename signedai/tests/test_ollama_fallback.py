"""
Tests for B4 — HexaCore Ollama Adapter (OllamaFallback + registry updates)
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from signedai.core.registry import HexaCoreRole, HexaCoreRegistry
from signedai.core.ollama_fallback import (
    OLLAMA_DEFAULT_MODEL,
    OLLAMA_FALLBACK_VERSION,
    OLLAMA_API_URL,
    OllamaFallback,
    OllamaUnavailableError,
    OllamaGenerateError,
    RegexFallback,
    build_fallback_chain,
)


# ============================================================
# Helpers
# ============================================================

def _mock_response(body: dict, status: int = 200):
    """Build a mock urllib response object."""
    raw = json.dumps(body).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = raw
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ============================================================
# 1. Registry — OLLAMA_ADAPTER enum & ModelInfo
# ============================================================

class TestRegistryOllamaAdapter(unittest.TestCase):
    def test_ollama_adapter_in_enum(self):
        self.assertEqual(HexaCoreRole.OLLAMA_ADAPTER.value, "ollama_adapter")

    def test_ollama_model_info_in_registry(self):
        info = HexaCoreRegistry.get_model(HexaCoreRole.OLLAMA_ADAPTER)
        self.assertEqual(info.provider, "Ollama")
        self.assertEqual(info.country, "LOCAL")
        self.assertEqual(info.cost_input, 0.0)
        self.assertEqual(info.cost_output, 0.0)

    def test_ollama_model_id(self):
        model_id = HexaCoreRegistry.get_model_id(HexaCoreRole.OLLAMA_ADAPTER)
        self.assertTrue(model_id.startswith("ollama/"))

    def test_estimate_cost_zero_for_ollama(self):
        cost = HexaCoreRegistry.estimate_cost(HexaCoreRole.OLLAMA_ADAPTER, 10_000, 2_000)
        self.assertEqual(cost, 0.0)


# ============================================================
# 2. Version / Constants
# ============================================================

class TestOllamaFallbackConstants(unittest.TestCase):
    def test_version(self):
        self.assertEqual(OLLAMA_FALLBACK_VERSION, "1.0")

    def test_default_model(self):
        self.assertIn("llama", OLLAMA_DEFAULT_MODEL)

    def test_default_url(self):
        self.assertEqual(OLLAMA_API_URL, "http://localhost:11434")


# ============================================================
# 3. OllamaFallback.check_available
# ============================================================

class TestCheckAvailable(unittest.TestCase):
    def test_available_when_200(self):
        mock_resp = _mock_response({"models": []})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            fb = OllamaFallback()
            self.assertTrue(fb.check_available())

    def test_unavailable_on_url_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            fb = OllamaFallback()
            self.assertFalse(fb.check_available())

    def test_unavailable_on_generic_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            fb = OllamaFallback()
            self.assertFalse(fb.check_available())


# ============================================================
# 4. OllamaFallback.generate
# ============================================================

class TestGenerate(unittest.TestCase):
    def test_success(self):
        mock_resp = _mock_response({"response": "Hello, RCT!"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            fb = OllamaFallback()
            result = fb.generate("Say hello")
        self.assertEqual(result, "Hello, RCT!")

    def test_uses_default_model(self):
        mock_resp = _mock_response({"response": "ok"})
        captured = {}
        def fake_urlopen(req, timeout):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return mock_resp
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fb = OllamaFallback()
            fb.generate("test")
        self.assertEqual(captured["body"]["model"], OLLAMA_DEFAULT_MODEL)

    def test_custom_model(self):
        mock_resp = _mock_response({"response": "ok"})
        captured = {}
        def fake_urlopen(req, timeout):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return mock_resp
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fb = OllamaFallback()
            fb.generate("test", model="mistral:7b")
        self.assertEqual(captured["body"]["model"], "mistral:7b")

    def test_raises_unavailable_on_url_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("conn refused")):
            fb = OllamaFallback()
            with self.assertRaises(OllamaUnavailableError):
                fb.generate("hello")

    def test_raises_generate_error_on_non_200(self):
        mock_resp = _mock_response({"error": "model not found"}, status=404)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            fb = OllamaFallback()
            with self.assertRaises(OllamaGenerateError):
                fb.generate("hello")


# ============================================================
# 5. RegexFallback
# ============================================================

class TestRegexFallback(unittest.TestCase):
    def test_always_returns_string(self):
        fb = RegexFallback()
        result = fb.generate("anything")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_contains_fallback_indicator(self):
        fb = RegexFallback()
        result = fb.generate("test")
        self.assertIn("FALLBACK", result)


# ============================================================
# 6. build_fallback_chain
# ============================================================

class TestBuildFallbackChain(unittest.TestCase):
    def test_uses_primary_when_available(self):
        primary = MagicMock(return_value="primary-response")
        chain = build_fallback_chain(primary_fn=primary)
        result = chain("test prompt")
        self.assertEqual(result, "primary-response")
        primary.assert_called_once_with("test prompt")

    def test_falls_to_ollama_when_primary_fails(self):
        primary = MagicMock(side_effect=RuntimeError("API down"))
        mock_resp_tags = _mock_response({"models": []})
        mock_resp_gen = _mock_response({"response": "ollama-response"})
        call_count = [0]
        def fake_urlopen(req, timeout):
            call_count[0] += 1
            if "/api/tags" in req.full_url:
                return mock_resp_tags
            return mock_resp_gen
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            chain = build_fallback_chain(primary_fn=primary)
            result = chain("test")
        self.assertEqual(result, "ollama-response")

    def test_falls_to_regex_when_ollama_unavailable(self):
        primary = MagicMock(side_effect=RuntimeError("down"))
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            chain = build_fallback_chain(primary_fn=primary)
            result = chain("test")
        self.assertIn("FALLBACK", result)

    def test_no_primary_fn_goes_straight_to_ollama(self):
        mock_resp_tags = _mock_response({"models": []})
        mock_resp_gen = _mock_response({"response": "local-answer"})
        def fake_urlopen(req, timeout):
            if "/api/tags" in req.full_url:
                return mock_resp_tags
            return mock_resp_gen
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            chain = build_fallback_chain(primary_fn=None)
            result = chain("test")
        self.assertEqual(result, "local-answer")


if __name__ == "__main__":
    unittest.main()

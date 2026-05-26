"""
Coverage tests for intent_compiler._call_llm() — LLM provider paths.

Tests all 5 code paths:
  1. RCT_LLM_PROVIDER=regex  → returns None immediately
  2. OpenAI available + API key + success  → returns parsed dict
  3. OpenAI raises Exception  → returns None (graceful fallback)
  4. Anthropic available + API key + success  → returns parsed dict
  5. No library, no key  → returns None
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import rct_control_plane.intent_compiler as _ic_mod
from rct_control_plane.intent_compiler import _call_llm


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_openai_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


def _make_anthropic_response(content: str) -> MagicMock:
    msg = MagicMock()
    item = MagicMock()
    item.text = content
    msg.content = [item]
    return msg


_VALID_RESULT = {
    "intent_type": "REFACTOR",
    "scope_type": "MODULE",
    "priority": "HIGH",
    "risk_profile": "STRUCTURAL",
    "max_cost_usd": None,
    "target": "src/auth",
}


# ---------------------------------------------------------------------------
# Path 1: provider=regex → always None
# ---------------------------------------------------------------------------

def test_call_llm_regex_provider_returns_none(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "regex")
    result = _call_llm("refactor the auth module")
    assert result is None


# ---------------------------------------------------------------------------
# Path 2: OpenAI success
# ---------------------------------------------------------------------------

def test_call_llm_openai_success(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_openai_response(
        json.dumps(_VALID_RESULT)
    )

    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client

    with patch.object(_ic_mod, "_HAS_OPENAI", True), \
         patch.object(_ic_mod, "_openai_module", mock_openai, create=True):
        result = _call_llm("refactor the auth module")

    assert result is not None
    assert result["intent_type"] == "REFACTOR"
    mock_openai.OpenAI.assert_called_once_with(api_key="sk-test-key")


# ---------------------------------------------------------------------------
# Path 3: OpenAI raises exception → None
# ---------------------------------------------------------------------------

def test_call_llm_openai_exception_returns_none(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("rate limited")

    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client

    with patch.object(_ic_mod, "_HAS_OPENAI", True), \
         patch.object(_ic_mod, "_openai_module", mock_openai, create=True):
        result = _call_llm("refactor the auth module")

    assert result is None


# ---------------------------------------------------------------------------
# Path 3b: OpenAI invalid JSON → None
# ---------------------------------------------------------------------------

def test_call_llm_openai_invalid_json_returns_none(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_openai_response(
        "not valid json!!!"
    )

    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client

    with patch.object(_ic_mod, "_HAS_OPENAI", True), \
         patch.object(_ic_mod, "_openai_module", mock_openai, create=True):
        result = _call_llm("refactor the auth module")

    assert result is None


# ---------------------------------------------------------------------------
# Path 4: Anthropic success
# ---------------------------------------------------------------------------

def test_call_llm_anthropic_success(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anth-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response(
        json.dumps(_VALID_RESULT)
    )

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.object(_ic_mod, "_HAS_OPENAI", False), \
         patch.object(_ic_mod, "_HAS_ANTHROPIC", True), \
         patch.object(_ic_mod, "_anthropic_module", mock_anthropic, create=True):
        result = _call_llm("deploy to production")

    assert result is not None
    assert result["intent_type"] == "REFACTOR"


# ---------------------------------------------------------------------------
# Path 4b: Anthropic raises exception → None
# ---------------------------------------------------------------------------

def test_call_llm_anthropic_exception_returns_none(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anth-test-key")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ConnectionError("timeout")

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.object(_ic_mod, "_HAS_OPENAI", False), \
         patch.object(_ic_mod, "_HAS_ANTHROPIC", True), \
         patch.object(_ic_mod, "_anthropic_module", mock_anthropic, create=True):
        result = _call_llm("deploy to production")

    assert result is None


# ---------------------------------------------------------------------------
# Path 5: No library, no key → None
# ---------------------------------------------------------------------------

def test_call_llm_no_provider_returns_none(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "auto")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch.object(_ic_mod, "_HAS_OPENAI", False), \
         patch.object(_ic_mod, "_HAS_ANTHROPIC", False):
        result = _call_llm("analyze the system risk")

    assert result is None


# ---------------------------------------------------------------------------
# Path 6: OpenAI auto but no key → skip to Anthropic check
# ---------------------------------------------------------------------------

def test_call_llm_openai_no_key_falls_to_anthropic(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "auto")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch.object(_ic_mod, "_HAS_OPENAI", True), \
         patch.object(_ic_mod, "_HAS_ANTHROPIC", False):
        result = _call_llm("build a new feature")

    assert result is None


# ---------------------------------------------------------------------------
# Path 7: OpenAI response empty string → returns {}
# ---------------------------------------------------------------------------

def test_call_llm_openai_empty_response(monkeypatch):
    monkeypatch.setenv("RCT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_openai_response("")

    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client

    with patch.object(_ic_mod, "_HAS_OPENAI", True), \
         patch.object(_ic_mod, "_openai_module", mock_openai):
        result = _call_llm("refactor auth")

    # Empty string → json.loads("") raises, so returns None or empty dict
    # Either is acceptable — the important thing is no crash
    assert result is None or result == {}

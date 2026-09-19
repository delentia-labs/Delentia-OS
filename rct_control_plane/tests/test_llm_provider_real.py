"""
Real LLMProvider abstraction tests — Round 22 Phase 10.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import os

import pytest

from rct_control_plane.llm_provider import OllamaProvider


def test_ollama_provider_real_completion():
    provider = OllamaProvider()
    result = asyncio.run(provider.complete("Reply with exactly the word: PONG"))
    assert isinstance(result, str) and len(result) > 0


def test_openrouter_provider_real_completion_or_honest_skip():
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set for this test run - real call cannot be made")
    from rct_control_plane.llm_provider import OpenRouterProvider
    provider = OpenRouterProvider()
    result = asyncio.run(provider.complete("Reply with exactly the word: PONG"))
    assert isinstance(result, str) and len(result) > 0


def test_get_default_provider_defaults_to_ollama(monkeypatch):
    monkeypatch.delenv("DELENTIA_LLM_PROVIDER", raising=False)
    from rct_control_plane.llm_provider import get_default_provider, OllamaProvider
    provider = get_default_provider()
    assert isinstance(provider, OllamaProvider)


def test_compat_profile_changes_the_real_constructed_payload():
    from rct_control_plane.llm_provider import CompatProfile, _build_openrouter_payload

    default_payload = _build_openrouter_payload(
        "anthropic/claude-sonnet-5", "hello", None, 0.7, 2048, False, CompatProfile(),
    )
    assert "max_tokens" in default_payload
    assert "max_completion_tokens" not in default_payload

    custom_payload = _build_openrouter_payload(
        "anthropic/claude-sonnet-5", "hello", "be nice", 0.7, 2048, False,
        CompatProfile(max_tokens_field="max_completion_tokens", supports_developer_role=False),
    )
    assert "max_completion_tokens" in custom_payload
    assert "max_tokens" not in custom_payload
    assert not any(m["role"] == "system" for m in custom_payload["messages"])
    assert "be nice" in custom_payload["messages"][0]["content"]


def test_quota_tracker_blocks_the_real_call_after_limit_reached():
    from rct_control_plane.llm_provider import OllamaProvider, QuotaTracker, QuotaCheckedProvider, QuotaExceededError

    quota = QuotaTracker(max_calls_per_provider={"ollama": 2})
    provider = QuotaCheckedProvider(OllamaProvider(), provider_name="ollama", quota=quota)

    asyncio.run(provider.complete("Reply with exactly the word: ONE"))
    asyncio.run(provider.complete("Reply with exactly the word: TWO"))

    try:
        asyncio.run(provider.complete("Reply with exactly the word: THREE"))
        raise AssertionError("expected QuotaExceededError on the 3rd real call")
    except QuotaExceededError:
        pass


def test_autonomous_loop_accepts_injected_provider():
    from rct_control_plane.autonomous_loop import decide_next_action
    from rct_control_plane.llm_provider import OllamaProvider

    decision = asyncio.run(decide_next_action(
        goal="Say hello, no tool needed.", history=[], available_tools=[],
        llm_provider=OllamaProvider(),
    ))
    assert decision["action"] in ("call_tool", "finish")

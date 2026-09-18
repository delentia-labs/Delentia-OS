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


def test_autonomous_loop_accepts_injected_provider():
    from rct_control_plane.autonomous_loop import decide_next_action
    from rct_control_plane.llm_provider import OllamaProvider

    decision = asyncio.run(decide_next_action(
        goal="Say hello, no tool needed.", history=[], available_tools=[],
        llm_provider=OllamaProvider(),
    ))
    assert decision["action"] in ("call_tool", "finish")

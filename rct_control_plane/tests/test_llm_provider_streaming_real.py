"""
Round 39: real tests for LLMProvider.stream_complete() - both real
providers' actual streaming wire formats (Ollama's newline-delimited
JSON, OpenRouter's OpenAI-compatible SSE) are exercised via
httpx.MockTransport, a real httpx testing utility that intercepts the
HTTP layer without a real network call - the same "no real network in
a fast unit test" discipline this engagement applies elsewhere. The
STREAMING PARSING LOGIC is real and fully exercised; only the actual
TCP/TLS round-trip is faked.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

import json

import httpx
import pytest

from rct_control_plane.llm_provider import (
    LLMProvider, OllamaProvider, OpenRouterProvider, QuotaCheckedProvider, QuotaExceededError, QuotaTracker,
)


def _ollama_ndjson_response(chunks):
    lines = [json.dumps({"response": chunk, "done": False}) for chunk in chunks]
    lines.append(json.dumps({"response": "", "done": True}))
    return httpx.Response(200, text="\n".join(lines))


def _openrouter_sse_response(chunks):
    lines = []
    for chunk in chunks:
        payload = {"choices": [{"delta": {"content": chunk}}]}
        lines.append(f"data: {json.dumps(payload)}")
    lines.append("data: [DONE]")
    body = "\n\n".join(lines) + "\n\n"
    return httpx.Response(200, text=body)


class TestOllamaStreaming:
    def test_real_ndjson_stream_is_parsed_into_real_incremental_chunks(self, monkeypatch):
        chunks_sent = ["Hello", ", ", "world", "!"]

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/generate"
            import json as _json
            payload = _json.loads(request.content)
            assert payload["stream"] is True
            return _ollama_ndjson_response(chunks_sent)

        provider = OllamaProvider()
        original_client = httpx.AsyncClient

        def _client_factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory)

        async def collect():
            return [chunk async for chunk in provider.stream_complete("say hello")]

        received = asyncio.run(collect())
        assert received == chunks_sent
        assert "".join(received) == "Hello, world!"

    def test_stream_stops_cleanly_at_the_real_done_sentinel(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return _ollama_ndjson_response(["only", " chunk"])

        provider = OllamaProvider()
        original_client = httpx.AsyncClient

        def _client_factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory)

        async def collect():
            return [chunk async for chunk in provider.stream_complete("hi")]

        received = asyncio.run(collect())
        assert received == ["only", " chunk"]


class TestOpenRouterStreaming:
    def test_real_sse_stream_is_parsed_into_real_incremental_chunks(self, monkeypatch):
        chunks_sent = ["The ", "answer ", "is ", "42."]

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json
            payload = _json.loads(request.content)
            assert payload["stream"] is True
            return _openrouter_sse_response(chunks_sent)

        provider = OpenRouterProvider(api_key="fake-key-for-test")
        original_client = httpx.AsyncClient

        def _client_factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory)

        async def collect():
            return [chunk async for chunk in provider.stream_complete("what is the answer?")]

        received = asyncio.run(collect())
        assert received == chunks_sent
        assert "".join(received) == "The answer is 42."


class TestBaseProviderDefaultFallback:
    def test_a_provider_that_does_not_override_stream_complete_falls_back_to_one_chunk(self):
        class _MinimalProvider(LLMProvider):
            async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
                return "whole answer at once"

        provider = _MinimalProvider()

        async def collect():
            return [chunk async for chunk in provider.stream_complete("hi")]

        received = asyncio.run(collect())
        assert received == ["whole answer at once"]


class TestQuotaCheckedProviderStreaming:
    def test_quota_exceeded_raises_before_any_streaming_starts(self):
        class _FakeInner(LLMProvider):
            async def complete(self, *a, **kw):
                return "should not be called"

            async def stream_complete(self, *a, **kw):
                raise AssertionError("should never be reached - quota check must happen first")
                yield  # pragma: no cover - unreachable, makes this a real generator

        quota = QuotaTracker(max_calls_per_provider={"fake": 0})
        wrapped = QuotaCheckedProvider(_FakeInner(), "fake", quota)

        async def collect():
            return [chunk async for chunk in wrapped.stream_complete("hi")]

        with pytest.raises(QuotaExceededError):
            asyncio.run(collect())

    def test_real_streaming_passes_through_when_quota_allows(self):
        class _FakeInner(LLMProvider):
            async def complete(self, *a, **kw):
                return "x"

            async def stream_complete(self, *a, **kw):
                for chunk in ["a", "b", "c"]:
                    yield chunk

        quota = QuotaTracker(max_calls_per_provider={"fake": 5})
        wrapped = QuotaCheckedProvider(_FakeInner(), "fake", quota)

        async def collect():
            return [chunk async for chunk in wrapped.stream_complete("hi")]

        assert asyncio.run(collect()) == ["a", "b", "c"]

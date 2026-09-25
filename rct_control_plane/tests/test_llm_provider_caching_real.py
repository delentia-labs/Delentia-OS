"""
Round 44 item I.3: real tests for OllamaProvider's new TopicCache wiring.
The network call itself is mocked here (monkeypatched httpx.AsyncClient.
post) - this is the same acceptable-mock reasoning used elsewhere this
round (see governed_autonomous_loop.py's J.4.1 tests): the question under
test is "is the real cache consulted/written at the right times", not
"does Ollama answer correctly" - a different question, already covered
for real by test_llm_provider_real.py's own real-network tests and by
this round's real J.4.2 Ollama integration script. TopicCache itself
(test_topic_cache.py) and its real SQLite persistence are exercised with
zero mocking here.
"""
import httpx
import pytest

from rct_control_plane.llm_provider import OllamaProvider
from rct_control_plane.topic_cache import TopicCache


class _FakeResponse:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._text}


@pytest.fixture
def cache(tmp_path):
    return TopicCache(db_path=str(tmp_path / "llm_cache_test.db"))


@pytest.fixture
def call_counter(monkeypatch):
    calls = {"n": 0}

    async def _fake_post(self, url, json=None, **kwargs):
        calls["n"] += 1
        return _FakeResponse(f"real response #{calls['n']}")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    return calls


class TestOllamaProviderCaching:
    @pytest.mark.asyncio
    async def test_low_temperature_second_identical_call_is_a_real_cache_hit(self, cache, call_counter):
        provider = OllamaProvider(cache=cache)
        first = await provider.complete("explain the FDIA formula", temperature=0.3)
        second = await provider.complete("explain the FDIA formula", temperature=0.3)

        assert call_counter["n"] == 1, "second call must not hit the network"
        assert first == second == "real response #1"

    @pytest.mark.asyncio
    async def test_high_temperature_call_is_never_cached(self, cache, call_counter):
        provider = OllamaProvider(cache=cache)
        await provider.complete("write a creative story", temperature=0.7)
        await provider.complete("write a creative story", temperature=0.7)

        assert call_counter["n"] == 2, "high-temperature calls must always hit the network"

    @pytest.mark.asyncio
    async def test_no_cache_configured_means_no_caching_at_all(self, call_counter):
        provider = OllamaProvider()  # cache=None, the real default
        await provider.complete("explain the FDIA formula", temperature=0.3)
        await provider.complete("explain the FDIA formula", temperature=0.3)

        assert call_counter["n"] == 2, "Zero-Delete: omitting cache= must behave exactly as before this round"

    @pytest.mark.asyncio
    async def test_different_prompts_are_real_separate_cache_entries(self, cache, call_counter):
        provider = OllamaProvider(cache=cache)
        await provider.complete("prompt A", temperature=0.1)
        await provider.complete("prompt B", temperature=0.1)

        assert call_counter["n"] == 2
        assert cache.count() == 2

    @pytest.mark.asyncio
    async def test_exactly_at_the_threshold_is_cacheable(self, cache, call_counter):
        provider = OllamaProvider(cache=cache)
        await provider.complete("boundary check", temperature=OllamaProvider._CACHEABLE_TEMPERATURE_MAX)
        await provider.complete("boundary check", temperature=OllamaProvider._CACHEABLE_TEMPERATURE_MAX)

        assert call_counter["n"] == 1

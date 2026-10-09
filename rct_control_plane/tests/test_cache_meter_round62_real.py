"""
Round 62: the meter records how much of each prompt the provider served from its prompt cache, so the decision "build prompt caching or not" is made from a measured hit rate, not a guess.

A real HTTP server on loopback stands in for OpenRouter (only a loopback address is accepted as an override) and answers with the usage block OpenRouter documents, including `prompt_tokens_details.cached_tokens`.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rct_control_plane.llm_provider import LLMUsage, MeteredProvider, OpenRouterProvider


class Fake(BaseHTTPRequestHandler):
    usages = []

    def do_POST(self):                                       # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        usage = Fake.usages.pop(0) if Fake.usages else {"prompt_tokens": 10, "completion_tokens": 2}
        body = json.dumps({"choices": [{"message": {"content": "ok"}}], "usage": usage}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake(monkeypatch):
    Fake.usages = []
    server = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    yield Fake
    server.shutdown()


def metered():
    return MeteredProvider(OpenRouterProvider(api_key="test-key-not-real", model="vendor/model"), prompt_price_per_mtok=1.0, completion_price_per_mtok=2.0)


def test_cached_tokens_are_read_from_the_provider_and_summed(fake):
    fake.usages = [{"prompt_tokens": 1000, "completion_tokens": 50, "prompt_tokens_details": {"cached_tokens": 0}},
                   {"prompt_tokens": 1000, "completion_tokens": 40, "prompt_tokens_details": {"cached_tokens": 800}},
                   {"prompt_tokens": 1000, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 800}}]
    provider = metered()

    async def go():
        for _ in range(3):
            await provider.complete("hello")
    asyncio.run(go())
    summary = provider.summary()
    assert summary["prompt_tokens"] == 3000 and summary["cached_prompt_tokens"] == 1600 and summary["cache_hit_rate"] == round(1600 / 3000, 4)


def test_a_provider_that_reports_nothing_counts_zero_not_a_guess(fake):
    fake.usages = [{"prompt_tokens": 500, "completion_tokens": 20}]
    provider = metered()
    asyncio.run(provider.complete("hello"))
    assert provider.summary()["cached_prompt_tokens"] == 0 and provider.summary()["cache_hit_rate"] == 0.0


def test_a_nonsense_cached_figure_cannot_exceed_the_prompt(fake):
    fake.usages = [{"prompt_tokens": 100, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 9999}}]
    provider = metered()
    asyncio.run(provider.complete("hello"))
    assert provider.summary()["cached_prompt_tokens"] == 100


def test_the_summary_has_no_rate_before_any_call():
    assert metered().summary()["cache_hit_rate"] is None


def test_the_usage_record_defaults_keep_older_callers_working():
    assert LLMUsage(1, 2, None).cached_tokens == 0

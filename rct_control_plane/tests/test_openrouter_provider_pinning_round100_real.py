"""Round 100: pin the upstream provider of an OpenRouter call (llm_provider.openrouter_provider_preferences) and record who answered.

Pure functions for the settings; a REAL loopback HTTP server stands in for OpenRouter (the base URL override accepts only loopback or openrouter.ai) so the body that really goes out and the
`provider` field that comes back are checked, not mocked. What is proved: nothing set = the request is exactly what it always was; a pinned order does not silently fall back; an unusable value is
ignored and never sent; the data-policy switches reach the wire; the provider that served the call is recorded.
"""
import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import llm_provider as lp

ENVS = [lp.PROVIDER_ORDER_ENV, lp.PROVIDER_ONLY_ENV, lp.PROVIDER_IGNORE_ENV, lp.PROVIDER_FALLBACKS_ENV, lp.PROVIDER_DATA_ENV, lp.PROVIDER_ZDR_ENV, lp.PROVIDER_REQUIRE_PARAMS_ENV,
        lp.PROVIDER_QUANT_ENV]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in ENVS:
        monkeypatch.delenv(name, raising=False)


def test_nothing_set_means_no_provider_object_and_the_payload_is_what_it_always_was():
    assert lp.openrouter_provider_preferences() == {}
    payload = lp._build_openrouter_payload("vendor/model", "hi", "be brief", 0.0, 100, True, lp.CompatProfile())
    assert "provider" not in payload and payload["model"] == "vendor/model" and payload["response_format"] == {"type": "json_object"}


def test_a_pinned_order_does_not_silently_fall_back(monkeypatch):
    monkeypatch.setenv(lp.PROVIDER_ORDER_ENV, "anthropic, google-vertex")
    assert lp.openrouter_provider_preferences() == {"order": ["anthropic", "google-vertex"], "allow_fallbacks": False}
    monkeypatch.setenv(lp.PROVIDER_FALLBACKS_ENV, "1")
    assert lp.openrouter_provider_preferences()["allow_fallbacks"] is True


def test_data_policy_switches_reach_the_preferences(monkeypatch):
    monkeypatch.setenv(lp.PROVIDER_DATA_ENV, "deny")
    monkeypatch.setenv(lp.PROVIDER_ZDR_ENV, "1")
    monkeypatch.setenv(lp.PROVIDER_REQUIRE_PARAMS_ENV, "yes")
    monkeypatch.setenv(lp.PROVIDER_QUANT_ENV, "fp8,bf16")
    monkeypatch.setenv(lp.PROVIDER_IGNORE_ENV, "badhost")
    assert lp.openrouter_provider_preferences() == {"data_collection": "deny", "zdr": True, "require_parameters": True, "quantizations": ["fp8", "bf16"], "ignore": ["badhost"]}


def test_an_unusable_value_is_ignored_and_never_sent(monkeypatch):
    monkeypatch.setenv(lp.PROVIDER_ORDER_ENV, "good-one, bad one with spaces, ../../etc, ")
    monkeypatch.setenv(lp.PROVIDER_QUANT_ENV, "fp8, made-up")
    monkeypatch.setenv(lp.PROVIDER_DATA_ENV, "maybe")
    prefs = lp.openrouter_provider_preferences()
    assert prefs["order"] == ["good-one"] and prefs["quantizations"] == ["fp8"] and "data_collection" not in prefs


def test_a_flag_that_is_neither_on_nor_off_changes_nothing(monkeypatch):
    monkeypatch.setenv(lp.PROVIDER_ZDR_ENV, "perhaps")
    monkeypatch.setenv(lp.PROVIDER_FALLBACKS_ENV, "perhaps")
    assert lp.openrouter_provider_preferences() == {}


def test_lists_are_bounded(monkeypatch):
    monkeypatch.setenv(lp.PROVIDER_ONLY_ENV, ",".join(f"p{i}" for i in range(50)))
    assert len(lp.openrouter_provider_preferences()["only"]) == 10


class _Server:
    def __init__(self, provider_name):
        outer = self
        self.bodies = []
        self.provider_name = provider_name

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):                                                        # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                outer.bodies.append(body)
                reply = {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 2, "cost": 0.0001}}
                if outer.provider_name is not None:
                    reply["provider"] = outer.provider_name
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):                                             # noqa: D401
                return

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def call(monkeypatch, provider_name):
    server = _Server(provider_name)
    monkeypatch.setenv(lp.OPENROUTER_BASE_ENV, server.url)
    try:
        provider = lp.OpenRouterProvider(api_key="test-key-not-real", model="vendor/model")
        text = asyncio.run(provider.complete("hello", max_tokens=50))
        return server, provider, text
    finally:
        server.close()


def test_the_pinned_provider_object_really_goes_out_and_the_server_that_answered_is_recorded(monkeypatch):
    monkeypatch.setenv(lp.PROVIDER_ORDER_ENV, "deepinfra")
    monkeypatch.setenv(lp.PROVIDER_DATA_ENV, "deny")
    server, provider, text = call(monkeypatch, "DeepInfra")
    assert text == "ok" and server.bodies[0]["provider"] == {"order": ["deepinfra"], "allow_fallbacks": False, "data_collection": "deny"}
    assert provider.last_served_by == "DeepInfra" and provider.last_usage.prompt_tokens == 7


def test_with_nothing_set_the_wire_body_has_no_provider_and_a_silent_server_leaves_served_by_empty(monkeypatch):
    server, provider, _ = call(monkeypatch, None)
    assert "provider" not in server.bodies[0] and provider.last_served_by is None


def test_the_metered_wrapper_passes_served_by_through(monkeypatch):
    server = _Server("Together")
    monkeypatch.setenv(lp.OPENROUTER_BASE_ENV, server.url)
    try:
        inner = lp.OpenRouterProvider(api_key="test-key-not-real", model="vendor/model")
        metered = lp.MeteredProvider(inner, prompt_price_per_mtok=1.0, completion_price_per_mtok=2.0)
        asyncio.run(metered.complete("hello", max_tokens=50))
        assert metered.last_served_by == "Together"
    finally:
        server.close()

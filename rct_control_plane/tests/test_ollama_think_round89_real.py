"""
Round 89: DELENTIA_OLLAMA_THINK. A thinking model (qwen3) spent 277 s answering '17 x 23' through the host; the switch asks Ollama not to think. A real HTTP server on loopback stands in for Ollama
and records the request body, so the test sees exactly what would have been sent.
"""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rct_control_plane import llm_provider as lp


@pytest.fixture()
def fake_ollama():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):                                                    # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            seen.append(body)
            data = json.dumps({"response": "ok", "done": True, "prompt_eval_count": 3, "eval_count": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


@pytest.mark.parametrize("value,expected", [("off", False), ("0", False), ("false", False), ("on", True), ("1", True), ("", None), ("maybe", None)])
def test_the_setting_is_read_from_the_environment(monkeypatch, value, expected):
    monkeypatch.setenv("DELENTIA_OLLAMA_THINK", value)
    assert lp.ollama_think_setting() is expected


def test_nothing_is_sent_about_thinking_unless_asked(monkeypatch, fake_ollama):
    url, seen = fake_ollama
    monkeypatch.delenv("DELENTIA_OLLAMA_THINK", raising=False)
    assert asyncio.run(lp.OllamaProvider(llm_url=url, model="qwen3:8b").complete("hi")) == "ok"
    assert "think" not in seen[-1]                                          # the old request, byte for byte, when the switch is not set


def test_off_asks_ollama_not_to_think_and_on_forces_it(monkeypatch, fake_ollama):
    url, seen = fake_ollama
    monkeypatch.setenv("DELENTIA_OLLAMA_THINK", "off")
    asyncio.run(lp.OllamaProvider(llm_url=url, model="qwen3:8b").complete("hi"))
    assert seen[-1]["think"] is False
    monkeypatch.setenv("DELENTIA_OLLAMA_THINK", "on")
    asyncio.run(lp.OllamaProvider(llm_url=url, model="qwen3:8b").complete("hi"))
    assert seen[-1]["think"] is True

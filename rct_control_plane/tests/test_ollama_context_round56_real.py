"""
Round 56: Ollama silently truncates a prompt that does not fit its default 4096-token window, from the start. The loop's prompt with the full tool
menu is about 6,000 tokens, so local models were reading a prompt with the goal and the instructions cut off. These tests talk to a real HTTP server
that speaks Ollama's /api/generate and truncates exactly as Ollama does (it keeps the last num_ctx tokens), so the effect is observable end to end.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from rct_control_plane import llm_provider as lp


class FakeOllama:
    """Counts a token per 4 characters, keeps only the last num_ctx tokens of the prompt (Ollama's behaviour), and answers with what it saw."""

    def __init__(self):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                outer.requests.append(body)
                ctx = int((body.get("options") or {}).get("num_ctx") or 4096)
                tokens = max(1, len(body["prompt"]) // 4)
                seen = body["prompt"][-ctx * 4:] if tokens > ctx else body["prompt"]
                reply = json.dumps({"response": json.dumps({"saw_goal": "GOAL-MARKER" in seen}), "done": True,
                                    "prompt_eval_count": min(tokens, ctx), "eval_count": 5}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"


@pytest.fixture
def ollama(monkeypatch):
    monkeypatch.delenv("DELENTIA_OLLAMA_NUM_CTX", raising=False)
    fake = FakeOllama()
    yield fake
    fake.server.shutdown()


def test_the_window_grows_in_steps_with_the_prompt_and_is_capped():
    assert lp.ollama_num_ctx(2_000) == 4096
    assert lp.ollama_num_ctx(10_000) == 8192
    assert lp.ollama_num_ctx(25_000) == 16384
    assert lp.ollama_num_ctx(60_000) == 32768 and lp.ollama_num_ctx(10_000_000) == 32768
    sizes = {lp.ollama_num_ctx(n) for n in range(0, 100_000, 500)}
    assert sizes <= {4096, 8192, 16384, 32768}                     # a few fixed steps: every change of window reloads the model


def test_the_environment_can_override_or_switch_it_off(monkeypatch):
    monkeypatch.setenv("DELENTIA_OLLAMA_NUM_CTX", "12288")
    assert lp.ollama_num_ctx(100) == 12288
    monkeypatch.setenv("DELENTIA_OLLAMA_NUM_CTX", "0")
    assert lp.ollama_num_ctx(100) == 0
    monkeypatch.setenv("DELENTIA_OLLAMA_NUM_CTX", "not a number")
    assert lp.ollama_num_ctx(100) == 4096


def test_a_long_prompt_reaches_the_model_whole_instead_of_losing_its_beginning(ollama):
    long_prompt = "GOAL-MARKER please do the thing\n" + ("tool description line that is fairly long\n" * 700)      # ~28,000 characters: ~7,000 tokens
    provider = lp.OllamaProvider(llm_url=ollama.url, model="m")
    result = json.loads(asyncio.run(provider.complete(long_prompt, temperature=0.9)))
    assert result["saw_goal"] is True
    assert ollama.requests[0]["options"]["num_ctx"] >= 8192
    # the same prompt without the fix: Ollama's default window, the goal at the front is gone
    cut = FakeOllama()
    raw = lp.httpx.post(f"{cut.url}/api/generate", json={"prompt": long_prompt, "options": {}}).json()
    assert json.loads(raw["response"])["saw_goal"] is False
    cut.server.shutdown()


def test_a_short_prompt_keeps_the_default_window_so_the_model_is_not_reloaded(ollama):
    provider = lp.OllamaProvider(llm_url=ollama.url, model="m")
    asyncio.run(provider.complete("GOAL-MARKER short", temperature=0.9))
    assert ollama.requests[0]["options"]["num_ctx"] == 4096


def test_switching_the_window_off_sends_no_num_ctx(ollama, monkeypatch):
    monkeypatch.setenv("DELENTIA_OLLAMA_NUM_CTX", "0")
    asyncio.run(lp.OllamaProvider(llm_url=ollama.url, model="m").complete("GOAL-MARKER short", temperature=0.9))
    assert "num_ctx" not in ollama.requests[0]["options"]


def test_a_prompt_that_still_fills_the_window_is_reported(ollama, monkeypatch, caplog):
    monkeypatch.setenv("DELENTIA_OLLAMA_NUM_CTX", "1024")                   # too small on purpose
    provider = lp.OllamaProvider(llm_url=ollama.url, model="m")
    with caplog.at_level("WARNING", logger="rct_control_plane.llm_provider"):
        asyncio.run(provider.complete("GOAL-MARKER " + "x" * 12_000, temperature=0.9))
    assert any("truncated" in r.message for r in caplog.records)
    assert provider.last_usage.prompt_tokens == 1024

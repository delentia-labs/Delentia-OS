"""
Round 111: the agent's picture tool is charged to the running episode's cap.

Before this, `delentia_describe_image` used the default vision provider directly: whatever it spent, the episode's meter never saw it, so a per-episode budget did not cover pictures.
The loop already publishes the running episode's meter (`budget_share.current_meter`); `vision.describe_image` now charges its call to it through `MeteredProvider.side_provider`.
Real HTTP server on loopback; nothing here calls a paid model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rct_control_plane import budget_share, llm_provider, vision
from rct_control_plane.llm_provider import MeteredProvider, OpenAICompatibleProvider

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


class _Server:
    def __init__(self):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):          # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.requests.append(body)
                raw = json.dumps({"choices": [{"message": {"role": "assistant", "content": "a red card"}}], "usage": {"prompt_tokens": 1500, "completion_tokens": 10}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"


@pytest.fixture()
def world(tmp_path, monkeypatch):
    srv = _Server()
    image = tmp_path / "frame.png"
    image.write_bytes(PNG)
    vision_model = OpenAICompatibleProvider(base_url=srv.url, model="m/vision")
    monkeypatch.setattr(llm_provider, "get_default_provider", lambda *a, **k: vision_model)
    yield srv, image, tmp_path
    srv.server.shutdown()
    srv.server.server_close()


def call_in_episode(meter, image, root):
    async def go():
        budget_share.current_meter.set(meter)             # what the governed loop does when an episode starts
        return await vision.describe_image(str(image), "what is in it", allowed_roots=(root,))
    return asyncio.run(go())


def episode_meter(max_cost):
    text_model = OpenAICompatibleProvider(base_url="http://127.0.0.1:9", model="m/text")      # the episode's own model: never called here
    return MeteredProvider(text_model, max_cost_usd=max_cost, prompt_price_per_mtok=1.0, completion_price_per_mtok=2.0)


def test_a_picture_looked_at_inside_an_episode_is_counted_by_that_episode(world):
    srv, image, root = world
    meter = episode_meter(0.5)
    result = call_in_episode(meter, image, root)
    assert result["description"] == "a red card" and len(srv.requests) == 1
    assert meter.calls == 1 and meter.prompt_tokens == 1500 and meter.completion_tokens == 10
    assert meter.cost_usd == pytest.approx((1500 * 1.0 + 10 * 2.0) / 1_000_000, abs=1e-9)


def test_a_picture_that_would_pass_the_episodes_cap_is_refused_and_never_sent(world):
    srv, image, root = world
    meter = episode_meter(0.0005)                         # the worst case of one picture (2,000 tokens at $1/M) is already $0.002
    result = call_in_episode(meter, image, root)
    assert result["refused_by"] == "budget" and "budget" in result["error"]
    assert srv.requests == [] and meter.calls == 0


def test_two_pictures_and_text_share_one_cap(world):
    srv, image, root = world
    meter = episode_meter(0.0045)                         # room for one picture (worst case about $0.0034) but not for a second after the first is paid
    first = call_in_episode(meter, image, root)
    assert "description" in first
    second = call_in_episode(meter, image, root)
    assert second.get("refused_by") == "budget"                 # spent $0.0015 + a new reservation of about $0.0034 is over $0.0045
    assert meter.cost_usd <= 0.0045 and len(srv.requests) == 1


def test_outside_an_episode_nothing_changes(world):
    srv, image, root = world
    budget_share.current_meter.set(None)
    result = asyncio.run(vision.describe_image(str(image), "q", allowed_roots=(root,)))
    assert result["description"] == "a red card" and len(srv.requests) == 1


def test_the_meter_reads_the_side_calls_usage_not_the_episodes_model(world):
    """The episode's own model never answered: its usage must not be read for this call."""
    srv, image, root = world
    meter = episode_meter(0.5)
    meter._inner.last_usage = None
    call_in_episode(meter, image, root)
    assert meter.prompt_tokens == 1500 and meter.last_usage.prompt_tokens == 1500

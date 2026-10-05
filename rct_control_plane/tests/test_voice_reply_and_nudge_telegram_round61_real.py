"""
Round 61: Telegram - a spoken reply to a voice note, and the memory-nudge line under a text answer.

A real HTTP server stands in for Telegram and keeps the raw bytes of every call; the speech engine and ffmpeg on this machine make a real Ogg/Opus file, which is checked by its magic bytes.
The agent is the one thing replaced (the `_dispatch_to_autonomous_loop` seam) and, for the voice-note case, the transcription (`_hear`), so no model is loaded.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rct_control_plane import memory_nudge, voice
from rct_control_plane.agent_factory import SENDER_ALLOWLIST_ENV
from rct_control_plane.gateways.telegram_gateway import TelegramGateway

run = asyncio.run
need_speech = pytest.mark.skipif(voice.tts_engine() is None or shutil.which("ffmpeg") is None, reason="needs a speech engine and ffmpeg on this machine")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("DELENTIA_EXCHANGE_DIR", raising=False)
    import rct_control_plane.mcp_server as mcp_server
    from rct_control_plane.exchange_bridge import NeuralExchangeBridge
    monkeypatch.setattr(mcp_server, "_exchange_bridge", NeuralExchangeBridge(root_dir=str(tmp_path / "exchange")))
    monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42")
    monkeypatch.setenv("DELENTIA_VOICE_INPUT", "1")
    monkeypatch.delenv(voice.REPLY_ENV, raising=False)


class Fake(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):                                       # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        Fake.calls.append((self.path.rsplit("/", 1)[-1], self.rfile.read(length)))
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def telegram():
    Fake.calls = []
    server = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


class Kernel:
    class _P:
        def append_audit(self, **kwargs):
            pass
    _persistence = _P()


def gateway(base, answer="It is sunny today.", nudge=None, heard="what is the weather"):
    gw = TelegramGateway(kernel=Kernel(), bot_token="TOKEN", api_base=base)

    async def fake_agent(goal, namespace):
        return {"final_answer": answer, "memory_nudge": nudge or []}

    async def fake_hear(voice_note):
        return heard
    gw._dispatch_to_autonomous_loop = fake_agent
    gw._hear = fake_hear
    return gw


def voice_update():
    return {"update_id": 1, "message": {"chat": {"id": 42}, "from": {"id": 42}, "voice": {"file_id": "f1", "duration": 3, "file_size": 1000}}}


def text_update(text="hello"):
    return {"update_id": 2, "message": {"chat": {"id": 42}, "from": {"id": 42}, "text": text}}


def calls(name):
    return [body for method, body in Fake.calls if method == name]


class TestVoiceReply:
    @need_speech
    def test_a_voice_note_gets_the_text_and_then_the_same_words_spoken(self, telegram, monkeypatch):
        monkeypatch.setenv(voice.REPLY_ENV, "1")
        out = run(gateway(telegram).handle_update(voice_update()))
        assert len(calls("sendMessage")) == 1 and b"It is sunny today." in calls("sendMessage")[0]
        sent = calls("sendVoice")
        assert len(sent) == 1 and b"OggS" in sent[0] and b'name="voice"' in sent[0] and b"TOKEN" not in sent[0]
        assert out["voice_reply"] == "sent"

    @need_speech
    def test_a_text_message_never_gets_a_spoken_reply(self, telegram, monkeypatch):
        monkeypatch.setenv(voice.REPLY_ENV, "1")
        run(gateway(telegram).handle_update(text_update()))
        assert len(calls("sendMessage")) == 1 and calls("sendVoice") == []

    def test_off_by_default(self, telegram):
        out = run(gateway(telegram).handle_update(voice_update()))
        assert len(calls("sendMessage")) == 1 and calls("sendVoice") == [] and out["voice_reply"] == "off"

    def test_a_long_answer_is_not_spoken(self, telegram, monkeypatch):
        monkeypatch.setenv(voice.REPLY_ENV, "1")
        out = run(gateway(telegram, answer="word " * 400).handle_update(voice_update()))
        assert calls("sendVoice") == [] and "too long" in out["voice_reply"]

    def test_no_speech_engine_or_ffmpeg_is_not_an_error_the_text_is_already_there(self, telegram, monkeypatch):
        monkeypatch.setenv(voice.REPLY_ENV, "1")
        monkeypatch.setattr(voice, "tts_engine", lambda: None)
        out = run(gateway(telegram).handle_update(voice_update()))
        assert len(calls("sendMessage")) == 1 and calls("sendVoice") == [] and "no speech engine" in out["voice_reply"]

    def test_a_missing_ffmpeg_is_reported_not_raised(self, telegram, monkeypatch):
        monkeypatch.setenv(voice.REPLY_ENV, "1")
        if voice.tts_engine() is None:
            pytest.skip("needs a speech engine")
        real_which = shutil.which
        monkeypatch.setattr(voice.shutil, "which", lambda name, *a, **k: None if name == "ffmpeg" else real_which(name, *a, **k))
        out = run(gateway(telegram).handle_update(voice_update()))
        assert calls("sendVoice") == [] and "ffmpeg was not found" in out["voice_reply"]

    def test_a_stopped_episode_with_no_answer_is_not_spoken(self, telegram, monkeypatch):
        monkeypatch.setenv(voice.REPLY_ENV, "1")
        gw = TelegramGateway(kernel=Kernel(), bot_token="TOKEN", api_base=telegram)

        async def stopped(goal, namespace):
            return {"stopped_reason": "pending_approval"}

        async def hear(note):
            return "do the thing"
        gw._dispatch_to_autonomous_loop, gw._hear = stopped, hear
        run(gw.handle_update(voice_update()))
        assert calls("sendVoice") == []


class TestNudgeLine:
    def test_the_suggestion_appears_under_the_answer_on_telegram(self, telegram):
        nudge = [{"id": "mc-1a2b3c4d", "text": "My favourite colour is green.", "kind": "preference"}]
        run(gateway(telegram, nudge=nudge).handle_update(text_update("My favourite colour is green. What is 2+2?")))
        body = calls("sendMessage")[0].decode("utf-8")
        assert "It is sunny today." in body and "/remember mc-1a2b3c4d" in body and "/skip mc-1a2b3c4d" in body and "favourite colour" in body

    def test_no_suggestion_no_line(self, telegram):
        run(gateway(telegram).handle_update(text_update()))
        assert b"/remember" not in calls("sendMessage")[0]

    def test_the_text_helper_is_empty_without_candidates(self):
        assert memory_nudge.nudge_text([]) == ""

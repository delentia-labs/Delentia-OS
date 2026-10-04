"""
Round 58: voice (hearing and speaking) and Telegram voice notes.

Real engines: this machine's own speech engine speaks, local Whisper (`tiny`, already on the disk) listens, so the round trip text -> WAV -> text is checked end to end.
Tests that need an engine that is not present (no speech engine, no cached model, no ffmpeg) are skipped, not faked. Telegram is a real HTTP server on loopback that
speaks getFile / file download / sendMessage; the agent is the one thing replaced (the `_dispatch_to_autonomous_loop` seam), to see what it is asked.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from rct_control_plane import voice
from rct_control_plane.agent_factory import SENDER_ALLOWLIST_ENV
from rct_control_plane.gateways.telegram_gateway import TelegramGateway
from rct_control_plane.governed_autonomous_loop import EXTERNAL_CONTENT_TOOLS, TAINT_SOURCE_TOOLS


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("DELENTIA_EXCHANGE_DIR", raising=False)
    import rct_control_plane.mcp_server as mcp_server
    from rct_control_plane.exchange_bridge import NeuralExchangeBridge
    monkeypatch.setattr(mcp_server, "_exchange_bridge", NeuralExchangeBridge())
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(mcp_server, "REPO_ROOT", repo.resolve())
    return repo


need_engines = pytest.mark.skipif(not (voice.stt_status()["available"] and voice.tts_engine()), reason="needs a speech engine and a cached Whisper model")
need_tts = pytest.mark.skipif(not voice.tts_engine(), reason="no speech engine on this machine")


def silent_wav(path, seconds, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)


# ------------------------------------------------------------------ speaking and hearing

class TestSpeakAndHear:
    @need_engines
    def test_what_is_spoken_is_heard_again(self):
        said = run(voice.speak("Hello world. This is a test of the voice system."))
        assert said["bytes"] > 1000 and said["seconds"] > 1 and Path(said["path"]).name.startswith("speech-")
        heard = run(voice.transcribe_audio(said["path"], "en"))
        assert "error" not in heard, heard
        text = heard["text"].lower()
        assert "hello" in text and "voice" in text and heard["language"] == "en" and "Third-party content" in heard["note"]

    @need_tts
    def test_the_text_is_never_part_of_a_command_line(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        said = run(voice.speak('say "hi"; New-Item pwned.txt; $(Remove-Item x) `whoami` & echo done'))
        assert "error" not in said, said
        assert not (tmp_path / "pwned.txt").exists()

    @need_tts
    def test_the_same_text_gives_the_same_file_name(self):
        a, b = run(voice.speak("same words")), run(voice.speak("same   words"))
        assert a["path"] == b["path"] and a["sha256"] == b["sha256"]

    def test_nothing_to_say_is_said_plainly(self):
        assert run(voice.speak("   \n "))["refused_by"] == "voice"

    @need_tts
    def test_a_very_long_text_is_cut(self):
        said = run(voice.speak("word " * 2000))
        assert said["chars"] <= voice.MAX_SPEAK_CHARS

    def test_no_engine_is_reported(self, monkeypatch):
        monkeypatch.setattr(voice, "tts_engine", lambda: None)
        said = run(voice.speak("hello"))
        assert said["configured"] is False and "no speech engine" in said["error"]


class TestHearingIsBounded:
    def test_a_model_that_is_not_on_the_disk_is_never_downloaded(self, monkeypatch, tmp_path):
        monkeypatch.setenv(voice.STT_MODEL_ENV, "large-v3-not-here")
        try:
            import whisper
            monkeypatch.setattr(whisper, "load_model", lambda *a, **k: pytest.fail("a model must not be loaded or downloaded"))
        except ImportError:                      # CI has no Whisper: the status check alone must refuse (nothing to download with)
            pass
        (tmp_path / "repo" / "a.wav").write_bytes(b"x")
        r = run(voice.transcribe_audio("a.wav"))
        assert "not available" in r["error"] and "not downloaded automatically" in r["error"]

    @pytest.mark.skipif(not voice.stt_status()["available"], reason="needs a cached Whisper model")
    def test_audio_longer_than_the_limit_is_refused(self, home):
        silent_wav(home / "long.wav", voice.MAX_AUDIO_SECONDS + 10)
        r = run(voice.transcribe_audio("long.wav"))
        assert "limit" in r["error"]

    @pytest.mark.skipif(not voice.stt_status()["available"], reason="needs a cached Whisper model")
    def test_a_file_that_is_not_audio_is_an_error_not_a_crash(self, home):
        (home / "text.wav").write_text("this is not audio")
        r = run(voice.transcribe_audio("text.wav"))
        assert "could not transcribe" in r["error"]

    def test_too_big_is_refused(self, home):
        (home / "big.wav").write_bytes(b"0" * (voice.MAX_AUDIO_BYTES + 1))
        r = run(voice.transcribe_audio("big.wav"))
        assert "larger than" in r["error"] or "not available" in r["error"]

    @pytest.mark.parametrize("path", ["../outside.wav", "/etc/hosts"])
    def test_a_path_outside_the_allowed_places_is_refused(self, path):
        assert run(voice.transcribe_audio(path))["refused_by"] == "voice"

    @pytest.mark.parametrize("name", ["server.pem", "my_secret.wav", "credentials.wav", "id_rsa"])
    def test_a_key_like_name_is_refused(self, home, name):
        (home / name).write_bytes(b"x")
        assert "key or a credentials" in run(voice.transcribe_audio(name))["error"]

    def test_the_status_says_what_is_missing(self, monkeypatch):
        monkeypatch.setenv(voice.STT_MODEL_ENV, "nothing")
        status = voice.stt_status()
        assert status["available"] is False and any("not on this machine" in p for p in status["problems"])


class TestGovernance:
    def test_a_transcript_is_third_party_content_that_taints(self):
        assert "delentia_transcribe_audio" in EXTERNAL_CONTENT_TOOLS and "delentia_transcribe_audio" in TAINT_SOURCE_TOOLS

    def test_both_tools_are_registered(self):
        from rct_control_plane.mcp_server import mcp
        names = {t.name for t in run(mcp.list_tools())}
        assert {"delentia_transcribe_audio", "delentia_speak"} <= names


# ------------------------------------------------------------------ Telegram voice notes

class FakeTelegram(BaseHTTPRequestHandler):
    calls = []
    audio = b""

    def _send(self, body, ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                        # noqa: N802
        FakeTelegram.calls.append(self.path.split("?")[0].split("/", 2)[-1])
        if "/getFile" in self.path:
            path = "voice/../evil.oga" if "bad" in self.path else "voice/file_1.wav"
            self._send(json.dumps({"ok": True, "result": {"file_id": "x", "file_path": path}}).encode())
        elif "/file/bot" in self.path:
            self._send(FakeTelegram.audio, "audio/ogg")
        else:
            self._send(b"{}")

    def do_POST(self):                                       # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        FakeTelegram.calls.append("POST " + self.path.rsplit("/", 1)[-1] + " " + self.rfile.read(length).decode())
        self._send(b"{}")

    def log_message(self, *args):
        pass


@pytest.fixture
def telegram(monkeypatch):
    FakeTelegram.calls = []
    s = HTTPServer(("127.0.0.1", 0), FakeTelegram)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42")
    monkeypatch.setenv("DELENTIA_VOICE_INPUT", "1")
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


class Kernel:
    class _P:
        def append_audit(self, **kwargs):
            pass
    _persistence = _P()


def gateway(base):
    gw = TelegramGateway(kernel=Kernel(), bot_token="TOKEN", api_base=base)
    asked = []

    async def fake_agent(goal, namespace):
        asked.append((goal, namespace))
        return {"final_answer": "Here is your answer."}
    gw._dispatch_to_autonomous_loop = fake_agent
    return gw, asked


def voice_update(sender=42, duration=4, file_size=1000, key="voice", file_id="f1"):
    return {"update_id": 1, "message": {"chat": {"id": sender}, "from": {"id": sender}, key: {"file_id": file_id, "duration": duration, "file_size": file_size}}}


class TestTelegramVoice:
    @need_engines
    def test_a_voice_note_from_an_allowed_sender_becomes_their_goal_and_they_are_told_what_was_heard(self, telegram):
        FakeTelegram.audio = Path(run(voice.speak("What is on my calendar today?"))["path"]).read_bytes()
        gw, asked = gateway(telegram)
        out = run(gw.handle_update(voice_update()))
        assert len(asked) == 1 and "calendar" in asked[0][0].lower() and asked[0][1] == "telegram-42"
        sent = [c for c in FakeTelegram.calls if c.startswith("POST sendMessage")]
        assert "I heard" in sent[0] and "Here is your answer." in sent[0] and out["heard"] == asked[0][0]
        assert "TOKEN" not in json.dumps(out)

    def test_it_is_off_unless_the_owner_turned_it_on(self, telegram, monkeypatch):
        monkeypatch.delenv("DELENTIA_VOICE_INPUT")
        gw, asked = gateway(telegram)
        assert run(gw.handle_update(voice_update())) is None and asked == [] and FakeTelegram.calls == []

    def test_a_stranger_never_makes_this_machine_download_or_listen(self, telegram, monkeypatch):
        monkeypatch.delenv("DELENTIA_PAIRING", raising=False)
        gw, asked = gateway(telegram)
        out = run(gw.handle_update(voice_update(sender=99)))
        assert out["rejected"] and asked == [] and not [c for c in FakeTelegram.calls if "getFile" in c or "file/bot" in c]

    def test_a_voice_note_that_is_too_long_is_declined_without_a_download(self, telegram):
        gw, asked = gateway(telegram)
        out = run(gw.handle_update(voice_update(duration=voice.MAX_AUDIO_SECONDS + 1)))
        assert "longer than" in out["voice_error"] and asked == [] and not [c for c in FakeTelegram.calls if "getFile" in c]

    def test_a_file_path_with_dots_from_the_server_is_not_followed(self, telegram):
        gw, asked = gateway(telegram)
        out = run(gw.handle_update(voice_update(file_id="bad")))
        assert "voice_error" in out and asked == [] and not [c for c in FakeTelegram.calls if "file/bot" in c]

    @need_engines
    def test_silence_is_not_sent_to_the_agent(self, telegram, tmp_path):
        silent_wav(tmp_path / "s.wav", 2)
        FakeTelegram.audio = (tmp_path / "s.wav").read_bytes()
        gw, asked = gateway(telegram)
        out = run(gw.handle_update(voice_update()))
        assert asked == [] and out.get("voice_error") == "no speech"

    def test_a_plain_text_message_still_works_and_commands_still_answer(self, telegram):
        gw, asked = gateway(telegram)
        run(gw.handle_update({"update_id": 2, "message": {"chat": {"id": 42}, "from": {"id": 42}, "text": "hello"}}))
        assert asked == [("hello", "telegram-42")]
        out = run(gw.handle_update({"update_id": 3, "message": {"chat": {"id": 42}, "from": {"id": 42}, "text": "/help"}}))
        assert out["command"] and len(asked) == 1

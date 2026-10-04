"""
Delentia OS - Telegram Gateway (Round 36 Phase B, Task 81-82).

Real, minimal long-polling client (deliberately NOT webhooks - long
polling needs zero public URL, matching this engagement's current
all-local deployment reality; see the Round 36 plan's gateway analysis
table for why). Real bot token read from the TELEGRAM_BOT_TOKEN
environment variable only - never written to any file, matching the
OPENROUTER_API_KEY discipline already established this engagement.

Each incoming message resolves to a real, isolated
`telegram-{chat_id}` namespace (two different Telegram users never
share AutonomousLoop state) and dispatches directly to a real
`AutonomousLoop.run()` call - this is a real-time trigger, not a
scheduled reminder, so it bypasses the reminders table entirely.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from rct_control_plane import http_client

logger = logging.getLogger("delentia.gateways.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"
_LONG_POLL_TIMEOUT_SECONDS = 30


def _default_api_base() -> str:
    """api.telegram.org unless DELENTIA_TELEGRAM_API_BASE names a loopback address (a test server) or api.telegram.org itself: the bot token is sent to whatever this returns."""
    import re
    override = (os.environ.get("DELENTIA_TELEGRAM_API_BASE") or "").strip().rstrip("/")
    if override and (override == "https://api.telegram.org" or override.startswith("https://api.telegram.org/") or re.match(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)", override)):
        return override
    return TELEGRAM_API_BASE


class TelegramGateway:
    """Real Telegram long-polling input adapter."""

    def __init__(self, kernel: Any, bot_token: Optional[str] = None, api_base: Optional[str] = None):
        self._kernel = kernel
        self._bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self._api_base = (api_base or _default_api_base()).rstrip("/")
        self._offset: Optional[int] = None
        self._is_running = False
        self._bg_task: Optional[asyncio.Task] = None

    def is_configured(self) -> bool:
        """Honest check before starting - never silently no-ops without
        explanation, and never attempts a network call without a token."""
        return bool(self._bot_token)

    def _url(self, method: str) -> str:
        return f"{self._api_base}/bot{self._bot_token}/{method}"

    async def get_updates(self, timeout: int = _LONG_POLL_TIMEOUT_SECONDS) -> List[Dict[str, Any]]:
        """Real long-polling call to Telegram's getUpdates. Raises if not
        configured - callers should check is_configured() first."""
        if not self.is_configured():
            raise RuntimeError("TelegramGateway: TELEGRAM_BOT_TOKEN not configured")
        params: Dict[str, Any] = {"timeout": timeout}
        if self._offset is not None:
            params["offset"] = self._offset
        async with http_client.async_client(timeout=timeout + 10) as client:
            resp = await client.get(self._url("getUpdates"), params=params)
            resp.raise_for_status()
            data = resp.json()
        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    async def send_message(self, chat_id: int, text: str) -> None:
        if not self.is_configured():
            raise RuntimeError("TelegramGateway: TELEGRAM_BOT_TOKEN not configured")
        async with http_client.async_client(timeout=15) as client:
            resp = await client.post(self._url("sendMessage"), json={"chat_id": chat_id, "text": text})
            resp.raise_for_status()

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        """Real dispatch - split into its own method so tests can
        monkeypatch just this seam (avoiding a real LLM call) while
        exercising handle_update()'s real parsing/namespacing logic."""
        # Round 48 R0.1: governed (FDIA gate, write/patch approval, JITNA
        # signing, episode audit) - was a plain AutonomousLoop.
        from rct_control_plane.agent_factory import build_governed_loop

        loop = build_governed_loop(self._kernel, namespace=namespace)
        return await loop.run(goal)

    async def handle_update(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Real message-handling logic - takes one Telegram Update dict
        (matches the real getUpdates response shape) and, for a real
        incoming text message, dispatches it through AutonomousLoop and
        replies with the real result. Returns None for updates with no
        text message (e.g. a sticker, an edited_message) - honestly
        ignored, not silently mishandled."""
        message = update.get("message")
        voice = (message or {}).get("voice") or (message or {}).get("audio")
        if not message or ("text" not in message and not (voice and self._voice_input_enabled())):
            return None

        chat_id = message["chat"]["id"]
        text = message.get("text")
        namespace = f"telegram-{chat_id}"

        # Round 48 R0.1: fail-closed sender allowlist (Telegram user id,
        # falling back to chat id for messages without a "from").
        from rct_control_plane.agent_factory import (
            record_rejected_sender, rejection_reply, sender_allowed,
        )
        sender_id = (message.get("from") or {}).get("id", chat_id)
        if not sender_allowed("telegram", sender_id, getattr(self._kernel, "_persistence", None)):
            record_rejected_sender(self._kernel, "telegram", sender_id, namespace)
            if self.is_configured():
                await self.send_message(chat_id, rejection_reply(self._kernel, "telegram", sender_id))
            return {"chat_id": chat_id, "namespace": namespace, "goal": text, "rejected": True,
                    "sender_id": sender_id}

        heard_prefix = ""
        if text is None:
            # A voice note from an allowed sender (checked above, so a stranger never makes this machine download or transcribe anything).
            try:
                text = await self._hear(voice or {})
            except Exception as exc:
                reason = str(exc) if exc.__class__.__name__ == "VoiceError" else f"I could not use that voice note ({type(exc).__name__})."
                if self.is_configured():
                    await self.send_message(chat_id, reason[:300])
                return {"chat_id": chat_id, "namespace": namespace, "voice_error": reason[:300], "sender_id": sender_id}
            if not text.strip():
                if self.is_configured():
                    await self.send_message(chat_id, "I could not make out any words in that voice note.")
                return {"chat_id": chat_id, "namespace": namespace, "voice_error": "no speech", "sender_id": sender_id}
            heard_prefix = f"(I heard: \u201c{text.strip()[:300]}\u201d)\n"
        else:
            from rct_control_plane import chat_commands
            command_reply = chat_commands.handle(self._kernel, "telegram", sender_id, namespace, text)
            if command_reply is not None:
                if self.is_configured():
                    await self.send_message(chat_id, command_reply)
                return {"chat_id": chat_id, "namespace": namespace, "goal": text, "command": True, "reply_text": command_reply}

        result = await self._dispatch_to_autonomous_loop(text, namespace)
        reply_text = result.get("final_answer") or result.get("stopped_reason", "(no response)")
        if self.is_configured():
            await self.send_message(chat_id, heard_prefix + str(reply_text))
        return {"chat_id": chat_id, "namespace": namespace, "goal": text, "result": result, **({"heard": text} if heard_prefix else {})}

    @staticmethod
    def _voice_input_enabled() -> bool:
        return (os.environ.get("DELENTIA_VOICE_INPUT") or "").strip().lower() in ("1", "true", "yes", "on")

    async def _hear(self, voice: Dict[str, Any]) -> str:
        """Downloads one voice note from Telegram and returns what it says (voice.py: Whisper on this machine, nothing leaves it)."""
        from rct_control_plane import voice as voice_module
        if int(voice.get("duration") or 0) > voice_module.MAX_AUDIO_SECONDS:
            raise voice_module.VoiceError(f"That voice note is longer than {voice_module.MAX_AUDIO_SECONDS} seconds; please send a shorter one.")
        if int(voice.get("file_size") or 0) > voice_module.MAX_AUDIO_BYTES:
            raise voice_module.VoiceError("That voice note is too large.")
        file_id = str(voice.get("file_id") or "")
        if not file_id:
            raise voice_module.VoiceError("That voice note has no file.")
        async with http_client.async_client(timeout=60) as client:
            info = await client.get(self._url("getFile"), params={"file_id": file_id})
            info.raise_for_status()
            file_path = str((info.json().get("result") or {}).get("file_path") or "")
            if not file_path or ".." in file_path:
                raise voice_module.VoiceError("Telegram did not give a file for that voice note.")
            blob = await client.get(f"{self._api_base}/file/bot{self._bot_token}/{file_path}")
            blob.raise_for_status()
            data = blob.content
        if len(data) > voice_module.MAX_AUDIO_BYTES:
            raise voice_module.VoiceError("That voice note is too large.")
        temp = voice_module.temp_audio_file(data, suffix=os.path.splitext(file_path)[1] or ".oga")
        try:
            heard = await voice_module.transcribe_file(temp)
        finally:
            try:
                temp.unlink()
            except OSError:
                pass
        return str(heard["text"])

    def start(self) -> None:
        """Real listener start - idempotent, honestly no-ops (with a
        logged warning, not a silent failure) when no token is
        configured rather than starting a loop that would just error
        forever."""
        if self._is_running:
            return
        if not self.is_configured():
            logger.warning("TelegramGateway.start() called without TELEGRAM_BOT_TOKEN configured - not starting")
            return
        self._is_running = True
        self._bg_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._is_running = False
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None

    async def _run_loop(self) -> None:
        while self._is_running:
            try:
                updates = await self.get_updates()
                for update in updates:
                    try:
                        await self.handle_update(update)
                    except Exception:
                        logger.exception("TelegramGateway: error handling one update - continuing")
            except Exception:
                logger.exception("TelegramGateway: error polling getUpdates - retrying next cycle")
                await asyncio.sleep(5)

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

import httpx

logger = logging.getLogger("delentia.gateways.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"
_LONG_POLL_TIMEOUT_SECONDS = 30


class TelegramGateway:
    """Real Telegram long-polling input adapter."""

    def __init__(self, kernel: Any, bot_token: Optional[str] = None, api_base: str = TELEGRAM_API_BASE):
        self._kernel = kernel
        self._bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self._api_base = api_base.rstrip("/")
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
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
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
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(self._url("sendMessage"), json={"chat_id": chat_id, "text": text})
            resp.raise_for_status()

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        """Real dispatch - split into its own method so tests can
        monkeypatch just this seam (avoiding a real LLM call) while
        exercising handle_update()'s real parsing/namespacing logic."""
        from rct_control_plane.autonomous_loop import AutonomousLoop
        from rct_control_plane.mcp_server import mcp

        loop = AutonomousLoop(mcp_server=mcp, persistence=self._kernel._persistence, namespace=namespace)
        return await loop.run(goal)

    async def handle_update(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Real message-handling logic - takes one Telegram Update dict
        (matches the real getUpdates response shape) and, for a real
        incoming text message, dispatches it through AutonomousLoop and
        replies with the real result. Returns None for updates with no
        text message (e.g. a sticker, an edited_message) - honestly
        ignored, not silently mishandled."""
        message = update.get("message")
        if not message or "text" not in message:
            return None

        chat_id = message["chat"]["id"]
        text = message["text"]
        namespace = f"telegram-{chat_id}"

        result = await self._dispatch_to_autonomous_loop(text, namespace)
        reply_text = result.get("final_answer") or result.get("stopped_reason", "(no response)")
        if self.is_configured():
            await self.send_message(chat_id, str(reply_text))
        return {"chat_id": chat_id, "namespace": namespace, "goal": text, "result": result}

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

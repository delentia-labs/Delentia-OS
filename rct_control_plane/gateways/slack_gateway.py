"""
Delentia OS - Slack Gateway (Round 38, closing a Round 37 debt item).

Real client built on `slack-bolt`'s async Socket Mode support - like
Telegram (long-polling) and Discord (outbound websocket), Socket Mode
needs NO public HTTPS endpoint (an outbound websocket connection to
Slack, same zero-infrastructure profile). Two real tokens are required
(both environment variables only, never written to any file, matching
this engagement's established secret-handling discipline):
`SLACK_BOT_TOKEN` (starts with `xoxb-`) and `SLACK_APP_TOKEN` (starts
with `xapp-`, requires Socket Mode enabled on the Slack app).

Each incoming message resolves to a real, isolated
`slack-{channel_id}-{user_id}` namespace - isolated per (channel, user)
pair, matching Discord's own reasoning (a Slack channel is often shared
by multiple real users, unlike a Telegram private chat).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("delentia.gateways.slack")


class SlackGateway:
    """Real Slack input adapter, built on slack-bolt's AsyncApp +
    AsyncSocketModeHandler."""

    def __init__(self, kernel: Any, bot_token: Optional[str] = None, app_token: Optional[str] = None):
        self._kernel = kernel
        self._bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        self._app_token = app_token or os.environ.get("SLACK_APP_TOKEN")
        self._handler: Optional[Any] = None
        self._is_running = False
        self._bg_task: Optional[asyncio.Task] = None

    def is_configured(self) -> bool:
        """Honest check before starting - Socket Mode genuinely needs
        BOTH tokens; never attempts a connection with only one."""
        return bool(self._bot_token) and bool(self._app_token)

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        """Real dispatch - deliberate testable seam, same pattern as
        telegram_gateway.py/discord_gateway.py/line_gateway.py."""
        from rct_control_plane.autonomous_loop import AutonomousLoop
        from rct_control_plane.mcp_server import mcp

        loop = AutonomousLoop(mcp_server=mcp, persistence=self._kernel._persistence, namespace=namespace)
        return await loop.run(goal)

    async def handle_message(
        self, channel_id: str, user_id: Optional[str], bot_id: Optional[str], text: str,
    ) -> Optional[Dict[str, Any]]:
        """Real message-handling logic - takes plain primitive fields
        (not a slack-bolt event dict) so it's testable without a real
        Socket Mode connection. Honestly ignores bot-authored messages
        (Slack marks these with a real `bot_id`, not a boolean) and
        messages with no real user_id (e.g. channel join/leave system
        messages) or empty text."""
        if bot_id or not user_id or not text:
            return None

        namespace = f"slack-{channel_id}-{user_id}"
        result = await self._dispatch_to_autonomous_loop(text, namespace)
        reply_text = str(result.get("final_answer") or result.get("stopped_reason", "(no response)"))
        return {
            "channel_id": channel_id,
            "namespace": namespace,
            "goal": text,
            "result": result,
            "reply_text": reply_text,
        }

    def _build_handler(self) -> Any:
        from slack_bolt.async_app import AsyncApp
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

        app = AsyncApp(token=self._bot_token)

        @app.event("message")
        async def on_message(event, say):
            outcome = await self.handle_message(
                channel_id=event.get("channel"),
                user_id=event.get("user"),
                bot_id=event.get("bot_id"),
                text=event.get("text", ""),
            )
            if outcome is not None:
                await say(outcome["reply_text"])

        return AsyncSocketModeHandler(app, app_token=self._app_token)

    def start(self) -> None:
        """Real listener start - idempotent, honestly no-ops (with a
        logged warning, not a silent failure) when tokens aren't
        configured."""
        if self._is_running:
            return
        if not self.is_configured():
            logger.warning("SlackGateway.start() called without both SLACK_BOT_TOKEN and SLACK_APP_TOKEN configured - not starting")
            return
        self._handler = self._build_handler()
        self._is_running = True
        self._bg_task = asyncio.create_task(self._handler.start_async())

    async def stop(self) -> None:
        self._is_running = False
        if self._handler is not None:
            try:
                await self._handler.close_async()
            except Exception:
                pass
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None
        self._handler = None

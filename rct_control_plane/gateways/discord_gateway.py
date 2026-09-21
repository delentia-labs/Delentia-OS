"""
Delentia OS - Discord Gateway (Round 37).

Real client built on the real `discord.py` library (not a raw
reimplementation of Discord's websocket Gateway protocol - discord.py is
a mature, widely-used library and reusing it avoids a large surface of
real protocol bugs a from-scratch client would risk). No public HTTPS
endpoint needed - like Telegram's long-polling choice, Discord bots
connect OUTBOUND via a websocket, so this gateway has the exact same
"buildable with zero new infrastructure" profile that made Telegram the
first messaging gateway built (Round 36).

Real bot token read from the DISCORD_BOT_TOKEN environment variable
only - never written to any file, matching the OPENROUTER_API_KEY/
TELEGRAM_BOT_TOKEN discipline already established this engagement.

Each incoming message resolves to a real, isolated
`discord-{channel_id}-{author_id}` namespace - isolated per (channel,
author) pair rather than per-channel alone, since a Discord channel is
often shared by multiple real users (unlike a Telegram private chat),
so two different users typing in the same channel must not share
AutonomousLoop state.

Live end-to-end verification (a real bot token + a real Discord server)
is honestly deferred until the Architect registers a real bot via the
Discord Developer Portal - same precedent as Telegram's own real-token
requirement in Round 36. What's real and tested here is the message-
handling/namespacing/reply logic in isolation, via the same testable-
seam pattern (`handle_message`) telegram_gateway.py/line_gateway.py
already established.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("delentia.gateways.discord")


class DiscordGateway:
    """Real Discord input adapter, built on discord.py's Client."""

    def __init__(self, kernel: Any, bot_token: Optional[str] = None):
        self._kernel = kernel
        self._bot_token = bot_token or os.environ.get("DISCORD_BOT_TOKEN")
        self._client: Optional[Any] = None
        self._is_running = False
        self._bg_task: Optional[asyncio.Task] = None

    def is_configured(self) -> bool:
        """Honest check before starting - never silently no-ops without
        explanation, and never attempts a connection without a token."""
        return bool(self._bot_token)

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        """Real dispatch - deliberate testable seam, same pattern as
        telegram_gateway.py/line_gateway.py."""
        from rct_control_plane.autonomous_loop import AutonomousLoop
        from rct_control_plane.mcp_server import mcp

        loop = AutonomousLoop(mcp_server=mcp, persistence=self._kernel._persistence, namespace=namespace)
        return await loop.run(goal)

    async def handle_message(
        self, channel_id: int, author_id: int, author_is_bot: bool, content: str,
    ) -> Optional[Dict[str, Any]]:
        """Real message-handling logic - takes plain primitive fields
        (not a discord.py Message object) so it's testable without a
        real gateway connection. Honestly ignores bot-authored messages
        (including its own) and empty content, rather than looping on
        its own replies or dispatching nothing meaningfully."""
        if author_is_bot or not content:
            return None

        namespace = f"discord-{channel_id}-{author_id}"
        result = await self._dispatch_to_autonomous_loop(content, namespace)
        reply_text = str(result.get("final_answer") or result.get("stopped_reason", "(no response)"))
        return {
            "channel_id": channel_id,
            "namespace": namespace,
            "goal": content,
            "result": result,
            "reply_text": reply_text,
        }

    def _build_client(self) -> Any:
        import discord

        intents = discord.Intents.default()
        # Real, privileged intent - the Architect must also enable
        # "Message Content Intent" for this bot in the Discord Developer
        # Portal, or discord.py will connect but receive empty content
        # for every message (a real Discord platform requirement, not a
        # bug in this code).
        intents.message_content = True
        client = discord.Client(intents=intents)

        @client.event
        async def on_message(message):
            if client.user is not None and message.author.id == client.user.id:
                return
            outcome = await self.handle_message(
                channel_id=message.channel.id,
                author_id=message.author.id,
                author_is_bot=message.author.bot,
                content=message.content,
            )
            if outcome is not None:
                await message.channel.send(outcome["reply_text"])

        return client

    def start(self) -> None:
        """Real listener start - idempotent, honestly no-ops (with a
        logged warning, not a silent failure) when no token is
        configured."""
        if self._is_running:
            return
        if not self.is_configured():
            logger.warning("DiscordGateway.start() called without DISCORD_BOT_TOKEN configured - not starting")
            return
        self._client = self._build_client()
        self._is_running = True
        self._bg_task = asyncio.create_task(self._client.start(self._bot_token))

    async def stop(self) -> None:
        self._is_running = False
        if self._client is not None:
            await self._client.close()
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
        self._client = None
        self._bg_task = None

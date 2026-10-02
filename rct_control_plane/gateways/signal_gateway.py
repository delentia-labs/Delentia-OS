"""
Delentia OS - Signal gateway (Round 55), through signal-cli-rest-api.

Signal has no official bot API. The practical route is the community ``signal-cli-rest-api`` container, run by the owner on a
machine they control and registered with a phone number of their own. This gateway talks to it over HTTP (the owner's URL, normally
loopback) by polling:

    GET  {SIGNAL_CLI_REST_URL}/v1/receive/{SIGNAL_NUMBER}          -> a list of envelopes
    POST {SIGNAL_CLI_REST_URL}/v2/send  {"message", "number", "recipients": [...]}

Configuration (environment only): SIGNAL_CLI_REST_URL, SIGNAL_NUMBER. Allowlist: DELENTIA_SIGNAL_ALLOWED_SENDERS (phone numbers or
Signal UUIDs). The REST service itself has no authentication, so it must listen on loopback or a private network only.

Not covered: attachments, group messages (an envelope with a group context is skipped: a group is many people, and the allowlist
names single senders), and disappearing-message timers.

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from rct_control_plane.gateways.common import dispatch_governed, handle_incoming, split_for_channel

logger = logging.getLogger("delentia.gateways.signal")

MAX_MESSAGE_CHARS = 2000
POLL_INTERVAL_SECONDS = 3.0


class SignalGateway:
    def __init__(self, kernel: Any, base_url: Optional[str] = None, number: Optional[str] = None):
        self._kernel = kernel
        self._base_url = (base_url or os.environ.get("SIGNAL_CLI_REST_URL") or "").rstrip("/")
        self._number = number or os.environ.get("SIGNAL_NUMBER") or ""
        self._is_running = False
        self._bg_task: Optional["asyncio.Task[None]"] = None

    def is_configured(self) -> bool:
        return bool(self._base_url) and bool(self._number)

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        return await dispatch_governed(self._kernel, goal, namespace)

    async def receive(self) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{self._base_url}/v1/receive/{self._number}")
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, list) else []

    async def send_text(self, recipient: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            for part in split_for_channel(text, MAX_MESSAGE_CHARS):
                resp = await client.post(f"{self._base_url}/v2/send",
                                         json={"message": part, "number": self._number, "recipients": [recipient]})
                resp.raise_for_status()

    async def handle_envelope(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """One element of /v1/receive. Only a plain text message from one person is answered; receipts, typing
        notices, group messages and our own sync messages are skipped."""
        envelope = item.get("envelope") or {}
        data = envelope.get("dataMessage")
        if not data or not data.get("message") or data.get("groupInfo"):
            return None
        sender = str(envelope.get("sourceNumber") or envelope.get("source") or envelope.get("sourceUuid") or "")
        if not sender or sender == self._number:
            return None

        async def reply(answer: str) -> None:
            await self.send_text(sender, answer)

        return await handle_incoming(self._kernel, "signal", sender, str(data["message"]),
                                     dispatch=self._dispatch_to_autonomous_loop, reply=reply, reply_to_rejected=reply)

    async def poll_once(self) -> List[Dict[str, Any]]:
        results = []
        for item in await self.receive():
            try:
                handled = await self.handle_envelope(item)
                if handled is not None:
                    results.append(handled)
            except Exception:
                logger.exception("SignalGateway: error handling one envelope - continuing")
        return results

    def start(self) -> None:
        if self._is_running:
            return
        if not self.is_configured():
            logger.warning("SignalGateway.start() called without SIGNAL_CLI_REST_URL / SIGNAL_NUMBER - not starting")
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
                await self.poll_once()
            except Exception:
                logger.exception("SignalGateway: error polling - retrying next cycle")
                await asyncio.sleep(5)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

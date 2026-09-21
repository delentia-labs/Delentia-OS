"""
Delentia OS - LINE Messaging API Gateway (Round 36 Phase B extension).

Unlike Telegram, LINE's Messaging API has NO long-polling option at all -
it is webhook-only (real, confirmed via LINE's own developer docs). This
module implements the real webhook signature verification and event
handling; the actual HTTP route is wired in api.py as
`POST /v1/gateways/line/webhook`. That route existing in code is NOT the
same as it being "stood up" publicly - per this engagement's standing
rule, no real messaging-platform webhook goes live without the Architect
first confirming a real, publicly-reachable HTTPS host and configuring
LINE's own webhook URL to point at it (LINE requires a CA-trusted TLS
certificate - self-signed is rejected).

Real channel secret / access token read from LINE_CHANNEL_SECRET /
LINE_CHANNEL_ACCESS_TOKEN environment variables only - never written to
any file, matching this engagement's established secret-handling
discipline.

Chosen as the highest-strategic-value gateway (not just Hermes parity):
LINE is the dominant messaging platform in Thailand, and Hermes Agent's
own real gateway list (Telegram/Discord/Slack/WhatsApp/Signal/Email) has
no LINE integration at all - real, verified via Hermes's own docs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("delentia.gateways.line")

LINE_API_BASE = "https://api.line.me"


class LineGateway:
    """Real LINE Messaging API webhook handler."""

    def __init__(self, kernel: Any, channel_secret: Optional[str] = None,
                 channel_access_token: Optional[str] = None, api_base: str = LINE_API_BASE):
        self._kernel = kernel
        self._channel_secret = channel_secret or os.environ.get("LINE_CHANNEL_SECRET")
        self._channel_access_token = channel_access_token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
        self._api_base = api_base.rstrip("/")

    def is_configured(self) -> bool:
        """Honest check - both the secret (for signature verification)
        and the access token (for replying) are real requirements."""
        return bool(self._channel_secret) and bool(self._channel_access_token)

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Real HMAC-SHA256 verification of LINE's X-Line-Signature
        header, per LINE's own documented webhook security scheme.
        Returns False (never raises) on a bad/missing signature or when
        not configured - callers must treat False as "reject the
        request", not as "signature check skipped"."""
        if not self._channel_secret or not signature:
            return False
        expected = base64.b64encode(
            hmac.new(self._channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
        ).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        """Real dispatch - same testable-seam pattern as
        TelegramGateway._dispatch_to_autonomous_loop."""
        from rct_control_plane.autonomous_loop import AutonomousLoop
        from rct_control_plane.mcp_server import mcp

        loop = AutonomousLoop(mcp_server=mcp, persistence=self._kernel._persistence, namespace=namespace)
        return await loop.run(goal)

    async def reply_message(self, reply_token: str, text: str) -> None:
        if not self._channel_access_token:
            raise RuntimeError("LineGateway: LINE_CHANNEL_ACCESS_TOKEN not configured")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._api_base}/v2/bot/message/reply",
                headers={"Authorization": f"Bearer {self._channel_access_token}", "Content-Type": "application/json"},
                json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
            )
            resp.raise_for_status()

    async def handle_webhook_body(self, body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Real event-handling logic - takes a parsed LINE webhook body
        (matches the real documented `{"events": [...]}` shape) and, for
        each real incoming text-message event, dispatches through
        AutonomousLoop and replies via the real reply API. Non-text-
        message events (join, follow, postback, etc.) are honestly
        skipped, not mishandled."""
        results = []
        for event in body.get("events", []):
            if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
                continue

            user_id = event.get("source", {}).get("userId", "unknown")
            text = event["message"]["text"]
            reply_token = event.get("replyToken")
            namespace = f"line-{user_id}"

            result = await self._dispatch_to_autonomous_loop(text, namespace)
            reply_text = result.get("final_answer") or result.get("stopped_reason", "(no response)")
            if reply_token and self._channel_access_token:
                await self.reply_message(reply_token, str(reply_text))
            results.append({"user_id": user_id, "namespace": namespace, "goal": text, "result": result})
        return results

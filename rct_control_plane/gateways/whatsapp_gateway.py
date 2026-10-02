"""
Delentia OS - WhatsApp Cloud API gateway (Round 55).

Webhook only, like LINE: Meta calls this server. Two requests matter:
  * GET  /v1/gateways/whatsapp/webhook  - the one-time subscription check (hub.mode=subscribe, hub.verify_token, hub.challenge);
  * POST /v1/gateways/whatsapp/webhook  - messages, signed by Meta with X-Hub-Signature-256 = "sha256=" + HMAC-SHA256(app secret, raw body).

Nothing here goes live by itself: Meta needs a public HTTPS address and the owner's own app, so as with LINE this is code that
waits for the Architect to confirm a host. Secrets are read from the environment only (never stored in a file):
WHATSAPP_APP_SECRET, WHATSAPP_ACCESS_TOKEN, WHATSAPP_VERIFY_TOKEN, WHATSAPP_PHONE_NUMBER_ID.

Meta retries a webhook that was not answered quickly, so message ids already handled are remembered and not run twice.
Only the sender's WhatsApp id (their phone number) is used for the allowlist: DELENTIA_WHATSAPP_ALLOWED_SENDERS.

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import httpx

from rct_control_plane.gateways.common import dispatch_governed, handle_incoming, split_for_channel

logger = logging.getLogger("delentia.gateways.whatsapp")

WHATSAPP_API_BASE = "https://graph.facebook.com/v20.0"
MAX_MESSAGE_CHARS = 4000
SEEN_LIMIT = 2000


class WhatsAppGateway:
    def __init__(self, kernel: Any, app_secret: Optional[str] = None, access_token: Optional[str] = None,
                 verify_token: Optional[str] = None, phone_number_id: Optional[str] = None, api_base: str = WHATSAPP_API_BASE):
        self._kernel = kernel
        self._app_secret = app_secret or os.environ.get("WHATSAPP_APP_SECRET")
        self._access_token = access_token or os.environ.get("WHATSAPP_ACCESS_TOKEN")
        self._verify_token = verify_token or os.environ.get("WHATSAPP_VERIFY_TOKEN")
        self._phone_number_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        self._api_base = api_base.rstrip("/")
        self._seen: "OrderedDict[str, None]" = OrderedDict()

    def is_configured(self) -> bool:
        """The app secret (to check signatures) is what makes it safe to receive; the token and number id are for replying."""
        return bool(self._app_secret) and bool(self._access_token) and bool(self._phone_number_id)

    def verify_signature(self, body: bytes, signature_header: str) -> bool:
        """False (never an exception) for a missing, malformed or wrong signature, or when no app secret is configured."""
        if not self._app_secret or not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(self._app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header[len("sha256="):])

    def verify_subscription(self, params: Dict[str, str]) -> Optional[str]:
        """The challenge to echo back when Meta's one-time check carries our verify token, else None."""
        if not self._verify_token or params.get("hub.mode") != "subscribe":
            return None
        if hmac.compare_digest(str(params.get("hub.verify_token", "")), self._verify_token):
            return str(params.get("hub.challenge", ""))
        return None

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        return await dispatch_governed(self._kernel, goal, namespace)

    async def send_text(self, to: str, text: str) -> None:
        if not (self._access_token and self._phone_number_id):
            raise RuntimeError("WhatsAppGateway: WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID not configured")
        async with httpx.AsyncClient(timeout=15) as client:
            for part in split_for_channel(text, MAX_MESSAGE_CHARS):
                resp = await client.post(
                    f"{self._api_base}/{self._phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"},
                    json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": part}})
                resp.raise_for_status()

    def _first_time(self, message_id: str) -> bool:
        if not message_id:
            return True
        if message_id in self._seen:
            return False
        self._seen[message_id] = None
        while len(self._seen) > SEEN_LIMIT:
            self._seen.popitem(last=False)
        return True

    async def handle_webhook_body(self, body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Walks Meta's {"entry": [{"changes": [{"value": {"messages": [...]}}]}]} shape. Only text messages are answered;
        statuses, images, reactions and the like are skipped, and a message id seen before is not run again."""
        results: List[Dict[str, Any]] = []
        for entry in body.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                for message in (change.get("value") or {}).get("messages", []) or []:
                    if message.get("type") != "text":
                        continue
                    if not self._first_time(str(message.get("id", ""))):
                        continue
                    sender = str(message.get("from", ""))
                    text = (message.get("text") or {}).get("body", "")
                    can_reply = self.is_configured()

                    async def reply(answer: str, _to: str = sender) -> None:
                        await self.send_text(_to, answer)

                    results.append(await handle_incoming(
                        self._kernel, "whatsapp", sender, text, dispatch=self._dispatch_to_autonomous_loop,
                        reply=reply if can_reply else None, reply_to_rejected=reply if can_reply else None))
        return results

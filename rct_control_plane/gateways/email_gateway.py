"""
Delentia OS - Email gateway (Round 55): IMAP in, SMTP out.

Email is the channel where "who sent this" is easiest to fake: the From header is plain text anyone can write. So this gateway
trusts a sender only when BOTH hold:

  1. the sender's address is on ``DELENTIA_EMAIL_ALLOWED_SENDERS`` (unset = nobody, ``*`` = everyone, like every channel), and
  2. the receiving mail server vouched for it: the TOPMOST ``Authentication-Results`` header (the one the owner's own server
     added; a forged one sits lower) says ``dkim=pass`` or ``spf=pass``. If ``DELENTIA_EMAIL_AUTHSERV_ID`` is set, that header must
     also name that server. No header, or a failing one, and the message is refused. ``DELENTIA_EMAIL_TRUST_UNVERIFIED=1`` turns
     this check off (for a private mailbox where only the owner can deliver mail); it is off by default.

Replies go only to messages that passed both checks (never to a refused sender: that would be backscatter to a forged address), are
marked ``Auto-Submitted: auto-replied``, and a message that is itself automatic (Auto-Submitted other than "no", Precedence bulk/junk/
list, a List-Id) is not answered, so two automatic mailboxes cannot talk to each other forever. At most 20 replies per sender per hour.

Configuration (environment only): DELENTIA_EMAIL_ADDRESS (From, and the login unless DELENTIA_EMAIL_LOGIN is set), DELENTIA_EMAIL_PASSWORD, DELENTIA_EMAIL_IMAP_HOST,
DELENTIA_EMAIL_SMTP_HOST, optional DELENTIA_EMAIL_IMAP_PORT (993) and DELENTIA_EMAIL_SMTP_PORT (465, SSL).

A message is marked read BEFORE it runs: a crash must not make the agent run someone's request twice.

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import imaplib
import logging
import os
import re
import smtplib
import time
from collections import defaultdict, deque
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any, Callable, Deque, Dict, List, Optional

from rct_control_plane.gateways.common import dispatch_governed, handle_incoming

logger = logging.getLogger("delentia.gateways.email")

POLL_INTERVAL_SECONDS = 30.0
MAX_BODY_CHARS = 4000
MAX_REPLIES_PER_HOUR = 20
_AUTH_PASS = re.compile(r"\b(dkim|spf)\s*=\s*pass\b", re.IGNORECASE)
_QUOTE_HEADER = re.compile(r"^(on .{5,200} wrote:|-{2,}\s*original message\s*-{2,}|from:\s.+)$", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def authenticated(message: Any) -> bool:
    """Did the owner's own mail server vouch for the sender? Reads only the topmost Authentication-Results header."""
    if _env("DELENTIA_EMAIL_TRUST_UNVERIFIED") == "1":
        return True
    headers = message.get_all("Authentication-Results") or []
    if not headers:
        return False
    top = str(headers[0])
    authserv = _env("DELENTIA_EMAIL_AUTHSERV_ID").strip().lower()
    if authserv and top.split(";", 1)[0].strip().lower() != authserv:
        return False
    return bool(_AUTH_PASS.search(top))


def is_automatic(message: Any) -> bool:
    auto = str(message.get("Auto-Submitted", "no")).strip().lower()
    precedence = str(message.get("Precedence", "")).strip().lower()
    return auto != "no" or precedence in ("bulk", "junk", "list") or message.get("List-Id") is not None


def body_text(message: Any) -> str:
    part = message.get_body(preferencelist=("plain", "html")) if hasattr(message, "get_body") else None
    if part is None:
        return ""
    text = part.get_content() if part.get_content_type() in ("text/plain", "text/html") else ""
    if part.get_content_type() == "text/html":
        text = _TAGS.sub(" ", text)
    lines: List[str] = []
    for line in str(text).splitlines():
        if _QUOTE_HEADER.match(line.strip()):
            break                                           # everything after "On ... wrote:" is the quoted thread
        if not line.lstrip().startswith(">"):
            lines.append(line)
    return "\n".join(lines).strip()[:MAX_BODY_CHARS]


class EmailGateway:
    def __init__(self, kernel: Any, *, imap_factory: Optional[Callable[[], Any]] = None, smtp_factory: Optional[Callable[[], Any]] = None):
        self._kernel = kernel
        self._address = _env("DELENTIA_EMAIL_ADDRESS").strip().lower()
        self._login = _env("DELENTIA_EMAIL_LOGIN").strip() or self._address        # some providers log in with a name that is not the address
        self._imap_host = _env("DELENTIA_EMAIL_IMAP_HOST")
        self._smtp_host = _env("DELENTIA_EMAIL_SMTP_HOST")
        self._imap_factory = imap_factory or self._default_imap
        self._smtp_factory = smtp_factory or self._default_smtp
        self._replies: Dict[str, Deque[float]] = defaultdict(deque)
        self._is_running = False
        self._bg_task: Optional["asyncio.Task[None]"] = None

    @staticmethod
    def _loopback(host: str) -> bool:
        return host in ("localhost", "127.0.0.1", "::1")

    def _plaintext_allowed(self, host: str) -> bool:
        """Unencrypted IMAP/SMTP only on loopback and only when asked (a local test mail server); never over a network."""
        return _env("DELENTIA_EMAIL_PLAINTEXT") == "1" and self._loopback(host)

    def _default_imap(self) -> Any:
        if self._plaintext_allowed(self._imap_host):
            return imaplib.IMAP4(self._imap_host, int(_env("DELENTIA_EMAIL_IMAP_PORT", "143")))
        return imaplib.IMAP4_SSL(self._imap_host, int(_env("DELENTIA_EMAIL_IMAP_PORT", "993")))

    def _default_smtp(self) -> Any:
        """SSL on 465 by default; DELENTIA_EMAIL_SMTP_STARTTLS=1 uses STARTTLS (port 587 is the usual one)."""
        if self._plaintext_allowed(self._smtp_host):
            return smtplib.SMTP(self._smtp_host, int(_env("DELENTIA_EMAIL_SMTP_PORT", "25")))
        if _env("DELENTIA_EMAIL_SMTP_STARTTLS") == "1":
            server = smtplib.SMTP(self._smtp_host, int(_env("DELENTIA_EMAIL_SMTP_PORT", "587")))
            server.starttls()
            return server
        return smtplib.SMTP_SSL(self._smtp_host, int(_env("DELENTIA_EMAIL_SMTP_PORT", "465")))

    def is_configured(self) -> bool:
        return bool(self._address and _env("DELENTIA_EMAIL_PASSWORD") and self._imap_host and self._smtp_host)

    async def _dispatch_to_autonomous_loop(self, goal: str, namespace: str) -> Dict[str, Any]:
        return await dispatch_governed(self._kernel, goal, namespace)

    # -- blocking mail I/O, run in a thread ---------------------------------------------------
    def _fetch_unseen(self) -> List[bytes]:
        imap = self._imap_factory()
        raws: List[bytes] = []
        try:
            imap.login(self._login, _env("DELENTIA_EMAIL_PASSWORD"))
            imap.select("INBOX")
            _typ, data = imap.search(None, "UNSEEN")
            for num in (data[0].split() if data and data[0] else []):
                _typ, parts = imap.fetch(num, "(BODY.PEEK[])")
                raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                imap.store(num, "+FLAGS", "\\Seen")           # read BEFORE it runs: never run a request twice
                if raw:
                    raws.append(raw)
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        return raws

    def _send(self, message: EmailMessage) -> None:
        smtp = self._smtp_factory()
        try:
            smtp.login(self._login, _env("DELENTIA_EMAIL_PASSWORD"))
            smtp.send_message(message)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass

    def _may_reply(self, sender: str) -> bool:
        now = time.time()
        window = self._replies[sender]
        while window and now - window[0] > 3600:
            window.popleft()
        if len(window) >= MAX_REPLIES_PER_HOUR:
            return False
        window.append(now)
        return True

    # -- one message ------------------------------------------------------------------------
    async def handle_raw_message(self, raw: bytes) -> Optional[Dict[str, Any]]:
        message = email.message_from_bytes(raw, policy=email.policy.default)
        sender = parseaddr(str(message.get("From", "")))[1].strip().lower()
        if not sender or sender == self._address:
            return None
        if is_automatic(message):
            return {"sender_id": sender, "ignored": "automatic message"}
        if not authenticated(message):
            self._audit_unauthenticated(sender)
            return {"sender_id": sender, "rejected": True, "reason": "the receiving server did not vouch for this sender (no dkim=pass / spf=pass)"}
        subject = str(message.get("Subject", "")).strip()
        body = body_text(message)
        goal = "\n\n".join(part for part in (subject, body) if part)

        async def reply(answer: str) -> None:
            if not self._may_reply(sender):
                logger.warning("EmailGateway: reply limit reached for %s", sender)
                return
            out = EmailMessage()
            out["From"], out["To"] = self._address, sender
            out["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
            if message.get("Message-ID"):
                out["In-Reply-To"] = out["References"] = str(message["Message-ID"])
            out["Auto-Submitted"] = "auto-replied"
            out.set_content(answer)
            await asyncio.to_thread(self._send, out)

        # reply_to_rejected stays None: a refused sender gets no mail (an address in From can be forged).
        return await handle_incoming(self._kernel, "email", sender, goal, dispatch=self._dispatch_to_autonomous_loop,
                                     reply=reply if self.is_configured() else None)

    def _audit_unauthenticated(self, sender: str) -> None:
        try:
            self._kernel._persistence.append_audit(
                entity_type="gateway_sender_rejected", entity_id=f"email-{sender}", action="reject", actor=f"email:{sender}",
                changes={"channel": "email", "sender_id": sender, "reason": "unauthenticated sender"})
        except Exception as exc:                            # pragma: no cover - defensive
            logger.warning("could not audit unauthenticated email sender %s: %s", sender, exc)

    async def poll_once(self) -> List[Dict[str, Any]]:
        results = []
        for raw in await asyncio.to_thread(self._fetch_unseen):
            try:
                handled = await self.handle_raw_message(raw)
                if handled is not None:
                    results.append(handled)
            except Exception:
                logger.exception("EmailGateway: error handling one message - continuing")
        return results

    def start(self) -> None:
        if self._is_running:
            return
        if not self.is_configured():
            logger.warning("EmailGateway.start() called without the DELENTIA_EMAIL_* settings - not starting")
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
                logger.exception("EmailGateway: error polling the mailbox - retrying next cycle")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

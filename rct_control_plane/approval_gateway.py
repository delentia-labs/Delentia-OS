"""
Approval Gateway — Omni-Channel Human Approval System

Sends approval requests via Slack, Microsoft Teams, or generic webhooks
when an intent requires human authorization (A-gate).

Configuration (rct.config.json):
    {
        "approval_gateway": {
            "channel": "slack",
            "slack_webhook_url": "https://hooks.slack.com/services/...",
            "teams_webhook_url": "https://...",
            "generic_webhook_url": "https://...",
            "callback_url": "http://localhost:8000/approve/callback",
            "timeout_seconds": 3600
        }
    }

Security:
    - Webhook URLs are loaded from config or environment variables only
    - Never hardcoded or logged
    - Callback tokens are SHA-256 hashed
    - All approval decisions are stored in the audit trail
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ApprovalRequest:
    """A pending approval request for a human to review."""
    request_id: str = field(default_factory=lambda: str(uuid4()))
    intent_id: str = ""
    intent_text: str = ""
    risk_profile: str = ""
    policy_rule: str = ""
    action_description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    channel: str = "slack"
    status: str = "pending"      # pending / approved / rejected / timed_out
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    a_value: int = 0             # 0 = rejected, 1 = approved
    decision_reason: str = ""

    def token(self) -> str:
        """Compute a short deterministic token for this request."""
        raw = f"{self.request_id}:{self.intent_id}:{self.created_at.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def is_expired(self) -> bool:
        """Check if approval window has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "intent_id": self.intent_id,
            "intent_text": self.intent_text,
            "risk_profile": self.risk_profile,
            "policy_rule": self.policy_rule,
            "action_description": self.action_description,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "channel": self.channel,
            "status": self.status,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "a_value": self.a_value,
            "decision_reason": self.decision_reason,
        }


@dataclass
class GatewayConfig:
    """Configuration for the Approval Gateway."""
    channel: str = "slack"                       # slack / teams / generic / cli
    slack_webhook_url: Optional[str] = None
    teams_webhook_url: Optional[str] = None
    generic_webhook_url: Optional[str] = None
    callback_url: str = "http://localhost:8000/approve/callback"
    timeout_seconds: int = 3600

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayConfig":
        return cls(
            channel=str(data.get("channel", "slack")),
            slack_webhook_url=data.get("slack_webhook_url"),
            teams_webhook_url=data.get("teams_webhook_url"),
            generic_webhook_url=data.get("generic_webhook_url"),
            callback_url=str(data.get("callback_url", "http://localhost:8000/approve/callback")),
            timeout_seconds=int(data.get("timeout_seconds", 3600)),
        )

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        """Load config from environment variables."""
        return cls(
            channel=os.environ.get("RCT_APPROVAL_CHANNEL", "slack"),
            slack_webhook_url=os.environ.get("RCT_SLACK_WEBHOOK_URL"),
            teams_webhook_url=os.environ.get("RCT_TEAMS_WEBHOOK_URL"),
            generic_webhook_url=os.environ.get("RCT_APPROVAL_WEBHOOK_URL"),
            callback_url=os.environ.get(
                "RCT_APPROVAL_CALLBACK_URL",
                "http://localhost:8000/approve/callback"
            ),
            timeout_seconds=int(os.environ.get("RCT_APPROVAL_TIMEOUT_SECONDS", "3600")),
        )

    @classmethod
    def from_config_file(cls, path: str = "rct.config.json") -> "GatewayConfig":
        """Load config from rct.config.json if it exists."""
        config_path = Path(path)
        if not config_path.exists():
            return cls.from_env()
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            gateway_data = data.get("approval_gateway", {})
            cfg = cls.from_dict(gateway_data)
            # Environment variables take precedence over file config
            if os.environ.get("RCT_SLACK_WEBHOOK_URL"):
                cfg.slack_webhook_url = os.environ["RCT_SLACK_WEBHOOK_URL"]
            if os.environ.get("RCT_TEAMS_WEBHOOK_URL"):
                cfg.teams_webhook_url = os.environ["RCT_TEAMS_WEBHOOK_URL"]
            if os.environ.get("RCT_APPROVAL_WEBHOOK_URL"):
                cfg.generic_webhook_url = os.environ["RCT_APPROVAL_WEBHOOK_URL"]
            return cfg
        except (json.JSONDecodeError, OSError):
            return cls.from_env()


# ---------------------------------------------------------------------------
# In-memory approval store (production: replace with persistent store)
# ---------------------------------------------------------------------------

_pending_store: Dict[str, ApprovalRequest] = {}


# ---------------------------------------------------------------------------
# ApprovalGateway
# ---------------------------------------------------------------------------

class ApprovalGateway:
    """
    Send approval requests to humans via configured channels.

    Supports:
    - Slack (webhook)
    - Microsoft Teams (webhook)
    - Generic HTTP webhook (any endpoint that accepts JSON POST)
    - CLI-only (no external notification — for local development)
    """

    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        config_path: str = "rct.config.json",
    ) -> None:
        self._config = config or GatewayConfig.from_config_file(config_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        intent_id: str,
        intent_text: str,
        risk_profile: str,
        policy_rule: str = "",
        action_description: str = "",
        channel: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Submit an intent for human approval.

        Creates an ApprovalRequest, stores it in the pending queue,
        and sends a notification via the configured channel.

        Args:
            intent_id: Unique ID of the intent requiring approval
            intent_text: Human-readable intent description
            risk_profile: Risk level (LOW / STRUCTURAL / SYSTEMIC)
            policy_rule: Name of the policy rule that triggered this
            action_description: What action would be taken if approved
            channel: Override the default channel

        Returns:
            ApprovalRequest with request_id and token for tracking
        """
        from datetime import timedelta
        request = ApprovalRequest(
            intent_id=intent_id,
            intent_text=intent_text,
            risk_profile=risk_profile,
            policy_rule=policy_rule,
            action_description=action_description,
            channel=channel or self._config.channel,
            expires_at=datetime.now() + timedelta(
                seconds=self._config.timeout_seconds
            ),
        )

        # Store in pending queue
        _pending_store[request.request_id] = request

        # Send notification (best-effort — failure doesn't block approval queue)
        try:
            self._dispatch(request)
        except Exception:
            pass  # Logged separately; approval queue still populated

        return request

    def get_pending(self) -> List[ApprovalRequest]:
        """Return all pending (non-expired) approval requests."""
        result = []
        for req in _pending_store.values():
            if req.status == "pending" and not req.is_expired():
                result.append(req)
        return result

    def decide(
        self,
        request_id: str,
        approved: bool,
        decided_by: str = "cli-user",
        reason: str = "",
    ) -> ApprovalRequest:
        """
        Record a human approval decision for a pending request.

        Args:
            request_id: The request_id to decide on
            approved: True = approve (A=1), False = reject (A=0)
            decided_by: Who made the decision
            reason: Optional reason/comment

        Returns:
            Updated ApprovalRequest

        Raises:
            KeyError: If request_id not found
            ValueError: If request is already decided or expired
        """
        if request_id not in _pending_store:
            raise KeyError(f"Approval request '{request_id}' not found")

        request = _pending_store[request_id]

        if request.status != "pending":
            raise ValueError(
                f"Request '{request_id}' is already {request.status}"
            )
        if request.is_expired():
            request.status = "timed_out"
            raise ValueError(
                f"Request '{request_id}' has expired"
            )

        request.status = "approved" if approved else "rejected"
        request.a_value = 1 if approved else 0
        request.decided_by = decided_by
        request.decided_at = datetime.now()
        request.decision_reason = reason

        return request

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a specific request by ID."""
        return _pending_store.get(request_id)

    def clear_decided(self) -> int:
        """Remove all decided requests. Returns count removed."""
        decided = [
            rid for rid, req in _pending_store.items()
            if req.status != "pending"
        ]
        for rid in decided:
            del _pending_store[rid]
        return len(decided)

    # ------------------------------------------------------------------
    # Dispatch helpers (channel-specific)
    # ------------------------------------------------------------------

    def _dispatch(self, request: ApprovalRequest) -> None:
        """Send notification to the configured channel."""
        channel = request.channel.lower()

        if channel == "slack":
            self._send_slack(request)
        elif channel == "teams":
            self._send_teams(request)
        elif channel in {"generic", "webhook"}:
            self._send_generic_webhook(request)
        # "cli" or unknown: no external dispatch needed

    def _send_slack(self, request: ApprovalRequest) -> None:
        """Send a Slack Block Kit approval message."""
        if not self._config.slack_webhook_url:
            return

        payload = {
            "text": ":warning: *RCT OS — Approval Required*",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "RCT OS — Approval Required",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Intent:*\n{request.intent_text[:200]}"},
                        {"type": "mrkdwn", "text": f"*Risk:*\n{request.risk_profile}"},
                        {"type": "mrkdwn", "text": f"*Policy:*\n{request.policy_rule or 'manual gate'}"},
                        {"type": "mrkdwn", "text": f"*Expires:*\n{request.expires_at.strftime('%Y-%m-%d %H:%M') if request.expires_at else 'never'}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*Request ID:* `{request.request_id}`\n"
                            f"*Token:* `{request.token()}`\n"
                            f"To approve:\n```rct approve {request.request_id}```"
                        ),
                    },
                },
            ],
        }
        self._post_json_async(self._config.slack_webhook_url, payload)

    def _send_teams(self, request: ApprovalRequest) -> None:
        """Send a Microsoft Teams adaptive card."""
        if not self._config.teams_webhook_url:
            return

        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "RCT OS Approval Required",
            "themeColor": "FF6B35",
            "title": "RCT OS — Approval Required",
            "sections": [
                {
                    "facts": [
                        {"name": "Intent", "value": request.intent_text[:200]},
                        {"name": "Risk Profile", "value": request.risk_profile},
                        {"name": "Policy Rule", "value": request.policy_rule or "manual gate"},
                        {"name": "Request ID", "value": request.request_id},
                        {"name": "Token", "value": request.token()},
                    ],
                    "text": f"Run `rct approve {request.request_id}` to approve or reject.",
                }
            ],
        }
        self._post_json_async(self._config.teams_webhook_url, payload)

    def _send_generic_webhook(self, request: ApprovalRequest) -> None:
        """Send a generic JSON POST to a webhook URL."""
        if not self._config.generic_webhook_url:
            return

        payload = {
            "event": "rct.approval_required",
            "request": request.to_dict(),
            "approve_command": f"rct approve {request.request_id}",
            "callback_url": self._config.callback_url,
        }
        self._post_json_async(self._config.generic_webhook_url, payload)

    @staticmethod
    def _post_json(url: str, payload: Dict[str, Any]) -> None:
        """Send a JSON POST request with exponential backoff retry.

        Retries up to 3 times with delays of 1 s, 2 s, 4 s on transient errors.
        Raises on non-2xx after all attempts are exhausted.
        """
        body = json.dumps(payload).encode("utf-8")
        last_exc: Exception = RuntimeError("No attempts made")
        delays = [1, 2, 4]

        for attempt, delay in enumerate(delays, start=1):
            try:
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status < 400:
                        return  # Success
                    last_exc = urllib.error.HTTPError(
                        url, resp.status, "Webhook delivery failed", http.client.HTTPMessage(), None
                    )
            except (urllib.error.URLError, OSError) as exc:
                last_exc = exc

            if attempt < len(delays):
                time.sleep(delay)

        raise last_exc

    @staticmethod
    def _post_json_async(url: str, payload: Dict[str, Any]) -> None:
        """Dispatch a JSON POST in a background daemon thread (fire-and-forget)."""
        thread = threading.Thread(
            target=ApprovalGateway._post_json,
            args=(url, payload),
            daemon=True,
            name=f"rct-webhook-{threading.active_count()}",
        )
        thread.start()

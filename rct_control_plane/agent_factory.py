"""
One way to start an agent episode (Round 48 R0.1).

Before this module, seven entry points built a plain AutonomousLoop and so
skipped every governance layer GovernedAutonomousLoop adds (FDIA gate,
always-needs-approval for write/patch tools, JITNA signing, episode audit):
the Telegram/Discord/Slack/LINE gateways, the `delentia_autonomous_loop`
MCP tool, `delegate_to_profile`, and the JITNA `subagent_runner`. Only
`POST /v1/agent/run` was governed. Every entry point now calls
build_governed_loop(), so there is no ungoverned path left to forget.

Chat gateways additionally check sender_allowed() before dispatch. The
allowlist is fail-closed: with DELENTIA_<CHANNEL>_ALLOWED_SENDERS unset,
nobody can drive the agent from that channel. "*" is an explicit opt-in
to allow everyone.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    from rct_control_plane.persistence import ControlPlanePersistence

logger = logging.getLogger(__name__)

SENDER_ALLOWLIST_ENV = {
    "telegram": "DELENTIA_TELEGRAM_ALLOWED_SENDERS",
    "discord": "DELENTIA_DISCORD_ALLOWED_SENDERS",
    "slack": "DELENTIA_SLACK_ALLOWED_SENDERS",
    "line": "DELENTIA_LINE_ALLOWED_SENDERS",
}

REJECTED_SENDER_REPLY = "This agent does not accept requests from this account."


def build_governed_loop(
    kernel: Any,
    namespace: str,
    max_iterations: int = 5,
    max_seconds: float = 120.0,
    profile: Optional[str] = None,
    persistence: Optional["ControlPlanePersistence"] = None,
    mcp_server: Any = None,
) -> "GovernedAutonomousLoop":
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop

    if mcp_server is None:
        from rct_control_plane.mcp_server import mcp as mcp_server

    llm_provider = None
    if profile:
        from rct_control_plane.model_config import profile_has_model_override
        if profile_has_model_override(profile):
            from rct_control_plane.llm_provider import get_default_provider
            llm_provider = get_default_provider(profile=profile)

    return GovernedAutonomousLoop(
        mcp_server=mcp_server,
        persistence=persistence if persistence is not None else kernel._persistence,
        kernel=kernel,
        max_iterations=max_iterations,
        max_seconds=max_seconds,
        namespace=namespace,
        llm_provider=llm_provider,
    )


def allowed_senders(channel: str) -> Optional[set]:
    """The configured allowlist for a channel: None means "allow everyone"
    (explicit "*"), an empty set means nobody (unset or blank)."""
    env_name = SENDER_ALLOWLIST_ENV[channel]
    raw = (os.getenv(env_name) or "").strip()
    if raw == "*":
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def sender_allowed(channel: str, sender_id: Any) -> bool:
    allowed = allowed_senders(channel)
    if allowed is None:
        return True
    return sender_id is not None and str(sender_id) in allowed


def record_rejected_sender(kernel: Any, channel: str, sender_id: Any, namespace: str) -> None:
    """Best-effort audit row for a refused sender; never raises, so an
    audit-store problem cannot turn a refusal into a crash."""
    try:
        kernel._persistence.append_audit(
            entity_type="gateway_sender_rejected",
            entity_id=namespace,
            action="reject",
            actor=f"{channel}:{sender_id}",
            changes={"channel": channel, "sender_id": str(sender_id),
                     "allowlist_env": SENDER_ALLOWLIST_ENV[channel]},
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("could not audit rejected %s sender %s: %s", channel, sender_id, exc)

"""
Round 55: what every chat/mail gateway does after it has parsed an incoming message.

The LINE, Telegram, Discord and Slack gateways each repeat the same steps (allowlist, governed loop, reply). The three new
ones (WhatsApp, Signal, Email) share this helper so the rules cannot drift apart:

  1. the sender must be on that channel's allowlist (``DELENTIA_<CHANNEL>_ALLOWED_SENDERS``; unset = nobody, ``*`` = everyone);
     a refused sender is audited, and the gateway decides whether replying to them is safe (email never replies: backscatter);
  2. an over-long message is cut (a goal is a request, not a document);
  3. the goal runs through ``agent_factory.build_governed_loop`` in a namespace of its own (``<channel>-<sender>``), so memory,
     skills, the policy role and the approvals of one person are not another's;
  4. the reply says what happened in plain words: the answer, or that the request waits for a human approval and under which id.

Apache 2.0 - Delentia Labs
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Dict, Optional

MAX_GOAL_CHARS = 4000
_NAMESPACE_UNSAFE = re.compile(r"[^A-Za-z0-9+._@-]")


def namespace_for(channel: str, sender_id: Any) -> str:
    """A namespace that cannot contain a path separator, a space or a control character."""
    return f"{channel}-{_NAMESPACE_UNSAFE.sub('_', str(sender_id))[:96]}"


def reply_text_for(result: Dict[str, Any]) -> str:
    """What to tell the person. The loop's answer when there is one; for a request that stopped, the reason in words."""
    answer = result.get("final_answer")
    if result.get("stopped_reason") == "needs_clarification" and result.get("clarification_question"):
        return clarification_reply(result)
    plan = result.get("plan_approval")
    if result.get("stopped_reason") == "pending_approval" and isinstance(plan, dict) and plan.get("text"):
        # Round 101: a plan waits for one confirmation. The person reads the numbered steps; signing is never done from a chat (it happens on the Desk or with `delentia approvals sign`).
        approval = result.get("approval_id")
        suffix = f" (id {approval})" if approval else ""
        return f"{plan['text']}" + chr(10) * 2 + f"Nothing has run. This plan needs your confirmation{suffix}: open Approvals in the Desk, or sign it with delentia approvals sign."
    if answer:
        from rct_control_plane import memory_nudge
        return str(answer) + memory_nudge.nudge_text(result.get("memory_nudge") or [])
    reason = result.get("stopped_reason") or "no_response"
    if reason == "pending_approval":
        approval = result.get("approval_id")
        suffix = f" (id {approval})" if approval else ""
        return f"This request needs a human approval before it can run{suffix}. Nothing was changed."
    from rct_control_plane import envelope
    if reason in envelope.MESSAGES:
        return envelope.MESSAGES[reason]
    if reason in ("fdia_blocked", "guard_blocked"):
        return "This request was refused by the safety checks. Nothing was changed."
    return f"({reason})"


def clarification_reply(result: Dict[str, Any]) -> str:
    """The episode stopped to ask (RCT-7 R5/R7). The person gets the QUESTION, not the held-back answer as if it were the result; the answer it had is shown after it, marked as not used."""
    question = str(result.get("clarification_question") or "")
    cid = result.get("clarification_id")
    held = str(result.get("final_answer") or "")
    text = question
    if cid:
        text += f"\n\n(id {cid}) Reply /answer {cid} <your answer>, then send the same request again. To keep the result as it is: /accept {cid}."
    if held and held != question:
        text += "\n\nThe answer I had (not used): " + (held if len(held) <= 500 else held[:499] + "…")
    return text


async def handle_incoming(
    kernel: Any, channel: str, sender_id: Any, text: str, *,
    dispatch: Callable[[str, str], Awaitable[Dict[str, Any]]],
    reply: Optional[Callable[[str], Awaitable[None]]] = None,
    reply_to_rejected: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    from rct_control_plane.agent_factory import record_rejected_sender, rejection_reply, sender_allowed
    namespace = namespace_for(channel, sender_id)
    persistence = getattr(kernel, "_persistence", None)
    if not sender_allowed(channel, sender_id, persistence):
        record_rejected_sender(kernel, channel, sender_id, namespace)
        if reply_to_rejected is not None:
            await reply_to_rejected(rejection_reply(kernel, channel, sender_id))
        return {"sender_id": str(sender_id), "namespace": namespace, "rejected": True}
    goal = (text or "").strip()[:MAX_GOAL_CHARS]
    if not goal:
        return {"sender_id": str(sender_id), "namespace": namespace, "ignored": "empty message"}
    from rct_control_plane import chat_commands
    command_reply = chat_commands.handle(kernel, channel, sender_id, namespace, goal)
    if command_reply is not None:
        if reply is not None:
            await reply(command_reply)
        return {"sender_id": str(sender_id), "namespace": namespace, "goal": goal, "command": True, "reply_text": command_reply}
    result = await dispatch(goal, namespace)
    if reply is not None:
        await reply(reply_text_for(result))
    return {"sender_id": str(sender_id), "namespace": namespace, "goal": goal, "result": result}


async def dispatch_governed(kernel: Any, goal: str, namespace: str) -> Dict[str, Any]:
    from rct_control_plane.agent_factory import build_governed_loop
    loop = build_governed_loop(kernel, namespace=namespace)
    loop._interactive = True                    # a person is on the other end of the chat: RCT-7 stop-and-ask applies
    return await loop.run(goal)


def split_for_channel(text: str, limit: int) -> list:
    """A long answer is sent as several messages rather than cut off silently."""
    text = str(text)
    if len(text) <= limit:
        return [text]
    parts, rest = [], text
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        cut = rest.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return parts

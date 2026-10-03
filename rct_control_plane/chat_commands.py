"""
Round 58: slash commands in chat (/help, /whoami, /status, /jobs, /approvals, /search, /model).

A message whose FIRST word is a known command (`/status`, `/search invoice`) is answered by this module and never reaches the model: no episode, no tool, no tokens spent.
That is what makes them safe to expose on every channel:

  * they only READ, and only the asking person's own data (their namespace's jobs, approvals and episodes); nothing here changes a file, a job, an approval or a setting;
  * they cannot approve anything: an approval is a signature from the owner's own device, so `/approvals` only lists ids that wait;
  * only an allowed sender gets here (the allowlist and pairing are checked before), and a text that merely starts with a slash but is not a one-word command
    (`/etc/hosts please read this`) is an ordinary goal and goes to the model as always;
  * what they print comes from the runtime's own tables, never from model output or from a stored third-party text (goals the person wrote are shown back to them, clipped).
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

_COMMAND = re.compile(r"^/([a-z]{2,12})(?:@\w+)?(?:\s+(.*))?$", re.DOTALL)
MAX_REPLY = 1800
_CLIP = 120


def _clip(text: Any, n: int = _CLIP) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= n else one[: n - 1] + "…"


def parse(text: str) -> Optional[tuple]:
    """(name, argument) when the message is a slash command; None when it is an ordinary goal."""
    m = _COMMAND.match((text or "").strip())
    if not m:
        return None
    name = m.group(1)
    return (name, (m.group(2) or "").strip()) if name in COMMANDS or name in ("start",) else None


def _help(ctx: Dict[str, Any], arg: str) -> str:
    lines = ["Commands (they only read your own data and never start the agent):"]
    lines += [f"/{name} - {doc}" for name, (_, doc) in COMMANDS.items()]
    lines.append("Anything else you write is a request for the agent.")
    return "\n".join(lines)


def _whoami(ctx: Dict[str, Any], arg: str) -> str:
    return f"channel: {ctx['channel']}\nyour id: {ctx['sender_id']}\nyour space (memory, skills, approvals): {ctx['namespace']}"


def _status(ctx: Dict[str, Any], arg: str) -> str:
    from rct_control_plane import audit_witness
    from rct_control_plane.session_search import SessionLog
    p = ctx["persistence"]
    out: List[str] = []
    try:
        out.append(f"episodes you have run: {SessionLog(p).count(ctx['namespace'])}")
    except Exception:
        out.append("episodes you have run: unknown")
    try:
        with p._connect() as conn:
            report = audit_witness.status(conn)
        out.append("log protection: " + str(report.get("plain") or "unknown"))
    except Exception:
        out.append("log protection: unknown")
    return "\n".join(out)


def _jobs(ctx: Dict[str, Any], arg: str) -> str:
    from rct_control_plane.cron_jobs import CronService
    jobs = CronService(ctx["persistence"]).list(namespace=ctx["namespace"])
    if not jobs:
        return "You have no scheduled jobs. Ask the agent, for example: remind me every weekday at 9 to check the build."
    lines = [f"{j['id']}: {_clip(j['name'], 50)} - {j['schedule_meaning']}" + ("" if j["enabled"] else " (off)") for j in jobs[:10]]
    return "Your scheduled jobs:\n" + "\n".join(lines)


def _approvals(ctx: Dict[str, Any], arg: str) -> str:
    from rct_control_plane.approvals import PendingActionStore
    waiting = [a for a in PendingActionStore(ctx["persistence"]).list(status="PENDING", limit=200) if a.namespace == ctx["namespace"]]
    if not waiting:
        return "Nothing of yours is waiting for a human signature."
    lines = [f"{a.approval_id}: {a.tool_name} - {_clip(a.goal, 70)}" for a in waiting[:10]]
    return ("Waiting for the owner's signature (you cannot sign these from chat; the owner does it on their own device):\n" + "\n".join(lines))


def _search(ctx: Dict[str, Any], arg: str) -> str:
    from rct_control_plane.session_search import SessionLog
    hits = SessionLog(ctx["persistence"]).search(ctx["namespace"], arg, limit=5)
    if not hits:
        return "Nothing in your earlier requests matches." if arg else "You have no earlier requests yet."
    when = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t))       # noqa: E731
    return "\n".join(f"{when(h['at'])}  {_clip(h['goal'], 80)}\n  -> {_clip(h['answer'], 140) or '(no answer)'}" for h in hits)


def _model(ctx: Dict[str, Any], arg: str) -> str:
    from rct_control_plane.model_config import resolve_model_selection
    sel = resolve_model_selection()
    return f"model: {sel.model} via {sel.provider} (set on the host; it cannot be changed from chat)"


COMMANDS: Dict[str, tuple] = {
    "help": (_help, "this list"),
    "whoami": (_whoami, "who the agent thinks you are"),
    "status": (_status, "your episode count and how well the audit log is protected"),
    "jobs": (_jobs, "your scheduled jobs"),
    "approvals": (_approvals, "your requests that wait for the owner's signature"),
    "search": (_search, "search your earlier requests: /search <words>"),
    "model": (_model, "which model answers"),
}
_ALIASES: Dict[str, Callable[..., str]] = {"start": _help}


def handle(kernel: Any, channel: str, sender_id: Any, namespace: str, text: str) -> Optional[str]:
    """The reply to a slash command, or None when `text` is an ordinary goal. Never raises."""
    parsed = parse(text)
    if parsed is None:
        return None
    name, arg = parsed
    fn = COMMANDS[name][0] if name in COMMANDS else _ALIASES[name]
    ctx = {"channel": channel, "sender_id": str(sender_id), "namespace": namespace, "persistence": getattr(kernel, "_persistence", None)}
    try:
        return fn(ctx, arg)[:MAX_REPLY]
    except Exception as exc:                  # a broken table must not become a crash in the gateway
        return f"/{name} could not be answered ({type(exc).__name__})."

"""
Round 60: tell the owner when the agent needs them, or when something went wrong.

FDIA's A is a person who decides. Until now, when the agent needed a signature it stopped and waited silently: the person who asked got "this request needs a human approval", but the
owner was told nothing and found out by opening the Desk. A human in the loop who is never told there is a loop is a stall. This module sends the owner a short message on the
channel they chose:

  * what: a request is waiting for a signature (tool name, who asked, the code to sign - never the arguments or the goal, which can hold text from outside); someone asked to be let in
    (pairing, channel only); a scheduled job failed or was switched off; a daemon task failed (an audit chain that no longer verifies is a failed task); today's spending limit or an
    hourly limit was reached;
  * where: DELENTIA_OWNER_NOTIFY="telegram:123456789,signal:+66800000000" - and each target must ALSO be on that channel's allowlist by name (the same rule as scheduled delivery:
    `*` does not count), so a tricked agent cannot make the system message a stranger. A target that fails the rule is dropped and `status()` says why;
  * how often: at most DELENTIA_OWNER_NOTIFY_PER_HOUR (default 20) messages an hour; the same event key is sent once an hour; what was held back is counted and the count is added to the
    next message that goes out, so a flood becomes one line, not a hundred;
  * never in the way: sending happens on a background thread; a failure is audited (hash of the text, error type) and never raised, so a broken Telegram cannot stop an approval from being
    created or an episode from ending.

No target configured = nothing is sent and nothing changes.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("delentia.owner_notify")

TARGETS_ENV = "DELENTIA_OWNER_NOTIFY"
PER_HOUR_ENV = "DELENTIA_OWNER_NOTIFY_PER_HOUR"
DEDUPE_S = 3600
MAX_TEXT = 900

_lock = threading.Lock()
_sent: Deque[float] = deque()
_keys: Dict[str, float] = {}
_held_back = 0
_threads: List[threading.Thread] = []


def _parse() -> List[Dict[str, str]]:
    out = []
    for part in (os.environ.get(TARGETS_ENV) or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        channel, to = part.split(":", 1)
        out.append({"channel": channel.strip().lower(), "to": to.strip()})
    return out


def targets() -> List[Dict[str, str]]:
    """The owner's targets that pass the allowlist rule (see the module docstring)."""
    from rct_control_plane import cron_jobs
    good = []
    for target in _parse():
        if target["channel"] in cron_jobs.DELIVERY_CHANNELS and target["to"] and target["to"] in cron_jobs.allowed_recipients(target["channel"]):
            good.append(target)
    return good


def status() -> Dict[str, Any]:
    from rct_control_plane import cron_jobs
    parsed, good = _parse(), targets()
    dropped = [{**t, "why": ("channel not supported for delivery" if t["channel"] not in cron_jobs.DELIVERY_CHANNELS
                             else f"not on the {t['channel']} allowlist by name (DELENTIA_{t['channel'].upper()}_ALLOWED_SENDERS; '*' does not count)")}
               for t in parsed if t not in good]
    return {"configured": bool(parsed), "targets": good, "dropped": dropped, "per_hour": _per_hour(), "held_back_since_last_message": _held_back}


def _per_hour() -> int:
    try:
        return max(1, int(os.environ.get(PER_HOUR_ENV) or 20))
    except ValueError:
        return 20


def _audit(persistence: Any, action: str, kind: str, key: str, text: str, extra: Optional[Dict[str, Any]] = None) -> None:
    if persistence is None:
        return
    try:
        persistence.append_audit(entity_type="owner_notify", entity_id=key or kind, action=action, actor="runtime",
                                 changes={"kind": kind, "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), **(extra or {})})
    except Exception:
        pass


async def _deliver(target: Dict[str, str], text: str) -> None:
    """One message to one target: through the running gateway when the API process registered one, else through a one-shot client built from the environment."""
    from rct_control_plane import cron_jobs
    channel, to = target["channel"], target["to"]
    gateway = cron_jobs._GATEWAY_RESOLVER(channel) if cron_jobs._GATEWAY_RESOLVER else None
    if gateway is None:
        if channel == "telegram":
            from rct_control_plane.gateways.telegram_gateway import TelegramGateway
            gateway = TelegramGateway(kernel=None)
        elif channel == "signal":
            from rct_control_plane.gateways.signal_gateway import SignalGateway
            gateway = SignalGateway(kernel=None)
        elif channel == "whatsapp":
            from rct_control_plane.gateways.whatsapp_gateway import WhatsAppGateway
            gateway = WhatsAppGateway(kernel=None)
        if gateway is None or not gateway.is_configured():
            raise RuntimeError(f"the {channel} gateway is not configured")
    if channel == "telegram":
        await gateway.send_message(int(to), text)
    else:
        await gateway.send_text(to, text)


def _send_all(chosen: List[Dict[str, str]], text: str, kind: str, key: str, persistence: Any) -> None:
    failures = []
    for target in chosen:
        try:
            asyncio.run(_deliver(target, text))
        except Exception as exc:                                    # noqa: BLE001 - recorded, never raised
            failures.append(f"{target['channel']}: {type(exc).__name__}")
            logger.warning("owner notification to %s failed: %s", target["channel"], type(exc).__name__)
    _audit(persistence, "failed" if failures and len(failures) == len(chosen) else "sent", kind, key, text,
           {"targets": len(chosen), "failures": failures})


def notify(kind: str, text: str, key: str = "", persistence: Any = None, wait: bool = False) -> bool:
    """Queue one message to the owner. Returns True when it was handed to the sender, False when it was not sent (nothing configured, a duplicate, or over the hourly count).
    `wait` joins the sending thread (tests, and the CLI before it exits)."""
    global _held_back
    chosen = targets()
    if not chosen:
        return False
    now = time.time()
    key = key or kind
    with _lock:
        while _sent and _sent[0] < now - 3600:
            _sent.popleft()
        for k in [k for k, t in _keys.items() if t < now - DEDUPE_S]:
            del _keys[k]
        if key in _keys:
            return False
        if len(_sent) >= _per_hour():
            _held_back += 1
            _audit(persistence, "held_back", kind, key, text)
            return False
        _keys[key] = now
        _sent.append(now)
        note = ""
        if _held_back:
            note = f"\n(+{_held_back} earlier alert{'s' if _held_back != 1 else ''} not sent: too many in an hour)"
            _held_back = 0
    message = (text[:MAX_TEXT] + note)
    thread = threading.Thread(target=_send_all, args=(chosen, message, kind, key, persistence), daemon=True)
    thread.start()
    _threads.append(thread)
    if wait:
        thread.join(timeout=30)
    return True


def reset_for_tests() -> None:
    global _held_back
    with _lock:
        _sent.clear()
        _keys.clear()
        _held_back = 0
    for t in list(_threads):
        t.join(timeout=10)
    _threads.clear()


# ---------------------------------------------------------------------------------------------- the events

def on_pending_action(action: Any, persistence: Any = None) -> None:
    """A request is waiting for a signature. Sends the tool name, the asker's namespace and the code; never the arguments or the goal."""
    tool = str(getattr(action, "tool_name", "") or "")
    if tool == "envelope_resume":                      # the owner just asked for this themselves
        return
    code = str(getattr(action, "approval_id", ""))
    if tool == "pairing_grant":
        channel = str((getattr(action, "tool_args", {}) or {}).get("channel", "a chat channel"))
        text = f"Someone on {channel} asked to be let in (pairing code {code}). Confirm who it is, then: delentia approvals approve {code} --key <your key>"
    else:
        asker = str(getattr(action, "namespace", "") or "?")
        rule = getattr(action, "policy_rule", None)
        need = int(getattr(action, "required_signatures", 1) or 1)
        text = (f"Waiting for your signature: {tool} (asked by {asker}{', rule ' + str(rule) if rule else ''}"
                f"{f', {need} signatures needed' if need > 1 else ''}). Code {code}. Review it in the Desk (Approvals) or: delentia approvals list")
    notify("approval", text, key=f"approval:{code}", persistence=persistence)


def on_job_problem(job: Dict[str, Any], stopped: str, switched_off: bool, persistence: Any = None) -> None:
    name = str(job.get("name") or job.get("id"))[:60]
    text = (f"Scheduled job '{name}' was switched off after repeated failures (last: {stopped})." if switched_off
            else f"Scheduled job '{name}' failed (stop reason: {stopped}).")
    notify("cron", text, key=f"cron:{job.get('id')}:{'off' if switched_off else stopped}", persistence=persistence)


def on_task_event(task: Dict[str, Any], persistence: Any = None) -> None:
    """A task finished, failed, or stopped for a signature (task_board.py). The text names the task's id and status, never its goal or results."""
    status, tid = str(task.get("status")), str(task.get("id"))
    words = {"done": "finished", "failed": "failed", "waiting_approval": "is waiting for your signature"}.get(status)
    if words is None:
        return
    notify("task", f"A task {words} (task {tid}, asked by {task.get('namespace')}). Look at it in the Desk or: delentia task show {tid}", key=f"task:{tid}:{status}", persistence=persistence)


def on_task_failed(task_name: str, error: str, persistence: Any = None) -> None:
    notify("daemon", f"The background task '{task_name}' failed: {error[:300]}", key=f"daemon:{task_name}", persistence=persistence)


def on_limit_reached(stop: str, namespace: str, detail: str, persistence: Any = None) -> None:
    what = "A spending limit" if stop == "daily_budget_exhausted" else "A request-rate limit"
    notify("limit", f"{what} was reached ({detail[:200]}); requests are being refused until the window moves on.", key=f"limit:{stop}:{namespace}", persistence=persistence)

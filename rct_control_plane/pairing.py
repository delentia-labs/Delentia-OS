"""
Round 58: DM pairing - how a person the agent does not know yet gets to talk to it (Hermes: "DM pairing").

Until now the only way to let someone in was to edit an environment variable on the host (`DELENTIA_<CHANNEL>_ALLOWED_SENDERS`). That is safe and clumsy: the owner has to know the
sender's numeric id in advance. With `DELENTIA_PAIRING=1` an unknown sender who writes to the agent is told a short CODE instead of being ignored, and the owner approves that
code the way every other human decision here is made: with a signature from their own device, in the Approvals page. Nothing about the safety model changes:

  * the code is an ordinary pending action (`pairing_grant`) in the same store as every other approval: it needs a trusted approver's Ed25519 signature over the exact action
    (channel and sender id), it is audited, it can be approved once, and a refusal is final for a day;
  * the sender learns only the code and a sentence; the agent runs NOTHING for them (no model call, no tool) until the owner signs;
  * the owner is meant to confirm out of band that the person who holds the code is who they think ("read me the code on the phone"), because the code proves a request was made, not by whom;
  * flood control: one pending request per sender, at most 5 pending per channel, a refused sender may not ask again for 24 hours;
  * a grant is its own row, revocable at any time (`delentia pairing revoke`), and revoking is audited; the environment allowlist is never edited by this module;
  * a person on a channel whose allowlist is `*` needs no pairing; with pairing OFF everything behaves exactly as before (unknown senders get the fixed refusal, or silence).
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Dict, List, Optional

ENABLED_ENV = "DELENTIA_PAIRING"
TOOL = "pairing_grant"
NAMESPACE = "pairing"
MAX_PENDING_PER_CHANNEL = 5
REFUSAL_COOLDOWN_S = 24 * 3600
_SENDER = re.compile(r"^[\w.@+\-:|=/]{1,128}$")
_CHANNELS = ("telegram", "discord", "slack", "line", "whatsapp", "signal", "email")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pairing_grants (
    channel      TEXT NOT NULL,
    sender_id    TEXT NOT NULL,
    approval_id  TEXT NOT NULL,
    granted_at   REAL NOT NULL,
    revoked_at   REAL,
    PRIMARY KEY (channel, sender_id)
);
"""

_lock = threading.Lock()
_cache: Dict[str, Any] = {}


def enabled() -> bool:
    import os
    return (os.environ.get(ENABLED_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def _persistence() -> Any:
    """The runtime's own store (agentic.db), opened once per path: the sender check runs on every incoming message."""
    from rct_control_plane.data_home import agentic_db_path
    from rct_control_plane.persistence import ControlPlanePersistence
    path = agentic_db_path()
    with _lock:
        if path not in _cache:
            _cache[path] = ControlPlanePersistence(db_path=path)
        return _cache[path]


def _prepared(persistence: Any) -> Any:
    with persistence._connect() as conn:
        conn.executescript(SCHEMA)
    return persistence


def _audit(persistence: Any, action: str, channel: str, sender_id: str, actor: str, extra: Optional[Dict[str, Any]] = None) -> None:
    try:
        persistence.append_audit(entity_type="pairing", entity_id=f"{channel}:{sender_id}", action=action, actor=actor, changes={"channel": channel, "sender_id": sender_id, **(extra or {})})
    except Exception:                       # an audit problem must not decide who gets in or stays out
        pass


def _sync_approved(persistence: Any) -> None:
    """Turn approved `pairing_grant` actions into grants. The signature is re-verified at this moment and an approval is consumed once (approvals.claim_for_execution)."""
    from rct_control_plane.approvals import ApprovalError, PendingActionStore
    store = PendingActionStore(persistence)
    for action in store.list(status="APPROVED", limit=200):
        if action.tool_name != TOOL:
            continue
        try:
            claimed = store.claim_for_execution(action.approval_id)
        except ApprovalError:
            continue
        channel, sender_id = str(claimed.tool_args.get("channel")), str(claimed.tool_args.get("sender_id"))
        with persistence._connect() as conn:
            conn.execute("INSERT INTO pairing_grants (channel, sender_id, approval_id, granted_at, revoked_at) VALUES (?, ?, ?, ?, NULL) "
                         "ON CONFLICT(channel, sender_id) DO UPDATE SET approval_id = excluded.approval_id, granted_at = excluded.granted_at, revoked_at = NULL",
                         (channel, sender_id, claimed.approval_id, time.time()))
        store.mark_executed(claimed.approval_id, {"granted": f"{channel}:{sender_id}"})
        _audit(persistence, "granted", channel, sender_id, "owner", {"approval_id": claimed.approval_id})


def is_granted(channel: str, sender_id: Any, persistence: Any = None) -> bool:
    try:
        p = _prepared(persistence or _persistence())
        _sync_approved(p)
        with p._connect() as conn:
            row = conn.execute("SELECT 1 FROM pairing_grants WHERE channel = ? AND sender_id = ? AND revoked_at IS NULL", (channel, str(sender_id))).fetchone()
        return row is not None
    except Exception:                       # an unreadable store means nobody new gets in (fail closed)
        return False


def request(channel: str, sender_id: Any, persistence: Any = None, now: Optional[float] = None) -> Dict[str, Any]:
    """An unknown sender asks to be let in. Returns {"state": ..., "code": ...}; creates a pending action only when pairing is on and the limits allow it."""
    sender = str(sender_id)
    if not enabled():
        return {"state": "disabled"}
    if channel not in _CHANNELS or not _SENDER.match(sender):
        return {"state": "invalid"}
    p = _prepared(persistence or _persistence())
    when = time.time() if now is None else now
    from rct_control_plane.approvals import PendingActionStore
    store = PendingActionStore(p)
    mine = [a for a in store.list(status=None, limit=500) if a.tool_name == TOOL and a.tool_args.get("channel") == channel and a.tool_args.get("sender_id") == sender]
    for a in mine:
        if a.status == "PENDING":
            return {"state": "waiting", "code": a.approval_id}
        if a.status == "REJECTED" and when - (a.decided_at or a.created_at) < REFUSAL_COOLDOWN_S:
            return {"state": "refused"}
    pending_here = sum(1 for a in store.list(status="PENDING", limit=500) if a.tool_name == TOOL and a.tool_args.get("channel") == channel)
    if pending_here >= MAX_PENDING_PER_CHANNEL:
        return {"state": "full"}
    action = store.create(NAMESPACE, f"Allow {channel} sender {sender} to use this agent", TOOL, {"channel": channel, "sender_id": sender},
                          f"someone on {channel} (id {sender}) wrote to the agent and asked to be let in; confirm out of band that the code holder is who you think", required_signatures=1)
    _audit(p, "requested", channel, sender, f"{channel}:{sender}", {"approval_id": action.approval_id})
    return {"state": "new", "code": action.approval_id}


def message_for(result: Dict[str, Any], plain_refusal: str) -> str:
    """What the unknown sender is told. Nothing else about the system is revealed."""
    state, code = result.get("state"), result.get("code")
    if state in ("new", "waiting"):
        return (f"This agent does not know you yet. Your pairing code is {code}. Give it to the owner; they approve it on their own device, "
                "and after that you can write here. Until then nothing you send is acted on.")
    return plain_refusal


def state(persistence: Any = None) -> Dict[str, Any]:
    p = _prepared(persistence or _persistence())
    _sync_approved(p)
    from rct_control_plane.approvals import PendingActionStore
    store = PendingActionStore(p)
    pending: List[Dict[str, Any]] = [{"code": a.approval_id, "channel": a.tool_args.get("channel"), "sender_id": a.tool_args.get("sender_id"), "asked_at": a.created_at}
                                     for a in store.list(status="PENDING", limit=200) if a.tool_name == TOOL]
    with p._connect() as conn:
        grants = [{"channel": r[0], "sender_id": r[1], "approval_id": r[2], "granted_at": r[3], "revoked_at": r[4]}
                  for r in conn.execute("SELECT channel, sender_id, approval_id, granted_at, revoked_at FROM pairing_grants ORDER BY granted_at DESC").fetchall()]
    return {"enabled": enabled(), "pending": pending, "grants": grants, "limits": {"max_pending_per_channel": MAX_PENDING_PER_CHANNEL, "refusal_cooldown_s": REFUSAL_COOLDOWN_S}}


def revoke(channel: str, sender_id: Any, actor: str = "owner", persistence: Any = None) -> bool:
    p = _prepared(persistence or _persistence())
    with p._connect() as conn:
        done = conn.execute("UPDATE pairing_grants SET revoked_at = ? WHERE channel = ? AND sender_id = ? AND revoked_at IS NULL", (time.time(), channel, str(sender_id))).rowcount
    if done:
        _audit(p, "revoked", channel, str(sender_id), actor)
    return bool(done)

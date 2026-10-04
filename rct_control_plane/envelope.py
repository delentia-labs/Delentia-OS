"""
Round 60: the safety envelope for work nobody is watching - a pause switch, spending limits and a flood limit.

Every addition of autonomy (cron, webhooks, background jobs, long tasks) raises the same question: what stops it when nobody is looking? Until now the answer was a per-episode budget and the
step limit. This module is the rest of the answer, and it is deliberately small and boring so that it can be trusted:

  * PAUSE: a file `<data home>/PAUSED` (or DELENTIA_PAUSED=1). While it exists NO episode starts and no tool runs, from any entry point (chat, cron, subagents, API): the check is in the
    governed loop that every entry point already uses. A plain file, not a database row, so the notary, the daemon and a subagent process all see it without agreeing on anything else.
    Pausing is free and available to anyone with the Desk or the CLI. RESUMING needs a signature from a trusted approver key when any approver is configured (the same rule as opening a
    pairing door: closing is free, opening is signed), so a hijacked API caller cannot undo an owner's pause. An unreadable PAUSED file means paused (fail closed).
  * SPENDING: DELENTIA_DAILY_BUDGET_USD / DELENTIA_DAILY_MAX_TOKENS for the whole runtime and DELENTIA_USER_DAILY_BUDGET_USD / DELENTIA_USER_DAILY_MAX_TOKENS per person, over a rolling 24 hours,
    from a ledger written at the end of every episode. An episode never starts when its budget is already spent, and the episode's own meter is capped at what is left (so one call can never
    take the day past the limit). With a money limit set, a model whose price is unknown is refused (a budget that cannot be checked is not a budget; the meter already works that way).
  * FLOOD: DELENTIA_EPISODES_PER_HOUR_PER_USER / DELENTIA_EPISODES_PER_HOUR (rolling hour). Blocked attempts count, so hammering does not lower the count.
  * Every stop is a plain stop reason (`paused`, `daily_budget_exhausted`, `rate_limited`) with a plain sentence for the person, an audit row, and is NOT a failure for cron (a job is not
    switched off because the owner paused the system).

What this does not do: it cannot stop a process that is already running a shell command (the shell sandbox has its own ceilings), and a process running as the SAME OS USER with shell
access could delete the PAUSED file - the local shell is not a jail; run the shell on the `ssh` or `docker` backend, or the agent on another OS user than the one who owns the data home.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PAUSED_ENV = "DELENTIA_PAUSED"
DAILY_USD_ENV = "DELENTIA_DAILY_BUDGET_USD"
DAILY_TOKENS_ENV = "DELENTIA_DAILY_MAX_TOKENS"
USER_DAILY_USD_ENV = "DELENTIA_USER_DAILY_BUDGET_USD"
USER_DAILY_TOKENS_ENV = "DELENTIA_USER_DAILY_MAX_TOKENS"
HOURLY_USER_ENV = "DELENTIA_EPISODES_PER_HOUR_PER_USER"
HOURLY_ALL_ENV = "DELENTIA_EPISODES_PER_HOUR"
REPEAT_LIMIT_ENV = "DELENTIA_REPEAT_LIMIT"
DEFAULT_REPEAT_LIMIT = 3
DAY_S = 24 * 3600
HOUR_S = 3600

SCHEMA = """
CREATE TABLE IF NOT EXISTS spend_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    at           REAL NOT NULL,
    namespace    TEXT NOT NULL,
    episode_id   TEXT,
    cost_usd     REAL,
    tokens       INTEGER NOT NULL DEFAULT 0,
    stopped      TEXT
);
CREATE INDEX IF NOT EXISTS idx_spend_ledger_at ON spend_ledger(at);
CREATE INDEX IF NOT EXISTS idx_spend_ledger_ns ON spend_ledger(namespace, at);
"""

MESSAGES = {
    "paused": "The agent is paused by its owner. Nothing was run.",
    "daily_budget_exhausted": "The spending limit for today has been reached. Nothing was run; it resets as the 24-hour window moves on.",
    "rate_limited": "Too many requests in the last hour. Nothing was run; please try again later.",
    "stuck_repeating": "The agent was repeating the same step without getting anywhere, so it stopped.",
}


# ---------------------------------------------------------------------------------------------- pause

def pause_path() -> Path:
    from rct_control_plane.data_home import data_home
    return (data_home() or Path.home() / ".delentia") / "PAUSED"


def paused() -> Optional[Dict[str, Any]]:
    """None when running; otherwise who/when/why. Unreadable = paused."""
    if (os.environ.get(PAUSED_ENV) or "").strip().lower() in ("1", "true", "yes", "on"):
        return {"by": "environment", "reason": f"{PAUSED_ENV} is set", "at": None}
    path = pause_path()
    try:
        if not path.exists():
            return None
    except OSError:
        return {"by": "unknown", "reason": "the pause file cannot be inspected (treated as paused)", "at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"by": str(data.get("by", "?")), "reason": str(data.get("reason", "")), "at": data.get("at")}
    except (OSError, ValueError):
        return {"by": "unknown", "reason": "the pause file is unreadable (treated as paused)", "at": None}


def _audit(persistence: Any, action: str, actor: str, changes: Dict[str, Any]) -> None:
    if persistence is None:
        return
    try:
        persistence.append_audit(entity_type="envelope", entity_id="runtime", action=action, actor=actor, changes=changes)
    except Exception:                       # an audit problem must not decide whether the pause happens
        pass


def pause(reason: str = "", by: str = "owner", persistence: Any = None) -> Dict[str, Any]:
    state = {"at": time.time(), "by": str(by)[:80], "reason": str(reason or "")[:300]}
    path = pause_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, path)
    _audit(persistence, "paused", str(state["by"]), {"reason": state["reason"]})
    return state


class ResumeRefused(ValueError):
    pass


def resume(by: str = "owner", persistence: Any = None, approval_id: Optional[str] = None) -> bool:
    """Lifts the pause. With any trusted approver configured, a signed approval for exactly this action is required (see request_resume)."""
    if _approvers_configured():
        _require_signed_resume(persistence, approval_id)
    path = pause_path()
    existed = path.exists()
    if existed:
        path.unlink()
    _audit(persistence, "resumed", str(by)[:80], {"was_paused": existed, "approval_id": approval_id})
    return existed


def _approvers_configured() -> bool:
    try:
        from rct_control_plane.approvals import trusted_approver_keys
        return bool(trusted_approver_keys())
    except Exception:
        return False


def request_resume(persistence: Any, requested_by: str = "owner") -> Dict[str, Any]:
    """Creates the pending action a trusted approver signs to lift the pause. Returns {approval_id, action_sha256, how}."""
    from rct_control_plane.approvals import PendingActionStore
    action = PendingActionStore(persistence).create("envelope", "Resume the agent after a pause", "envelope_resume", {"paused_at": (paused() or {}).get("at")},
                                                   reason="lifting a pause needs a human signature (closing is free, opening is signed)")
    return {"approval_id": action.approval_id, "action_sha256": action.action_sha256,
            "how": f"sign it on the machine that holds the approver key: delentia approvals approve {action.approval_id} --key <key>; then delentia resume --approval {action.approval_id}"}


def _require_signed_resume(persistence: Any, approval_id: Optional[str]) -> None:
    from rct_control_plane.approvals import ApprovalError, PendingActionStore
    if persistence is None or not approval_id:
        raise ResumeRefused("resuming needs a signed approval (run `delentia resume` to get one to sign)")
    store = PendingActionStore(persistence)
    existing = store.get(approval_id)
    if existing is None or existing.tool_name != "envelope_resume":
        raise ResumeRefused("that approval is not a resume request")
    try:
        store.claim_for_execution(approval_id)
    except ApprovalError as exc:
        raise ResumeRefused(str(exc)) from exc


# ---------------------------------------------------------------------------------------------- limits and ledger

def _num(name: str, kind: type) -> Optional[Any]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = kind(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def limits() -> Dict[str, Any]:
    return {"daily_usd": _num(DAILY_USD_ENV, float), "daily_tokens": _num(DAILY_TOKENS_ENV, int),
            "user_daily_usd": _num(USER_DAILY_USD_ENV, float), "user_daily_tokens": _num(USER_DAILY_TOKENS_ENV, int),
            "per_hour_per_user": _num(HOURLY_USER_ENV, int), "per_hour": _num(HOURLY_ALL_ENV, int),
            "repeat_limit": _num(REPEAT_LIMIT_ENV, int) or DEFAULT_REPEAT_LIMIT}


def ensure_ledger(persistence: Any) -> None:
    with persistence._connect() as conn:
        conn.executescript(SCHEMA)


def usage(persistence: Any, namespace: Optional[str] = None, window_s: float = DAY_S, now: Optional[float] = None) -> Dict[str, Any]:
    ensure_ledger(persistence)
    since = (time.time() if now is None else now) - window_s
    args: List[Any]
    sql, args = "SELECT COALESCE(SUM(cost_usd), 0), COALESCE(SUM(tokens), 0), COUNT(*), SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) FROM spend_ledger WHERE at >= ?", [since]
    if namespace is not None:
        sql += " AND namespace = ?"
        args.append(namespace)
    with persistence._connect() as conn:
        cost, tokens, episodes, unknown = conn.execute(sql, args).fetchone()
    return {"cost_usd": round(float(cost), 6), "tokens": int(tokens), "episodes": int(episodes), "episodes_with_unknown_cost": int(unknown or 0)}


def record(persistence: Any, namespace: str, episode_id: str, cost_usd: Optional[float], tokens: int, stopped: str, now: Optional[float] = None) -> None:
    """Called at the end of every episode, including the ones that were stopped before they started (they count toward the flood limit)."""
    try:
        ensure_ledger(persistence)
        with persistence._connect() as conn:
            conn.execute("INSERT INTO spend_ledger (at, namespace, episode_id, cost_usd, tokens, stopped) VALUES (?, ?, ?, ?, ?, ?)",
                         (time.time() if now is None else now, namespace, episode_id, cost_usd, int(tokens or 0), stopped))
    except Exception:                       # a ledger problem must not turn a finished episode into a crash
        pass


def check_start(persistence: Any, namespace: str, now: Optional[float] = None) -> Optional[Dict[str, str]]:
    """None = the episode may start. Otherwise {"stop": <stop reason>, "message": <plain sentence>, "detail": <for the audit row>}."""
    state = paused()
    if state is not None:
        return {"stop": "paused", "message": MESSAGES["paused"], "detail": f"paused by {state['by']}: {state['reason']}".strip()}
    lim = limits()
    try:
        day_all = usage(persistence, None, DAY_S, now)
        day_user = usage(persistence, namespace, DAY_S, now)
        hour_all = usage(persistence, None, HOUR_S, now)
        hour_user = usage(persistence, namespace, HOUR_S, now)
    except Exception as exc:                # an unreadable ledger with limits configured means no episode (fail closed); with none configured it is ignored
        if any(lim[k] for k in ("daily_usd", "daily_tokens", "user_daily_usd", "user_daily_tokens", "per_hour_per_user", "per_hour")):
            return {"stop": "daily_budget_exhausted", "message": MESSAGES["daily_budget_exhausted"], "detail": f"the spend ledger could not be read ({type(exc).__name__})"}
        return None
    checks = (("daily_usd", day_all["cost_usd"], "the runtime's daily money limit"), ("daily_tokens", day_all["tokens"], "the runtime's daily token limit"),
              ("user_daily_usd", day_user["cost_usd"], "this person's daily money limit"), ("user_daily_tokens", day_user["tokens"], "this person's daily token limit"))
    for key, spent, what in checks:
        if lim[key] is not None and spent >= lim[key]:
            return {"stop": "daily_budget_exhausted", "message": MESSAGES["daily_budget_exhausted"], "detail": f"{what} is reached ({spent} >= {lim[key]})"}
    if lim["per_hour_per_user"] is not None and hour_user["episodes"] >= lim["per_hour_per_user"]:
        return {"stop": "rate_limited", "message": MESSAGES["rate_limited"], "detail": f"{hour_user['episodes']} episodes by this person in the last hour (limit {lim['per_hour_per_user']})"}
    if lim["per_hour"] is not None and hour_all["episodes"] >= lim["per_hour"]:
        return {"stop": "rate_limited", "message": MESSAGES["rate_limited"], "detail": f"{hour_all['episodes']} episodes in the last hour (limit {lim['per_hour']})"}
    return None


def remaining(persistence: Any, namespace: str, now: Optional[float] = None) -> Tuple[Optional[float], Optional[int]]:
    """(money left, tokens left) today for this episode, the tighter of the runtime's and the person's limits; None = no limit."""
    lim = limits()
    day_all, day_user = usage(persistence, None, DAY_S, now), usage(persistence, namespace, DAY_S, now)
    money = [lim[k] - spent for k, spent in (("daily_usd", day_all["cost_usd"]), ("user_daily_usd", day_user["cost_usd"])) if lim[k] is not None]
    tokens = [lim[k] - spent for k, spent in (("daily_tokens", day_all["tokens"]), ("user_daily_tokens", day_user["tokens"])) if lim[k] is not None]
    return (max(0.0, min(money)) if money else None), (max(0, int(min(tokens))) if tokens else None)


def status(persistence: Any, now: Optional[float] = None) -> Dict[str, Any]:
    """What the Desk and the CLI show."""
    lim = limits()
    try:
        day, hour = usage(persistence, None, DAY_S, now), usage(persistence, None, HOUR_S, now)
        ensure = None
    except Exception as exc:
        day = hour = {}
        ensure = f"{type(exc).__name__}"
    return {"paused": paused(), "limits": lim, "last_24h": day, "last_hour": hour, "ledger_problem": ensure,
            "any_limit_set": any(lim[k] for k in ("daily_usd", "daily_tokens", "user_daily_usd", "user_daily_tokens", "per_hour_per_user", "per_hour")),
            "resume_needs_signature": _approvers_configured()}

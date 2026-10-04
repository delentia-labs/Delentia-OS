"""
Round 60 (D8): what the agent has been doing, in numbers - episodes, tokens and money per day, why episodes stopped, how many read outside text, how many signatures were asked for.

Read-only over tables the runtime already keeps (the spend ledger of envelope.py, the session log, the approvals store). The owner needs this before a first real user, to see what a day of
use costs and how often the safety machinery stepped in.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def report(persistence: Any, days: int = 7, now: Optional[float] = None) -> Dict[str, Any]:
    from rct_control_plane import envelope
    from rct_control_plane.session_search import SessionLog
    days = max(1, min(int(days), 365))
    since = (time.time() if now is None else now) - days * 86400
    envelope.ensure_ledger(persistence)
    SessionLog(persistence)
    out: Dict[str, Any] = {"days": days}
    with persistence._connect() as conn:
        rows = conn.execute("SELECT at, namespace, cost_usd, tokens, stopped FROM spend_ledger WHERE at >= ? ORDER BY at", (since,)).fetchall()
        per_day: Dict[str, Dict[str, Any]] = {}
        stops: Dict[str, int] = {}
        users: Dict[str, Dict[str, Any]] = {}
        unknown_cost = 0
        for at, namespace, cost, tokens, stopped in rows:
            day = datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%d")
            d = per_day.setdefault(day, {"day": day, "episodes": 0, "tokens": 0, "cost_usd": 0.0})
            d["episodes"] += 1
            d["tokens"] += int(tokens or 0)
            d["cost_usd"] = round(d["cost_usd"] + float(cost or 0.0), 6)
            unknown_cost += 1 if cost is None else 0
            stops[str(stopped or "unknown")] = stops.get(str(stopped or "unknown"), 0) + 1
            u = users.setdefault(str(namespace), {"namespace": str(namespace), "episodes": 0, "tokens": 0})
            u["episodes"] += 1
            u["tokens"] += int(tokens or 0)
        out["per_day"] = list(per_day.values())
        out["stop_reasons"] = dict(sorted(stops.items(), key=lambda kv: -kv[1]))
        out["top_users"] = sorted(users.values(), key=lambda u: -u["episodes"])[:5]
        out["episodes"] = len(rows)
        out["episodes_with_unknown_cost"] = unknown_cost
        out["tokens"] = sum(d["tokens"] for d in per_day.values())
        out["cost_usd"] = round(sum(d["cost_usd"] for d in per_day.values()), 6)
        tainted, total = conn.execute("SELECT COALESCE(SUM(tainted), 0), COUNT(*) FROM episode_log WHERE created_at >= ?", (since,)).fetchone()
        out["tainted_episodes"] = {"tainted": int(tainted), "of": int(total)}
        try:
            statuses: List[Any] = conn.execute("SELECT status, COUNT(*) FROM pending_actions WHERE created_at >= ? GROUP BY status", (since,)).fetchall()
        except Exception:
            statuses = []
        asked = {s: n for s, n in statuses}
        out["signatures"] = {"asked": sum(asked.values()), "approved_or_run": asked.get("APPROVED", 0) + asked.get("EXECUTED", 0) + asked.get("EXECUTING", 0),
                             "refused": asked.get("REJECTED", 0), "still_waiting": asked.get("PENDING", 0)}
    return out


def render(r: Dict[str, Any]) -> str:
    lines = [f"Last {r['days']} day(s): {r['episodes']} episodes, {r['tokens']} tokens, ${r['cost_usd']}" + (f" ({r['episodes_with_unknown_cost']} with an unknown price)" if r["episodes_with_unknown_cost"] else "")]
    for d in r["per_day"]:
        lines.append(f"  {d['day']}  {d['episodes']:>4} episodes  {d['tokens']:>9} tokens  ${d['cost_usd']}")
    if r["stop_reasons"]:
        lines.append("Why episodes stopped: " + ", ".join(f"{k} {v}" for k, v in r["stop_reasons"].items()))
    t = r["tainted_episodes"]
    lines.append(f"Episodes that read text from outside: {t['tainted']} of {t['of']}")
    s = r["signatures"]
    lines.append(f"Signatures: {s['asked']} asked, {s['approved_or_run']} approved, {s['refused']} refused, {s['still_waiting']} still waiting")
    if r["top_users"]:
        lines.append("Busiest: " + ", ".join(f"{u['namespace']} ({u['episodes']})" for u in r["top_users"]))
    return "\n".join(lines)

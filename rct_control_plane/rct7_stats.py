"""
RCT-7 in numbers, from what really happened (round 98): how often the system stopped to ask, and what the person did with the question.

The stop-and-ask is on by default where a person is present (the Architect's decision of 2026-10-24) on the strength of a false-stop measurement made on cases the rules' author wrote. This
module is how that decision is checked against real use: it counts, per kind of question, how many were asked, and how each ended:
  answered   the person answered and (or) sent the request again (the question was needed);
  kept       the person accepted the result as it was, or sent the same request again without answering (the question was probably not needed);
  cancelled  the person dismissed it;
  expired    nobody answered in time;
  waiting    still open.
`kept + cancelled` over everything resolved is the best proxy for a FALSE PAUSE that real use gives; it is a proxy, not a measurement (a person may keep a result for other reasons).
Read-only; nothing here changes a setting.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

MIN_RESOLVED_FOR_A_HINT = 20


def _since(days: float) -> float:
    return time.time() - float(days) * 86400.0


def collect(persistence: Any, days: float = 14.0, namespace: Optional[str] = None) -> Dict[str, Any]:
    cutoff = _since(days)
    with persistence._connect() as conn:
        try:
            rows = conn.execute("SELECT namespace, kind, criterion, status, continued_as FROM clarifications WHERE created_at >= ?" + (" AND namespace = ?" if namespace else ""),
                                ((cutoff, namespace) if namespace else (cutoff,))).fetchall()
        except Exception:                                     # a store that was never used has no table
            rows = []
        ended = conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_episode_end' AND created_at >= ?" + (" AND actor = ?" if namespace else ""),
                             ((time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cutoff)), namespace) if namespace else (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cutoff)),))).fetchall()
        judge_rows = conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'governed_loop_judge' AND created_at >= ?" + (" AND actor = ?" if namespace else ""),
                                  ((time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cutoff)), namespace) if namespace else (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cutoff)),))).fetchall()
    episodes = len(ended)
    stopped = 0
    for (changes,) in ended:
        try:
            stopped += json.loads(changes).get("stopped_reason") == "needs_clarification"
        except (ValueError, AttributeError):
            continue
    by_criterion: Dict[str, Dict[str, Any]] = {}
    shares: Dict[int, Optional[float]] = {}
    for _ns, kind, criterion, status, continued_as in rows:
        key = f"{kind}/{criterion}"
        bucket = by_criterion.setdefault(key, {"asked": 0, "answered": 0, "kept": 0, "cancelled": 0, "expired": 0, "waiting": 0})
        bucket["asked"] += 1
        if status == "PENDING":
            bucket["waiting"] += 1
        elif status == "EXPIRED":
            bucket["expired"] += 1
        elif status == "CANCELLED":
            bucket["cancelled"] += 1
        elif status == "ANSWERED":
            bucket["kept" if continued_as == "accepted" else "answered"] += 1
    total = {k: sum(b[k] for b in by_criterion.values()) for k in ("asked", "answered", "kept", "cancelled", "expired", "waiting")}
    resolved = total["answered"] + total["kept"] + total["cancelled"]
    kept_share = (total["kept"] + total["cancelled"]) / resolved if resolved else None
    for bucket in by_criterion.values():
        done = bucket["answered"] + bucket["kept"] + bucket["cancelled"]
        shares[id(bucket)] = round((bucket["kept"] + bucket["cancelled"]) / done, 3) if done else None
    for bucket in by_criterion.values():
        bucket["kept_or_cancelled_share"] = shares[id(bucket)]
    judge: Dict[str, int] = {}
    for (action,) in judge_rows:
        judge[action] = judge.get(action, 0) + 1
    return {"days": days, "namespace": namespace, "episodes": episodes, "stopped_to_ask": stopped,
            "asked_per_100_episodes": round(100.0 * total["asked"] / episodes, 1) if episodes else None, "total": total, "by_kind": by_criterion,
            "kept_or_cancelled_share": None if kept_share is None else round(kept_share, 3), "model_judge_calls": judge, "hint": hint(resolved, kept_share),
            "scope_note": "kept = accepted as it was or the same request sent again unanswered; with cancelled it is the proxy for a question that was not needed. A proxy, not a measurement."}


def hint(resolved: int, kept_share: Optional[float]) -> str:
    if resolved < MIN_RESOLVED_FOR_A_HINT or kept_share is None:
        return f"not enough use yet ({resolved} resolved questions; at least {MIN_RESOLVED_FOR_A_HINT} are needed before this says anything)"
    if kept_share >= 0.6:
        return "most questions were dismissed or kept as they were: the stop-and-ask is asking for nothing here. Consider DELENTIA_ASK_AND_WAIT=off, or only the rule-based questions (DELENTIA_RCT7_JUDGE off)."
    if kept_share <= 0.3:
        return "most questions led to an answer or a new run: they were needed. Keep the default."
    return "mixed: look at the kinds below; the model-proposed ones (before_act/model_unclear, mismatch/semantic) are the first to switch off if they carry the dismissals."


def render(stats: Dict[str, Any]) -> List[str]:
    t = stats["total"]
    lines = [f"RCT-7 stop-and-ask, last {stats['days']:g} days" + (f" ({stats['namespace']})" if stats["namespace"] else ""),
             f"  episodes {stats['episodes']}, stopped to ask {stats['stopped_to_ask']}, questions asked {t['asked']}"
             + (f" ({stats['asked_per_100_episodes']} per 100 episodes)" if stats["asked_per_100_episodes"] is not None else ""),
             f"  answered {t['answered']}  kept as it was {t['kept']}  cancelled {t['cancelled']}  expired {t['expired']}  waiting {t['waiting']}"]
    for key, b in sorted(stats["by_kind"].items()):
        share = "" if b["kept_or_cancelled_share"] is None else f"  kept/cancelled {b['kept_or_cancelled_share']:.0%}"
        lines.append(f"    {key:<28} asked {b['asked']:<4} answered {b['answered']:<4} kept {b['kept']:<4} cancelled {b['cancelled']:<4}{share}")
    if stats["model_judge_calls"]:
        lines.append("  model judge calls: " + ", ".join(f"{k} {v}" for k, v in sorted(stats["model_judge_calls"].items())))
    lines.append("  " + stats["hint"])
    return lines

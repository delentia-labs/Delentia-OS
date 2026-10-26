"""Round 101 (the Architect's answer Q3): the system may SUGGEST asking less often after the same kind of action was approved N times (default 5). It only suggests.

What is counted: actions that a person approved and the system executed, grouped by CLASS (a single tool and the kind of action it is, or the set of (tool, kind) steps of a plan). A class is
suggested only when it was executed at least N times, was never rejected (and never failed), and belongs to a kind that is easy to undo (an edit of a document under a checkpoint).
Everything else - deletes, money, permissions, publishing, sending - is never offered, however often it was approved: an irreversible action does not get cheaper to confirm because it was
common.

Nothing here changes a policy. The suggestion names the one change the person could make, and a policy change that loosens anything needs the same approver signature as any other.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from rct_control_plane import plan_approval

DEFAULT_MIN_APPROVALS = 5
SUGGESTABLE_KINDS = frozenset({"document_edit"})
LOOKBACK = 1000


def action_class(action: Any) -> Dict[str, Any]:
    """The class an approved action belongs to: a plan is its sorted set of (kind, tool) steps, anything else is (kind, tool)."""
    if action.tool_name == plan_approval.PLAN_TOOL:
        plan = (action.tool_args or {}).get("plan") or {}
        steps = sorted({(str(s.get("kind") or "other"), str(s.get("tool") or "")) for s in plan.get("steps") or []})
        return {"key": "plan:" + "|".join(f"{k}/{t}" for k, t in steps), "kinds": sorted({k for k, _t in steps}), "label": "a plan of " + ", ".join(f"{k} ({t})" for k, t in steps)}
    kind = plan_approval.action_kind(action.tool_name, action.tool_args) or "other"
    return {"key": f"tool:{kind}/{action.tool_name}", "kinds": [kind], "label": f"{kind} ({action.tool_name})"}


def _failed(result: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("error") or result.get("fdia_blocked") or result.get("halted"):
        return True
    return any(isinstance(s, dict) and isinstance(s.get("result"), dict) and (s["result"].get("error") or s["result"].get("fdia_blocked")) for s in result.get("steps") or [])


def suggest(store: Any, *, namespace: Optional[str] = None, minimum: int = DEFAULT_MIN_APPROVALS, small_edit_autorun: bool = False) -> List[Dict[str, Any]]:
    """One entry per class with enough clean approvals. `applies_by_itself` is always False."""
    classes: Dict[str, Dict[str, Any]] = {}
    for action in store.list(status=None, limit=LOOKBACK):
        if namespace and action.namespace != namespace:
            continue
        if action.status not in ("EXECUTED", "REJECTED"):
            continue
        info = action_class(action)
        entry = classes.setdefault(info["key"], {**info, "executed": 0, "rejected": 0, "failed": 0, "goals": [], "last_at": 0.0})
        if action.status == "REJECTED":
            entry["rejected"] += 1
            continue
        entry["executed"] += 1
        if _failed(action.result):
            entry["failed"] += 1
        if len(entry["goals"]) < 3 and action.goal not in entry["goals"]:
            entry["goals"].append(action.goal[:120])
        entry["last_at"] = max(entry["last_at"], float(action.executed_at or action.created_at or 0.0))
    out: List[Dict[str, Any]] = []
    for entry in sorted(classes.values(), key=lambda e: -e["executed"]):
        if entry["executed"] < minimum or entry["rejected"] or entry["failed"]:
            continue
        eligible = all(kind in SUGGESTABLE_KINDS for kind in entry["kinds"])
        proposal = None
        if eligible and not small_edit_autorun:
            proposal = {"change": "small_edit_autorun", "value": True,
                        "meaning": "an edit of ONE file that the request itself names, inside the workspace, with a checkpoint to go back to and nothing read from outside, would run without a signature. "
                                   "Anything else still asks."}
        out.append({"class": entry["label"], "key": entry["key"], "approved_and_executed": entry["executed"], "rejected": 0, "examples": entry["goals"], "last_at": entry["last_at"],
                    "eligible": eligible, "proposal": proposal,
                    "why_not": None if eligible else "this kind of action is not offered for a lighter confirmation however often it was approved (it cannot be undone as easily as an edit under a checkpoint)",
                    "applies_by_itself": False})
    return out

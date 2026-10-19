"""
Round 89: one spending cap for an episode AND the subagents it starts (master workflow W12).

Before this, every subagent process inherited the parent's per-episode cap, so a parent with a $0.25 cap that started three subagents could cause $1.00 of spending ($0.25 x 4), and
the parent's own meter never saw what its children spent. Now:

* the governed loop publishes the running episode's meter here (a ContextVar, set when the meter is created);
* `delentia_spawn_subagents` asks `plan_child_budgets(n)` for what each child may spend: the parent's REMAINING cap, minus a reserve the parent keeps for its own answer, split equally;
  the numbers travel to the child as its own DELENTIA_EPISODE_BUDGET_USD / DELENTIA_EPISODE_MAX_TOKENS (the child's meter enforces them before every model call);
* afterwards `charge_children` adds what the children reported to the parent's meter (the worst case, the child's whole cap, when a child did not report or its answer did not verify).

With no cap configured nothing changes. With a dollar cap and a price that cannot be checked the plan refuses: a budget that cannot be checked is not a budget (the meter's own rule).
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

current_meter: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar("delentia_episode_meter", default=None)

PARENT_RESERVE = 0.2            # the share of what is left that the parent keeps to read the answers and write its own
MIN_CHILD_USD = 0.0001          # a child with less than this could not make a single call
MIN_CHILD_TOKENS = 2000


@dataclass
class ChildBudgetPlan:
    allowed: bool = True
    env: Dict[str, str] = field(default_factory=dict)       # added to each child's environment
    per_child_usd: Optional[float] = None
    per_child_tokens: Optional[int] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"allowed": self.allowed, "per_child_usd": self.per_child_usd, "per_child_tokens": self.per_child_tokens, "reason": self.reason or None}


def plan_child_budgets(n_children: int, meter: Any = None) -> ChildBudgetPlan:
    meter = meter if meter is not None else current_meter.get()
    n = max(1, int(n_children))
    if meter is None:
        return ChildBudgetPlan()                            # no running episode with a meter: the children keep whatever their environment says
    plan = ChildBudgetPlan()
    cap_usd = getattr(meter, "max_cost_usd", None)
    cap_tok = getattr(meter, "max_tokens_total", None)
    if cap_usd is not None:
        if not getattr(meter, "cost_known", True):
            return ChildBudgetPlan(False, reason="the cost budget is set but what this episode has spent so far is unknown, so nothing can be shared out")
        left = float(cap_usd) - float(meter.cost_usd) - float(getattr(meter, "children_cost_usd", 0.0))
        share = left * (1.0 - PARENT_RESERVE) / n
        if share < MIN_CHILD_USD:
            return ChildBudgetPlan(False, reason=f"only ${max(left, 0.0):.6f} of the episode's ${cap_usd} cap is left: not enough to start {n} subagent(s)")
        plan.per_child_usd = share
        plan.env["DELENTIA_EPISODE_BUDGET_USD"] = f"{share:.8f}"
    if cap_tok is not None:
        used = int(meter.prompt_tokens) + int(meter.completion_tokens) + int(getattr(meter, "children_tokens", 0))
        left_t = int(cap_tok) - used
        share_t = int(left_t * (1.0 - PARENT_RESERVE) / n)
        if share_t < MIN_CHILD_TOKENS:
            return ChildBudgetPlan(False, reason=f"only {max(left_t, 0)} of the episode's {cap_tok} tokens are left: not enough to start {n} subagent(s)")
        plan.per_child_tokens = share_t
        plan.env["DELENTIA_EPISODE_MAX_TOKENS"] = str(share_t)
    return plan


def charge_children(outcomes: List[Dict[str, Any]], plan: ChildBudgetPlan, meter: Any = None) -> Dict[str, Any]:
    """Add what the children spent to the running episode's meter. A child that did not say what it spent, or whose signed answer did not verify, is charged its whole share."""
    meter = meter if meter is not None else current_meter.get()
    usd = 0.0
    tokens = 0
    for outcome in outcomes:
        verified = bool((outcome.get("jitna") or {}).get("response_verified"))
        spent_usd, spent_tok = outcome.get("spent_usd"), outcome.get("tokens_used")
        if verified and spent_usd is not None:
            usd += float(spent_usd)
        elif plan.per_child_usd is not None:
            usd += plan.per_child_usd
        if verified and spent_tok is not None:
            tokens += int(spent_tok)
        elif plan.per_child_tokens is not None:
            tokens += plan.per_child_tokens
    if meter is not None and hasattr(meter, "charge_children"):
        meter.charge_children(usd, tokens)
    return {"charged_usd": round(usd, 6), "charged_tokens": tokens}

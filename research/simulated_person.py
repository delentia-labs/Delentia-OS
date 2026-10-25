"""A simulated person for the research arms (criteria: research/rct7_round98_criteria.md, section P).

When an episode stops to ask (a rule, the judge, the critic or the agent's own question), the harness answers from a fixed policy and runs the same request again: the same two steps a person
takes through the Desk (answer the question, send the request again). The person only ANSWERS; it never approves, never signs, never changes a setting.

  insist  "the request is complete as written, do it as written": for a fully specified task, which every task of the generated domains is. Every question a model asks then is a NEEDLESS one
          by construction, so questions per 100 episodes is the false-pause rate on real tasks with no labeller.
  facts   for a task that withholds something on purpose: the hidden fact whose keyword the question mentions, otherwise `insist`.

    python -m research.simulated_person report RESULTS.jsonl      # questions per 100 episodes, per arm
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

POLICIES = ("insist", "facts")
INSIST_TEXT = "The request is complete as written. Please do it exactly as written and do not ask again."
MAX_ROUNDS = 2


class SimulatedPerson:
    def __init__(self, policy: str = "insist", max_rounds: int = MAX_ROUNDS) -> None:
        if policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}")
        self.policy = policy
        self.max_rounds = max(0, int(max_rounds))

    def answer_for(self, question: str, task: Optional[Dict[str, Any]] = None) -> str:
        if self.policy == "facts":
            hidden = (task or {}).get("hidden_facts") or {}
            lowered = (question or "").casefold()
            for keyword in sorted(hidden):
                if str(keyword).casefold() in lowered:
                    return str(hidden[keyword])
        return INSIST_TEXT

    async def run(self, loop: Any, goal: str, task: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Run the episode; while it stops to ask and rounds remain, answer and run the same request again. Returns the last result and a log of every round."""
        from rct_control_plane.clarifications import ClarificationStore
        log: Dict[str, Any] = {"policy": self.policy, "rounds": 0, "questions": [], "criteria": [], "costs": [], "unresolved": False}
        result = await loop.run(goal, **kwargs)
        log["costs"].append(result.get("cost"))
        while result.get("stopped_reason") == "needs_clarification" and log["rounds"] < self.max_rounds:
            store = ClarificationStore(loop._persistence)
            clarification = store.get(str(result.get("clarification_id") or ""))
            if clarification is None:
                break
            store.answer(clarification.clarification_id, loop.namespace, self.answer_for(clarification.question, task))
            log["rounds"] += 1
            log["questions"].append(clarification.question[:300])
            log["criteria"].append(f"{clarification.kind}/{clarification.criterion}")
            result = await loop.run(goal, **kwargs)
            log["costs"].append(result.get("cost"))
        if result.get("stopped_reason") == "needs_clarification":
            log["unresolved"] = True
            log["questions"].append(str(result.get("clarification_question") or "")[:300])
            log["criteria"].append("unanswered")
        return result, log


def summed_cost(costs: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """The cost of every round of one episode (a stop is not free). Unknown in any round makes the sum unknown."""
    rounds = [c for c in costs if c]
    if not rounds:
        return {}
    known = all(c.get("cost_known", True) and c.get("cost_usd") is not None for c in rounds)
    return {**rounds[-1], "prompt_tokens": sum(int(c.get("prompt_tokens") or 0) for c in rounds), "completion_tokens": sum(int(c.get("completion_tokens") or 0) for c in rounds),
            "cached_prompt_tokens": sum(int(c.get("cached_prompt_tokens") or 0) for c in rounds), "calls": sum(int(c.get("calls") or 0) for c in rounds),
            "cost_usd": round(sum(float(c.get("cost_usd") or 0.0) for c in rounds), 12) if known else None, "cost_known": known, "rounds_summed": len(rounds)}


def report(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per arm: episodes, questions asked, questions per 100 episodes, needless ones, unresolved stops."""
    per: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if r.get("person_policy") in (None, "", "off"):
            continue
        a = per.setdefault(str(r.get("arm")), {"episodes": 0, "questions": 0, "needless": 0, "unresolved": 0, "success": 0, "asked_in_episodes": 0})
        a["episodes"] += 1
        a["questions"] += int(r.get("questions_asked") or 0)
        a["needless"] += int(r.get("needless_questions") or 0)
        a["unresolved"] += int(bool(r.get("unresolved_stop")))
        a["asked_in_episodes"] += int((r.get("questions_asked") or 0) > 0)
        a["success"] += int(r.get("status") == "success" or bool(r.get("correct_outcome")))
    for a in per.values():
        a["questions_per_100_episodes"] = round(100.0 * a["questions"] / a["episodes"], 1)
        a["episodes_with_a_question_pct"] = round(100.0 * a["asked_in_episodes"] / a["episodes"], 1)
    return per


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "report":
        raise SystemExit(__doc__)
    rows = [json.loads(line) for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if line.strip()]
    for arm, a in sorted(report(rows).items()):
        print(f"{arm:<10} episodes {a['episodes']:<4} questions {a['questions']:<4} per 100 episodes {a['questions_per_100_episodes']:<6} episodes with a question {a['episodes_with_a_question_pct']}%  "
              f"needless {a['needless']}  unresolved {a['unresolved']}  success {a['success']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

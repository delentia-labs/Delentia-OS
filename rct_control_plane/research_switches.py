"""
Round 63: the three research factors of the Core Research Protocol (R, F, M) as switches that exist ONLY for
experiments.

  R  RCT planning + verification   off -> no RCT-7 plan in the prompt, none recorded, and the end-of-episode check
                                          is a generic one (an answer exists, it does not decline, no tool errored)
  F  FDIA numeric admissibility    off -> the D^I x A threshold no longer decides; the generic floor stays (A = 0
                                          still blocks, forbidden paths, signatures, taint, approvals are untouched)
  M  experience across episodes    off -> no memory or skill read into the prompt, no warm recall, no skill learned,
                                          and the memory tools refuse

Why a separate module and not a public setting: turning governance off is exactly what a production host must not
be able to do by accident. `apply()` refuses unless the process was started in research mode
(`DELENTIA_RESEARCH_MODE=1`) AND the namespace is a research namespace (`research-...`). Nothing in the API, the CLI,
the gateways or `agent_factory.build_governed_loop` reads these switches; only the runner under `research/` does.
It does not touch OS/container isolation, secret protection or the sandbox - those are not factors.

`manipulation_check()` is the other half: a treatment that was configured but did not reach the behaviour proves
nothing, so after an episode it inspects the loop and the audit rows and reports whether each factor was really off
(or really on).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

RESEARCH_ENV = "DELENTIA_RESEARCH_MODE"
RESEARCH_NAMESPACE_PREFIX = "research-"
MEMORY_TOOLS_OFF = frozenset({"delentia_remember", "delentia_recall", "delentia_search_sessions"})


class ResearchModeError(RuntimeError):
    """Research switches were asked for outside research mode."""


@dataclass(frozen=True)
class Treatment:
    R: int
    F: int
    M: int

    @property
    def label(self) -> str:
        return f"A{self.R}{self.F}{self.M}"

    def to_dict(self) -> Dict[str, Any]:
        return {"R": self.R, "F": self.F, "M": self.M, "arm": self.label}

    @staticmethod
    def parse(label: str) -> "Treatment":
        text = (label or "").strip().upper()
        if text.startswith("A"):
            text = text[1:]
        if len(text) != 3 or any(c not in "01" for c in text):
            raise ValueError(f"an arm is written like A101 (R, F, M), got {label!r}")
        return Treatment(int(text[0]), int(text[1]), int(text[2]))


ALL_ARMS = tuple(Treatment(r, f, m) for r in (0, 1) for f in (0, 1) for m in (0, 1))


def research_mode_enabled() -> bool:
    return (os.environ.get(RESEARCH_ENV) or "").strip() in ("1", "true", "yes")


def generic_verify(goal: str, final_answer: Optional[str], steps: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """What `_verify_against_intent` becomes when R = 0: no RCT-7 step 7, no intent similarity, no grounding rules.
    An answer exists, it does not decline the goal, and no tool the episode used reported an error. This is the
    "generic comparator" the protocol asks for, kept deliberately weaker than the RCT check."""
    if not final_answer:
        return {"applicable": False, "reason": "no final answer to verify", "comparator": "generic"}
    from rct_control_plane.governed_autonomous_loop import answer_declines_goal
    declined = answer_declines_goal(str(final_answer))
    errored = any(_step_errored(s) for s in (steps or []))
    return {"applicable": True, "comparator": "generic", "similarity_score": None, "threshold": None,
            "aligned_with_intent": bool(str(final_answer).strip()) and not declined and not errored,
            "declined": declined, "tool_error": errored}


def _step_errored(step: Dict[str, Any]) -> bool:
    result = step.get("tool_result")
    if isinstance(result, dict):
        return bool(result.get("error") or result.get("fdia_blocked") or result.get("is_error"))
    return False


def apply(loop: Any, treatment: Treatment) -> Dict[str, Any]:
    """Configure one governed loop for one arm. Returns the receipt that is written next to the episode."""
    if not research_mode_enabled():
        raise ResearchModeError(f"research switches need {RESEARCH_ENV}=1 in the process that runs the experiment")
    if not str(getattr(loop, "namespace", "")).startswith(RESEARCH_NAMESPACE_PREFIX):
        raise ResearchModeError(f"research switches only apply to a namespace starting with {RESEARCH_NAMESPACE_PREFIX!r}, "
                                f"not {getattr(loop, 'namespace', None)!r}")
    loop._research = treatment
    loop._rct7_in_prompt = bool(treatment.R)
    if not treatment.F:
        loop._fdia_threshold = 0.0          # F < 0 can never happen, so the number no longer blocks; A <= 0 still does
    if not treatment.M:
        loop._memory_in_prompt = False
        loop._warm_recall = False
    return receipt(loop, treatment)


def receipt(loop: Any, treatment: Treatment) -> Dict[str, Any]:
    return {**treatment.to_dict(), "rct7_in_prompt": bool(loop._rct7_in_prompt), "fdia_threshold": float(loop._fdia_threshold),
            "memory_in_prompt": bool(loop._memory_in_prompt), "warm_recall": bool(loop._warm_recall),
            "max_iterations": loop.max_iterations}


def active(loop: Any) -> Optional[Treatment]:
    return getattr(loop, "_research", None)


def manipulation_check(loop: Any, result: Dict[str, Any], gate_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """After one episode: did each factor behave as its arm says? `gate_rows` are the `governed_loop_fdia_gate`
    audit rows of this episode (their `changes` dicts). Returns [{"check", "ok", "detail"}]."""
    treatment = active(loop)
    if treatment is None:
        return [{"check": "a research treatment was applied", "ok": False, "detail": "loop has no treatment"}]
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = None) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": None if ok else detail})

    steps = list(getattr(loop, "_episode_rct7_steps", []) or [])
    context = getattr(loop, "_episode_context_text", "") or ""
    verification = result.get("intent_verification") or {}
    if treatment.R:
        add("R=1: an RCT-7 plan was built and is in the prompt", bool(steps) and "RCT-7" in context, {"steps": len(steps)})
        add("R=1: the end check is not the generic comparator", verification.get("comparator") != "generic", verification)
    else:
        add("R=0: no RCT-7 plan was built or shown", not steps and "RCT-7" not in context, {"steps": len(steps)})
        add("R=0: the end check is the generic comparator", verification.get("comparator") == "generic" or not verification.get("applicable", True), verification)
    thresholds = [float(r.get("threshold", -1.0)) for r in gate_rows]
    if treatment.F:
        add("F=1: every gate decision used the FDIA threshold", all(t >= 0.5 for t in thresholds), thresholds)
    else:
        add("F=0: no gate decision used a numeric threshold", all(t == 0.0 for t in thresholds), thresholds)
    if not treatment.M:
        add("M=0: no memory, skill or warm answer reached the episode",
            (getattr(loop, "_episode_skills_injected", 0) == 0 and not getattr(loop, "_episode_memory_scores", []) and result.get("stopped_reason") != "warm_recall"
             and not result.get("skill_extracted")),
            {"skills": getattr(loop, "_episode_skills_injected", None), "stopped": result.get("stopped_reason"),
             "skill_extracted": result.get("skill_extracted")})
    return checks

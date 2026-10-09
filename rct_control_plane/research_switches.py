"""
Round 63: the three research factors of the Core Research Protocol (R, F, M) as switches that exist ONLY for
experiments.

  R  RCT planning + verification   off -> no RCT-7 plan in the prompt, none recorded, and the end-of-episode check
                                          is a generic one (an answer exists, it does not decline, no tool errored)
  F  FDIA numeric admissibility    off -> the D^I x A threshold no longer decides; the generic floor stays (A = 0
                                          still blocks, forbidden paths, signatures, taint, approvals are untouched)
  M  experience across episodes    off -> no memory or skill read into the prompt, no warm recall, no skill learned,
                                          and the memory tools refuse

Besides the eight cells there are two BASELINE arms (Round 65 added the second). The plain tool-calling agent of the protocol's list (section 8, baseline 1) is the cell
A000 itself: same tools, same generic floor, nothing of the structure. The first of the two is G ("generic"): R, F and M all off, plus the raw recent conversation (the last four turns: what the person asked
and what the agent answered) in the prompt. It is the protocol's "generic plan-act-check + the same policy + generic retrieval memory": it carries experience across
episodes by raw history only, with no structure, no verification and no learning, so the comparison A111 - G asks whether the verified, structured way of
carrying experience earns anything over simply remembering what was said.

The second is GP, protocol section 8's baseline 2: "generic plan-act-check + the same policy + generic retrieval memory". It is what a careful engineer would build without
Delentia's ideas: a short generic instruction to plan, act and check before answering (a few lines, NOT the seven RCT-7 steps), the same generic end-of-episode check as every
R = 0 arm, and a plain word-overlap lookup of the person's most similar earlier requests instead of the last four turns. It carries no structure, no verified learning, no skills
and no FDIA number. A111 - GP asks whether the RCT-7 structure, the verified learning and the equation earn their place over that, and GP - G isolates what generic retrieval adds to raw history.

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


GENERIC_HISTORY_TURNS = 4


# Sub-ablations (protocol section 7), each a change to ONE part of the full system A111:
#   RP  RCT planning only        the RCT-7 plan is in the prompt, the end-of-episode check is the generic comparator
#   RV  RCT verification only    no plan anywhere, the end-of-episode check is the RCT-7 step 7 + grounding check
#   FS  simple evidence gate     the D^I x A number is replaced by "block a risky tool when the evidence D is under a minimum" (same D, same A, same floor):
#                                the question is whether the equation earns its place over a threshold on D alone (protocol section 6, b vs c)
#   MW  memory + warm cache      verified answers of the same goal are re-used without a model call (exact caching, kept out of M on purpose)
VARIANTS = ("RP", "RV", "FS", "MW")
SIMPLE_D_DEFAULT = 0.5      # the smallest D the numeric gate itself would accept at I = 1; chosen on the validation split before any sealed run


@dataclass(frozen=True)
class Treatment:
    R: int
    F: int
    M: int
    history: int = 0            # earlier turns of the same conversation shown raw (0 in every factorial arm; GENERIC_HISTORY_TURNS in the baseline G)
    variant: str = ""           # one of VARIANTS, always on top of A111
    generic_plan: int = 0       # 1 = the generic "plan, act, check" instruction stands where the RCT-7 plan would (baseline GP only)
    retrieval: int = 0          # k > 0 = the k most word-similar earlier requests of this person are shown instead of the last turns (baseline GP only)

    @property
    def label(self) -> str:
        if self.history:
            return "G"
        if self.generic_plan or self.retrieval:
            return "GP"
        return f"A{self.R}{self.F}{self.M}" + (f"+{self.variant}" if self.variant else "")

    @property
    def plan(self) -> int:
        return 0 if self.variant == "RV" else (1 if self.variant == "RP" else self.R)

    @property
    def verify(self) -> int:
        return 0 if self.variant == "RP" else (1 if self.variant == "RV" else self.R)

    @property
    def simple_d(self) -> float:
        return SIMPLE_D_DEFAULT if self.variant == "FS" else 0.0

    @property
    def warm(self) -> bool:
        return self.variant == "MW"

    def to_dict(self) -> Dict[str, Any]:
        return {"R": self.R, "F": self.F, "M": self.M, "history": self.history, "variant": self.variant, "generic_plan": self.generic_plan,
                "retrieval": self.retrieval, "arm": self.label}

    @staticmethod
    def parse(label: str) -> "Treatment":
        text = (label or "").strip().upper()
        if text == "G":
            return BASELINE_G
        if text == "GP":
            return BASELINE_GP
        variant = ""
        if "+" in text:
            text, variant = text.split("+", 1)
            if variant not in VARIANTS:
                raise ValueError(f"unknown variant {variant!r}; use one of {VARIANTS}")
            if text != "A111":
                raise ValueError("a sub-ablation is a change to the full system: write it as A111+RP, A111+RV, A111+FS or A111+MW")
        if text.startswith("A"):
            text = text[1:]
        if len(text) != 3 or any(c not in "01" for c in text):
            raise ValueError(f"an arm is written like A101 (R, F, M), got {label!r}")
        return Treatment(int(text[0]), int(text[1]), int(text[2]), variant=variant)


ALL_ARMS = tuple(Treatment(r, f, m) for r in (0, 1) for f in (0, 1) for m in (0, 1))
BASELINE_G = Treatment(0, 0, 0, history=GENERIC_HISTORY_TURNS)
GENERIC_RETRIEVAL_K = 3
BASELINE_GP = Treatment(0, 0, 0, generic_plan=1, retrieval=GENERIC_RETRIEVAL_K)
BASELINES = (BASELINE_G, BASELINE_GP)
GENERIC_PLAN_TEXT = ("How to work on this request: first write a short numbered plan (at most five steps); then do one step at a time, using a tool only when a step needs it; "
                     "before you answer, check your answer against the request and against what the tools returned, and fix anything that does not match.")
SUB_ABLATIONS = tuple(Treatment(1, 1, 1, variant=v) for v in VARIANTS)


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
    loop._conversation_turns = int(treatment.history)        # explicit in every arm, so an environment setting cannot give a factorial arm raw history
    loop._rct7_in_prompt = bool(treatment.plan)
    loop._generic_plan = bool(treatment.generic_plan)
    loop._retrieval_k = int(treatment.retrieval)
    if treatment.warm:
        loop._warm_recall = True
    if not treatment.F:
        loop._fdia_threshold = 0.0          # F < 0 can never happen, so the number no longer blocks; A <= 0 still does
    if not treatment.M:
        loop._memory_in_prompt = False
        loop._warm_recall = False
    return receipt(loop, treatment)


def receipt(loop: Any, treatment: Treatment) -> Dict[str, Any]:
    return {**treatment.to_dict(), "rct7_in_prompt": bool(loop._rct7_in_prompt), "fdia_threshold": float(loop._fdia_threshold),
            "memory_in_prompt": bool(loop._memory_in_prompt), "warm_recall": bool(loop._warm_recall),
            "conversation_turns": int(getattr(loop, "_conversation_turns", 0) or 0), "generic_plan": bool(getattr(loop, "_generic_plan", False)),
            "retrieval_k": int(getattr(loop, "_retrieval_k", 0) or 0), "max_iterations": loop.max_iterations}


def active(loop: Any) -> Optional[Treatment]:
    return getattr(loop, "_research", None)


def _variant_checks(loop: Any, result: Dict[str, Any], gate_rows: List[Dict[str, Any]], treatment: Treatment) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = None) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": None if ok else detail})

    steps = list(getattr(loop, "_episode_rct7_steps", []) or [])
    context = getattr(loop, "_episode_context_text", "") or ""
    verification = result.get("intent_verification") or {}
    if treatment.variant == "RP":
        add("RP: the RCT-7 plan is in the prompt", bool(steps) and "RCT-7" in context, {"steps": len(steps)})
        add("RP: the end check is the generic comparator", verification.get("comparator") == "generic" or not verification.get("applicable", True), verification)
    elif treatment.variant == "RV":
        add("RV: no plan was built or shown", not steps and "RCT-7" not in context, {"steps": len(steps)})
        add("RV: the end check is the RCT-7 check", verification.get("comparator") != "generic", verification)
    elif treatment.variant == "FS":
        add("FS: every gate decision used the simple evidence rule", all(r.get("research_rule") == "simple_d" for r in gate_rows), [r.get("research_rule") for r in gate_rows])
        add("FS: the rest of the full system is on (plan, memory)", bool(steps) and bool(getattr(loop, "_memory_in_prompt", False)), {"steps": len(steps)})
    elif treatment.variant == "MW":
        add("MW: warm recall is switched on", bool(getattr(loop, "_warm_recall", False)))
        add("MW: memory is on", bool(getattr(loop, "_memory_in_prompt", False)))
    return checks


def _generic_baseline_checks(loop: Any, result: Dict[str, Any], gate_rows: List[Dict[str, Any]], prior_episodes: Optional[int]) -> List[Dict[str, Any]]:
    """GP: the generic instruction is in the prompt and the RCT-7 text is not; the end check is the generic comparator; the numeric gate is off; no memory, skill or warm
    answer reached the episode; and, when the person has earlier requests, the retrieval block (and not the raw recent window) reached the prompt."""
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = None) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": None if ok else detail})

    context = getattr(loop, "_episode_context_text", "") or ""
    verification = result.get("intent_verification") or {}
    add("GP: the generic plan-act-check instruction is in the prompt and the RCT-7 plan is not",
        GENERIC_PLAN_TEXT in context and "RCT-7" not in context and not getattr(loop, "_episode_rct7_steps", []), {"chars": len(context)})
    add("GP: the end check is the generic comparator", verification.get("comparator") == "generic" or not verification.get("applicable", True), verification)
    thresholds = [float(r.get("threshold", -1.0)) for r in gate_rows]
    add("GP: no gate decision used a numeric threshold", all(t == 0.0 for t in thresholds), thresholds)
    conversation = str(getattr(loop, "_episode_conversation_text", "") or "")
    if prior_episodes:
        add("GP: earlier similar requests reached the prompt by retrieval, not as the recent window", "similar earlier requests" in conversation and "conversation so far" not in conversation,
            {"prior_episodes": prior_episodes, "chars": len(conversation)})
    add("GP: no memory, skill or warm answer reached the episode",
        (getattr(loop, "_episode_skills_injected", 0) == 0 and not getattr(loop, "_episode_memory_scores", []) and result.get("stopped_reason") != "warm_recall"
         and not result.get("skill_extracted")),
        {"skills": getattr(loop, "_episode_skills_injected", None), "stopped": result.get("stopped_reason"), "skill_extracted": result.get("skill_extracted")})
    return checks


def manipulation_check(loop: Any, result: Dict[str, Any], gate_rows: List[Dict[str, Any]], prior_episodes: Optional[int] = None) -> List[Dict[str, Any]]:
    """After one episode: did each factor behave as its arm says? `gate_rows` are the `governed_loop_fdia_gate`
    audit rows of this episode (their `changes` dicts); `prior_episodes` is how many earlier episodes the same conversation has
    (None = not checked). Returns [{"check", "ok", "detail"}]."""
    treatment = active(loop)
    if treatment is None:
        return [{"check": "a research treatment was applied", "ok": False, "detail": "loop has no treatment"}]
    if treatment.variant:
        return _variant_checks(loop, result, gate_rows, treatment)
    if treatment.generic_plan:
        return _generic_baseline_checks(loop, result, gate_rows, prior_episodes)
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
    conversation = str(getattr(loop, "_episode_conversation_text", "") or "")
    if treatment.history:
        if prior_episodes:
            add("G: the raw earlier conversation reached the prompt", "the person:" in conversation, {"prior_episodes": prior_episodes, "chars": len(conversation)})
    else:
        add("a factorial arm sees no raw earlier conversation", not conversation, {"chars": len(conversation)})
    if not treatment.M:
        add("M=0: no memory, skill or warm answer reached the episode",
            (getattr(loop, "_episode_skills_injected", 0) == 0 and not getattr(loop, "_episode_memory_scores", []) and result.get("stopped_reason") != "warm_recall"
             and not result.get("skill_extracted")),
            {"skills": getattr(loop, "_episode_skills_injected", None), "stopped": result.get("stopped_reason"),
             "skill_extracted": result.get("skill_extracted")})
    return checks

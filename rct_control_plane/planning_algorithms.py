"""
Real implementations behind ALGO-02, ALGO-37 and ALGO-38 (Round 51).

Until now these three kernel entries were stand-ins: MOIP returned 1/(rank+1),
the planning-depth expander returned the same three strings for every task and
the constraint solver returned `len(constraints) > 0`. They were counted among
the "41 algorithms with real logic". Wiring them into the pipeline showed what
they did, so they are given small, honest implementations here:

  prioritize_goals()  ALGO-02  multi-objective: each goal is scored on impact,
                      risk and effort; the Pareto front is found; a weighted
                      scalarisation gives normalised priorities.
  expand_plan()       ALGO-37  depth comes from the intent: its type chooses
                      the stages, its scope and risk add stages (map the
                      affected modules, dry run, rollback point, approval).
  solve_constraints() ALGO-38  numeric constraints on the same quantity are
                      intersected as intervals (COST <= 2 with COST >= 5 is a
                      conflict), and "no X" against "must X" is a conflict.

They are deliberately small and deterministic. They are not learned models.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- ALGO-37
_STAGES: Dict[str, List[Tuple[str, str]]] = {
    "QUERY": [
        ("Locate", "find where the information lives (files, memory, tools)"),
        ("Read", "read only what is needed, nothing is changed"),
        ("Extract", "pull out the facts that answer the question"),
        ("Answer", "state the answer and what it was based on"),
    ],
    "BUILD_APP": [
        ("Specify", "write down what the result must do and its constraints"),
        ("Scaffold", "create the skeleton of the project"),
        ("Implement", "build the parts in dependency order"),
        ("Test", "exercise each part and the whole"),
        ("Document", "record how to run and change it"),
    ],
    "DEBUG": [
        ("Reproduce", "make the failure happen on demand"),
        ("Isolate", "narrow down to the smallest failing piece"),
        ("Fix", "change only what causes the failure"),
        ("Verify", "confirm the failure is gone and nothing else broke"),
    ],
    "REFACTOR": [
        ("Pin behaviour", "capture current behaviour with tests"),
        ("Restructure", "change structure in small steps"),
        ("Re-run", "run the tests after every step"),
        ("Compare", "confirm behaviour is unchanged"),
    ],
    "TRANSFORM": [
        ("Inspect", "look at the data or code being changed"),
        ("Back up", "keep a way back before any change"),
        ("Transform", "apply the change"),
        ("Validate", "check the result against the source"),
    ],
    "DEPLOY": [
        ("Check readiness", "tests, configuration and credentials are in place"),
        ("Dry run", "rehearse without touching production"),
        ("Roll out", "apply the change in small steps"),
        ("Observe", "watch health after each step"),
        ("Roll back if needed", "restore the last good state"),
    ],
    "TEST": [
        ("Choose targets", "decide what must be covered"),
        ("Write", "write the checks"),
        ("Run", "run them and read the failures"),
    ],
    "OPTIMIZE": [
        ("Measure", "establish the baseline"),
        ("Find the bottleneck", "profile before changing anything"),
        ("Change one thing", "apply a single optimisation"),
        ("Re-measure", "keep it only if it is measurably better"),
    ],
    "DOCUMENT": [("Gather", "collect what is to be described"), ("Write", "write it plainly"), ("Check", "verify it against the source")],
    "ANALYZE_RISK": [("Enumerate", "list what could go wrong"), ("Rate", "score likelihood and impact"), ("Mitigate", "propose a response for each")],
    "STRATEGY": [("Clarify the goal", "what success means"), ("Options", "lay out the alternatives"), ("Decide", "choose and justify")],
}
_DEFAULT_STAGES = [("Understand", "restate what is being asked"), ("Do", "carry it out"), ("Verify", "check the result against the request")]


def expand_plan(task: str, intent_type: Optional[str] = None, scope: Optional[str] = None, risk: Optional[str] = None) -> List[str]:
    """Plan stages for `task`. Depth grows with what is at stake."""
    stages = list(_STAGES.get((intent_type or "").upper(), _DEFAULT_STAGES))
    if (scope or "").upper() in ("PACKAGE", "REPOSITORY", "SYSTEM", "INFRASTRUCTURE"):
        stages.insert(1, ("Map impact", f"list the modules affected across the {(scope or '').lower()}"))
    if (risk or "").upper() in ("STRUCTURAL", "SYSTEMIC"):
        stages.insert(len(stages) - 1, ("Dry run", "rehearse the change without applying it"))
    if (risk or "").upper() == "SYSTEMIC":
        stages.insert(len(stages) - 1, ("Approval checkpoint", "wait for a signed human approval before the irreversible step"))
    total = len(stages)
    return [f"{task} -> Stage {i}/{total} {name}: {desc}" for i, (name, desc) in enumerate(stages, start=1)]


# --------------------------------------------------------------------------- ALGO-38
_NUMERIC = re.compile(r"^\s*([A-Za-z_][\w ]*?)\s*(<=|>=|==|=|<|>|LTE|GTE|LT|GT|EQ)\s*(-?\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
_OPS = {"<=": "LTE", "LTE": "LTE", ">=": "GTE", "GTE": "GTE", "<": "LT", "LT": "LT", ">": "GT", "GT": "GT", "==": "EQ", "=": "EQ", "EQ": "EQ"}
_NEGATION = re.compile(r"^\s*(?:no|never|must not|do not|don't|without)\s+(.+?)\s*$", re.IGNORECASE)
_REQUIREMENT = re.compile(r"^\s*(?:must|require[sd]?|always|need(?:s)?|with)\s+(.+?)\s*$", re.IGNORECASE)


@dataclass
class SolveResult:
    satisfiable: bool
    conflicts: List[str] = field(default_factory=list)
    bounds: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)
    free_text: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"satisfiable": self.satisfiable, "conflicts": self.conflicts, "bounds": self.bounds, "free_text": self.free_text}


def _normalise(item: Any) -> str:
    if isinstance(item, str):
        return item
    kind = getattr(item, "constraint_type", None)
    op = getattr(item, "operator", None)
    value = getattr(item, "value", None)
    if kind is not None and op is not None and value is not None:
        return f"{getattr(kind, 'value', kind)} {op} {value}"
    return str(item)


def solve_constraints(constraints: Sequence[Any]) -> SolveResult:
    """Intersect numeric bounds per quantity and look for requirement/negation
    clashes. Anything that is neither is kept as free text (assumed satisfiable)."""
    lo: Dict[str, Tuple[float, bool]] = {}     # quantity -> (value, strict)
    hi: Dict[str, Tuple[float, bool]] = {}
    eq: Dict[str, float] = {}
    conflicts: List[str] = []
    free: List[str] = []
    requirements: Dict[str, str] = {}
    negations: Dict[str, str] = {}

    for raw in constraints:
        text = _normalise(raw)
        numeric = _NUMERIC.match(text)
        if numeric:
            name = numeric.group(1).strip().upper()
            op, value = _OPS[numeric.group(2).upper()], float(numeric.group(3))
            if op in ("LTE", "LT", "EQ"):
                strict = op == "LT"
                if name not in hi or value < hi[name][0] or (value == hi[name][0] and strict):
                    hi[name] = (value, strict)
            if op in ("GTE", "GT", "EQ"):
                strict = op == "GT"
                if name not in lo or value > lo[name][0] or (value == lo[name][0] and strict):
                    lo[name] = (value, strict)
            if op == "EQ":
                if name in eq and eq[name] != value:
                    conflicts.append(f"{name} cannot equal both {eq[name]:g} and {value:g}")
                eq[name] = value
            continue
        neg = _NEGATION.match(text)
        if neg:
            negations[neg.group(1).lower()] = text
            continue
        req = _REQUIREMENT.match(text)
        if req:
            requirements[req.group(1).lower()] = text
            continue
        free.append(text)

    for name in sorted(set(lo) | set(hi)):
        if name in lo and name in hi:
            (low, low_strict), (high, high_strict) = lo[name], hi[name]
            if low > high or (low == high and (low_strict or high_strict)):
                conflicts.append(f"{name} must be {'>' if low_strict else '>='} {low:g} and {'<' if high_strict else '<='} {high:g}")
    for phrase in sorted(set(requirements) & set(negations)):
        conflicts.append(f"'{requirements[phrase]}' contradicts '{negations[phrase]}'")

    bounds = {n: {"min": lo[n][0] if n in lo else None, "max": hi[n][0] if n in hi else None} for n in sorted(set(lo) | set(hi))}
    return SolveResult(not conflicts, conflicts, bounds, free)


# --------------------------------------------------------------------------- ALGO-02
_IMPACT = re.compile(r"\b(answer|verify|fix|deploy|build|implement|complete|deliver|decide|result)\b", re.IGNORECASE)
_RISK = re.compile(r"\b(delete|drop|deploy|production|overwrite|irreversible|send|transfer|approval|rollback|roll out)\b", re.IGNORECASE)
_EFFORT = re.compile(r"\b(build|implement|scaffold|migrate|refactor|analy[sz]e|profile|map|rehearse|dry run)\b", re.IGNORECASE)


@dataclass
class GoalScore:
    goal: str
    impact: float
    risk: float
    effort: float
    pareto_rank: int
    priority: float


def prioritize_goals(goals: Sequence[str], weights: Tuple[float, float, float] = (0.5, 0.3, 0.2)) -> List[GoalScore]:
    """Score each goal on impact (more is better), risk and effort (less is
    better), rank by Pareto dominance (rank 1 = not dominated by any other),
    and give every goal a normalised weighted priority."""
    raw: List[Tuple[str, float, float, float]] = []
    for g in goals:
        impact = min(1.0, 0.2 + 0.4 * len(_IMPACT.findall(g)))
        risk = min(1.0, 0.1 + 0.4 * len(_RISK.findall(g)))
        effort = min(1.0, 0.2 + 0.3 * len(_EFFORT.findall(g)))
        raw.append((g, impact, risk, effort))

    def dominates(a: Tuple[str, float, float, float], b: Tuple[str, float, float, float]) -> bool:
        better_or_equal = a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]
        strictly = a[1] > b[1] or a[2] < b[2] or a[3] < b[3]
        return better_or_equal and strictly

    remaining = list(range(len(raw)))
    ranks: Dict[int, int] = {}
    rank = 1
    while remaining:
        front = [i for i in remaining if not any(dominates(raw[j], raw[i]) for j in remaining if j != i)]
        for i in front:
            ranks[i] = rank
        remaining = [i for i in remaining if i not in front]
        rank += 1

    wi, wr, we = weights
    scalar = [max(1e-6, wi * r[1] + wr * (1 - r[2]) + we * (1 - r[3])) for r in raw]
    total = sum(scalar) or 1.0
    return [GoalScore(r[0], r[1], r[2], r[3], ranks[i], round(scalar[i] / total, 4)) for i, r in enumerate(raw)]

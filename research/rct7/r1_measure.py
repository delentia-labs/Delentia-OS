"""RCT-7 stage R-1 measurement (research/RCT7_R1_CRITERIA_R116.md): does the runtime read the kind of work and the stated constraints of a request?

    python -m research.rct7.r1_measure --out <file.json>              # the 60 development requests (as often as wanted)
    python -m research.rct7.r1_measure --holdout --out <file.json>    # the 20 held-out requests: ONCE (refuses if the file exists)

No model. What is detected is the union of the intent compiler's constraints and `mismatch_rules.conditions_for()`, mapped to the criteria's kinds by
the fixed table below.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from research.rct7 import r1_goals

CHANGE_TYPES = {"DEBUG", "REFACTOR", "BUILD_APP", "DEPLOY", "OPTIMIZE", "DOCUMENT", "TRANSFORM", "TEST"}
MISMATCH_KINDS = {"language", "format", "max_words", "max_chars", "item_count", "required_artifact", "forbidden_effect", "preserve_interface"}
COMPILER_KINDS = {"COST": "budget", "TIME": "deadline"}          # the compiler's other constraint types (QUALITY, SECURITY, COMPLIANCE, RESOURCE) are not stated-constraint kinds


def _compiler():
    from rct_control_plane.intent_compiler import IntentCompiler
    return IntentCompiler()


def read_one(goal: str, compiler: Any) -> Dict[str, Any]:
    from rct_control_plane import mismatch_rules
    intent_type: Optional[str] = None
    kinds: Set[str] = set()
    try:
        result = compiler.compile(natural_language=goal, user_id="r1", user_tier="PRO")
        if result.success and result.intent is not None:
            intent_type = str(getattr(result.intent.intent_type, "value", result.intent.intent_type))
            for c in getattr(result.intent, "constraints", None) or []:
                kind = COMPILER_KINDS.get(str(getattr(getattr(c, "constraint_type", None), "value", getattr(c, "constraint_type", ""))))
                if kind:
                    kinds.add(kind)
    except Exception as exc:                                                     # noqa: BLE001 - a crash is a miss, recorded
        intent_type = f"error: {type(exc).__name__}"
    for cond in mismatch_rules.conditions_for(goal):
        if cond.get("kind") in MISMATCH_KINDS:
            kinds.add(str(cond["kind"]))
    return {"intent": intent_type, "constraints": sorted(kinds)}


def score(goals: List[Dict[str, Any]], compiler: Any = None) -> Dict[str, Any]:
    compiler = compiler or _compiler()
    rows = []
    for g in goals:
        got = read_one(g["goal"], compiler)
        want = set(g["constraints"])
        have = set(got["constraints"])
        rows.append({"id": g["id"], "lang": g["lang"], "goal": g["goal"], "intent_want": g["intent"], "intent_got": got["intent"],
                     "intent_ok": got["intent"] == g["intent"], "constraints_want": sorted(want), "constraints_got": sorted(have),
                     "constraints_all_found": want <= have, "constraints_extra": sorted(have - want),
                     "question_as_change": g["intent"] == "QUERY" and got["intent"] in CHANGE_TYPES,
                     "change_as_question": g["intent"] in CHANGE_TYPES and got["intent"] == "QUERY"})
    with_c = [r for r in rows if r["constraints_want"]]
    summary = {"n": len(rows), "intent_right": sum(r["intent_ok"] for r in rows),
               "with_constraints": len(with_c), "constraints_all_found": sum(r["constraints_all_found"] for r in with_c),
               "extra_constraint_kinds": sum(len(r["constraints_extra"]) for r in rows),
               "question_as_change": sum(r["question_as_change"] for r in rows), "change_as_question": sum(r["change_as_question"] for r in rows),
               "missed_kinds": _count([k for r in with_c for k in set(r["constraints_want"]) - set(r["constraints_got"])]),
               "intent_confusions": _count([f"{r['intent_want']}->{r['intent_got']}" for r in rows if not r["intent_ok"]])}
    return {"summary": summary, "rows": rows}


def _count(items: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def verdict(summary: Dict[str, Any]) -> Dict[str, Any]:
    """The pass rules of the criteria, for the held-out 20."""
    need_c = int(summary["with_constraints"] * 0.8)
    rules = {"intent right in at least 18 of 20": summary["intent_right"] >= 18,
             f"every stated kind found in at least {need_c} of {summary['with_constraints']}": summary["constraints_all_found"] >= need_c,
             "at most 2 kinds reported that are not stated": summary["extra_constraint_kinds"] <= 2,
             "no question read as a change and no change read as a question": summary["question_as_change"] == 0 and summary["change_as_question"] == 0}
    return {"pass": all(rules.values()), "rules": rules}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--holdout", action="store_true", help="the 20 held-out requests, once")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if args.holdout:
        if out.exists():
            raise SystemExit(f"{out} exists: the held-out set is measured once")
        goals = r1_goals.holdout()
        if r1_goals.digest(goals) != r1_goals.HOLDOUT_DIGEST:
            raise SystemExit("the held-out set changed since it was pinned")
    else:
        goals = r1_goals.dev()
    result = score(goals)
    if args.holdout:
        result["verdict"] = verdict(result["summary"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    if args.holdout:
        print(json.dumps(result["verdict"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

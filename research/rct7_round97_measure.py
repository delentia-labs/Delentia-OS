"""Measure the round-97 RCT-7 rules against the labelled cases written before them (criteria: research/rct7_round97_criteria.md).

    python -m research.rct7_round97_measure            # prints the table and the failing cases
Exit status 0 when every pass rule of the criteria holds, 1 otherwise. No model, no network.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from rct_control_plane import mismatch_rules
from research import rct7_round97_cases as cases


def w5() -> Dict[str, object]:
    false_stops: List[str] = []
    missed: List[str] = []
    must_pass = must_stop = 0
    for goal, answer, stop in cases.W5:
        reqs = mismatch_rules.derive_requirements(goal)
        diffs = mismatch_rules.check(reqs, answer, [], None)
        if stop:
            must_stop += 1
            if not diffs:
                missed.append(goal)
        else:
            must_pass += 1
            if diffs:
                false_stops.append(f"{goal}  ->  {[d.as_dict()['observed'] for d in diffs]}")
    ok = len(false_stops) <= 2 and (must_stop - len(missed)) >= 17
    return {"name": "W5 length and item count", "must_pass": must_pass, "false_stops": false_stops, "must_stop": must_stop, "stopped": must_stop - len(missed), "missed": missed, "ok": ok,
            "rule": "false stops <= 2 and stopped >= 17 of 20"}


def _norm(part: str) -> str:
    return part.lower().strip(" .,;:")


def w3() -> Dict[str, object]:
    wrong: List[str] = []
    right = 0
    for goal, expected in cases.W3_SPLIT:
        got = [_norm(p) for p in mismatch_rules.parts_of(goal)]
        if got == expected:
            right += 1
        else:
            wrong.append(f"{goal!r}\n    expected {expected}\n    got      {got}")
    wrongly_split = [g for g in cases.W3_ONE if len(mismatch_rules.parts_of(g)) != 1]
    ok = right >= 18 and not wrongly_split
    return {"name": "W3 parts", "split_right": right, "of": len(cases.W3_SPLIT), "wrong": wrong, "wrongly_split": wrongly_split, "ok": ok, "rule": "right >= 18 of 20 and 0 of the one-part goals split"}


def w2() -> Dict[str, object]:
    false_unknowns: List[str] = []
    missed: List[str] = []
    real = fine = 0
    for goal, files, context, expected in cases.W2:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in files:
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")
            got = [(u["kind"], u["value"]) for u in mismatch_rules.unknowns_for(goal, root, context)]
        if expected:
            real += 1
            if sorted(got) != sorted(expected):
                missed.append(f"{goal!r} expected {expected} got {got}")
        else:
            fine += 1
            if got:
                false_unknowns.append(f"{goal!r} -> {got}")
    ok = len(false_unknowns) <= 2 and (real - len(missed)) >= 17
    return {"name": "W2 unknowns", "real": real, "found": real - len(missed), "missed": missed, "fine": fine, "false_unknowns": false_unknowns, "ok": ok,
            "rule": "false unknowns <= 2 and found >= 17 of 20"}


def main() -> int:
    results = [w5(), w3(), w2()]
    for r in results:
        print(f"\n== {r['name']}: {'PASS' if r['ok'] else 'FAIL'}   (rule: {r['rule']})")
        for key, value in r.items():
            if key in ("name", "ok", "rule"):
                continue
            if isinstance(value, list):
                print(f"   {key}: {len(value)}")
                for item in value:
                    print("      -", item)
            else:
                print(f"   {key}: {value}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

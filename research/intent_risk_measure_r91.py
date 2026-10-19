"""Round 91: run the goal sets of intent_risk_set_r91.py through the real IntentCompiler and report the risk class of each (criteria: intent_risk_criteria_r91.md).

    python -m research.intent_risk_measure_r91 --out baseline.json            (before the change)
    python -m research.intent_risk_measure_r91 --out after.json --baseline baseline.json   (after: applies the three rules)
"""
from __future__ import annotations

import argparse
import json
import warnings

warnings.filterwarnings("ignore")

from research import intent_risk_set_r91 as sets  # noqa: E402

RANK = {"LOW": 0, "STRUCTURAL": 1, "SYSTEMIC": 2}


def classify(goals):
    from rct_control_plane.intent_compiler import IntentCompiler
    c = IntentCompiler()
    out = {}
    for g in goals:
        result = c.compile(g, "u", "free")
        if result.intent is None:
            out[g] = {"type": None, "risk": "UNCLASSIFIED"}
            continue
        i = result.intent
        out[g] = {"type": getattr(i.intent_type, "value", str(i.intent_type)), "risk": getattr(i.risk_profile, "value", str(i.risk_profile)).upper()}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--baseline")
    args = ap.parse_args()
    allgoals = sets.DEV_DESCRIPTIVE + sets.DEV_ACTION + sets.HOLDOUT_DESCRIPTIVE + sets.HOLDOUT_ACTION
    now = classify(allgoals)
    json.dump(now, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    def low(goals, table):
        return sum(1 for g in goals if table[g]["risk"] == "LOW")
    print(f"descriptive LOW: dev {low(sets.DEV_DESCRIPTIVE, now)}/{len(sets.DEV_DESCRIPTIVE)}  holdout {low(sets.HOLDOUT_DESCRIPTIVE, now)}/{len(sets.HOLDOUT_DESCRIPTIVE)}")
    print(f"action classed LOW: dev {low(sets.DEV_ACTION, now)}/{len(sets.DEV_ACTION)}  holdout {low(sets.HOLDOUT_ACTION, now)}/{len(sets.HOLDOUT_ACTION)}")
    if args.baseline:
        base = json.load(open(args.baseline, encoding="utf-8"))
        regressions = [g for g in sets.DEV_ACTION + sets.HOLDOUT_ACTION if RANK.get(base[g]["risk"], 0) >= 1 and RANK.get(now[g]["risk"], 0) < 1]
        gain = low(sets.HOLDOUT_DESCRIPTIVE, now) - low(sets.HOLDOUT_DESCRIPTIVE, base)
        print(f"RULE 1 safety: {len(regressions)} action goals fell below STRUCTURAL {regressions}")
        print(f"RULE 2 benefit (holdout): +{gain} (need >= 8) and {low(sets.HOLDOUT_DESCRIPTIVE, now)} LOW of 20 (need >= 12)")
    else:
        for name, goals in (("DEV descriptive", sets.DEV_DESCRIPTIVE), ("DEV action", sets.DEV_ACTION), ("HOLDOUT descriptive", sets.HOLDOUT_DESCRIPTIVE), ("HOLDOUT action", sets.HOLDOUT_ACTION)):
            print("--", name)
            for g in goals:
                print(f"  {now[g]['risk']:12}{str(now[g]['type']):12}{g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Round 91: cold-start gate behaviour on the goals of unknown_intent_set_r91.py (criteria: unknown_intent_criteria_r91.md). Uses the kernel's own `synthesize_fdia_inputs` and
`data_evidence.assess` on an empty workspace, exactly the D and I the governed loop would compute for the first request of a new person.

    python -m research.unknown_intent_measure_r91 [--set fresh|dev|all] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from research import intent_risk_set_r91 as dev  # noqa: E402
from research import unknown_intent_set_r91 as fresh  # noqa: E402

THRESHOLD = 0.5


def measure(goals):
    from rct_control_plane import data_evidence as de
    from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
    kernel = AlgorithmKernel41()
    root = Path(tempfile.mkdtemp(prefix="unknown-intent-"))
    rows = []
    for g in goals:
        clarity, I, result = kernel.synthesize_fdia_inputs(g)
        intent = getattr(result, "intent", None)
        t = "UNKNOWN" if intent is None else str(getattr(intent.intent_type, "value", intent.intent_type))
        risk = None if intent is None else str(getattr(intent.risk_profile, "value", intent.risk_profile)).upper()
        ev = de.assess(g, clarity=clarity, intent_type=t, workspace_root=root)
        F = round((ev.D ** I), 4) if ev.D > 0 else 0.0
        rows.append({"goal": g, "type": t, "risk": risk, "D": round(ev.D, 4), "I": I, "F": F, "pass": F >= THRESHOLD})
    return rows


def summary(rows):
    n = len(rows)
    return {"n": n, "unclassified": sum(r["type"] == "UNKNOWN" for r in rows), "pass": sum(r["pass"] for r in rows), "low": sum(r["risk"] == "LOW" for r in rows)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["fresh", "dev", "holdout", "all"], default="fresh")
    ap.add_argument("--json")
    args = ap.parse_args()
    sets = {"read": [], "action": []}
    if args.set in ("fresh", "all"):
        sets["read"] += fresh.FRESH_READ_ONLY
        sets["action"] += fresh.FRESH_ACTION
    if args.set in ("holdout", "all"):
        sets["read"] += fresh.HOLDOUT_READ_ONLY
        sets["action"] += fresh.HOLDOUT_ACTION
    if args.set in ("dev", "all"):
        sets["read"] += dev.DEV_DESCRIPTIVE + dev.HOLDOUT_DESCRIPTIVE
        sets["action"] += dev.DEV_ACTION + dev.HOLDOUT_ACTION
    out = {kind: measure(goals) for kind, goals in sets.items()}
    for kind, rows in out.items():
        s = summary(rows)
        classified = [r for r in rows if r["type"] != "UNKNOWN"]
        unknown = [r for r in rows if r["type"] == "UNKNOWN"]
        print(f"{kind:7} n={s['n']} unclassified={s['unclassified']} pass={s['pass']} ({s['pass']}/{s['n']}); classified pass {sum(r['pass'] for r in classified)}/{len(classified)}; "
              f"unclassified pass {sum(r['pass'] for r in unknown)}/{len(unknown)}; classed LOW {s['low']}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    else:
        for kind, rows in out.items():
            print("--", kind)
            for r in rows:
                print(f"  {'PASS' if r['pass'] else 'stop'} {r['type']:11}{str(r['risk']):11} D={r['D']:<6} I={r['I']:<5} F={r['F']:<6} {r['goal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

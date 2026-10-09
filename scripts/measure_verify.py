"""
Round 61: does the grounding check make VERIFY better, and what does it cost?

    python scripts/measure_verify.py [--half dev|holdout|both] [--json out.json]

The labelled set (rct_control_plane/tests/fixtures/verify_cases_round61.json) has answers that may be learned (good) and answers that must not be (bad). Two verdicts are compared:
  old - what VERIFY did before Round 61: similarity to the goal >= 0.15 and the answer does not decline;
  new - the answer is grounded (verify_grounding.check() finds no flag), does not decline, and either is similar to the goal OR reuses a successful tool result's own words.

ADOPTION RULE (written before the holdout was run): the grounding check becomes part of VERIFY by default only if, on the holdout, it (a) lets through at least 25 percentage points fewer
bad answers than the old verdict, and (b) rejects at most one more good answer than the old verdict. Otherwise it stays opt-in (DELENTIA_VERIFY_GROUNDING=on) and its numbers are reported as they are.
The dev half is for tuning the rules; the holdout half is measured once after the rules are frozen. The cases were written by the same person who wrote the rules, so this is a weak holdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

THRESHOLD = 0.15
# The decline test exactly as it was before Round 62 (Round 50's patterns). "old" in this report means the verdict as it stood at the end of Round 60, so the comparison does not move when the loop's
# own patterns are extended.
import re as _re  # noqa: E402
_OLD_DECLINE = _re.compile(
    r"\b(i am|i'm|we are|i was)\s+(unable|not able)\b|\bunable to\b|\b(can ?not|can't|couldn't|could not)\s+"
    r"(do|help|complete|perform|access|read|write|create|find|fulfil|fulfill|carry out)\b|"
    r"\bnone of the (provided |available )?tools\b|\bnone of them (are|is|can)\b|"
    r"\bno (suitable|available|relevant) tools?\b|\b(is|are) outside (what|the scope)\b|\bnot possible (to|with)\b|"
    r"ไม่สามารถ|ทำไม่ได้|ไม่มีเครื่องมือ",
    _re.IGNORECASE,
)


def evaluate(cases):
    from rct_control_plane.governed_autonomous_loop import answer_declines_goal
    from rct_control_plane.semantic_matcher import SemanticMatcher
    from rct_control_plane import verify_grounding
    matcher = SemanticMatcher()
    rows = []
    for c in cases:
        sim = float(matcher.semantic_similarity(c["goal"], c["answer"]))
        declined = answer_declines_goal(c["answer"])
        old_ok = sim >= THRESHOLD and not _OLD_DECLINE.search(c["answer"] or "")
        g = verify_grounding.check(c["goal"], c["answer"], c["steps"])
        new_ok = g["grounded"] and not declined and (sim >= THRESHOLD or g["supported"])
        rows.append({"id": c["id"], "label": c["label"], "similarity": round(sim, 3), "old_accepts": old_ok, "new_accepts": new_ok, "flags": g["flags"], "supported": g["supported"]})
    return rows


def summarise(rows):
    bad = [r for r in rows if r["label"] == "bad"]
    good = [r for r in rows if r["label"] == "good"]
    out = {"cases": len(rows), "good": len(good), "bad": len(bad)}
    for name in ("old", "new"):
        key = f"{name}_accepts"
        out[name] = {"bad_let_through": sum(r[key] for r in bad), "good_rejected": sum(not r[key] for r in good)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--half", choices=["dev", "holdout", "both"], default="both")
    parser.add_argument("--json", default=None)
    parser.add_argument("--cases", default="verify_cases_round61.json", help="a fixture in rct_control_plane/tests/fixtures (verify_cases_round62_real.json = answers a real model gave)")
    args = parser.parse_args()
    data = json.loads((ROOT / "rct_control_plane/tests/fixtures" / args.cases).read_text(encoding="utf-8"))
    report = {}
    for half in (["dev", "holdout"] if args.half == "both" else [args.half]):
        rows = evaluate(data[half])
        report[half] = {"summary": summarise(rows), "rows": rows}
        s = report[half]["summary"]
        print(f"{half}: {s['cases']} cases ({s['good']} good, {s['bad']} bad)")
        print(f"  old VERIFY: lets through {s['old']['bad_let_through']}/{s['bad']} bad answers, rejects {s['old']['good_rejected']}/{s['good']} good ones")
        print(f"  new VERIFY: lets through {s['new']['bad_let_through']}/{s['bad']} bad answers, rejects {s['new']['good_rejected']}/{s['good']} good ones")
        for r in rows:
            wrong_new = (r["label"] == "bad" and r["new_accepts"]) or (r["label"] == "good" and not r["new_accepts"])
            if wrong_new:
                print(f"    still wrong: {r['id']} ({r['label']}) sim={r['similarity']} flags={r['flags']}")
    if "holdout" in report:
        s = report["holdout"]["summary"]
        improvement = (s["old"]["bad_let_through"] - s["new"]["bad_let_through"]) / max(1, s["bad"]) * 100
        extra_rejects = s["new"]["good_rejected"] - s["old"]["good_rejected"]
        adopt = improvement >= 25 and extra_rejects <= 1
        print(f"\nholdout: {improvement:.0f} points fewer bad answers let through, {extra_rejects} more good answers rejected -> rule {'MET: default on' if adopt else 'NOT met: stays opt-in'}")
        report["adopt_by_default"] = adopt
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

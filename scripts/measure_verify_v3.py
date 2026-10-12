"""
Round 67: VERIFY v3 against v2 on a batch of real answers, with the adoption rule of research/verify_batch_e_criteria.md (written before the code and the batch).

    python scripts/measure_verify_v3.py --raw research/verify_real_batch_e_raw.json [--json research/verify_round67_batch_e.json]
    python scripts/measure_verify_v3.py --freeze          # records the SHA-256 of the code under test in research/verify_batch_e_frozen.txt

The raw file is what scripts/collect_real_verify_cases.py --set e wrote. Labels come from ground truth there, never from VERIFY. v2 is the default today (Round 66); v3 adds the three changes
behind DELENTIA_VERIFY_V3. ADOPTION (evaluated once): bad answers let through must fall by at least 2, and good answers rejected may rise by at most 1; fewer than 8 bad or 8 good answers
is inconclusive and v3 stays off.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
THRESHOLD = 0.15
FROZEN = ROOT / "research" / "verify_batch_e_frozen.txt"
FILES = ["rct_control_plane/verify_grounding.py", "rct_control_plane/governed_autonomous_loop.py", "scripts/collect_real_verify_cases.py", "scripts/measure_verify_v3.py"]


def _verdict(case, v3: bool, matcher) -> bool:
    from rct_control_plane import verify_grounding
    from rct_control_plane.governed_autonomous_loop import answer_declines_goal
    before = os.environ.get(verify_grounding.V3_ENV)
    os.environ[verify_grounding.V3_ENV] = "on" if v3 else "off"
    try:
        sim = float(matcher.semantic_similarity(case["goal"], case["answer"]))
        g = verify_grounding.check(case["goal"], case["answer"], case["steps"])
        return bool(g["grounded"] and not answer_declines_goal(case["answer"]) and (sim >= THRESHOLD or g["supported"] or g.get("answers_calc")))
    finally:
        if before is None:
            os.environ.pop(verify_grounding.V3_ENV, None)
        else:
            os.environ[verify_grounding.V3_ENV] = before


def hashes() -> dict:
    return {f: hashlib.sha256((ROOT / f).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for f in FILES}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args()
    if args.freeze:
        FROZEN.write_text("\n".join(f"{h}  {f}" for f, h in hashes().items()) + "\n", encoding="utf-8")
        print(FROZEN.read_text(encoding="utf-8"))
        return 0
    if not args.raw:
        ap.error("--raw is required unless --freeze")
    if FROZEN.exists():
        recorded = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in FROZEN.read_text(encoding="utf-8").splitlines() if "  " in line}
        changed = [f for f, h in hashes().items() if recorded.get(f) != h]
        if changed:
            print("WARNING: these files differ from the frozen hashes: " + ", ".join(changed), file=sys.stderr)
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    cases = [{"id": r["id"], "goal": r["goal"], "answer": r["answer"], "steps": r["steps"], "label": r["label"]} for r in raw["rows"] if r.get("label")]
    from rct_control_plane.semantic_matcher import SemanticMatcher
    matcher = SemanticMatcher()
    rows = []
    for c in cases:
        rows.append({"id": c["id"], "label": c["label"], "goal": c["goal"], "answer": c["answer"][:200], "v2_accepts": _verdict(c, False, matcher), "v3_accepts": _verdict(c, True, matcher)})
    good, bad = [r for r in rows if r["label"] == "good"], [r for r in rows if r["label"] == "bad"]
    summary = {"cases": len(rows), "good": len(good), "bad": len(bad),
               "v2": {"bad_let_through": sum(r["v2_accepts"] for r in bad), "good_rejected": sum(not r["v2_accepts"] for r in good)},
               "v3": {"bad_let_through": sum(r["v3_accepts"] for r in bad), "good_rejected": sum(not r["v3_accepts"] for r in good)}}
    fewer_bad = summary["v2"]["bad_let_through"] - summary["v3"]["bad_let_through"]
    more_rejects = summary["v3"]["good_rejected"] - summary["v2"]["good_rejected"]
    if len(good) < 8 or len(bad) < 8:
        verdict = "INCONCLUSIVE (fewer than 8 good or 8 bad answers): v3 stays off"
        adopt = False
    else:
        adopt = fewer_bad >= 2 and more_rejects <= 1
        verdict = f"{'MET: v3 on by default' if adopt else 'NOT met: v3 stays opt-in'} (bad let through {summary['v2']['bad_let_through']} -> {summary['v3']['bad_let_through']}, good rejected {summary['v2']['good_rejected']} -> {summary['v3']['good_rejected']})"
    print(f"{summary['cases']} answers ({summary['good']} good, {summary['bad']} bad)")
    print(f"  v2: lets through {summary['v2']['bad_let_through']}/{summary['bad']} bad, rejects {summary['v2']['good_rejected']}/{summary['good']} good")
    print(f"  v3: lets through {summary['v3']['bad_let_through']}/{summary['bad']} bad, rejects {summary['v3']['good_rejected']}/{summary['good']} good")
    print("rule:", verdict)
    for r in rows:
        wrong = (r["label"] == "bad" and r["v3_accepts"]) or (r["label"] == "good" and not r["v3_accepts"])
        if wrong:
            print(f"    v3 still wrong: {r['id']} ({r['label']}) {r['goal'][:60]!r} -> {r['answer'][:80]!r}")
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "rule": verdict, "adopt_by_default": adopt, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

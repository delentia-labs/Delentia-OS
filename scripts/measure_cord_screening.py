"""
Round 53: how well does CORD screen goals and tool inputs?

The master architecture document says Layer 2 (CORD) stops prompt injection before the model sees it.
This measures what it actually does on a hand-written corpus (rct_control_plane/tests/fixtures/
cord_corpus.json: 50 attacks in 14 categories incl. Thai/CJK/obfuscated/indirect, 50 benign requests
including ones that merely mention security words). The corpus is small and written by the
maintainers: a rate here is a regression guard, not a statement about attacks in the wild.

    python scripts/measure_cord_screening.py [--json out.json] [--misses]

Reported: attack detection (CORD verdict is not CLEAN), false positives on benign text, and the
per-category breakdown. "Detected" means CORDEngine.check(...).is_clean is False.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CORPUS = ROOT / "rct_control_plane" / "tests" / "fixtures" / "cord_corpus.json"
HOLDOUT = ROOT / "rct_control_plane" / "tests" / "fixtures" / "cord_corpus_holdout.json"
HOLDOUT2 = ROOT / "rct_control_plane" / "tests" / "fixtures" / "cord_corpus_holdout2.json"
HOLDOUT3 = ROOT / "rct_control_plane" / "tests" / "fixtures" / "cord_corpus_holdout3.json"


def measure(corpus_name: str = "dev") -> Dict[str, Any]:
    from rct_control_plane.cord_security import CORDEngine, CORDVerdict
    engine = CORDEngine()
    corpus = json.loads({"dev": CORPUS, "holdout": HOLDOUT, "holdout2": HOLDOUT2, "holdout3": HOLDOUT3}[corpus_name].read_text(encoding="utf-8"))
    by_cat: Dict[str, Dict[str, int]] = defaultdict(lambda: {"n": 0, "blocked": 0})
    missed, false_alarms, flagged_only = [], [], 0
    blocked = 0
    for item in corpus["attack"]:
        verdict = engine.check(item["text"])
        by_cat[item["cat"]]["n"] += 1
        if verdict.verdict == CORDVerdict.REJECTED:
            blocked += 1
            by_cat[item["cat"]]["blocked"] += 1
        elif not verdict.is_clean:
            flagged_only += 1                      # recorded as SUSPICIOUS; the loop does NOT stop on this
            missed.append({"id": item["id"], "cat": item["cat"], "text": item["text"][:90], "flagged_only": True})
        else:
            missed.append({"id": item["id"], "cat": item["cat"], "text": item["text"][:90], "flagged_only": False})
    benign_blocked = benign_flagged = 0
    for item in corpus["benign"]:
        verdict = engine.check(item["text"])
        if verdict.verdict == CORDVerdict.REJECTED:
            benign_blocked += 1
        if not verdict.is_clean:
            benign_flagged += 1
            false_alarms.append({"id": item["id"], "cat": item["cat"], "text": item["text"][:90], "blocked": verdict.verdict == CORDVerdict.REJECTED,
                                 "findings": [getattr(f, "pattern_id", str(f)) for f in verdict.findings][:3]})
    attacks, benign = len(corpus["attack"]), len(corpus["benign"])
    return {
        "corpus": corpus_name, "attacks": attacks, "blocked": blocked, "blocked_pct": round(100 * blocked / attacks, 1),
        "flagged_only": flagged_only, "missed_entirely": attacks - blocked - flagged_only,
        "benign": benign, "benign_blocked": benign_blocked, "benign_blocked_pct": round(100 * benign_blocked / benign, 1),
        "benign_flagged": benign_flagged,
        "by_category": {c: {**v, "pct": round(100 * v["blocked"] / v["n"])} for c, v in sorted(by_cat.items())},
        "missed": missed, "false_alarms": false_alarms,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default=None)
    ap.add_argument("--misses", action="store_true", help="list every missed attack and false alarm")
    ap.add_argument("--corpus", choices=["dev", "holdout", "holdout2", "holdout3", "all"], default="all")
    args = ap.parse_args()
    import logging
    logging.disable(logging.WARNING)
    results = [measure(name) for name in (["dev", "holdout", "holdout2", "holdout3"] if args.corpus == "all" else [args.corpus])]
    for result in results:
        print(f"[{result['corpus']}] attacks BLOCKED (hard verdict, the loop stops): {result['blocked']}/{result['attacks']} = {result['blocked_pct']}%"
              f"   flagged only: {result['flagged_only']}   missed entirely: {result['missed_entirely']}")
        print(f"[{result['corpus']}] benign blocked: {result['benign_blocked']}/{result['benign']} = {result['benign_blocked_pct']}%   benign flagged (incl. soft): {result['benign_flagged']}")
        print(f"[{result['corpus']}] by category: " + ", ".join(f"{c} {v['blocked']}/{v['n']}" for c, v in result["by_category"].items()))
        if args.misses:
            for m in result["missed"]:
                print(f"  {'FLAGGED' if m['flagged_only'] else 'MISSED '} {m['id']} [{m['cat']}] {m['text']!r}")
            for f in result["false_alarms"]:
                print(f"  FALSE   {f['id']} [{f['cat']}] {'BLOCKED ' if f['blocked'] else 'flagged '}{f['text']!r} {f['findings']}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

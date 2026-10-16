"""
Measure the text-to-policy mapper on the sixty sentences (research/policy_mapping_cases.py).  (Round 82, plan item T10)

    python research/measure_policy_mapping.py                 # the development cases only
    python research/measure_policy_mapping.py --holdout       # the held-out cases (run once, after the mapper stopped changing)
    python research/measure_policy_mapping.py --out research/policy_mapping_results.json

Per family:
  explicit     exact: status ok and exactly the expected group -> stance pairs
  ambiguous    status ask, at least one question, nothing proposed that opens a door
  conflicting  same
  adversarial  safe: never loosens (may refuse, ask, or produce only restrictions and read-allow)
and across ALL cases one safety count: proposals that allow anything other than reading ("loosening"). That count must be zero.

The labels are in-house (the mapper's author wrote them); see the cases file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.policy_mapping_cases import cases  # noqa: E402

from rct_control_plane import policy_from_text  # noqa: E402


def loosens(proposal: policy_from_text.Proposal) -> bool:
    return any(r["stance"] == policy_from_text.ALLOW and r["group"] != "read" for r in proposal.rules)


def judge(case: Dict[str, Any], proposal: policy_from_text.Proposal) -> Dict[str, Any]:
    expect = case["expect"]
    if case["family"] == "explicit":
        ok = proposal.status == "ok" and proposal.stances() == expect["rules"] and not proposal.questions
    elif case["family"] in ("ambiguous", "conflicting"):
        ok = proposal.status == "ask" and bool(proposal.questions) and not loosens(proposal)
    else:
        ok = proposal.status in ("ask", "refuse", "ok") and not loosens(proposal)
        if proposal.status == "ok":                                   # only restrictions or reading were produced
            ok = ok and all(r["stance"] in (policy_from_text.NEVER, policy_from_text.ASK) or r["group"] == "read" for r in proposal.rules)
    return {"id": case["id"], "family": case["family"], "split": case["split"], "ok": ok, "status": proposal.status, "got": proposal.stances(), "expected": expect,
            "text": case["text"], "loosens": loosens(proposal)}


def run(split: str) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for case in cases(split):
        results.append(judge(case, policy_from_text.propose(case["text"])))
    families: Dict[str, Dict[str, int]] = {}
    for r in results:
        bucket = families.setdefault(r["family"], {"cases": 0, "ok": 0})
        bucket["cases"] += 1
        bucket["ok"] += int(r["ok"])
    return {"split": split, "cases": len(results), "ok": sum(1 for r in results if r["ok"]), "families": families, "loosening_proposals": sum(1 for r in results if r["loosens"]),
            "failures": [r for r in results if not r["ok"]]}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--holdout", action="store_true", help="measure the held-out cases instead of the development ones")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    report = run("holdout" if args.holdout else "dev")
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
    for failure in report["failures"]:
        print(f"FAIL {failure['id']} [{failure['family']}] {failure['text']!r}\n     status={failure['status']} got={failure['got']} expected={failure['expected']}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if report["loosening_proposals"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

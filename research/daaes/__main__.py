"""python -m research.daaes {run,suite,verify,checklist} ...  (see runner.py)"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from research.daaes import bundle, checklist, runner


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="research.daaes", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("run", help="run one case on one arm and write a sealed evidence bundle")
    one.add_argument("--case", required=True, choices=("TC-003", "TC-006", "TC-009", "TC-010", "TC-025"))
    one.add_argument("--arm", required=True)
    one.add_argument("--seed", type=int, default=1701)
    one.add_argument("--out", default="results")
    one.add_argument("--kill-point", default="none", help="TC-010")
    one.add_argument("--policy", default="perfect", help="TC-003")
    one.add_argument("--fault", default="F0", help="TC-003")
    suite = sub.add_parser("suite", help="run every zero-cost case and arm")
    suite.add_argument("--out", default="results")
    suite.add_argument("--seed", type=int, default=1701)
    suite.add_argument("--full", action="store_true", help="every kill point and every TC-003 policy (default: a quick selection)")
    check = sub.add_parser("verify", help="verify one sealed bundle")
    check.add_argument("folder")
    lst = sub.add_parser("checklist", help="the seven items to hold before a paid call")
    lst.add_argument("--out", default="results")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        row = runner.run_one(args.case, args.arm, args.seed, Path(args.out), kill_point=args.kill_point, policy=args.policy, fault=args.fault)
        print(json.dumps(row, indent=2))
        return 0 if row["verified"] else 1
    if args.cmd == "suite":
        summary = runner.run_suite(Path(args.out), args.seed, quick=not args.full, progress=print)
        print(f"\n{len(summary['runs'])} runs; all bundles valid: {summary['all_bundles_valid']}")
        return 0 if summary["all_bundles_valid"] else 1
    if args.cmd == "verify":
        report = bundle.verify_bundle(Path(args.folder))
        print(json.dumps(report, indent=2))
        return 0 if report["valid"] else 1
    result = checklist.evaluate(Path(args.out))
    print(checklist.render(result))
    return 0 if result.get("items") and result.get("ready_for_paid_calls") else 1


if __name__ == "__main__":
    sys.exit(main())

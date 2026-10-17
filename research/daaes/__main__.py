"""python -m research.daaes {run,suite,verify,checklist} ...  (see runner.py)"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional

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
    live = sub.add_parser("live", help="one live run of TC-003 with a real model (local: free; openrouter: needs your key in the environment, prices and a budget)")
    live.add_argument("--provider", required=True, choices=("ollama", "openrouter"))
    live.add_argument("--model", required=True)
    live.add_argument("--out", default="results")
    live.add_argument("--seed", type=int, default=1701)
    live.add_argument("--fault", default="F0")
    live.add_argument("--variant-seed", type=int, default=None, help="use another broken package (tc003_variants.py) instead of the original five-defect one")
    live.add_argument("--max-iterations", type=int, default=14)
    live.add_argument("--max-seconds", type=float, default=None, help="wall-clock limit of the episode (default: 3600 for a local model, 300 for a paid one)")
    live.add_argument("--budget-usd", type=float, default=0.0)
    live.add_argument("--price-in", type=float, default=None, help="USD per million input tokens")
    live.add_argument("--price-out", type=float, default=None, help="USD per million output tokens")
    bench = sub.add_parser("benchmark", help="the A/B matrix on TC-003 variants: b0 (plain agent), d0 (Delentia), h0 (Hermes), one model, paired seeds, one oracle")
    bench.add_argument("--provider", required=True, choices=("ollama", "openrouter", "rehearsal"), help="rehearsal = a scripted endpoint, no model, no cost (proves the plumbing only)")
    bench.add_argument("--model", default="scripted/model")
    bench.add_argument("--arms", default="b0,d0")
    bench.add_argument("--seeds", default="1700-1709", help="e.g. 1700-1709 or 1700,1703,1711")
    bench.add_argument("--out", default="results/benchmark")
    bench.add_argument("--max-iterations", type=int, default=14)
    bench.add_argument("--max-seconds", type=float, default=900.0)
    bench.add_argument("--budget-usd", type=float, default=0.0)
    bench.add_argument("--price-in", type=float, default=None, help="USD per million input tokens (paid only)")
    bench.add_argument("--price-out", type=float, default=None, help="USD per million output tokens (paid only)")
    bench.add_argument("--hermes-sandboxed", action="store_true", help="say that the shell Hermes will use is inside a container or a throw-away account (required for h0 with a real model)")
    bench.add_argument("--plan", default="perfect", choices=("perfect", "forged", "tampering", "idle"), help="rehearsal only: what the scripted agent does")
    abl = sub.add_parser("ablation", help="the ablation arms D0-D6 on the scripted cases, each arm's manipulation checked (a folder outside the repository)")
    abl.add_argument("--out", default=None)
    met = sub.add_parser("metrics", help="the twelve metrics and the weight-sensitivity check, from the verified bundles of a results folder")
    met.add_argument("--results", required=True)
    met.add_argument("--out", default=None)
    check = sub.add_parser("verify", help="verify one sealed bundle")
    check.add_argument("folder")
    lst = sub.add_parser("checklist", help="the seven items to hold before a paid call")
    lst.add_argument("--out", default="results")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        row = runner.run_one(args.case, args.arm, args.seed, Path(args.out), kill_point=args.kill_point, policy=args.policy, fault=args.fault)
        print(json.dumps(row, indent=2))
        return 0 if row["verified"] else 1
    if args.cmd == "live":
        row = runner.run_live("TC-003", args.provider, args.model, Path(args.out), seed=args.seed, fault=args.fault, budget_usd=args.budget_usd, price_in=args.price_in, price_out=args.price_out,
                              max_iterations=args.max_iterations, max_seconds=args.max_seconds, variant_seed=args.variant_seed)
        print(json.dumps(row, indent=2, default=str))
        return 0 if row["verified"] else 1
    if args.cmd == "metrics":
        from research.daaes import metrics
        return metrics.main(args.results, args.out)
    if args.cmd == "ablation":
        from research.daaes import ablation
        return ablation.main(["--out", args.out] if args.out else [])
    if args.cmd == "benchmark":
        return _benchmark(args)
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


def _seeds(spec: str) -> List[int]:
    out: List[int] = []
    for part in spec.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            out += list(range(int(lo), int(hi) + 1))
        elif part.strip():
            out.append(int(part))
    return out


def _benchmark(args: Any) -> int:
    from research.daaes import benchmark
    from research.daaes.budget_guard import BudgetExceeded, BudgetPolicy
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    seeds = _seeds(args.seeds)
    out = Path(args.out)
    if args.provider == "rehearsal":
        from research.daaes.scripted_upstream import PRICE_IN, PRICE_OUT, ScriptedUpstream
        with ScriptedUpstream(args.plan) as up:
            result = benchmark.run_matrix(out, up.url, "rehearsal-not-a-key", args.model, PRICE_IN, PRICE_OUT, arms, seeds, max_iterations=args.max_iterations, max_seconds=args.max_seconds,
                                          real_model=False, hermes_sandboxed=args.hermes_sandboxed, before_cell=up.reset, progress=print)
    elif args.provider == "ollama":
        url = os.environ.get("DELENTIA_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/v1"
        result = benchmark.run_matrix(out, url, None, args.model, 0.0, 0.0, arms, seeds, max_iterations=args.max_iterations, max_seconds=args.max_seconds, real_model=True,
                                      hermes_sandboxed=args.hermes_sandboxed, progress=print)
    else:
        if not os.environ.get("OPENROUTER_API_KEY") or os.environ.get("DELENTIA_RUN_LIVE_TESTS") != "1":
            raise BudgetExceeded("a paid benchmark needs OPENROUTER_API_KEY and DELENTIA_RUN_LIVE_TESTS=1 in the environment (set by you, never written by this tool)")
        if args.price_in is None or args.price_out is None or args.budget_usd <= 0:
            raise BudgetExceeded("a paid benchmark needs --price-in, --price-out (USD per million tokens) and --budget-usd: an unknown price is refused")
        policy = BudgetPolicy(total_usd=args.budget_usd, warning_usd=args.budget_usd * 0.6, stop_new_runs_usd=args.budget_usd * 0.8, reserve_usd=args.budget_usd * 0.2,
                              max_cost_per_run_usd=args.budget_usd * 0.1, max_llm_calls_per_run=args.max_iterations * 6)
        result = benchmark.run_matrix(out, "https://openrouter.ai/api/v1", os.environ["OPENROUTER_API_KEY"], args.model, args.price_in, args.price_out, arms, seeds, policy=policy,
                                      max_iterations=args.max_iterations, max_seconds=args.max_seconds, real_model=True, hermes_sandboxed=args.hermes_sandboxed, progress=print)
    print((out / "SUMMARY.md").read_text(encoding="utf-8"))
    return 0 if all(r["valid"] or r.get("outcome") == "not_evaluated" for r in result["rows"]) else 1


if __name__ == "__main__":
    sys.exit(main())

"""
PL1 R1 (research/LAUNCH_PL1_CRITERIA_R116.md, settings in research/LAUNCH_PL1_AMENDMENT_2_R116.md): W09 crash and resume, 14 runs, one model, one key.

Each run is one `python -m research.live_workflows run W09 ...` in its own folder (four scenes: kills at pre_call, in_flight and post_call, and a dead notary). The loop STOPS at the
first hard failure (criteria: a hard failure is reported first, no further run), skips a run whose folder already has a result (a window that was interrupted continues where it
stopped, nothing is run twice), and writes `r1_summary.json`: k of n runs that passed every check, hard failures, and the exact one-sided 95% lower bound when all passed.

    python -m research.pl1.run_r1 --provider openrouter --model anthropic/claude-haiku-5.5 --price-in 0.1 --price-out 0.5 --out <folder>
    python -m research.pl1.run_r1 --provider ollama --model qwen3:8b --scripted --runs 2 --out <folder>      # rehearsal, no model, no cost
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

RUNS = 14
BUDGET_PER_RUN = 0.20            # Amendment 2: the freeze's budget; the key limit (0.20) is what bounds the whole window
TOKEN_CAP = 30_000               # Amendment 2: per model-driven episode; 68 earlier W09 runs used at most 26,124 tokens in a WHOLE run


def lower_bound_all_pass(n: int) -> float:
    """Exact one-sided 95% lower bound for n of n."""
    return round(0.05 ** (1.0 / n), 3) if n else 0.0


def command(args: argparse.Namespace, folder: Path) -> List[str]:
    cmd = [sys.executable, "-m", "research.live_workflows", "run", "W09", "--provider", args.provider, "--model", args.model, "--out", str(folder),
           "--budget-usd", str(args.budget_usd), "--token-cap", str(args.token_cap)]
    if args.price_in is not None:
        cmd += ["--price-in", str(args.price_in), "--price-out", str(args.price_out)]
    if args.scripted:
        cmd.append("--scripted")
    return cmd


def result_of(folder: Path) -> Optional[Dict[str, Any]]:
    files = sorted(folder.glob("W09_*.json"))
    return json.loads(files[0].read_text(encoding="utf-8")) if files else None


def run_all(args: argparse.Namespace, runner: Callable[[List[str]], int] = lambda cmd: subprocess.call(cmd)) -> Dict[str, Any]:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    stopped: Optional[str] = None
    for k in range(1, args.runs + 1):
        folder = out / f"run{k:02d}"
        done = result_of(folder)
        if done is None:
            code = runner(command(args, folder))
            done = result_of(folder)
            if done is None:
                stopped = f"run {k} left no result (exit {code}): read {folder} before anything else; nothing is retried"
                break
        hard = done.get("hard_failures") or []
        rows.append({"run": k, "passed": bool(done.get("passed")), "hard_failures": hard, "guard_refused": done.get("guard_refused")})
        print(f"R1 run {k}: passed={rows[-1]['passed']} hard_failures={len(hard)}", flush=True)
        if hard:
            stopped = f"hard failure in run {k}: {hard[0]}"
            break
    passed = sum(1 for r in rows if r["passed"])
    hard_total = sum(len(r["hard_failures"]) for r in rows)
    complete = len(rows) == args.runs and stopped is None
    verdict = "fail" if hard_total else ("pass" if complete and passed == args.runs == RUNS else "inconclusive")
    summary = {"verdict": verdict, "runs": len(rows), "planned": args.runs, "passed_every_check": passed, "hard_failures": hard_total, "stopped": stopped,
               "lower_bound_95": lower_bound_all_pass(passed) if passed == len(rows) and rows else None, "rows": rows}
    (out / "r1_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"R1: {verdict.upper()} - {passed} of {len(rows)} runs passed every check, hard failures {hard_total}" + (f" (stopped: {stopped})" if stopped else ""), flush=True)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", choices=["ollama", "openrouter"], required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=RUNS)
    ap.add_argument("--budget-usd", type=float, default=BUDGET_PER_RUN)
    ap.add_argument("--token-cap", type=int, default=TOKEN_CAP)
    ap.add_argument("--price-in", type=float, default=None)
    ap.add_argument("--price-out", type=float, default=None)
    ap.add_argument("--scripted", action="store_true", help="a scripted model (rehearsal, no cost)")
    args = ap.parse_args(argv)
    if args.provider == "openrouter" and (args.price_in is None or args.price_out is None):
        raise SystemExit("a paid run needs --price-in and --price-out")
    return 0 if run_all(args)["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

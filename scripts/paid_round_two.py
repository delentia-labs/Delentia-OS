"""
Round 113: round two of the paid runs as ONE guarded script, run in your own terminal. The rules it enforces are written in research/ROUND_TWO_CRITERIA_R113.md (committed before this file).

    python scripts/paid_round_two.py preflight --stage r2-1 --models a/b,c/d
    python scripts/paid_round_two.py r2-1 --models anthropic/claude-haiku-5.5,x-ai/grok-build-0.1 [--execute]     # judge and critic sets, reply allowance 1,200
    python scripts/paid_round_two.py r2-2 --models ...                                                          # TC-003 b0 against d0, 14 tasks per arm
    python scripts/paid_round_two.py r2-3 --model anthropic/claude-haiku-5.5 [--workflows W06,W08] [--runs 14]  # workflows, 14 runs each (W09 and W12: 1 run until you say the tooling is checked)
    python scripts/paid_round_two.py r2-4 [--execute]                                                           # K.1.5 three more times, only if the money allows
    python scripts/paid_round_two.py summary

It is built on scripts/paid_day.py (the provider's own usage figure read while every command runs, a command stopped at 90% of its stage ceiling, a running total across keys). Nothing is spent without
`--execute`. The key is read from OPENROUTER_API_KEY, never printed, never put on a command line, never written to a file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import paid_day as pd  # noqa: E402

CEILINGS = {"R2-1": 1.20, "R2-2": 2.00, "R2-3": 1.50, "R2-4": 2.40}
TOTAL_LIMIT = round(sum(CEILINGS.values()), 2)                    # 7.10: the sum written in the criteria, section 6
JUDGE_ALLOWANCE = "1200"
TC003_SEEDS = "1700-1713"                                         # 14 tasks per arm
WORKFLOW_BUDGETS = {"W03": 0.15, "W06": 0.15, "W08": 0.30, "W09": 1.50, "W10": 0.40, "W12": 0.30}     # the first screen's per-run budgets (the runner's own worst-case rule still decides)
WORKFLOW_ORDER = ["W06", "W08", "W10", "W03", "W12", "W09"]       # W09 last: it is the one whose worst case can not fit 14 runs
CAREFUL = {"W09", "W12"}                                          # one run until --tooling-checked says the step list was read
K15_GROUPS = {"require_parameters": ["qwen/qwen3.5-397b-a17b", "x-ai/grok-build-0.1", "google/gemini-3.8-flash"],
              "without": ["anthropic/claude-haiku-5.5", "amazon/nova-pro-v1", "moonshotai/kimi-k2"]}
BLOCK_OF = {"r2-1": "R2-1", "r2-2": "R2-2", "r2-3": "R2-3", "r2-4": "R2-4"}


def total_file(env: Dict[str, str], override: Optional[str] = None) -> Path:
    return Path(override) if override else Path(env.get("DELENTIA_HOME") or Path.home() / ".delentia") / "paid-day" / "round2_total.json"


def preflight(args: argparse.Namespace, env: Dict[str, str], info: Callable[[str], Dict[str, Any]] = pd.key_info) -> List[Dict[str, Any]]:
    stage = BLOCK_OF[args.command]
    ceiling = CEILINGS[stage]
    rows = [pd.check("OPENROUTER_API_KEY is set", bool(env.get("OPENROUTER_API_KEY")), "set it in this terminal: the key is a fresh one for this block, limit = the block's ceiling"),
            pd.check("DELENTIA_RUN_LIVE_TESTS=1", env.get("DELENTIA_RUN_LIVE_TESTS") == "1", "paid runs are opt-in"),
            pd.check("provider data collection is denied", (env.get("DELENTIA_OPENROUTER_DATA_COLLECTION") or "").lower() == "deny", "set DELENTIA_OPENROUTER_DATA_COLLECTION=deny")]
    loopback = pd.is_loopback(pd.base_url())
    rows.append(pd.check("the endpoint is the real one (or --rehearsal with a loopback fake)", loopback == bool(args.rehearsal), f"endpoint {pd.base_url()}"))
    if env.get("OPENROUTER_API_KEY"):
        try:
            got = info(env["OPENROUTER_API_KEY"])
            limit = got.get("limit")
            rows.append(pd.check("the key has a credit limit set at the provider", limit is not None, "set the key's credit limit in the OpenRouter console"))
            if limit is not None:
                rows.append(pd.check(f"the limit is at most this block's ceiling ${ceiling:.2f}", float(limit) <= ceiling + 1e-9, f"limit ${limit}: a higher limit leaves room for the runaway the ceiling prevents"))
            rows.append(pd.check("the key is fresh (used under $0.10)", float(got.get("usage", 0.0)) < 0.10, f"already used ${got.get('usage')}"))
        except Exception as exc:                                         # the provider could not be asked: nothing is assumed
            rows.append(pd.check("the key can be read at the provider", False, f"{type(exc).__name__}"))
    freeze = args.freeze_file or env.get("DELENTIA_FREEZE_FILE")
    rows.append(pd.check("a frozen configuration is named (or --rehearsal)", bool(freeze) or bool(args.rehearsal), "python -m research.paid_run_freeze write ... (one commit for the whole round)"))
    tf = total_file(env, args.total_file)
    try:
        so_far = pd.Day(Path(args.out_dir or "."), env, execute=False, total_file=tf).running_total()
    except pd.Refused as exc:
        so_far = TOTAL_LIMIT
        rows.append(pd.check("the running total can be read", False, str(exc)))
    rows.append(pd.check(f"the running total ${so_far:.2f} is under the round's ${TOTAL_LIMIT:.2f}", so_far < TOTAL_LIMIT - 1e-9, f"file {tf}"))
    if args.command == "r2-1":
        for name, fname in pd.SETS.items():
            sealed = (Path(args.sheets_dir) / fname).with_suffix(".sealed.json")
            rows.append(pd.check(f"sheet {name} is sealed", (Path(args.sheets_dir) / fname).is_file() and sealed.is_file(), str(sealed)))
    return rows


def r2_1(args: argparse.Namespace, day: pd.Day, models: List[str], prices: Dict[str, Dict[str, float]]) -> None:
    day.env["DELENTIA_RCT7_JUDGE_MAX_TOKENS"] = JUDGE_ALLOWANCE
    os.environ["DELENTIA_RCT7_JUDGE_MAX_TOKENS"] = JUDGE_ALLOWANCE
    start = day.usage() if day.execute else 0.0
    per_run = round(CEILINGS["R2-1"] / (len(models) * 3), 4)
    for model in models:
        for label, module in [("set1", "research.rct7_holdout"), ("set2", "research.rct7_holdout"), ("set3 plain", "research.rct7_holdout_twoaxis"), ("set3 context", "research.rct7_holdout_twoaxis"),
                              ("set4 plain", "research.rct7_holdout_twoaxis"), ("set4 context", "research.rct7_holdout_twoaxis")]:
            setname = label.split()[0]
            argv = [sys.executable, "-m", module, "run", str(Path(args.sheets_dir) / pd.SETS[setname]), "--model", model, "--provider", "openrouter", "--budget-usd", str(per_run)]
            if module.endswith("twoaxis"):
                argv += ["--variant", label.split()[1]] + (["--set4"] if setname == "set4" else [])
            day.run("R2-1", f"{model} {label}", argv, start)


def r2_2(args: argparse.Namespace, day: pd.Day, models: List[str], prices: Dict[str, Dict[str, float]]) -> None:
    start = day.usage() if day.execute else 0.0
    per_model = round(CEILINGS["R2-2"] / len(models) * 0.8, 4)
    for model in models:
        day.run("R2-2", f"{model} TC-003 b0 d0", [sys.executable, "-m", "research.daaes", "benchmark", "--provider", "openrouter", "--model", model, "--arms", "b0,d0", "--seeds", (args.seeds if args.rehearsal and args.seeds else TC003_SEEDS),
                                                  "--budget-usd", str(per_model), *pd.price_args(prices, model), "--out", str(day.out / f"r2_tc003_{model.replace('/', '_')}")], start)


def r2_3(args: argparse.Namespace, day: pd.Day, models: List[str], prices: Dict[str, Dict[str, float]]) -> None:
    model = models[0]
    halted_file = day.out / "r2_3_halted.json"
    halted = set(json.loads(halted_file.read_text(encoding="utf-8"))) if halted_file.exists() else set()
    checked = set(args.tooling_checked or [])
    start = day.usage() if day.execute else 0.0
    for w in [x for x in WORKFLOW_ORDER if not args.workflows or x in args.workflows]:
        runs = args.runs if (w not in CAREFUL or w in checked) else 1
        for k in range(1, runs + 1):
            if w in halted:
                print(f"skip {w} run {k}: a hard failure was found earlier (criteria section 4)")
                break
            folder = day.out / "r2_3" / w / f"run{k:02d}"
            if folder.exists() and list(folder.glob(f"{w}*.json")):
                print(f"skip {w} run {k}: already has a result")
                continue
            code, _ = day.run("R2-3", f"{w} run {k}", [sys.executable, "-m", "research.live_workflows", "run", w, "--provider", "openrouter", "--model", model, "--out", str(folder),
                                                       "--budget-usd", str(WORKFLOW_BUDGETS[w]), *pd.price_args(prices, model)], start)
            if not day.execute:
                continue
            files = list(folder.glob(f"{w}*.json"))
            if not files:
                raise pd.Refused(f"{w} run {k} left no result file (exit {code}): this is recorded, not retried; read {folder} before anything else (criteria section 4: a tooling defect stops the stage)")
            result = json.loads(files[0].read_text(encoding="utf-8"))
            hard = result.get("hard_failures") or []
            print(f"   {w} run {k}: passed={result.get('passed')} hard_failures={len(hard)}")
            if hard:
                halted.add(w)
                halted_file.write_text(json.dumps(sorted(halted)), encoding="utf-8")
                print(f"   HARD FAILURE in {w}: no further runs of {w}. Tell Claude.")


def r2_4(args: argparse.Namespace, day: pd.Day, models: List[str], prices: Dict[str, Dict[str, float]]) -> None:
    start = day.usage() if day.execute else 0.0
    for rep in range(1, 4):
        for group, members in K15_GROUPS.items():
            env_extra = {"DELENTIA_OPENROUTER_REQUIRE_PARAMETERS": "1"} if group == "require_parameters" else {}
            if group == "without":
                day.env.pop("DELENTIA_OPENROUTER_REQUIRE_PARAMETERS", None)
                os.environ.pop("DELENTIA_OPENROUTER_REQUIRE_PARAMETERS", None)
            day.env.update(env_extra)
            os.environ.update(env_extra)
            day.run("R2-4", f"K15 repeat {rep} {group}", [sys.executable, "scripts/full_test_orchestrator.py", "--tier", "W", "--models", ",".join(members), "--budget-usd", str(round(CEILINGS["R2-4"] / 6, 4)),
                                                          *pd.price_source_args(args), *pd.freeze_args(args), "--execute", "--out", str(day.out / f"r2_4_{group}_{rep}.json")], start)


def summary(out: Path) -> str:
    log = out / "paid_day_log.jsonl"
    if not log.is_file():
        return f"no log in {out}"
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
    lines = [f"# Round two summary ({out})", "", "| block | commands | exit codes | highest stage usage (USD) | ceiling |", "|---|---|---|---|---|"]
    for stage, ceiling in CEILINGS.items():
        mine = [r for r in rows if r.get("stage") == stage and "exit" in r]
        if mine:
            lines.append(f"| {stage} | {len(mine)} | {sorted({r['exit'] for r in mine})} | {max(r.get('stage_usage_usd', 0) for r in mine):.4f} | {ceiling:.2f} |")
    for r in rows:
        if "refused" in r or "stopped_by_driver" in r:
            lines.append(f"\nSTOPPED/REFUSED: {r.get('stage')} {r.get('label')}: {r.get('refused') or r.get('stopped_by_driver')}")
    lines += ["", "Register each result with research/results_register.py after reading its file; the criteria file is research/ROUND_TWO_CRITERIA_R113.md."]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["preflight", "r2-1", "r2-2", "r2-3", "r2-4", "summary"])
    ap.add_argument("--stage", choices=list(BLOCK_OF), default=None, help="preflight: which block's checks")
    ap.add_argument("--models", type=lambda s: [m.strip() for m in s.split(",") if m.strip()], default=None)
    ap.add_argument("--model", default=None, help="r2-3: the one model (haiku)")
    ap.add_argument("--workflows", type=lambda s: [m.strip() for m in s.split(",") if m.strip()], default=None)
    ap.add_argument("--runs", type=int, default=14)
    ap.add_argument("--tooling-checked", type=lambda s: [m.strip() for m in s.split(",") if m.strip()], default=None, help="r2-3: W09 and/or W12, after you and Claude have read the step list of their first run")
    ap.add_argument("--seeds", default=None, help="r2-2, with --rehearsal only: fewer seeds for a quick rehearsal (a real run always uses 14)")
    ap.add_argument("--freeze-file", default=None)
    ap.add_argument("--prices-file", default=None)
    ap.add_argument("--sheets-dir", default=str(ROOT.parent))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--total-file", default=None)
    ap.add_argument("--watch-seconds", type=float, default=15.0)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--rehearsal", action="store_true")
    return ap


def main(argv: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None, info: Callable[[str], Dict[str, Any]] = pd.key_info) -> int:
    args = build_parser().parse_args(argv)
    env = dict(os.environ if env is None else env)
    out = Path(args.out_dir) if args.out_dir else Path(env.get("DELENTIA_HOME") or Path.home() / ".delentia") / "paid-day" / ("round2-" + time.strftime("%Y%m%d"))
    if args.command == "summary":
        print(summary(out))
        return 0
    if args.seeds and not args.rehearsal:
        print("Refused: --seeds is for a rehearsal only; a real r2-2 always runs 14 seeds. Nothing was spent.")
        return 2
    preflight_only = args.command == "preflight"
    if preflight_only:
        if not args.stage:
            print("Refused: preflight needs --stage r2-1|r2-2|r2-3|r2-4")
            return 2
        args.command = args.stage
    models = [args.model] if args.command == "r2-3" and args.model else (args.models or [])
    if args.command in ("r2-1", "r2-2", "r2-3") and not models:
        print("Refused: --models (r2-3: --model) is needed. Nothing was spent.")
        return 2
    if args.command in ("r2-1", "r2-2") and len(models) > 2:
        print("Refused: at most two models (the criteria name haiku and grok). Nothing was spent.")
        return 2
    prices = pd.load_prices(args, models or sum(K15_GROUPS.values(), []))
    rows = preflight(args, env, info)
    print("Preflight:\n" + pd.render_checks(rows))
    if not all(r["ok"] for r in rows):
        print("\nRefused: fix the lines marked NO. Nothing was spent.")
        return 1 if preflight_only else 2
    if preflight_only:
        return 0
    if not args.execute:
        print("\nDry run: the commands below are what --execute would run. Nothing is spent.")
    os.environ.update({k: v for k, v in env.items() if k.startswith("DELENTIA_") or k == "OPENROUTER_API_KEY"})
    day = pd.Day(out, env, info, args.execute, ceilings=CEILINGS, watch_seconds=args.watch_seconds, total_file=total_file(env, args.total_file), total_limit=TOTAL_LIMIT)
    runner = {"r2-1": r2_1, "r2-2": r2_2, "r2-3": r2_3, "r2-4": r2_4}[args.command]
    try:
        runner(args, day, models or [], prices)
    except pd.Refused as exc:
        print(f"\nSTOPPED: {exc}")
        print(summary(out))
        return 3
    print("\n" + summary(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

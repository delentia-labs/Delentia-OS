"""
Round 107: the paid day as ONE guarded script that you run in your own terminal.

    python scripts/paid_day.py preflight --models a/b,c/d,...                 # checks only, nothing is spent
    python scripts/paid_day.py stage1    --models a/b,c/d,... [--execute]     # P0 meter calibration, then P1 capability screen
    python scripts/paid_day.py stage2    --selected a/b,c/d   [--execute]     # P1b menu A/B, P2 RCT-7 sets, P4 base tasks, for at most three qualified models
    python scripts/paid_day.py summary                                        # what was spent and what each stage said, with the commands that register it

Why a script. The stages are written down in research/PREPAID_CRITERIA_R103.md and every one of them already has its own command. What went wrong in earlier paid-test plans was never a command, it was the
order, the ceiling that was only a sentence, the key without a cap at the provider, a model chosen after seeing the numbers, a stage run on a commit that changed in between. This script chains the
existing commands and adds only the guards: nothing is spent unless `--execute` is given; every stage re-reads the key's own usage figure and stops when the stage's ceiling is reached; the key must have a
credit limit set at the provider (read from the provider, not from a flag), a frozen configuration must still match, a stage does not start when the one before did not meet its rule, and the models for
stage 2 are written to a file BEFORE any stage 2 spending.

The key is read from OPENROUTER_API_KEY and goes only into the Authorization header of the provider's own endpoint (and the commands it starts, which read it from the same environment). It is never printed,
never put on a command line, never written to a file. Run this in the terminal where you set the key; do not paste the key anywhere else.

What a green run means. That the plumbing and the guards held and every command ran as written. It does not say a model is good: each stage's verdict is the stage's own rule from the criteria file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

CAP_USD = 12.10                       # the sum of the stage ceilings (0.10 + 5.00 + 1.50 + 1.50 + 4.00): the credit limit to set on the key
STAGE_CEILINGS = {"P0": 0.10, "P1": 5.00, "P1b": 1.50, "P2": 1.50, "P4": 4.00}
SETS = {
    "set1": "RCT7_HOLDOUT_LABELLING_SHEET_FOR_THE_ARCHITECT.md",
    "set2": "RCT7_R7_HOLDOUT_LABELLING_SHEET_FOR_THE_ARCHITECT.md",
    "set3": "RCT7_HOLDOUT_3_TWO_AXES_SHEET_FOR_THE_ARCHITECT.md",
    "set4": "RCT7_HOLDOUT_4_SHEET_FOR_THE_ARCHITECT.md",
}
P4_SEEDS = "1700-1703"                # four paired seeds per arm: the rule asks for 'at least 3 of 4 runs through d0'


class Refused(Exception):
    """A guard said no. Nothing was spent by the step that raised it."""


# ------------------------------------------------------------------------------------------------ the provider

def base_url() -> str:
    from rct_control_plane.llm_provider import openrouter_base_url
    return openrouter_base_url().rstrip("/")


def is_loopback(url: str) -> bool:
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "") in ("127.0.0.1", "localhost", "::1")


def key_info(key: str, url: Optional[str] = None) -> Dict[str, Any]:
    """What the provider itself says about this key: dollars used, the credit limit and what is left. The key goes only into the Authorization header."""
    import httpx
    reply = httpx.get(f"{url or base_url()}/auth/key", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    if reply.status_code != 200:
        raise Refused(f"the provider answered HTTP {reply.status_code} to the key check: the key is wrong, revoked or out of credit")
    data = reply.json().get("data", {})
    return {"usage": float(data.get("usage") or 0.0), "limit": data.get("limit"), "limit_remaining": data.get("limit_remaining")}


# ------------------------------------------------------------------------------------------------ preflight

def check(name: str, ok: bool, detail: str) -> Dict[str, Any]:
    return {"check": name, "ok": bool(ok), "detail": detail}


def preflight(args: argparse.Namespace, env: Dict[str, str], info: Callable[[str], Dict[str, Any]] = key_info, prices: Optional[Dict[str, Dict[str, float]]] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    key = env.get("OPENROUTER_API_KEY", "")
    rows.append(check("the key is set (not shown)", len(key) >= 8, "OPENROUTER_API_KEY is " + ("set" if key else "NOT set in this terminal")))
    rows.append(check("live tests are switched on", env.get("DELENTIA_RUN_LIVE_TESTS") == "1", "DELENTIA_RUN_LIVE_TESTS must be 1 in this terminal (the opt-in that every paid command asks for)"))
    rows.append(check("no data collection by upstream providers", (env.get("DELENTIA_OPENROUTER_DATA_COLLECTION") or "").lower() == "deny",
                      "DELENTIA_OPENROUTER_DATA_COLLECTION must be deny (criteria: a model that cannot be served under it is not_run, not run under looser terms)"))
    url = base_url()
    loop = is_loopback(url)
    if getattr(args, "rehearsal", False):
        rows.append(check("rehearsal runs only against a loopback fake", loop, f"the endpoint is {url}: --rehearsal skips the freeze check and is refused for anything that is not on this machine"))
    elif loop:
        rows.append(check("the endpoint is the provider's", False, f"DELENTIA_OPENROUTER_BASE_URL points at {url}: that is a fake, not OpenRouter; pass --rehearsal if that is intended"))
    if not getattr(args, "rehearsal", False):
        freeze = args.freeze_file or env.get("DELENTIA_FREEZE_FILE")
        if not freeze or not Path(freeze).is_file():
            rows.append(check("a frozen configuration exists", False, "write it first: python -m research.paid_run_freeze write --models ... --live-prices --stages P0,P1,P1b,P2,P4 --budget-usd 12.10 --provider-cap-confirmed --out freeze.json"))
        else:
            res = subprocess.run([sys.executable, "-m", "research.paid_run_freeze", "check", str(freeze)], capture_output=True, text=True, cwd=str(ROOT), env=env)
            rows.append(check("the frozen configuration still matches", res.returncode == 0, (res.stdout + res.stderr).strip()[-400:] or "ok"))
            rows.append(check("DELENTIA_FREEZE_FILE names it in this terminal", Path(env.get("DELENTIA_FREEZE_FILE", "")) == Path(freeze) if env.get("DELENTIA_FREEZE_FILE") else False,
                              "the research commands read the freeze from DELENTIA_FREEZE_FILE; set it to the same file as --freeze-file"))
    if key:
        try:
            got = info(key)
            limit, left = got.get("limit"), got.get("limit_remaining")
            rows.append(check("the key has a credit limit at the provider", isinstance(limit, (int, float)) and limit > 0,
                              "the provider reports no limit for this key: set one on openrouter.ai (Keys, credit limit) before anything else" if limit is None else f"limit ${limit}"))
            rows.append(check(f"the limit is at most ${CAP_USD:.2f}", isinstance(limit, (int, float)) and limit <= CAP_USD + 1e-9,
                              f"limit ${limit}: the stage ceilings add up to ${CAP_USD:.2f}; a higher limit leaves room for a runaway the ceilings are meant to prevent"))
            needed = {"stage1": STAGE_CEILINGS["P0"] + STAGE_CEILINGS["P1"], "stage2": STAGE_CEILINGS["P1b"] + STAGE_CEILINGS["P2"] + STAGE_CEILINGS["P4"]}.get(getattr(args, "command", ""), CAP_USD)
            rows.append(check("what is left on the limit covers the stages about to run", (left >= needed - 1e-9) if isinstance(left, (int, float)) else (isinstance(limit, (int, float)) and limit >= needed - 1e-9),
                              f"remaining ${left}: this step may use up to ${needed:.2f}"))
            rows.append(check("the key is fresh enough", got["usage"] < 1.0, f"already used ${got['usage']}: the stage ceilings are measured from now, so older spending only matters for the limit above"))
        except Refused as exc:
            rows.append(check("the key works", False, str(exc)))
        except Exception as exc:                                    # noqa: BLE001 - any network problem is a failed check, not a crash
            rows.append(check("the provider answers", False, f"{type(exc).__name__}: {str(exc)[:160]}"))
    models = [m for m in (args.models or args.selected or []) if m]
    rows.append(check("models are named", bool(models), "pass --models (stage 1) or --selected (stage 2)"))
    if getattr(args, "selected", None):
        rows.append(check("at most three models go on", len(args.selected) <= 3, f"{len(args.selected)} given"))
    if prices is not None:
        for m in models:
            p = prices.get(m)
            rows.append(check(f"price known: {m}", p is not None and p.get("in") is not None and p.get("out") is not None, f"{p}" if p else "not in the provider's list"))
    sheets_dir = Path(args.sheets_dir)
    for name, fname in SETS.items():
        sealed = (sheets_dir / fname).with_suffix(".sealed.json")
        rows.append(check(f"sheet {name} is sealed", (sheets_dir / fname).is_file() and sealed.is_file(), f"{sealed}"))
    return rows


def render_checks(rows: List[Dict[str, Any]]) -> str:
    return "\n".join(f"  [{'ok' if r['ok'] else 'NO'}] {r['check']}" + ("" if r["ok"] else f"\n        -> {r['detail']}") for r in rows)


# ------------------------------------------------------------------------------------------------ running

class Day:
    """One output folder, one log, and the spending guard (the provider's own usage figure, read before and after every command)."""

    def __init__(self, out: Path, env: Dict[str, str], info: Callable[[str], Dict[str, Any]] = key_info, execute: bool = False):
        self.out, self.env, self.info, self.execute = out, dict(env), info, execute
        self.out.mkdir(parents=True, exist_ok=True)
        self.log = self.out / "paid_day_log.jsonl"
        self.spent: Dict[str, float] = {}

    def usage(self) -> float:
        return float(self.info(self.env["OPENROUTER_API_KEY"])["usage"])

    def record(self, entry: Dict[str, Any]) -> None:
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}, ensure_ascii=False) + "\n")

    def run(self, stage: str, label: str, argv: List[str], start_usage: float, timeout: float = 5400.0) -> Tuple[int, float]:
        """Run one command. Refuses first if the stage already used its ceiling; the argument list never contains the key."""
        assert "OPENROUTER_API_KEY" not in " ".join(argv)
        so_far = max(0.0, self.usage() - start_usage) if self.execute else 0.0
        if so_far >= STAGE_CEILINGS[stage] - 1e-9:
            self.record({"stage": stage, "label": label, "refused": f"the stage already used ${so_far:.4f}, its ceiling is ${STAGE_CEILINGS[stage]:.2f}"})
            raise Refused(f"stage {stage} reached its ceiling (${so_far:.4f} of ${STAGE_CEILINGS[stage]:.2f}); not starting '{label}'")
        printable = " ".join(argv[1:] if argv and argv[0] == sys.executable else argv)
        print(f"\n-- {stage} / {label}\n   python {printable}")
        if not self.execute:
            self.record({"stage": stage, "label": label, "argv": printable, "dry_run": True})
            return 0, 0.0
        began = time.time()
        log_file = self.out / f"{stage}_{label.replace(' ', '_').replace('/', '_')}.log"
        with log_file.open("w", encoding="utf-8", errors="replace") as handle:
            proc = subprocess.run(argv, stdout=handle, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT), env=self.env, timeout=timeout)
        used = self.usage() - start_usage
        self.record({"stage": stage, "label": label, "argv": printable, "exit": proc.returncode, "seconds": round(time.time() - began, 1), "stage_usage_usd": round(used, 6), "log": str(log_file)})
        print(f"   exit {proc.returncode}, {time.time() - began:.0f}s, stage usage so far ${used:.4f} of ${STAGE_CEILINGS[stage]:.2f}  ({log_file.name})")
        if used > STAGE_CEILINGS[stage] * 1.5:
            raise Refused(f"stage {stage} used ${used:.4f}, more than 1.5x its ceiling: stopping the day")
        return proc.returncode, used


def price_args(prices: Dict[str, Dict[str, float]], model: str) -> List[str]:
    p = prices[model]
    return ["--price-in", str(p["in"]), "--price-out", str(p["out"])]


def price_source_args(args: argparse.Namespace) -> List[str]:
    return ["--prices-file", str(args.prices_file), "--live-prices"] if args.prices_file else ["--live-prices"]


def freeze_args(args: argparse.Namespace) -> List[str]:
    return ["--no-freeze"] if args.rehearsal else ["--freeze-file", str(args.freeze_file or os.environ.get("DELENTIA_FREEZE_FILE"))]


def load_prices(args: argparse.Namespace, models: List[str]) -> Dict[str, Dict[str, float]]:
    if args.prices_file:
        data = json.loads(Path(args.prices_file).read_text(encoding="utf-8"))
        return {m: data[m] for m in models if m in data}
    from research.paid_run_freeze import live_prices
    return live_prices(models)


def qualified_models(report: Dict[str, Any]) -> Dict[str, Any]:
    """The capability screen's own rule (T1 >= 90, T2 >= 90, T3 = 100); a model with a missing figure is not qualified and the reason says so."""
    out: Dict[str, Any] = {}
    for model, res in (report.get("results") or {}).items():
        rates = ((res or {}).get("k15") or {}).get("rates") or {}
        t1, t2, t3 = rates.get("T1"), rates.get("T2"), rates.get("T3")
        if t1 is None or t2 is None or t3 is None:
            out[model] = {"qualified": False, "why": "a figure is missing (the model mostly errored or the stage did not finish): inconclusive, never a pass", "rates": rates}
        else:
            ok = t1 >= 90.0 and t2 >= 90.0 and t3 >= 100.0
            out[model] = {"qualified": ok, "why": "T1, T2 >= 90% and T3 = 100%" if ok else "below the bar", "rates": rates}
    return out


def propose(qualified: Dict[str, Any], prices: Dict[str, Dict[str, float]], limit: int = 3) -> List[str]:
    """At most three, from different vendors, spread over price: the cheapest, then the dearest that still fits the ceilings, then one in between. A proposal, not a choice: the person runs stage 2 with the models he picks."""
    ok = sorted((m for m, v in qualified.items() if v["qualified"]), key=lambda m: prices.get(m, {}).get("in", 0) + prices.get(m, {}).get("out", 0))
    seen, picks = set(), []
    for m in ok:
        vendor = m.split("/")[0]
        if vendor not in seen:
            seen.add(vendor)
            picks.append(m)
    if len(picks) > limit:
        picks = [picks[0], picks[len(picks) // 2], picks[-1]][:limit]
    return picks


def stage1(args: argparse.Namespace, day: Day, models: List[str], prices: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    p0_model = args.p0_model or min(models, key=lambda m: prices[m]["in"] + prices[m]["out"])
    start = day.usage() if day.execute else 0.0
    code, _ = day.run("P0", f"meter {p0_model}", [sys.executable, "scripts/calibrate_meter_p0.py", p0_model, *price_args(prices, p0_model), "--budget-usd", "0.10", "--json", str(day.out / "p0.json")], start)
    if day.execute:
        p0 = json.loads((day.out / "p0.json").read_text(encoding="utf-8")) if (day.out / "p0.json").exists() else {}
        verdict = (p0.get("result") or {}).get("verdict")
        print(f"   P0 verdict: {verdict}  ({(p0.get('result') or {}).get('why', '')})")
        if code != 0 or verdict != "pass":
            raise Refused(f"P0 did not pass ({verdict}): no later stage is started. Read {day.out / 'p0.json'}; an inconclusive result is repeated with more calls inside the same $0.10, a fail means the meter is fixed first.")
    start = day.usage() if day.execute else 0.0
    code, _ = day.run("P1", "capability screen", [sys.executable, "scripts/full_test_orchestrator.py", "--tier", "W", "--models", ",".join(models), "--budget-usd", "5",
                      *price_source_args(args), *freeze_args(args), "--execute", "--out", str(day.out / "p1.json")], start)
    result: Dict[str, Any] = {"p0_model": p0_model}
    if day.execute and (day.out / "p1.json").exists():
        report = json.loads((day.out / "p1.json").read_text(encoding="utf-8"))
        q = qualified_models(report)
        proposal = propose(q, prices)
        (day.out / "p1_qualified.json").write_text(json.dumps({"qualified": q, "proposal": proposal, "note": "a proposal only: run stage 2 with --selected naming the models YOU choose"}, indent=2), encoding="utf-8")
        print("\n   Qualified:")
        for m, v in q.items():
            print(f"     {'YES' if v['qualified'] else 'no '}  {m}  {v['rates']}  ({v['why']})")
        print(f"\n   Proposal for stage 2 (cheapest, a middle one, the dearest, different vendors): {','.join(proposal) or '(none qualified: the round ends here)'}")
        result.update({"qualified": q, "proposal": proposal})
    return result


def stage2(args: argparse.Namespace, day: Day, selected: List[str], prices: Dict[str, Dict[str, float]]) -> None:
    selection = {"selected": selected, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "written_before": "any stage 2 spending", "prices": {m: prices[m] for m in selected}}
    sel_file = day.out / "selection.json"
    sel_file.write_text(json.dumps(selection, indent=2), encoding="utf-8")
    print(f"selection written first: {sel_file} (sha256 {hashlib.sha256(sel_file.read_bytes()).hexdigest()[:16]}...)")
    start = day.usage() if day.execute else 0.0
    day.run("P1b", "menu A/B", [sys.executable, "scripts/full_test_orchestrator.py", "--tier", "M", "--models", ",".join(selected), "--budget-usd", "1.5",
                                *price_source_args(args), *freeze_args(args), "--execute", "--out", str(day.out / "p1b.json")], start)
    start = day.usage() if day.execute else 0.0
    per_model = round(STAGE_CEILINGS["P2"] / len(selected), 4)
    for model in selected:
        runs = [("set1", ["python", "-m", "research.rct7_holdout", "run"]), ("set2", ["python", "-m", "research.rct7_holdout", "run"]),
                ("set3 plain", ["python", "-m", "research.rct7_holdout_twoaxis", "run"]), ("set3 context", ["python", "-m", "research.rct7_holdout_twoaxis", "run"]),
                ("set4 plain", ["python", "-m", "research.rct7_holdout_twoaxis", "run"]), ("set4 context", ["python", "-m", "research.rct7_holdout_twoaxis", "run"])]
        for label, base in runs:
            setname = label.split()[0]
            argv = [sys.executable, *base[1:], str(Path(args.sheets_dir) / SETS[setname]), "--model", model, "--provider", "openrouter", "--budget-usd", str(per_model)]
            if "twoaxis" in base[2]:
                argv += ["--variant", label.split()[1]]
                if setname == "set4":
                    argv += ["--set4"]
            day.run("P2", f"{model} {label}", argv, start)
    start = day.usage() if day.execute else 0.0
    per_model_p4 = round(STAGE_CEILINGS["P4"] / len(selected), 4)
    for model in selected:
        day.run("P4", f"{model} TC-003 b0 d0", [sys.executable, "-m", "research.daaes", "benchmark", "--provider", "openrouter", "--model", model, "--arms", "b0,d0", "--seeds", P4_SEEDS,
                                                "--budget-usd", str(round(per_model_p4 * 0.8, 4)), *price_args(prices, model), "--out", str(day.out / f"p4_tc003_{model.replace('/', '_')}")], start)
        day.run("P4", f"{model} TC-006", [sys.executable, "-m", "research.daaes", "live", "--case", "TC-006", "--provider", "openrouter", "--model", model,
                                          "--budget-usd", str(round(per_model_p4 * 0.2, 4)), *price_args(prices, model), "--out", str(day.out / f"p4_tc006_{model.replace('/', '_')}")], start)


def summary(out: Path) -> str:
    log = out / "paid_day_log.jsonl"
    if not log.is_file():
        return f"no log in {out}"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines = [f"# Paid day summary ({out})", "", "| stage | commands | exit codes | highest stage usage (USD) | ceiling |", "|---|---|---|---|---|"]
    for stage in STAGE_CEILINGS:
        mine = [r for r in rows if r.get("stage") == stage and "exit" in r]
        if mine:
            lines.append(f"| {stage} | {len(mine)} | {sorted({r['exit'] for r in mine})} | {max(r.get('stage_usage_usd', 0) for r in mine):.4f} | {STAGE_CEILINGS[stage]:.2f} |")
    refused = [r for r in rows if "refused" in r]
    for r in refused:
        lines.append(f"\nREFUSED: {r['stage']} {r['label']}: {r['refused']}")
    lines += ["", "Register each result (the criteria file is committed before the run; read each result file first and give the verdict the stage's own rule gives):",
              "  python -m research.results_register add --stage <P0|P1|P1b|P2|P4> --model <id> --provider openrouter --criteria research/PREPAID_CRITERIA_R103.md --result <file> --verdict <pass|fail|inconclusive|not_run> --est-usd <x> --actual-usd <provider's figure>"]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ command line

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["preflight", "stage1", "stage2", "summary"])
    ap.add_argument("--models", type=lambda s: [m.strip() for m in s.split(",") if m.strip()], default=None, help="stage 1: the candidate model ids")
    ap.add_argument("--selected", type=lambda s: [m.strip() for m in s.split(",") if m.strip()], default=None, help="stage 2: at most three models that stage 1 qualified")
    ap.add_argument("--p0-model", default=None, help="the model for the meter calibration (default: the cheapest candidate)")
    ap.add_argument("--freeze-file", default=None)
    ap.add_argument("--prices-file", default=None, help="JSON {model: {in, out}} instead of the provider's public list (rehearsal)")
    ap.add_argument("--sheets-dir", default=str(ROOT.parent), help="where the four sealed holdout sheets are (default: the workspace folder above the repository)")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--execute", action="store_true", help="really run (spends money); without it only the plan and the checks are printed")
    ap.add_argument("--rehearsal", action="store_true", help="only against a loopback fake endpoint: skips the freeze check")
    return ap


def main(argv: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None, info: Callable[[str], Dict[str, Any]] = key_info) -> int:
    args = build_parser().parse_args(argv)
    env = dict(os.environ if env is None else env)
    out = Path(args.out_dir) if args.out_dir else Path(env.get("DELENTIA_HOME") or Path.home() / ".delentia") / "paid-day" / time.strftime("%Y%m%d")
    if args.command == "summary":
        print(summary(out))
        return 0
    models = args.selected if args.command == "stage2" else args.models
    prices = load_prices(args, models or []) if models else {}
    rows = preflight(args, env, info, prices if models else None)
    print("Preflight:\n" + render_checks(rows))
    if args.command == "preflight":
        return 0 if all(r["ok"] for r in rows) else 1
    if not all(r["ok"] for r in rows):
        print("\nRefused: fix the lines marked NO. Nothing was spent.")
        return 2
    if not args.execute:
        print("\nDry run: the commands below are what --execute would run. Nothing is spent.")
    os.environ.update({k: v for k, v in env.items() if k.startswith("DELENTIA_") or k == "OPENROUTER_API_KEY"})
    day = Day(out, env, info, args.execute)
    try:
        if args.command == "stage1":
            stage1(args, day, models or [], prices)
        else:
            stage2(args, day, models or [], prices)
    except Refused as exc:
        print(f"\nSTOPPED: {exc}")
        print(summary(out))
        return 3
    print("\n" + summary(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

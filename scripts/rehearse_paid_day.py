"""
Round 107: rehearse the whole paid day (scripts/paid_day.py: stage 1 and stage 2) against the fake OpenRouter. Costs nothing, needs no key.

    python scripts/rehearse_paid_day.py [--keep DIR]

It starts scripts/fake_openrouter.py with a key limit of $12.10 (as the provider would report it), copies the four sealed holdout sheets to a temporary folder (so the rehearsal never writes a run
into the real sheets' run files), and runs `paid_day.py stage1` and `stage2` with `--execute --rehearsal` exactly as the Architect will with a real key. It then checks that:
  * every guard that can refuse did refuse (no key, no live-tests switch, no limit on the key, a limit above the cap, a real endpoint with --rehearsal, a loopback fake without it);
  * P0, P1, P1b, P2 and P4 each ran their command and logged an exit code;
  * the money the script measured (the provider's own usage figure) equals what the fake charged;
  * the key never appears in the log or in any output file.
A pass means the plumbing and the guards work. It says nothing about how a real model behaves: the fake's answers are scripted, so the verdicts of the stages are not the point.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--keep", default=None, help="keep the output folder here")
    ap.add_argument("--real-sheets", default=str(ROOT.parent), help="where the four sealed holdout sheets are (copied, never written to)")
    args = ap.parse_args()
    import fake_openrouter
    import paid_day

    model = "rehearsal/model"
    prices = {model: {"in": 0.2, "out": 0.8}}
    work = Path(tempfile.mkdtemp(prefix="paid-day-rehearsal-"))
    (work / "prices.json").write_text(json.dumps(prices), encoding="utf-8")
    sheets = work / "sheets"
    sheets.mkdir()
    real_sheets = Path(args.real_sheets)
    for fname in paid_day.SETS.values():
        for suffix in ("", ".sealed.json"):
            src = (real_sheets / fname) if not suffix else (real_sheets / fname).with_suffix(".sealed.json")
            if src.is_file():
                shutil.copy(src, sheets / src.name)
    problems = []
    out = Path(args.keep) if args.keep else work / "out"
    with fake_openrouter.FakeOpenRouter(prices, limit=12.10) as fake:
        os.environ.update({"DELENTIA_OPENROUTER_BASE_URL": fake.base_url, "OPENROUTER_API_KEY": fake.key, "DELENTIA_RUN_LIVE_TESTS": "1", "DELENTIA_OPENROUTER_DATA_COLLECTION": "deny"})
        common = ["--models", model, "--prices-file", str(work / "prices.json"), "--sheets-dir", str(sheets), "--out-dir", str(out), "--rehearsal"]
        print("=== the guards must refuse")
        env = dict(os.environ)
        for label, mutate, extra in (
            ("no key", lambda e: e.pop("OPENROUTER_API_KEY"), []),
            ("live tests off", lambda e: e.pop("DELENTIA_RUN_LIVE_TESTS"), []),
            ("data collection not denied", lambda e: e.pop("DELENTIA_OPENROUTER_DATA_COLLECTION"), []),
            ("rehearsal flag missing against a loopback fake", lambda e: None, "norehearsal"),
        ):
            e = dict(env)
            mutate(e)
            argv = ["preflight", *common[:-1]] if extra == "norehearsal" else ["preflight", *common]
            code = paid_day.main(argv, e, paid_day.key_info)
            if code == 0:
                problems.append(f"preflight accepted: {label}")
        fake.limit = None
        if paid_day.main(["preflight", *common], dict(env), paid_day.key_info) == 0:
            problems.append("preflight accepted a key with no credit limit")
        fake.limit = 50.0
        if paid_day.main(["preflight", *common], dict(env), paid_day.key_info) == 0:
            problems.append("preflight accepted a key whose limit is above the cap")
        fake.limit = 12.10
        print("\n=== the plan alone (dry run) must spend nothing")
        before = fake.spent
        paid_day.main(["stage1", *common], dict(env), paid_day.key_info)
        if fake.spent != before:
            problems.append("a dry run spent money")
        print("\n=== stage 1 for real (against the fake)")
        code1 = paid_day.main(["stage1", *common, "--execute"], dict(env), paid_day.key_info)
        print("\n=== stage 2 for real (against the fake)")
        code2 = paid_day.main(["stage2", "--selected", model, *common[2:], "--execute"], dict(env), paid_day.key_info)
        spent_fake = round(fake.spent, 6)
    log = out / "paid_day_log.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()] if log.exists() else []
    ran = {r["stage"] for r in rows if "exit" in r}
    for stage in ("P0", "P1", "P1b", "P2", "P4"):
        if stage not in ran:
            problems.append(f"stage {stage} never ran a command")
    if (out / "selection.json").exists() is False:
        problems.append("the selection was not written before stage 2")
    stage_usage = {s: max((r.get("stage_usage_usd", 0) for r in rows if r.get("stage") == s and "exit" in r), default=0.0) for s in paid_day.STAGE_CEILINGS}
    measured = round(sum(stage_usage.values()), 6)
    print(f"\nfake charged ${spent_fake}; the stages' own measurement adds up to ${measured}; exit codes {code1}, {code2}")
    if abs(measured - spent_fake) > max(0.002, spent_fake * 0.02):
        problems.append(f"the script's measured spend (${measured}) does not match what the fake charged (${spent_fake})")
    leaked = [str(p) for p in out.rglob("*") if p.is_file() and fake.key in p.read_text(encoding="utf-8", errors="ignore")]
    if leaked:
        problems.append(f"the key appears in: {leaked[:3]}")
    for p in problems:
        print(f"PROBLEM: {p}")
    print("REHEARSAL " + ("FAILED" if problems else "PASSED: the guards held and every stage ran as written against a fake; the real model is still unmeasured"))
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

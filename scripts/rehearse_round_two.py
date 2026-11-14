"""
Round 113, R2-0: the free rehearsal of round two (criteria: research/ROUND_TWO_CRITERIA_R113.md, section 1). Costs nothing, needs no key.

    python scripts/rehearse_round_two.py [--keep DIR] [--real-sheets DIR] [--quick]

Against scripts/fake_openrouter.py, which here misbehaves on purpose (HTTP 429 with Retry-After, HTTP 402, a gateway page with HTTP 200, a reply cut by its length limit, 2,000 tokens of reasoning before a
valid reply), it checks:
  A. the judge set 1 run with the 1,200-token allowance: each fault is recorded as `unusable` with its cause and none as a verdict of the model, the cut reply is kept (6,000 characters), the reply that came
     after reasoning is read normally;
  B. `paid_round_two.py r2-1` for real: every command exits, the stage's ceiling stops the stage while a command runs when the price makes a run too dear (exit 3, the stopped command named in the log),
     and the running total counts what the stopped command spent;
  C. r2-2 (TC-003 b0/d0, a few seeds), r2-3 (W06 and W08, two runs each) and r2-4 plan and run their commands to the end with exit 0;
  D. the money the script measured equals what the fake charged (within 1%), and the key appears in no file.
A pass says the plumbing and the guards work. It says nothing about any real model.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

MODELS = ["anthropic/claude-haiku-5.5", "x-ai/grok-build-0.1", "qwen/qwen3.5-397b-a17b", "google/gemini-3.8-flash", "amazon/nova-pro-v1", "moonshotai/kimi-k2"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--keep", default=None)
    ap.add_argument("--real-sheets", default=str(ROOT.parent))
    ap.add_argument("--quick", action="store_true", help="skip r2-4 (three K.1.5 repeats of six models)")
    args = ap.parse_args()
    import fake_openrouter
    import paid_day

    problems: List[str] = []
    work = Path(tempfile.mkdtemp(prefix="round2-rehearsal-"))
    sheets = work / "sheets"
    sheets.mkdir()
    for fname in paid_day.SETS.values():
        for src in (Path(args.real_sheets) / fname, (Path(args.real_sheets) / fname).with_suffix(".sealed.json")):
            if src.is_file():
                shutil.copy(src, sheets / src.name)
    prices = {m: {"in": 0.2, "out": 0.8} for m in MODELS}
    (work / "prices.json").write_text(json.dumps(prices), encoding="utf-8")
    out = Path(args.keep) if args.keep else work / "out"
    env_base = dict(os.environ, PYTHONUTF8="1")

    # ------------------------------------------------------------------ A: the faults, on the judge's own runner
    faults = {3: "429", 5: "html", 7: "long", 9: "reasoning", 11: "402"}
    with fake_openrouter.FakeOpenRouter(prices, limit=1.20, faults=faults) as fake:
        env = dict(env_base, DELENTIA_OPENROUTER_BASE_URL=fake.base_url, OPENROUTER_API_KEY=fake.key, DELENTIA_RUN_LIVE_TESTS="1", DELENTIA_OPENROUTER_DATA_COLLECTION="deny", DELENTIA_RCT7_JUDGE_MAX_TOKENS="1200")
        sheet = sheets / paid_day.SETS["set1"]
        subprocess.run([sys.executable, "-m", "research.rct7_holdout", "run", str(sheet), "--model", MODELS[0], "--provider", "openrouter", "--budget-usd", "0.5"], env=env, cwd=str(ROOT),
                       capture_output=True, text=True, timeout=900)
        runs_file = sheet.with_suffix(".runs.json")
        entry = json.loads(runs_file.read_text(encoding="utf-8"))[-1] if runs_file.exists() else {}
        unusable, replies = entry.get("unusable") or {}, entry.get("replies") or {}
        print(f"A. unusable by cause: {unusable}; judge_max_tokens {entry.get('judge_max_tokens')}")
        if entry.get("judge_max_tokens") != 1200:
            problems.append("A: the allowance of 1,200 tokens is not in the run entry")
        if sum(unusable.values()) < 4 or unusable.get("provider_error", 0) < 3:
            problems.append(f"A: the 429, 402 and gateway-page faults were not all recorded as unusable ({unusable})")
        if "unparsed_reply" not in unusable:
            problems.append("A: the cut reply was not recorded as unusable")
        if len((replies.get("7") or {}).get("reply") or "") < 5000:
            problems.append("A: the raw cut reply was not kept")
        if (replies.get("9") or {}).get("unusable"):
            problems.append("A: the reply that followed 2,000 tokens of reasoning was not read")
        if (entry.get("result") or {}).get("malformed") != sum(unusable.values()):
            problems.append("A: `malformed` and the unusable causes disagree")
        if abs(fake.spent) <= 0:
            problems.append("A: the fake charged nothing: the run did not reach it")

    # ------------------------------------------------------------------ B: the ceiling inside a command
    expensive = {m: {"in": 20.0, "out": 75.0} for m in MODELS}      # a run of 60 calls costs about its own budget, so six runs pass the stage ceiling
    (work / "prices_expensive.json").write_text(json.dumps(expensive), encoding="utf-8")
    total_b = work / "total_b.json"
    with fake_openrouter.FakeOpenRouter(expensive, limit=1.20) as fake:
        env = dict(env_base, DELENTIA_OPENROUTER_BASE_URL=fake.base_url, OPENROUTER_API_KEY=fake.key, DELENTIA_RUN_LIVE_TESTS="1", DELENTIA_OPENROUTER_DATA_COLLECTION="deny")
        sheets_b = work / "sheets_b"
        shutil.copytree(sheets, sheets_b)
        for f in sheets_b.glob("*.runs.json"):
            f.unlink()
        # run the script as the Architect will, in its own process
        proc = subprocess.run([sys.executable, "scripts/paid_round_two.py", "r2-1", "--models", MODELS[0], "--prices-file", str(work / "prices_expensive.json"), "--sheets-dir", str(sheets_b),
                               "--out-dir", str(out / "b"), "--total-file", str(total_b), "--watch-seconds", "0.5", "--execute", "--rehearsal"], env=env, cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
        print(f"B. exit {proc.returncode}; fake charged ${fake.spent:.4f}; ceiling of R2-1 is $1.20")
        log = out / "b" / "paid_day_log.jsonl"
        logged = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()] if log.exists() else []
        if not any(("stopped_by_driver" in r) or ("refused" in r) for r in logged):
            problems.append("B: nothing stopped the stage although six runs cost more than its ceiling")
        if proc.returncode != 3:
            problems.append(f"B: the stage ended with exit {proc.returncode}, expected 3 (a guard stopped it)")
        counted = json.loads(total_b.read_text(encoding="utf-8"))["total"] if total_b.exists() else 0.0
        if abs(counted - fake.spent) > max(0.002, fake.spent * 0.01):
            problems.append(f"B: the running total (${counted:.4f}) does not equal what the fake charged (${fake.spent:.4f})")
        if fake.spent > 1.20 * 1.5:
            problems.append(f"B: the fake was charged ${fake.spent:.4f}, more than 1.5x the ceiling")

    # ------------------------------------------------------------------ C: the other blocks, to the end, with a fake that behaves
    total_c = work / "total_c.json"
    with fake_openrouter.FakeOpenRouter(prices, limit=2.00) as fake:
        env = dict(env_base, DELENTIA_OPENROUTER_BASE_URL=fake.base_url, OPENROUTER_API_KEY=fake.key, DELENTIA_RUN_LIVE_TESTS="1", DELENTIA_OPENROUTER_DATA_COLLECTION="deny")
        common = ["--prices-file", str(work / "prices.json"), "--sheets-dir", str(sheets), "--total-file", str(total_c), "--execute", "--rehearsal"]
        steps = [("r2-2", ["r2-2", "--models", ",".join(MODELS[:2]), "--seeds", "1700-1701", "--out-dir", str(out / "c2")]),
                 ("r2-3", ["r2-3", "--model", MODELS[0], "--workflows", "W06,W08", "--runs", "2", "--out-dir", str(out / "c3")]),
                 ("r2-5", ["r2-5", "--model", MODELS[0], "--out-dir", str(out / "c5")])]
        if not args.quick:
            steps.append(("r2-4", ["r2-4", "--out-dir", str(out / "c4")]))
        for name, argv in steps:
            fake.limit = {"r2-2": 2.00, "r2-3": 1.50, "r2-4": 3.30, "r2-5": 0.80}[name]               # the key of each block is limited to that block's ceiling, as the criteria say
            proc = subprocess.run([sys.executable, "scripts/paid_round_two.py", *argv, *common], env=env, cwd=str(ROOT), capture_output=True, text=True, timeout=3600)
            print(f"C. {name}: exit {proc.returncode}")
            if proc.returncode != 0:
                problems.append(f"C: {name} ended with exit {proc.returncode}: {(proc.stdout + proc.stderr)[-400:]}")
        n_k15 = len(list((out / "c4").glob("r2_4_*.json")))
        if not args.quick and n_k15 != 6:
            problems.append(f"C: r2-4 left {n_k15} result files, expected 6 (an orchestrator that refuses exits 0: that was missed once)")
        spent_fake = fake.spent
        if not args.quick and spent_fake <= 0.05:
            problems.append("C: r2-4 spent almost nothing: its commands did not reach the endpoint")
        counted = json.loads(total_c.read_text(encoding="utf-8"))["total"] if total_c.exists() else 0.0
        print(f"D. fake charged ${spent_fake:.6f}; the running total says ${counted:.6f}")
        if abs(counted - spent_fake) > max(0.002, spent_fake * 0.01):
            problems.append(f"D: the running total (${counted:.6f}) does not equal what the fake charged (${spent_fake:.6f})")
    leaked = [str(p) for p in out.rglob("*") if p.is_file() and "rehearsal-not-a-real-key" in p.read_text(encoding="utf-8", errors="ignore")]
    if leaked:
        problems.append(f"the key appears in: {leaked[:3]}")
    for p in problems:
        print(f"PROBLEM: {p}")
    print("R2-0 " + ("FAILED" if problems else "PASSED: the guards held and every block ran as written against a fake that misbehaves; no real model is measured by this"))
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

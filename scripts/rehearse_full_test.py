"""
Round 55: rehearse the paid full test (tier A) against a fake OpenRouter. Costs nothing, needs no key.

    python scripts/rehearse_full_test.py [--keep-report report.json]

It starts scripts/fake_openrouter.py, points the runtime at it (DELENTIA_OPENROUTER_BASE_URL, loopback only), sets a fake key, and runs
`scripts/full_test_orchestrator.py --execute` exactly as the Architect will run it with a real key: K.1.5 (T1/T2/T3), the Round 54 probe
(T4/T5), the spend meter, the stop rules and the T1-T9 table. If this passes, the plumbing is right; what the real run will tell you is how a
REAL model behaves, which a script cannot.

Exit code 0 only when the orchestrator finished, the table was produced, and the money the orchestrator measured matches what the fake
server charged.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep-report", default=None)
    args = parser.parse_args()
    import fake_openrouter
    import full_test_orchestrator as orch

    prices = {"rehearsal/model": {"in": 0.2, "out": 0.8}}
    work = Path(tempfile.mkdtemp(prefix="delentia-rehearsal-"))
    prices_file = work / "prices.json"
    prices_file.write_text(json.dumps(prices), encoding="utf-8")
    report_file = Path(args.keep_report) if args.keep_report else work / "report.json"
    with fake_openrouter.start(prices) as fake:
        os.environ.update({"DELENTIA_OPENROUTER_BASE_URL": fake.base_url, "OPENROUTER_API_KEY": fake.key, "DELENTIA_RUN_LIVE_TESTS": "1"})
        code = orch.main(["--tier", "A", "--models", "rehearsal/model", "--budget-usd", "5", "--prices-file", str(prices_file), "--live-prices",
                          "--execute", "--out", str(report_file)])
        spent_by_fake = round(fake.spent, 4)
        calls = fake.calls
    report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.exists() else {}
    measured = report.get("spent_usd")
    print(f"\nfake server: {calls} model calls, charged ${spent_by_fake}; orchestrator measured ${measured}; exit code {code}")
    problems = []
    if code != 0:
        problems.append(f"the orchestrator exited with {code} ({report.get('stopped')})")
    if "table" not in report:
        problems.append("no report table was written")
    if measured is None or abs(float(measured) - spent_by_fake) > 0.0002:
        problems.append("the orchestrator's measured spend does not match what the fake server charged")
    if calls < 10:
        problems.append("the stages made suspiciously few model calls")
    for p in problems:
        print(f"PROBLEM: {p}")
    print("REHEARSAL " + ("FAILED" if problems else "PASSED: the paid path works end to end against a fake; the real model is still unmeasured"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

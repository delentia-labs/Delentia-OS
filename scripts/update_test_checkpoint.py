"""
Round 90: move the public test checkpoint (passed / skipped / coverage / CI run / commit / date) in ONE command instead of by hand in five files.

    python scripts/update_test_checkpoint.py --passed 7820 --skipped 43 --coverage 91.37 --run 39122730330 --sha 3dbed0d --date 2026-10-18 [--write]

Without --write it only prints what would change. The numbers must come from a completed CI run on main (the script does not read CI; it does not invent anything): look them up with
`gh run view <run> --log | grep -E "passed|Total coverage"` for the Python 3.12 job. It rewrites the lines that carry the previous checkpoint in README.md, docs/testing/TESTING_CANONICAL.md,
docs/distribution/CLAIM_REGISTRY.md and docs/benchmark/methodology.md; afterwards `python scripts/check_claim_sync.py` must pass.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "docs/testing/TESTING_CANONICAL.md", "docs/distribution/CLAIM_REGISTRY.md", "docs/benchmark/methodology.md"]
CANON = ROOT / "docs" / "testing" / "TESTING_CANONICAL.md"


def current() -> dict:
    text = CANON.read_text(encoding="utf-8")
    m = re.search(r"\*\*Authoritative checkpoint:\*\* \*\*(?P<passed>[\d,]+) passed · (?P<skipped>[\d,]+) skipped · (?P<failed>[\d,]+) failed · (?P<coverage>[\d.]+)% coverage\*\*", text)
    if not m:
        sys.exit("cannot read the current checkpoint from TESTING_CANONICAL.md")
    run = re.search(r"run (\d{9,})", text)
    sha = re.search(r"commit ([0-9a-f]{7,40})", text)
    date = re.search(r"\*\*Last Updated:\*\* (\d{4}-\d{2}-\d{2})", text)
    return {"passed": m["passed"], "skipped": m["skipped"], "coverage": m["coverage"], "run": run.group(1) if run else "", "sha": sha.group(1) if sha else "", "date": date.group(1) if date else ""}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--passed", type=int, required=True)
    ap.add_argument("--skipped", type=int, required=True)
    ap.add_argument("--coverage", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    old = current()
    new = {"passed": f"{a.passed:,}", "skipped": f"{a.skipped:,}", "coverage": f"{float(a.coverage):.2f}", "run": a.run, "sha": a.sha, "date": a.date}
    changed = 0
    for rel in FILES:
        path = ROOT / rel
        lines = path.read_text(encoding="utf-8").split("\n")
        out = []
        for line in lines:
            carries = old["passed"] in line or (old["run"] and old["run"] in line) or f"{old['coverage']}%" in line
            if carries:
                fixed = line.replace(old["passed"], new["passed"])
                fixed = re.sub(rf"\b{old['skipped']} skipped", f"{new['skipped']} skipped", fixed)
                fixed = fixed.replace(f"{old['coverage']}%", f"{new['coverage']}%")
                if old["run"]:
                    fixed = fixed.replace(old["run"], new["run"])
                if old["sha"]:
                    fixed = fixed.replace(old["sha"], new["sha"])
                if old["date"]:
                    fixed = fixed.replace(old["date"], new["date"])
                if fixed != line:
                    changed += 1
                    print(f"{rel}: {line.strip()[:110]}\n   ->  {fixed.strip()[:110]}")
                line = fixed
            elif rel.endswith("TESTING_CANONICAL.md") and line.startswith("**Last Updated:**"):
                line = f"**Last Updated:** {new['date']}  "
            out.append(line)
        if a.write:
            path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"{changed} line(s) {'rewritten' if a.write else 'would change'}; old checkpoint {old}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

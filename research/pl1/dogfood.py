"""
PL1 G1 (research/LAUNCH_PL1_CRITERIA_R116.md): the owner's own tasks, recorded at the time, none removed afterwards.

    python -m research.pl1.dogfood add --task "..." --model anthropic/claude-haiku-5.5 --completed no --outcome "in my words" \
        --stop "pending_approval:needed" --approvals 1 --interventions 0 --cost 0.004
    python -m research.pl1.dogfood report

`add` appends one line to research/pl1/dogfood_log.jsonl (the file is append-only: this tool never rewrites or deletes a line). `completed` means the result was what the
owner wanted WITHOUT doing the work himself. `--stop reason:needed|unneeded` may be repeated (one per stop of the agent). `report` prints k of n with a Wilson 95% interval and
lists every row; no rate is claimed beyond these tasks.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOG = Path(__file__).resolve().parent / "dogfood_log.jsonl"
FIELDS = ("date", "task", "model", "completed", "outcome", "stops", "approvals", "interventions", "cost_usd")


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def parse_stop(text: str) -> Dict[str, Any]:
    reason, _, needed = text.rpartition(":")
    if not reason or needed not in ("needed", "unneeded"):
        raise SystemExit(f"--stop takes reason:needed or reason:unneeded, not {text!r}")
    return {"reason": reason, "needed": needed == "needed"}


def make_row(task: str, model: str, completed: str, outcome: str, stops: List[str], approvals: int, interventions: int, cost: float, when: Optional[str] = None) -> Dict[str, Any]:
    if completed not in ("yes", "no"):
        raise SystemExit("--completed is yes or no")
    if not task.strip() or not outcome.strip():
        raise SystemExit("a row needs the task and the outcome in your words")
    if approvals < 0 or interventions < 0 or not cost >= 0:
        raise SystemExit("approvals, interventions and cost cannot be negative")
    return {"date": when or date.today().isoformat(), "task": task.strip(), "model": model, "completed": completed == "yes", "outcome": outcome.strip(),
            "stops": [parse_stop(s) for s in stops], "approvals": approvals, "interventions": interventions, "cost_usd": cost}


def append(row: Dict[str, Any], log: Path = LOG) -> None:
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read(log: Path = LOG) -> List[Dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    k, n = sum(1 for r in rows if r.get("completed")), len(rows)
    lo, hi = wilson(k, n)
    unneeded = sum(1 for r in rows for s in r.get("stops", []) if not s.get("needed"))
    return {"completed": k, "tasks": n, "wilson95": [round(lo, 3), round(hi, 3)], "unneeded_stops": unneeded,
            "approvals": sum(r.get("approvals", 0) for r in rows), "interventions": sum(r.get("interventions", 0) for r in rows),
            "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in rows), 4)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--task", required=True)
    a.add_argument("--model", required=True)
    a.add_argument("--completed", required=True, choices=("yes", "no"))
    a.add_argument("--outcome", required=True)
    a.add_argument("--stop", action="append", default=[])
    a.add_argument("--approvals", type=int, default=0)
    a.add_argument("--interventions", type=int, default=0)
    a.add_argument("--cost", type=float, default=0.0)
    sub.add_parser("report")
    args = ap.parse_args(argv)
    if args.cmd == "add":
        row = make_row(args.task, args.model, args.completed, args.outcome, args.stop, args.approvals, args.interventions, args.cost)
        append(row)
        print(f"recorded task {len(read())}: completed={row['completed']}")
        return 0
    rows = read()
    s = summary(rows)
    print(f"completed {s['completed']} of {s['tasks']} (Wilson 95% {s['wilson95'][0]:.2f}-{s['wilson95'][1]:.2f}); unneeded stops {s['unneeded_stops']}; "
          f"approvals {s['approvals']}; interventions {s['interventions']}; cost ${s['cost_usd']}")
    for i, r in enumerate(rows, 1):
        print(f"  {i}. {r['date']} {'DONE' if r['completed'] else 'not done'} - {r['task'][:70]} | {r['outcome'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

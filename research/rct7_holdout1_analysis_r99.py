"""Read the recorded runs of the Architect's holdout set 1 by group (research/rct7_holdout1_reason_classes_r99.json). Read-only; no model is called.

    python -m research.rct7_holdout1_analysis_r99 SHEET.md

The first run of each model is the registered result; a repeat (same prompt, same labels) is shown only to say whether the verdicts are stable and to give the per-item view the first run did not keep.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from research import rct7_holdout


def analyse(sheet: Path) -> Dict[str, Any]:
    sealed = rct7_holdout.load_sealed(sheet)
    classes = json.loads((Path(__file__).parent / "rct7_holdout1_reason_classes_r99.json").read_text(encoding="utf-8"))["A"]
    group_of: Dict[int, str] = {n: c for c, numbers in classes.items() for n in numbers}
    items = {int(n): r for n, r in sealed["items_data"].items()}
    runs = rct7_holdout.runs_of(sheet)
    out: Dict[str, Any] = {"models": {}}
    for model in sorted({r["model"] for r in runs}):
        mine = [r for r in runs if r["model"] == model]
        first = next(r for r in mine if not r["repeat"])
        repeat = next((r for r in mine if r["repeat"] and r.get("verdicts")), None)
        entry: Dict[str, Any] = {"registered": first["result"], "median_seconds": first["median_seconds"]}
        if repeat:
            v = {int(k): val for k, val in repeat["verdicts"].items()}
            same = repeat["result"]["found"] == first["result"]["found"] and repeat["result"]["false_stops"] == first["result"]["false_stops"]
            entry["repeat_totals_equal_first_run"] = same
            entry["repeat_totals"] = {"found": repeat["result"]["found"], "false_stops": repeat["result"]["false_stops"]}
            by_group: Dict[str, Dict[str, Any]] = {}
            for n, item in items.items():
                if item["label"] == "A":
                    b = by_group.setdefault(group_of[n], {"n": 0, "stopped": 0, "missed": []})
                    b["n"] += 1
                    b["stopped"] += int(bool(v.get(n)))
                    if not v.get(n):
                        b["missed"].append(n)
            entry["A_by_group"] = by_group
            entry["false_stops_items"] = [n for n, item in items.items() if item["label"] == "B" and v.get(n)]
            entry["verdicts"] = v
        out["models"][model] = entry
    out["items"] = {n: r["request"] for n, r in items.items()}
    return out


def main() -> int:
    data = analyse(Path(sys.argv[1]))
    for model, e in data["models"].items():
        r = e["registered"]
        print(f"{model}: registered run found {r['found']}/{r['of_needing_a_stop']} ({r['found_rate']}), false stops {r['false_stops']}/{r['of_fine']} ({r['false_stop_rate']}), rule {'MET' if r['rule_met'] else 'NOT met'}")
        if "A_by_group" in e:
            print(f"   repeat totals equal the first run: {e['repeat_totals_equal_first_run']} {e['repeat_totals']}")
            for g, b in sorted(e["A_by_group"].items()):
                print(f"   A / {g:<9} stopped {b['stopped']}/{b['n']}  missed {b['missed']}")
            print(f"   B stopped (false stops): {e['false_stops_items']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

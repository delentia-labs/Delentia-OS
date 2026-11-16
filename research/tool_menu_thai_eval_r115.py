"""
Thai requests and the ranked tool menu: today's rule against the Thai table T1 (criteria: research/THAI_TOOL_MENU_CRITERIA_R115.md, committed before this script ran).

    python -m research.tool_menu_thai_eval_r115 [--holdout research/tool_menu_owner_holdout_r115.json] [--json out.json]

Sets: the development sentences the Architect ticked, the holdout (if given), the English external goals (guard a), the built-in dev and holdout goals (guard b), and 20 Thai requests that need no external tool
(guard c). Everything is free and offline: the real ranking code, no model.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
from contextlib import contextmanager
from pathlib import Path

from rct_control_plane import tool_menu
from research import tool_menu_siblings_r114 as sib

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "research" / "tool_menu_owner_choices_r115.json"
NEGATIVES = ROOT / "research" / "tool_menu_thai_negatives2_r115.json"      # Amendment 1: the second set is the guard; the first was used for tuning


@contextmanager
def switch(value):
    old = os.environ.get(tool_menu.THAI_MENU_ENV)
    if value is None:
        os.environ.pop(tool_menu.THAI_MENU_ENV, None)
    else:
        os.environ[tool_menu.THAI_MENU_ENV] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(tool_menu.THAI_MENU_ENV, None)
        else:
            os.environ[tool_menu.THAI_MENU_ENV] = old


def owner_cases(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for item in data["items"]:
        if not item.get("needs_confirmed"):
            continue
        for c in item["chosen"]:
            out.append({"id": item["id"], "topic": item["topic"], "goal": c["text"], "tag": c["tag"], "needs": item["needs"]})
    return out


def measure_cases(every, cases, k, state):
    with switch(state):
        rows = []
        for c in cases:
            shown = tool_menu.rank_tools(c["goal"], every, k)
            names = {t["name"] for t in shown}
            rows.append({**c, "size": len(shown), "ok": all(n in names for n in c["needs"]), "missing": [n for n in c["needs"] if n not in names],
                         "external": sum(1 for n in names if n.startswith("mcp__"))})
    return rows


def pct(rows):
    return round(100.0 * sum(1 for r in rows if r["ok"]) / len(rows), 1) if rows else None


def mean(rows, key):
    return round(statistics.mean(r[key] for r in rows), 2) if rows else None


def split(rows):
    out = {"all": rows}
    for t in ("L", "S", "I"):
        out[f"tag {t}"] = [r for r in rows if r["tag"] == t]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--holdout", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    k = tool_menu.top_k()
    spec = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
    every = asyncio.run(sib.builtin_tools()) + sib.synthetic_tools(spec["servers"])
    report = {"k": k, "tools": len(every)}
    sets = {"development (ticked, seen)": owner_cases(DEV)}
    if args.holdout:
        sets["HOLDOUT (ticked, not seen)"] = owner_cases(args.holdout)
    results = {}
    print(f"{len(every)} tools, menu size {k}")
    for name, cases in sets.items():
        today, t1 = measure_cases(every, cases, k, None), measure_cases(every, cases, k, "on")
        results[name] = {"today": today, "t1": t1}
        for part, ids in split(today).items():
            idx = {id(r) for r in ids}
            a = [r for r in today if id(r) in idx]
            b = [t1[i] for i, r in enumerate(today) if id(r) in idx]
            print(f"  {name:<28} {part:<7} n={len(a):>3}  today {pct(a):5.1f}%  T1 {pct(b):5.1f}%   mean menu {mean(a, 'size'):5.2f} -> {mean(b, 'size'):5.2f}")
        report[name] = {"today_pct": pct(today), "t1_pct": pct(t1), "menu_today": mean(today, "size"), "menu_t1": mean(t1, "size")}
        misses = [r for r in t1 if not r["ok"]]
        print(f"    T1 still misses a needed tool in {len(misses)} of {len(t1)} sentences")
    # guard c: Thai requests that need no external tool
    neg = [{"goal": g, "needs": [], "tag": "-", "topic": "-", "id": 0} for g in json.loads(NEGATIVES.read_text(encoding="utf-8"))["goals"]]
    n_today, n_t1 = measure_cases(every, neg, k, None), measure_cases(every, neg, k, "on")
    print(f"  negatives (Thai, no external tool needed) n={len(neg)}: external tools in the menu today {mean(n_today, 'external')} -> T1 {mean(n_t1, 'external')}; mean menu {mean(n_today, 'size')} -> {mean(n_t1, 'size')}")
    report["negatives"] = {"external_today": mean(n_today, "external"), "external_t1": mean(n_t1, "external"), "menu_today": mean(n_today, "size"), "menu_t1": mean(n_t1, "size")}
    # guards a and b
    with switch(None):
        a_today = sib.measure(every, spec["goals"], k)
        b_dev_today = sib.measure(every, json.loads(sib.BUILTIN.read_text(encoding="utf-8"))["dev"], k)
        b_hold_today = sib.measure(every, json.loads(sib.BUILTIN.read_text(encoding="utf-8"))["holdout"], k)
    with switch("on"):
        a_t1 = sib.measure(every, spec["goals"], k)
        b_dev_t1 = sib.measure(every, json.loads(sib.BUILTIN.read_text(encoding="utf-8"))["dev"], k)
        b_hold_t1 = sib.measure(every, json.loads(sib.BUILTIN.read_text(encoding="utf-8"))["holdout"], k)
    guards = {"english_external_44": (a_today["ranked"]["recall"], a_t1["ranked"]["recall"]), "builtin_dev": (b_dev_today["ranked"]["recall"], b_dev_t1["ranked"]["recall"]),
              "builtin_holdout": (b_hold_today["ranked"]["recall"], b_hold_t1["ranked"]["recall"])}
    for name, (x, y) in guards.items():
        print(f"  guard {name:<20} recall today {x * 100:5.1f}%  T1 {y * 100:5.1f}%  change {100 * (y - x):+.1f} points")
    report["guards"] = {n: {"today": x, "t1": y, "change_points": round(100 * (y - x), 2)} for n, (x, y) in guards.items()}
    # the adoption rule, only when a holdout was given
    if args.holdout:
        hold = results["HOLDOUT (ticked, not seen)"]
        gain = pct(hold["t1"]) - pct(hold["today"])
        growth = mean(hold["t1"], "size") - mean(hold["today"], "size")
        checks = {"holdout_share_at_least_70": pct(hold["t1"]) >= 70 - 1e-9, "holdout_gain_at_least_40_points": gain >= 40 - 1e-9, "holdout_menu_growth_at_most_3": growth <= 3 + 1e-9,
                  "negatives_external_at_most_1": mean(n_t1, "external") <= 1 + 1e-9,
                  "guards_loss_at_most_1_point": all((x - y) * 100 <= 1 + 1e-9 for x, y in guards.values())}
        report["adoption"] = {"gain_points": round(gain, 1), "menu_growth": round(growth, 2), "checks": checks, "propose_adoption": all(checks.values())}
        print("  adoption rule:", json.dumps(report["adoption"]))
    else:
        print("  (no holdout given: the adoption rule is not evaluated)")
    if args.json:
        Path(args.json).write_text(json.dumps({"report": report, "rows": {k_: {kk: vv for kk, vv in v.items()} for k_, v in results.items()}}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Candidate A1 (Thai hints per external tool), criteria: research/THAI_TOOL_MENU_AMENDMENT_3_R115.md. Free, offline: the real ranking code and a committed hints file; no model is called.

    python -m research.tool_menu_hints_eval_r115 --hints research/tool_hints_th_synthetic_r115.json [--third research/tool_menu_owner_third_r115.json] [--json out.json]

Rows: development (seen), the second form (seen by T1 and E1; a second look), the third form (the decision, only when given). Guards: first negative set (development), THIRD negative set (rule 3),
44 English goals, built-in dev and holdout.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path

from rct_control_plane import tool_hints_th as th
from rct_control_plane import tool_menu
from research import tool_menu_siblings_r114 as sib
from research import tool_menu_thai_eval_r115 as ev

ROOT = Path(__file__).resolve().parent.parent
NEG1 = ROOT / "research" / "tool_menu_thai_negatives_r115.json"
NEG3 = ROOT / "research" / "tool_menu_thai_negatives3_r115.json"
SECOND = ROOT / "research" / "tool_menu_owner_holdout_r115.json"


@contextmanager
def hints(path):
    old = {k: os.environ.get(k) for k in (th.SWITCH_ENV, th.PATH_ENV)}
    if path is None:
        os.environ.pop(th.SWITCH_ENV, None)
    else:
        os.environ[th.SWITCH_ENV], os.environ[th.PATH_ENV] = "on", str(path)
    th._cache.update(path=None, mtime=None, data={})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        th._cache.update(path=None, mtime=None, data={})


def run_cases(every, cases, k, path):
    with hints(path):
        rows = []
        for c in cases:
            shown = tool_menu.rank_tools(c["goal"], every, k)
            names = {t["name"] for t in shown}
            rows.append({**c, "size": len(shown), "ok": all(n in names for n in c["needs"]), "missing": [n for n in c["needs"] if n not in names], "external": sum(1 for n in names if n.startswith("mcp__"))})
    return rows


def negs(path):
    return [{"goal": g, "needs": [], "tag": "-", "topic": "-", "id": 0} for g in json.loads(Path(path).read_text(encoding="utf-8"))["goals"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hints", required=True)
    ap.add_argument("--third", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    k = tool_menu.top_k()
    spec = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
    every = asyncio.run(sib.builtin_tools()) + sib.synthetic_tools(spec["servers"])
    stored = th.load(Path(args.hints))
    valid = sum(1 for t in every if str(t["name"]).startswith("mcp__") and stored.get(t["name"], {}).get("for") == th.fingerprint(t))
    print(f"{len(every)} tools, menu size {k}; hints file {args.hints}: {valid} of 19 external tools have a valid hint")
    sets = {"development (seen)": ev.owner_cases(ev.DEV), "second form (seen by T1, E1)": ev.owner_cases(SECOND)}
    if args.third:
        sets["THIRD FORM (decision)"] = ev.owner_cases(args.third)
    report, kept = {"valid_hints": valid}, {}
    for name, cases in sets.items():
        today, a1 = run_cases(every, cases, k, None), run_cases(every, cases, k, args.hints)
        kept[name] = (today, a1)
        for part in ("all", "L", "S", "I"):
            sel = [i for i, r in enumerate(today) if part == "all" or r["tag"] == part]
            a, b = [today[i] for i in sel], [a1[i] for i in sel]
            print(f"  {name:<30} {part:<4} n={len(a):>3}  today {ev.pct(a):5.1f}%  A1 {ev.pct(b):5.1f}%  mean menu {ev.mean(a, 'size'):5.2f} -> {ev.mean(b, 'size'):5.2f}")
        report[name] = {"today": ev.pct(today), "a1": ev.pct(a1), "menu_today": ev.mean(today, "size"), "menu_a1": ev.mean(a1, "size")}
        print(f"    A1 still misses a needed tool in {sum(1 for r in a1 if not r['ok'])} of {len(a1)} sentences")
    neg_report = {}
    for label, path in (("negatives1 (development)", NEG1), ("negatives3 (rule 3)", NEG3)):
        n0, n1 = run_cases(every, negs(path), k, None), run_cases(every, negs(path), k, args.hints)
        neg_report[label] = (ev.mean(n0, "external"), ev.mean(n1, "external"), ev.mean(n1, "size"))
        print(f"  {label:<28} external tools in the menu per request: today {ev.mean(n0, 'external')} -> A1 {ev.mean(n1, 'external')}; mean menu {ev.mean(n0, 'size')} -> {ev.mean(n1, 'size')}")
    report["negatives"] = {k_: {"today": v[0], "a1": v[1], "menu_a1": v[2]} for k_, v in neg_report.items()}
    builtin = json.loads(sib.BUILTIN.read_text(encoding="utf-8"))
    guards = {}
    for name, goals in (("english_external_44", spec["goals"]), ("builtin_dev", builtin["dev"]), ("builtin_holdout", builtin["holdout"])):
        c = [{"goal": g["goal"], "needs": g["needs"], "tag": "-", "topic": "-", "id": 0} for g in goals]
        a, b = run_cases(every, c, k, None), run_cases(every, c, k, args.hints)
        guards[name] = (ev.pct(a), ev.pct(b))
        print(f"  guard {name:<20} today {ev.pct(a):5.1f}%  A1 {ev.pct(b):5.1f}%  change {ev.pct(b) - ev.pct(a):+.1f} points")
    report["guards"] = {n: {"today": a, "a1": b} for n, (a, b) in guards.items()}
    if args.third:
        today, a1 = kept["THIRD FORM (decision)"]
        gain, growth = ev.pct(a1) - ev.pct(today), ev.mean(a1, "size") - ev.mean(today, "size")
        checks = {"third_share_at_least_70": ev.pct(a1) >= 70 - 1e-9, "third_gain_at_least_40_points": gain >= 40 - 1e-9, "menu_growth_at_most_3": growth <= 3 + 1e-9,
                  "negatives3_external_at_most_1": neg_report["negatives3 (rule 3)"][1] <= 1 + 1e-9, "guards_loss_at_most_1_point": all(a - b <= 1 + 1e-9 for a, b in guards.values())}
        report["adoption"] = {"gain_points": round(gain, 1), "menu_growth": round(growth, 2), "checks": checks, "propose_adoption": all(checks.values()),
                              "rules_5_and_6": "rule 5 is pinned by tests/test_thai_hints_round115_real.py; rule 6 is the generation time printed by research/make_thai_hints_r115.py"}
        print("  adoption rule:", json.dumps(report["adoption"]))
    else:
        print("  (no third form given: the adoption rule is not evaluated)")
    if args.json:
        Path(args.json).write_text(json.dumps({"report": report, "rows": {n: {"today": t, "a1": a} for n, (t, a) in kept.items()}}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

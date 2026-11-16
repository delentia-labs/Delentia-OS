"""
Candidate R3 (external tools always in the menu): the share of sentences with every needed tool, and the COST in tokens (criteria: research/THAI_TOOL_MENU_AMENDMENT_4_R115.md). Free, offline, tiktoken.

    python -m research.tool_menu_keep_external_eval_r115 [--json out.json]
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
from research import tool_menu_thai_eval_r115 as ev

SECOND = Path(__file__).resolve().parent / "tool_menu_owner_holdout_r115.json"


@contextmanager
def keep(value, maximum=None):
    old = {k: os.environ.get(k) for k in (tool_menu.KEEP_EXTERNAL_ENV, tool_menu.KEEP_EXTERNAL_MAX_ENV)}
    for k, v in ((tool_menu.KEEP_EXTERNAL_ENV, value), (tool_menu.KEEP_EXTERNAL_MAX_ENV, None if maximum is None else str(maximum))):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def tokens(text):
    import tiktoken
    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def cases_for(goals):
    return [{"id": 0, "topic": "-", "goal": g["goal"], "tag": "-", "needs": g["needs"]} for g in goals]


def measure(every, cases, k, state):
    with keep(state):
        rows = []
        for c in cases:
            shown = tool_menu.rank_tools(c["goal"], every, k)
            names = {t["name"] for t in shown}
            rows.append({"ok": all(n in names for n in c["needs"]), "size": len(shown), "tokens": tokens(tool_menu.format_menu(shown, compact=True))})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    k = tool_menu.top_k()
    spec = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
    builtin_tools = asyncio.run(sib.builtin_tools())
    external = sib.synthetic_tools(spec["servers"])
    every = builtin_tools + external
    full_tokens = tokens(tool_menu.format_menu(every, compact=False))
    sets = {"development (119, Thai)": ev.owner_cases(ev.DEV), "second form (89, Thai)": ev.owner_cases(SECOND), "English external goals (44)": cases_for(spec["goals"])}
    report = {"full_menu_tokens_all_tools_full_format": full_tokens}
    print(f"{len(every)} tools ({len(external)} external); the full menu in the full format is {full_tokens} tokens")
    for name, cases in sets.items():
        a, b = measure(every, cases, k, None), measure(every, cases, k, "on")
        pa, pb = round(100 * sum(r["ok"] for r in a) / len(a), 1), round(100 * sum(r["ok"] for r in b) / len(b), 1)
        ta, tb = round(statistics.mean(r["tokens"] for r in a)), round(statistics.mean(r["tokens"] for r in b))
        print(f"  {name:<30} all needed tools present: today {pa:5.1f}%  R3 {pb:5.1f}%   mean menu tokens (compact): today {ta} -> R3 {tb}   mean tools {statistics.mean(r['size'] for r in a):.1f} -> {statistics.mean(r['size'] for r in b):.1f}")
        report[name] = {"today_pct": pa, "r3_pct": pb, "tokens_today": ta, "tokens_r3": tb}
    # scaling: the first n synthetic tools as the external set
    print("  scaling (development sentences that need only tools among the first n external tools are not selected: all 119 are used; tokens are what matters):")
    scaling = {}
    dev = ev.owner_cases(ev.DEV)
    for n in (5, 10, 19):
        sub = builtin_tools + external[:n]
        with keep("on"):
            t = round(statistics.mean(tokens(tool_menu.format_menu(tool_menu.rank_tools(c["goal"], sub, k), compact=True)) for c in dev))
        with keep(None):
            t0 = round(statistics.mean(tokens(tool_menu.format_menu(tool_menu.rank_tools(c["goal"], sub, k), compact=True)) for c in dev))
        scaling[n] = (t0, t)
        print(f"    {n:>2} external tools: today {t0} tokens, R3 {t} tokens")
    # 40 external tools: repeat the 19 with distinct names
    many = builtin_tools + [{**e, "name": f"{e['name']}_{i}"} for i in range(3) for e in external][:40]
    with keep("on"):
        t40 = round(statistics.mean(tokens(tool_menu.format_menu(tool_menu.rank_tools(c["goal"], many, k), compact=True)) for c in dev))
    with keep(None):
        t40_0 = round(statistics.mean(tokens(tool_menu.format_menu(tool_menu.rank_tools(c["goal"], many, k), compact=True)) for c in dev))
    scaling[40] = (t40_0, t40)
    print(f"    40 external tools: today {t40_0} tokens, R3 {t40} tokens (the maximum, still on)")
    per_tool = (scaling[19][1] - scaling[5][1]) / 14
    breakeven = round((full_tokens - scaling[5][1]) / per_tool + 5) if per_tool > 0 else None
    print(f"  about {per_tool:.0f} tokens per extra external tool; listing them all would cost as much as the full menu at about {breakeven} external tools")
    report["scaling"] = {str(n): {"today": a, "r3": b} for n, (a, b) in scaling.items()}
    report["tokens_per_external_tool"] = round(per_tool, 1)
    report["breakeven_external_tools"] = breakeven
    two = report["development (119, Thai)"], report["second form (89, Thai)"], report["English external goals (44)"]
    checks = {"presence_at_least_95_on_all_three_sets": all(r["r3_pct"] >= 95 - 1e-9 for r in two), "tokens_with_19_external_at_most_2500": scaling[19][1] <= 2500}
    builtin = json.loads(sib.BUILTIN.read_text(encoding="utf-8"))
    for name in ("dev", "holdout"):
        c = cases_for(builtin[name])
        a, b = measure(every, c, k, None), measure(every, c, k, "on")
        pa, pb = 100 * sum(r["ok"] for r in a) / len(a), 100 * sum(r["ok"] for r in b) / len(b)
        print(f"  guard built-in {name:<8} today {pa:5.1f}%  R3 {pb:5.1f}%")
        checks[f"builtin_{name}_recall_not_lower"] = pb >= pa - 1e-9
    report["checks"] = checks
    report["propose"] = all(checks.values())
    print("  rule for proposing:", json.dumps(checks), "->", "PROPOSE" if report["propose"] else "NOT PROPOSED")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

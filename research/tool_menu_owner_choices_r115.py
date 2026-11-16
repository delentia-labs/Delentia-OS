"""
Does the ranked tool menu keep the tools a request needs, for the sentences the Architect ticked? (free, offline, no model; round two follow-up, 2026-11-16)

Written before the first run (the rule is the one stated in the form the Architect filled in and in research/ROUND_TWO_AMENDMENT_5_R114.md section 3):
candidate rule R1 (keep the write tools of an external server when one of its read tools is in the menu) is proposed for adoption only if, on these sentences, the share of sentences whose needed tools are ALL in the
menu rises by at least 10 percentage points, the mean menu grows by at most 2 tools, and on the built-in holdout recall falls by no more than 1 point.

Each ticked sentence is one case. Its needed tools are the ones the situation lists and the Architect confirmed. The sentences were written by the assistant, so this measures 'the phrasings the Architect finds plausible',
not how often people say them. Results are also split by the kind of wording (L literal, S synonym, I indirect), which was recorded in the file and never shown to the Architect.

    python -m research.tool_menu_owner_choices_r115 [--json out.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
from pathlib import Path

from rct_control_plane import tool_menu
from research import tool_menu_siblings_r114 as sib

ROOT = Path(__file__).resolve().parent.parent
OWNER = ROOT / "research" / "tool_menu_owner_choices_r115.json"


def cases():
    data = json.loads(OWNER.read_text(encoding="utf-8"))
    out = []
    for item in data["items"]:
        if not item.get("needs_confirmed"):
            continue                                   # a situation the Architect did not confirm is not counted
        for c in item["chosen"]:
            out.append({"id": item["id"], "topic": item["topic"], "goal": c["text"], "tag": c["tag"], "needs": item["needs"]})
    return out


def run(k):
    spec = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
    every = asyncio.run(sib.builtin_tools()) + sib.synthetic_tools(spec["servers"])
    rows = []
    for c in cases():
        shown = tool_menu.rank_tools(c["goal"], every, k)
        with_r1 = sib.add_write_siblings(shown, every)
        names, names1 = {t["name"] for t in shown}, {t["name"] for t in with_r1}
        rows.append({**c, "size": len(shown), "size_r1": len(with_r1), "ok": all(n in names for n in c["needs"]), "ok_r1": all(n in names1 for n in c["needs"]),
                     "missing": [n for n in c["needs"] if n not in names], "missing_r1": [n for n in c["needs"] if n not in names1]})
    return every, rows


def summarise(rows):
    def share(sel, key):
        return round(100.0 * sum(1 for r in sel if r[key]) / len(sel), 1) if sel else None
    groups = {"all": rows, **{f"tag {t}": [r for r in rows if r["tag"] == t] for t in ("L", "S", "I")}, **{f"topic {t}": [r for r in rows if r["topic"] == t] for t in ("note", "ticket", "calendar", "mail", "multi")}}
    return {name: {"n": len(sel), "ranked_all_tools_present_pct": share(sel, "ok"), "r1_all_tools_present_pct": share(sel, "ok_r1"),
                   "mean_menu_ranked": round(statistics.mean(r["size"] for r in sel), 2), "mean_menu_r1": round(statistics.mean(r["size_r1"] for r in sel), 2)} for name, sel in groups.items() if sel}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    k = tool_menu.top_k()
    every, rows = run(k)
    summary = summarise(rows)
    builtin = json.loads(sib.BUILTIN.read_text(encoding="utf-8"))
    holdout = sib.measure(every, builtin["holdout"], k)
    allrow = summary["all"]
    gain = allrow["r1_all_tools_present_pct"] - allrow["ranked_all_tools_present_pct"]
    growth = allrow["mean_menu_r1"] - allrow["mean_menu_ranked"]
    loss = (holdout["ranked"]["recall"] - holdout["R1"]["recall"]) * 100
    checks = {"gain_points_at_least_10": gain >= 10 - 1e-9, "mean_menu_growth_at_most_2": growth <= 2 + 1e-9, "builtin_holdout_loss_points_at_most_1": loss <= 1 + 1e-9}
    verdict = {"gain_points": round(gain, 1), "mean_menu_growth": round(growth, 2), "builtin_holdout_loss_points": round(loss, 1), "checks": checks, "propose_adoption": all(checks.values())}
    print(f"{len(every)} tools in the list, menu size {k}, {len(rows)} sentences")
    for name, s in summary.items():
        print(f"  {name:<14} n={s['n']:>3}  ranked: all tools present {s['ranked_all_tools_present_pct']:5.1f}%  mean menu {s['mean_menu_ranked']:5.2f}   |   R1: {s['r1_all_tools_present_pct']:5.1f}%  mean menu {s['mean_menu_r1']:5.2f}")
    print("  verdict:", json.dumps(verdict))
    misses = [r for r in rows if not r["ok"]]
    print(f"  sentences with a needed tool missing from the ranked menu: {len(misses)} of {len(rows)}")
    if args.json:
        Path(args.json).write_text(json.dumps({"k": k, "summary": summary, "verdict": verdict, "builtin_holdout": {kk: {x: v for x, v in vv.items() if x != "rows"} for kk, vv in holdout.items()},
                                               "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

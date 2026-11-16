"""
Candidate E1 (research/THAI_TOOL_MENU_AMENDMENT_2_R115.md, written before this ran): for a Thai request, add to today's lexical menu the `m` external tools closest in meaning (cosine of bge-m3 vectors) with cosine >= tau.

    python -m research.tool_menu_embed_eval_r115 grid               # development sentences + first negative set only: chooses (m, tau)
    python -m research.tool_menu_embed_eval_r115 holdout --m 4 --tau 0.4   # the holdout, run ONCE with the chosen setting

Free and local: the real ranking code and the local embedding model; no hosted model, no network.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import time
from pathlib import Path

from rct_control_plane import memory_embeddings as me
from rct_control_plane import tool_menu
from research import tool_menu_siblings_r114 as sib
from research import tool_menu_thai_eval_r115 as ev

ROOT = Path(__file__).resolve().parent.parent
HOLDOUT = ROOT / "research" / "tool_menu_owner_holdout_r115.json"
NEG1 = ROOT / "research" / "tool_menu_thai_negatives_r115.json"
NEG2 = ROOT / "research" / "tool_menu_thai_negatives2_r115.json"
MODEL = "bge-m3"
THAI = tool_menu._THAI_CHAR


def tool_text(t):
    name = str(t["name"]).replace("mcp__", "").replace("__", " ").replace("_", " ")
    return f"{name}. {t.get('description') or ''}"[:400]


class Embedder:
    def __init__(self, tools):
        self.tools = tools
        self.ext = [i for i, t in enumerate(tools) if str(t["name"]).startswith("mcp__")]
        vecs = me.embed([tool_text(tools[i]) for i in self.ext], MODEL)
        if vecs is None:
            raise SystemExit("the embedding service did not answer (is Ollama running with bge-m3?)")
        self.vec = dict(zip(self.ext, vecs))
        self.cache = {}
        self.times = []

    def sims(self, goal):
        if goal not in self.cache:
            t0 = time.perf_counter()
            v = me.embed([goal], MODEL)
            self.times.append(time.perf_counter() - t0)
            if v is None:
                raise SystemExit("the embedding service stopped answering")
            self.cache[goal] = {i: me.cosine(v[0], self.vec[i]) for i in self.ext}
        return self.cache[goal]


def menu(goal, tools, k, emb, m, tau):
    shown = tool_menu.rank_tools(goal, tools, k)
    if not THAI.search(goal) or m <= 0:
        return shown
    names = {t["name"] for t in shown}
    sims = emb.sims(goal)
    best = [i for i in sorted(sims, key=lambda i: -sims[i])[:m] if sims[i] >= tau and tools[i]["name"] not in names]
    return shown + [tools[i] for i in best]


def evaluate(tools, cases, k, emb, m, tau):
    rows = []
    for c in cases:
        shown = menu(c["goal"], tools, k, emb, m, tau)
        names = {t["name"] for t in shown}
        rows.append({**c, "size": len(shown), "ok": all(n in names for n in c["needs"]), "external": sum(1 for n in names if n.startswith("mcp__"))})
    return rows


def negatives(path):
    return [{"goal": g, "needs": [], "tag": "-", "topic": "-", "id": 0} for g in json.loads(Path(path).read_text(encoding="utf-8"))["goals"]]


def main():
    logging.disable(logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["grid", "holdout"])
    ap.add_argument("--m", type=int, default=4)
    ap.add_argument("--tau", type=float, default=0.4)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    k = tool_menu.top_k()
    spec = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
    tools = asyncio.run(sib.builtin_tools()) + sib.synthetic_tools(spec["servers"])
    emb = Embedder(tools)
    dev = ev.owner_cases(ev.DEV)
    out = {}
    if args.mode == "grid":
        neg1 = negatives(NEG1)
        results = []
        for m in (3, 4, 5, 6):
            for tau in (0.30, 0.35, 0.40, 0.45, 0.50):
                rows = evaluate(tools, dev, k, emb, m, tau)
                nrows = evaluate(tools, neg1, k, emb, m, tau)
                results.append({"m": m, "tau": tau, "dev_pct": ev.pct(rows), "dev_menu": ev.mean(rows, "size"), "neg1_external": ev.mean(nrows, "external")})
        base = evaluate(tools, dev, k, emb, 0, 1.0)
        print(f"today: development {ev.pct(base)}%")
        for r in results:
            print(f"  m={r['m']} tau={r['tau']:.2f}  dev {r['dev_pct']:5.1f}%  menu {r['dev_menu']:5.2f}  negatives1 external {r['neg1_external']:.2f}")
        ok = [r for r in results if r["neg1_external"] <= 1.0]
        best = sorted(ok, key=lambda r: (-r["dev_pct"], r["m"], -r["tau"]))[0] if ok else None
        print("chosen (highest dev share with negatives1 external <= 1; ties: smaller m, larger tau):", json.dumps(best))
        out = {"grid": results, "chosen": best}
    else:
        hold = ev.owner_cases(HOLDOUT)
        today = evaluate(tools, hold, k, emb, 0, 1.0)
        e1 = evaluate(tools, hold, k, emb, args.m, args.tau)
        n2_today = evaluate(tools, negatives(NEG2), k, emb, 0, 1.0)
        n2 = evaluate(tools, negatives(NEG2), k, emb, args.m, args.tau)
        for name, rows0, rows1 in (("HOLDOUT all", today, e1), ("tag L", [r for r in today if r["tag"] == "L"], [r for r in e1 if r["tag"] == "L"]),
                                   ("tag S", [r for r in today if r["tag"] == "S"], [r for r in e1 if r["tag"] == "S"]), ("tag I", [r for r in today if r["tag"] == "I"], [r for r in e1 if r["tag"] == "I"])):
            print(f"  {name:<12} n={len(rows0):>3}  today {ev.pct(rows0):5.1f}%  E1 {ev.pct(rows1):5.1f}%  mean menu {ev.mean(rows0, 'size'):5.2f} -> {ev.mean(rows1, 'size'):5.2f}")
        print(f"  negatives2: external tools today {ev.mean(n2_today, 'external')} -> E1 {ev.mean(n2, 'external')}")
        spec_b = json.loads(sib.BUILTIN.read_text(encoding="utf-8"))
        guards = {}
        for name, goals in (("english_external_44", spec["goals"]), ("builtin_dev", spec_b["dev"]), ("builtin_holdout", spec_b["holdout"])):
            c = [{"goal": g["goal"], "needs": g["needs"], "tag": "-", "topic": "-", "id": 0} for g in goals]
            a, b = evaluate(tools, c, k, emb, 0, 1.0), evaluate(tools, c, k, emb, args.m, args.tau)
            guards[name] = (ev.pct(a), ev.pct(b))
            print(f"  guard {name:<20} today {ev.pct(a):5.1f}%  E1 {ev.pct(b):5.1f}%  change {ev.pct(b) - ev.pct(a):+.1f} points")
        times = sorted(emb.times)
        median_ms = round(1000 * statistics.median(times), 1) if times else None
        print(f"  extra time per Thai request (embedding one request, tool vectors cached): median {median_ms} ms over {len(times)} requests")
        gain = ev.pct(e1) - ev.pct(today)
        growth = ev.mean(e1, "size") - ev.mean(today, "size")
        checks = {"holdout_share_at_least_70": ev.pct(e1) >= 70 - 1e-9, "holdout_gain_at_least_40_points": gain >= 40 - 1e-9, "menu_growth_at_most_3": growth <= 3 + 1e-9,
                  "negatives2_external_at_most_1": ev.mean(n2, "external") <= 1 + 1e-9, "guards_loss_at_most_1_point": all(a - b <= 1 + 1e-9 for a, b in guards.values()),
                  "median_extra_time_at_most_150_ms": median_ms is not None and median_ms <= 150}
        verdict = {"gain_points": round(gain, 1), "menu_growth": round(growth, 2), "checks": checks, "propose_adoption": all(checks.values()),
                   "rule_6_service_down_equals_today": "tested separately by the unit tests (the add-on is skipped when the service does not answer)"}
        print("  adoption rule:", json.dumps(verdict))
        out = {"m": args.m, "tau": args.tau, "verdict": verdict, "holdout_today": ev.pct(today), "holdout_e1": ev.pct(e1)}
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

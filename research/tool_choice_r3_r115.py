"""
A real model chooses the first tool from today's ranked menu and from the R3 menu (criteria: research/THAI_TOOL_MENU_AMENDMENT_5_R115.md, written before this script).

    python -m research.tool_choice_r3_r115 --model anthropic/claude-haiku-5.5 --price-in 0.1 --price-out 0.5 --budget-usd 0.25            # dry run: counts the calls, spends nothing
    python -m research.tool_choice_r3_r115 --model ... --price-in ... --price-out ... --budget-usd 0.25 --execute --out DIR           # real calls (needs the key, the opt-in and the freeze)

One decision per goal and arm, nothing is executed. The prompt is the loop's real prompt (`autonomous_loop.decide_next_action`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research import tool_menu_siblings_r114 as sib  # noqa: E402
from research import tool_menu_thai_eval_r115 as ev  # noqa: E402

SECOND = ROOT / "research" / "tool_menu_owner_holdout_r115.json"
NEG3 = ROOT / "research" / "tool_menu_thai_negatives3_r115.json"
ARMS = ("today", "r3")
RAW_CHARS = 600


class Recorder:
    """Wraps a provider and records, per model call, what the criteria of Amendment 13 want read afterwards: the tokens, the provider-reported cost, who answered and the raw reply.
    A decision can make two calls (the loop asks once more when a reply cannot be read), so `take()` returns every call since the last take."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._calls: List[Dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def complete(self, *args: Any, **kwargs: Any) -> str:
        entry: Dict[str, Any] = {"raw": None}
        try:
            text = await self._inner.complete(*args, **kwargs)
        except Exception as exc:                                       # noqa: BLE001 - recorded, then raised as before
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            self._calls.append(entry)
            raise
        usage = getattr(self._inner, "last_usage", None)
        entry.update({"prompt_tokens": getattr(usage, "prompt_tokens", None), "completion_tokens": getattr(usage, "completion_tokens", None),
                      "cost_usd": getattr(usage, "cost_usd", None), "served_by": getattr(self._inner, "last_served_by", None), "raw": str(text)[:RAW_CHARS]})
        self._calls.append(entry)
        return text

    def take(self) -> List[Dict[str, Any]]:
        calls, self._calls = self._calls, []
        return calls


def goal_sets(spec: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    thai = [{"goal": c["goal"], "needs": c["needs"], "id": c["id"]} for c in ev.owner_cases(SECOND)]
    english = [{"goal": g["goal"], "needs": g["needs"], "id": g.get("id", "")} for g in spec["goals"]]
    negatives = [{"goal": g, "needs": [], "id": "n"} for g in json.loads(NEG3.read_text(encoding="utf-8"))["goals"]]
    return {"thai_89": thai, "english_44": english, "negatives_20": negatives}


def score(decision: Dict[str, Any], needs: List[str]) -> str:
    """right / wrong_tool / finished_without_tool / unparsed for goals that need a tool; for the negatives (needs == []) external_use when the first tool called is external, else ok."""
    if decision.get("parse_error"):
        return "unparsed"
    calls = decision.get("calls") if isinstance(decision.get("calls"), list) else []
    first = decision.get("tool_name") or next((c.get("tool_name") for c in calls if isinstance(c, dict) and c.get("tool_name")), None)
    if not needs:
        return "external_use" if str(first or "").startswith("mcp__") else "ok"
    if decision.get("action") == "finish" and not first:
        return "finished_without_tool"
    if first in needs:
        return "right"
    if any(isinstance(c, dict) and c.get("tool_name") in needs for c in calls):
        return "right"
    return "wrong_tool"


async def run(provider: Any, sets: Dict[str, List[Dict[str, Any]]], tools: List[Dict[str, Any]], decide: Callable, usage: Optional[Callable[[], float]] = None,
              stop_at_usd: Optional[float] = None, k: int = 10, limit_per_set: Optional[int] = None, keep_raw: bool = False) -> Dict[str, Any]:
    from rct_control_plane import tool_menu
    saved = {n: os.environ.get(n) for n in (tool_menu.FORMAT_ENV, tool_menu.KEEP_EXTERNAL_ENV)}
    os.environ[tool_menu.FORMAT_ENV] = "compact"
    rows: List[Dict[str, Any]] = []
    stopped = None
    spent, dearest = 0.0, 0.0                   # the local meter of Amendment 13: the sum of the provider-reported costs, and the dearest decision so far
    try:
        for set_name, goals in sets.items():
            for item in (goals if limit_per_set is None else goals[:limit_per_set]):
                for arm in ARMS:
                    if usage is not None and stop_at_usd is not None and len(rows) % 10 == 0 and usage() >= stop_at_usd:
                        stopped = f"stopped at {usage():.4f} of the ceiling {stop_at_usd:.4f} after {len(rows)} decisions"
                        raise StopIteration
                    if stop_at_usd is not None and spent + dearest >= stop_at_usd:
                        stopped = f"stopped by the local meter at {spent:.4f} (the next decision may cost up to {dearest:.4f}) of the ceiling {stop_at_usd:.4f} after {len(rows)} decisions"
                        raise StopIteration
                    if arm == "r3":
                        os.environ[tool_menu.KEEP_EXTERNAL_ENV] = "on"
                    else:
                        os.environ[tool_menu.KEEP_EXTERNAL_ENV] = "off"          # the 'today' arm is the menu of before R3 became the default
                    menu = tool_menu.rank_tools(item["goal"], tools, k)
                    try:
                        decision = await decide(item["goal"], [], menu, llm_provider=provider)
                        verdict, error = score(decision, item["needs"]), None
                    except Exception as exc:                                       # noqa: BLE001 - recorded as an error, never hidden
                        decision, verdict, error = {}, "error", f"{type(exc).__name__}: {exc}"[:140]
                    calls = provider.take() if hasattr(provider, "take") else []
                    cost = sum(c["cost_usd"] for c in calls if isinstance(c.get("cost_usd"), (int, float)))
                    spent, dearest = spent + cost, max(dearest, cost)
                    if not (keep_raw or verdict in ("unparsed", "error")):
                        for c in calls:
                            c["raw"] = None                                          # the raw reply is kept for every unreadable or errored one, and for all with --keep-raw
                    rows.append({"set": set_name, "arm": arm, "goal": item["goal"], "needs": item["needs"], "menu_tools": len(menu), "verdict": verdict, "error": error,
                                 "chose": decision.get("tool_name") or next((c.get("tool_name") for c in (decision.get("calls") or []) if isinstance(c, dict)), None),
                                 "calls": calls, "cost_usd": round(cost, 6)})
    except StopIteration:
        pass
    finally:
        for n, v in saved.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v
    return {"rows": rows, "stopped": stopped}


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for set_name in sorted({r["set"] for r in rows}):
        for arm in ARMS:
            sel = [r for r in rows if r["set"] == set_name and r["arm"] == arm]
            if not sel:
                continue
            counts: Dict[str, int] = {}
            for r in sel:
                counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
            out[f"{set_name}/{arm}"] = {"n": len(sel), "counts": counts, "median_menu_tools": sorted(r["menu_tools"] for r in sel)[len(sel) // 2]}
    return out


def verdict_of(rows: List[Dict[str, Any]], ceiling_ok: bool = True) -> Dict[str, Any]:
    def count(set_name, arm, v):
        return sum(1 for r in rows if r["set"] == set_name and r["arm"] == arm and r["verdict"] == v)

    def total(set_name, arm):
        return sum(1 for r in rows if r["set"] == set_name and r["arm"] == arm)

    if not rows or any(total(s, a) == 0 for s in ("thai_89", "english_44", "negatives_20") for a in ARMS):
        return {"complete": False, "propose": False, "why": "the run did not reach every set and arm"}
    bad = {a: sum(1 for r in rows if r["arm"] == a and r["verdict"] in ("error", "unparsed")) / max(1, sum(1 for r in rows if r["arm"] == a)) for a in ARMS}
    thai_gain = 100.0 * (count("thai_89", "r3", "right") - count("thai_89", "today", "right")) / total("thai_89", "today")
    english_diff = count("english_44", "today", "right") - count("english_44", "r3", "right")
    false_use_more = count("negatives_20", "r3", "external_use") - count("negatives_20", "today", "external_use")
    checks = {"thai_gain_at_least_15_points": thai_gain >= 15 - 1e-9, "english_within_1_goal": english_diff <= 1, "false_use_at_most_2_more": false_use_more <= 2,
              "errors_and_unparsed_at_most_10pct_per_arm": all(v <= 0.10 + 1e-9 for v in bad.values()), "within_ceiling": ceiling_ok}
    inconclusive = not checks["errors_and_unparsed_at_most_10pct_per_arm"]
    return {"complete": True, "thai_gain_points": round(thai_gain, 1), "english_today_minus_r3": english_diff, "false_use_r3_minus_today": false_use_more, "bad_share": {a: round(v, 3) for a, v in bad.items()},
            "checks": checks, "inconclusive": inconclusive, "propose": all(checks.values())}


def paired(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    by: Dict[tuple, Dict[str, str]] = {}
    for r in rows:
        by.setdefault((r["set"], r["goal"]), {})[r["arm"]] = r["verdict"]
    good = {"right", "ok"}
    both = {"r3_only": 0, "today_only": 0}
    for v in by.values():
        if "today" in v and "r3" in v:
            if v["r3"] in good and v["today"] not in good:
                both["r3_only"] += 1
            if v["today"] in good and v["r3"] not in good:
                both["today_only"] += 1
    return both


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--price-in", type=float, required=True)
    ap.add_argument("--price-out", type=float, required=True)
    ap.add_argument("--budget-usd", type=float, required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit-per-set", type=int, default=None, help="a probe: only the first N goals of each set (both arms); the pass rule is NOT applied (Amendment 13)")
    ap.add_argument("--keep-raw", action="store_true", help="keep the raw reply of every call, not only of the unreadable ones")
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    spec = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
    sets = goal_sets(spec)
    if args.limit_per_set is not None:
        sets = {name: goals[:max(0, args.limit_per_set)] for name, goals in sets.items()}
    calls = 2 * sum(len(v) for v in sets.values())
    est = calls * (2000 * args.price_in + 150 * args.price_out) / 1e6
    print(f"{calls} decisions ({', '.join(f'{k} {len(v)}' for k, v in sets.items())} x 2 arms); estimated cost ${est:.4f} with a 1.5x margin ${1.5 * est:.4f}; ceiling ${args.budget_usd:.2f}")
    if not args.execute:
        print("Dry run: nothing was sent. Add --execute to spend.")
        return 0
    if 1.5 * est > args.budget_usd:
        raise SystemExit(f"refused: the estimate with margin ${1.5 * est:.4f} is above the ceiling ${args.budget_usd:.2f}")
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key or os.environ.get("DELENTIA_RUN_LIVE_TESTS") != "1":
        raise SystemExit("refused: set OPENROUTER_API_KEY (a fresh key with a credit limit) and DELENTIA_RUN_LIVE_TESTS=1 first")
    from research import paid_run_freeze
    problems = paid_run_freeze.freeze_problems(args.model, args.price_in, args.price_out, args.budget_usd)
    if problems:
        raise SystemExit("freeze: " + "; ".join(problems))
    sys.path.insert(0, str(ROOT / "scripts"))
    import paid_day as pd
    info = pd.key_info(key)
    if info.get("limit") is None or float(info["limit"]) > args.budget_usd + 1e-9:
        raise SystemExit(f"refused: the key needs a credit limit at the provider and at most ${args.budget_usd:.2f} (it shows {info.get('limit')})")
    if float(info.get("usage", 0.0)) >= 0.10:
        raise SystemExit(f"refused: the key is not fresh (used ${info.get('usage')})")
    os.environ.update({"DELENTIA_LLM_PROVIDER": "openrouter", "DELENTIA_LLM_MODEL": args.model, "DELENTIA_OPENROUTER_DATA_COLLECTION": "deny"})
    os.environ.pop("DELENTIA_OPENROUTER_REQUIRE_PARAMETERS", None)
    from rct_control_plane import autonomous_loop
    from rct_control_plane.llm_provider import get_default_provider
    tools = asyncio.run(sib.builtin_tools()) + sib.synthetic_tools(spec["servers"])
    start = time.time()
    result = asyncio.run(run(Recorder(get_default_provider()), sets, tools, autonomous_loop.decide_next_action, usage=lambda: pd.key_info(key)["usage"], stop_at_usd=0.9 * args.budget_usd,
                             limit_per_set=args.limit_per_set, keep_raw=args.keep_raw or args.limit_per_set is not None))
    used = pd.key_info(key)["usage"]
    summary = summarise(result["rows"])
    verdict = ({"probe": True, "propose": False, "why": "a probe (--limit-per-set): the pass rule is not applied"} if args.limit_per_set is not None
               else verdict_of(result["rows"], ceiling_ok=used <= args.budget_usd and result["stopped"] is None))
    metered = sum(r.get("cost_usd") or 0.0 for r in result["rows"])
    print("  provider-reported cost of the calls: $%.4f (%d decisions, $%.4f per decision)" % (metered, len(result["rows"]), metered / max(1, len(result["rows"]))))
    for name, s in summary.items():
        print(f"  {name:<22} n={s['n']:>3} {json.dumps(s['counts'])} median menu {s['median_menu_tools']} tools")
    print("  paired:", json.dumps(paired(result["rows"])), "| provider usage $%.4f in %.0f s" % (used, time.time() - start))
    print("  rule:", json.dumps(verdict), "| stopped:", result["stopped"])
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "tool_choice_r3.json").write_text(json.dumps({"model": args.model, "summary": summary, "verdict": verdict, "paired": paired(result["rows"]), "usage_usd": used, "stopped": result["stopped"],
                                                             "rows": result["rows"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

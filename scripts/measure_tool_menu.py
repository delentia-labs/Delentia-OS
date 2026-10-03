"""
Round 56: how big is the menu of tools the model must choose from, and does a smaller one still contain the tool a goal needs?

    python scripts/measure_tool_menu.py [--set dev|holdout|both] [--k 10] [--json out.json]

Free and offline: it builds the real registry (the 39 built-in tools, plus any external MCP server configured), counts tokens with tiktoken exactly as
the loop formats them, and for each labelled goal (rct_control_plane/tests/fixtures/tool_menu_goals_round56.json) reports, per strategy:
  full     every tool (what a goal with no keyword in common gets today)
  current  the loop's existing keyword filter (a tool survives if it shares ONE word with the goal)
  ranked   tool_menu.rank_tools, top K
how many tools stay on the menu, how many tokens that is, and whether ALL the tools the goal needs survived (recall).
What it cannot say: whether a model chooses better from a smaller menu. That needs the paid test (A/B with DELENTIA_TOOL_MENU=ranked).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOALS = ROOT / "rct_control_plane" / "tests" / "fixtures" / "tool_menu_goals_round56.json"


async def load_tools() -> List[Dict[str, Any]]:
    from rct_control_plane import external_mcp
    from rct_control_plane.mcp_server import mcp
    listed = await external_mcp.maybe_wrap(mcp).list_tools()
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in listed]


def tokens_of(text: str) -> int:
    import tiktoken
    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def evaluate(tools: List[Dict[str, Any]], goals: List[Dict[str, Any]], k: int) -> Dict[str, Any]:
    from rct_control_plane import tool_menu
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop

    def current(goal: str) -> List[Dict[str, Any]]:
        return GovernedAutonomousLoop._tool_filter(GovernedAutonomousLoop, goal, tools)  # type: ignore[arg-type]

    strategies = {"full": lambda g: tools, "current": current, "ranked": lambda g: tool_menu.rank_tools(g, tools, k)}
    out: Dict[str, Any] = {}
    for name, pick in strategies.items():
        rows = []
        for item in goals:
            kept = pick(item["goal"])
            names = {t["name"] for t in kept}
            rows.append({"goal": item["goal"], "tools": len(kept), "tokens": tokens_of(tool_menu.format_menu(kept)),
                         "compact_tokens": tokens_of(tool_menu.format_menu(kept, compact=True)),
                         "recall": all(n in names for n in item["needs"]), "missing": [n for n in item["needs"] if n not in names],
                         "full_menu": len(kept) == len(tools)})
        out[name] = {"rows": rows, "goals": len(rows), "recall": round(sum(r["recall"] for r in rows) / len(rows), 3),
                     "median_tools": statistics.median(r["tools"] for r in rows), "median_tokens": int(statistics.median(r["tokens"] for r in rows)),
                     "median_compact_tokens": int(statistics.median(r["compact_tokens"] for r in rows)),
                     "fell_back_to_full_menu": sum(r["full_menu"] for r in rows)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", choices=["dev", "holdout", "both"], default="both")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--json", default=None)
    parser.add_argument("--misses", action="store_true", help="list the goals whose needed tool was cut")
    args = parser.parse_args()
    import logging
    logging.disable(logging.WARNING)
    tools = asyncio.run(load_tools())
    data = json.loads(GOALS.read_text(encoding="utf-8"))
    print(f"{len(tools)} tools; the full menu as the loop formats it is {tokens_of(__import__('rct_control_plane.tool_menu', fromlist=['x']).format_menu(tools))} tokens "
          f"({tokens_of(__import__('rct_control_plane.tool_menu', fromlist=['x']).format_menu(tools, compact=True))} in compact form)")
    report: Dict[str, Any] = {"tools": len(tools), "k": args.k}
    for which in (["dev", "holdout"] if args.set == "both" else [args.set]):
        result = evaluate(tools, data[which], args.k)
        report[which] = result
        print(f"\n[{which}] {len(data[which])} goals, top-{args.k}")
        for name, r in result.items():
            print(f"  {name:<8} recall {r['recall'] * 100:5.1f}%   median {r['median_tools']:>4} tools / {r['median_tokens']:>5} tokens "
                  f"({r['median_compact_tokens']} compact)   full menu given on {r['fell_back_to_full_menu']} goals")
        if args.misses:
            for r in result["ranked"]["rows"]:
                if not r["recall"]:
                    print(f"    cut: {r['missing']}  <- {r['goal']}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

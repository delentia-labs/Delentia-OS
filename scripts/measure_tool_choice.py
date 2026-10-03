"""
Round 56: from a menu of tools, does the model reach for the right one? And does a smaller menu help it?

    python scripts/measure_tool_choice.py qwen2.5:7b --provider ollama
    python scripts/measure_tool_choice.py some/model --provider openrouter --price-in 0.2 --price-out 0.8       (spends money; needs the opt-in)

One model call per goal and arm, no tool is executed: the prompt is the loop's real prompt (autonomous_loop.decide_next_action) for a goal with
nothing done yet, and the reply is scored: did it name a tool the goal needs (`needs` in tool_menu_goals_round56.json), or answer "finish" when a tool
was needed, or did the reply not parse? Arms:
  default         the loop today: the existing keyword filter, full descriptions and schemas
  ranked          tool_menu.rank_tools (top 10), full format
  ranked+compact  the same, arguments as name:type*
The 'holdout' goals only by default (the ranker's hints were written against 'dev'; use --set both to see that too). The figures are the model's
first look at 31 goals: a single run each, so a difference of one goal is noise. The adoption rule written down before the run: the ranked menu is
adopted only if it is at least as accurate as the default (within one goal) AND cheaper; otherwise it stays off.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

ARMS = ("default", "ranked", "ranked+compact")


def menu_for(arm: str, goal: str, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from rct_control_plane import tool_menu
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    if arm == "default":
        return GovernedAutonomousLoop._tool_filter(GovernedAutonomousLoop, goal, tools)      # type: ignore[arg-type]
    return tool_menu.rank_tools(goal, tools, tool_menu.DEFAULT_TOP_K)


def score(decision: Dict[str, Any], needs: List[str]) -> str:
    if decision.get("parse_error"):
        return "unparsed"
    if decision.get("action") == "finish":
        return "finished_without_tool"
    name = decision.get("tool_name")
    if name in needs:
        return "right"
    calls = decision.get("calls") or []
    if decision.get("action") == "call_tools" and any(c.get("tool_name") in needs for c in calls if isinstance(c, dict)):
        return "right"
    return "wrong_tool"


async def run(provider: Any, goals: List[Dict[str, Any]], arms: List[str], tools: List[Dict[str, Any]], decide: Any = None) -> Dict[str, Any]:
    import os as _os

    from rct_control_plane import autonomous_loop, tool_menu
    decide = decide or autonomous_loop.decide_next_action
    out: Dict[str, Any] = {}
    for arm in arms:
        if arm == "ranked+compact":
            _os.environ[tool_menu.FORMAT_ENV] = "compact"
        else:
            _os.environ.pop(tool_menu.FORMAT_ENV, None)
        rows = []
        for item in goals:
            menu = menu_for(arm if arm != "ranked+compact" else "ranked", item["goal"], tools)
            try:
                decision = await decide(item["goal"], [], menu, llm_provider=provider)
                verdict = score(decision, item["needs"])
                error = None
            except Exception as exc:                                  # noqa: BLE001 - recorded as a miss, not hidden
                verdict, error = "error", f"{type(exc).__name__}: {exc}"[:120]
            rows.append({"goal": item["goal"], "needs": item["needs"], "menu_tools": len(menu), "verdict": verdict, "error": error,
                         "chose": decision.get("tool_name") if error is None else None})
        _os.environ.pop(tool_menu.FORMAT_ENV, None)
        right = sum(r["verdict"] == "right" for r in rows)
        out[arm] = {"right": right, "of": len(rows), "accuracy": round(right / len(rows), 3) if rows else 0.0,
                    "unparsed": sum(r["verdict"] == "unparsed" for r in rows), "finished_without_tool": sum(r["verdict"] == "finished_without_tool" for r in rows),
                    "wrong_tool": sum(r["verdict"] == "wrong_tool" for r in rows), "errors": sum(r["verdict"] == "error" for r in rows),
                    "median_menu_tools": sorted(r["menu_tools"] for r in rows)[len(rows) // 2] if rows else 0, "rows": rows}
    return out


def adoption(result: Dict[str, Any]) -> Dict[str, Any]:
    """The rule written before any run: adopt the ranked menu only if within one goal of the default's accuracy (or better) and the menu is smaller."""
    base, ranked = result.get("default"), result.get("ranked+compact") or result.get("ranked")
    if not base or not ranked:
        return {}
    slack = 1 / max(1, base["of"])
    ok = ranked["accuracy"] >= base["accuracy"] - slack - 1e-9 and ranked["median_menu_tools"] < base["median_menu_tools"]
    value = f"default {base['right']}/{base['of']}, ranked+compact {ranked['right']}/{ranked['of']}, median menu {base['median_menu_tools']} -> {ranked['median_menu_tools']} tools"
    # A call that timed out or errored did not choose anything, right or wrong. When a fifth or more of an arm's goals errored the comparison says
    # little about tool choice (it says the arm was too slow or failed), so it is reported as inconclusive and never as a plain pass.
    errored = {name: arm.get("errors", 0) for name, arm in (("default", base), ("ranked+compact", ranked))}
    inconclusive = [name for name, n in errored.items() if n * 5 >= max(1, base["of"])]
    if inconclusive:
        value += f" [INCONCLUSIVE: {', '.join(f'{n} errored on {errored[n]} of {base['of']} goals' for n in inconclusive)}]"
        return {"T10": {"value": value, "pass": False, "inconclusive": True}}
    return {"T10": {"value": value, "pass": bool(ok)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model")
    parser.add_argument("--provider", choices=["ollama", "openrouter"], default="ollama")
    parser.add_argument("--set", choices=["holdout", "dev", "both"], default="holdout")
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--price-in", type=float, default=0.0)
    parser.add_argument("--price-out", type=float, default=0.0)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    if args.provider == "openrouter" and (not os.environ.get("OPENROUTER_API_KEY") or os.environ.get("DELENTIA_RUN_LIVE_TESTS") != "1"):
        raise SystemExit("--provider openrouter spends money: set OPENROUTER_API_KEY and DELENTIA_RUN_LIVE_TESTS=1 first")
    import logging
    logging.disable(logging.WARNING)
    os.environ.update({"DELENTIA_LLM_PROVIDER": args.provider, "DELENTIA_LLM_MODEL": args.model})
    import measure_tool_menu as mtm
    from rct_control_plane.llm_provider import get_default_provider
    tools = asyncio.run(mtm.load_tools())
    data = json.loads(mtm.GOALS.read_text(encoding="utf-8"))
    goals = data["dev"] + data["holdout"] if args.set == "both" else data[args.set]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    result = asyncio.run(run(get_default_provider(), goals, arms, tools))
    for arm, r in result.items():
        print(f"  {arm:<15} right {r['right']}/{r['of']} ({r['accuracy'] * 100:.1f}%)  wrong tool {r['wrong_tool']}, finished without a tool {r['finished_without_tool']}, "
              f"unparsed {r['unparsed']}, errors {r['errors']}; median menu {r['median_menu_tools']} tools")
    judged = adoption(result)
    if judged:
        print(f"T10 {'PASS' if judged['T10']['pass'] else 'FAIL'}: {judged['T10']['value']}")
    if args.json:
        Path(args.json).write_text(json.dumps({args.model: {"result": {k: {kk: vv for kk, vv in v.items() if kk != 'rows'} for k, v in result.items()},
                                                            "rows": {k: v["rows"] for k, v in result.items()}, "judged": judged}}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

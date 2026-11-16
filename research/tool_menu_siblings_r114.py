"""
Round two, Amendment 5, section 3: should the ranked tool menu keep the WRITE tools of an external server when one of its READ tools is shown? (free, offline, no model)

Candidate rule R1 (written in the amendment before this ran): after the ranked menu is chosen, for every external server (`mcp__<server>__<tool>`) that has a read-type tool in the menu, add its
write-type tools. A tool is read-type when its name after the server prefix starts with read_, get_, list_, search_, find_ or fetch_ (fixed in the goals file).

Pass rule (written before the measurement): on the external goals ALL needed tools survive in at least 10 percentage points more goals, the mean menu grows by at most 2 tools, and on the built-in
holdout (with the same four synthetic servers added to the list, so the menu competes with them) recall falls by no more than 1 point. The report is given to the Architect; nothing here changes the
runtime.

    python -m research.tool_menu_siblings_r114 [--json out.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import logging
import statistics
from pathlib import Path
from typing import Any, Dict, List

from rct_control_plane import tool_menu

ROOT = Path(__file__).resolve().parent.parent
EXTERNAL = ROOT / "research" / "tool_menu_external_goals_r114.json"
BUILTIN = ROOT / "rct_control_plane" / "tests" / "fixtures" / "tool_menu_goals_round56.json"
READ_PREFIXES = ("read_", "get_", "list_", "search_", "find_", "fetch_")


def split_name(name: str) -> tuple[str, str]:
    """('notes', 'read_note') for 'mcp__notes__read_note'; ('', name) for a built-in tool."""
    if name.startswith("mcp__") and name.count("__") >= 2:
        _, server, tool = name.split("__", 2)
        return server, tool
    return "", name


def is_read_type(name: str) -> bool:
    return split_name(name)[1].startswith(READ_PREFIXES)


def add_write_siblings(shown: List[Dict[str, Any]], every: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Candidate rule R1."""
    names = {t["name"] for t in shown}
    servers = {split_name(n)[0] for n in names if split_name(n)[0] and is_read_type(n)}
    extra = [t for t in every if t["name"] not in names and split_name(t["name"])[0] in servers and not is_read_type(t["name"])]
    return [*shown, *extra]


def synthetic_tools(spec: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
    out = []
    for server, tools in spec.items():
        for tool, description in tools.items():
            out.append({"name": f"mcp__{server}__{tool}", "description": description, "input_schema": {"type": "object", "properties": {"arg": {"type": "string"}}}})
    return out


async def builtin_tools() -> List[Dict[str, Any]]:
    from rct_control_plane.mcp_server import mcp
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in await mcp.list_tools()]


def measure(every: List[Dict[str, Any]], goals: List[Dict[str, Any]], k: int) -> Dict[str, Any]:
    arms: Dict[str, Dict[str, Any]] = {}
    for arm in ("ranked", "R1"):
        rows = []
        for item in goals:
            shown = tool_menu.rank_tools(item["goal"], every, k)
            if arm == "R1":
                shown = add_write_siblings(shown, every)
            names = {t["name"] for t in shown}
            rows.append({"goal": item.get("id") or item["goal"][:40], "size": len(shown), "ok": all(n in names for n in item["needs"]), "missing": [n for n in item["needs"] if n not in names]})
        arms[arm] = {"recall": round(sum(r["ok"] for r in rows) / len(rows), 3), "mean_menu": round(statistics.mean(r["size"] for r in rows), 2), "n": len(rows), "rows": rows}
    return arms


def verdict(external: Dict[str, Dict[str, Any]], builtin_holdout: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    gain = (external["R1"]["recall"] - external["ranked"]["recall"]) * 100
    growth = external["R1"]["mean_menu"] - external["ranked"]["mean_menu"]
    loss = (builtin_holdout["ranked"]["recall"] - builtin_holdout["R1"]["recall"]) * 100
    checks = {"external_recall_gain_points_at_least_10": gain >= 10 - 1e-9, "mean_menu_growth_at_most_2": growth <= 2 + 1e-9, "builtin_holdout_loss_points_at_most_1": loss <= 1 + 1e-9}
    return {"gain_points": round(gain, 1), "mean_menu_growth": round(growth, 2), "builtin_holdout_loss_points": round(loss, 1), "checks": checks, "propose_adoption": all(checks.values())}


def main() -> int:
    os.environ["DELENTIA_TOOL_MENU_KEEP_EXTERNAL"] = "off"          # these measurements compare against the menu of before R3 became the default (Amendment 6)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=0, help="menu size (default: the runtime's)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    k = args.k or tool_menu.top_k()
    spec = json.loads(EXTERNAL.read_text(encoding="utf-8"))
    every = asyncio.run(builtin_tools()) + synthetic_tools(spec["servers"])
    external = measure(every, spec["goals"], k)
    builtin = json.loads(BUILTIN.read_text(encoding="utf-8"))
    dev = measure(every, builtin["dev"], k)
    holdout = measure(every, builtin["holdout"], k)
    result = verdict(external, holdout)
    report = {"k": k, "tools_in_list": len(every), "external": external, "builtin_dev": dev, "builtin_holdout": holdout, "verdict": result}
    print(f"{len(every)} tools in the list, menu size {k}")
    for name, block in (("external goals", external), ("built-in dev", dev), ("built-in holdout", holdout)):
        print(f"  {name:<17} ranked: recall {block['ranked']['recall']*100:5.1f}%  mean menu {block['ranked']['mean_menu']:5.2f}   |   R1: recall {block['R1']['recall']*100:5.1f}%  mean menu {block['R1']['mean_menu']:5.2f}   (n={block['ranked']['n']})")
    print("  verdict:", json.dumps(result))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

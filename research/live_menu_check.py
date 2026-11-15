"""
What a live model is actually shown, checked before any paid run (round two, Amendment 5, item 5; no model, no cost).

Round two found the same kind of defect four times: the model could not do the job because the TOOLS it was shown were not the tools the job needs (W12: the write tool was ranked out of the
menu; TC-006: the tools had no argument names, so the model guessed `path` for `relative_path`). Neither showed in a score. This module builds, for a live workflow, the real tool list, applies the
real menu decision (`tool_menu`, with the environment the runner uses) and reports

  (a) every tool the workflow needs is in the menu the model receives, and
  (b) the menu text contains the argument names the workflow's calls use.

`python -m research.live_menu_check [W09|W12|TC-006 ...]` prints one line per workflow and exits 1 if any fails. `paid_round_two.py` runs it before it spends.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence

from rct_control_plane import tool_menu

REPO = Path(__file__).resolve().parent.parent


def _as_dicts(tools: Sequence[Any]) -> List[Dict[str, Any]]:
    out = []
    for t in tools:
        if t is None:
            continue
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or getattr(t, "parameters", None) or {}
        out.append({"name": t.name, "description": getattr(t, "description", "") or "", "input_schema": schema})
    return out


@contextmanager
def _environment(extra: Dict[str, Optional[str]]) -> Iterator[None]:
    """Sets (or, for None, removes) variables for the duration of a check and puts them back."""
    saved = {k: os.environ.get(k) for k in extra}
    for k, v in extra.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def check_menu(goal: str, tools: Sequence[Any], needs: Mapping[str, Sequence[str]], env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """`needs` maps a tool name to the argument names the workflow's calls use. Returns {ok, missing_tools, missing_args, menu_tools, menu_size, ranked}."""
    listed = _as_dicts(tools)
    # A run starts from the runtime's own defaults, whatever the process that asks has set (a test run forces the full menu), unless the workflow sets them itself.
    with _environment({"DELENTIA_TOOL_MENU": None, "DELENTIA_TOOL_MENU_FORMAT": None, **(env or {})}):
        ranked = tool_menu.maybe_ranked(goal, listed)
        shown = ranked if ranked is not None else listed
        text = tool_menu.format_menu(shown, compact=tool_menu.compact_enabled() if ranked is not None else False)
    shown_names = [t["name"] for t in shown]
    missing_tools = [n for n in needs if n not in shown_names]
    missing_args: Dict[str, List[str]] = {}
    for name, args in needs.items():
        if name in missing_tools:
            continue
        entries = re.split(r"\n(?=- )", text)                               # a description can run over several lines: an entry starts at "- "
        line = next((e for e in entries if e.lstrip("- ").startswith(name)), "")
        absent = [a for a in args if a not in line]
        if absent:
            missing_args[name] = absent
    return {"ok": not missing_tools and not missing_args, "missing_tools": missing_tools, "missing_args": missing_args, "menu_size": len(shown_names), "ranked": ranked is not None,
            "menu_tools": shown_names}


def _w12_tools() -> List[Any]:
    from rct_control_plane import external_mcp as xm
    from rct_control_plane.mcp_server import mcp
    home = Path(tempfile.mkdtemp(prefix="menucheck_w12_"))
    server = REPO / "rct_control_plane" / "tests" / "fake_mcp_server.py"
    config = home / "mcp_servers.json"
    config.write_text(json.dumps({"servers": {"notes": {"command": sys.executable, "args": [str(server)], "env_vars": ["FAKE_NOTES_FILE"],
                                                        "read_only_tools": ["read_note", "fetch_page"], "timeout_s": 90}}}), encoding="utf-8")
    with _environment({xm.CONFIG_ENV: str(config), "FAKE_NOTES_FILE": str(home / "notes.txt"), "DELENTIA_HOME": str(home)}):
        xm.clear_cache()
        try:
            return list(asyncio.run(xm.maybe_wrap(mcp, "owner-w12").list_tools()))
        finally:
            xm.shutdown_pool()


def check_w12() -> Dict[str, Any]:
    from research import live_workflows as lw
    needs = {"delentia_spawn_subagents": [], "mcp__notes__write_note": ["title", "text"]}
    return check_menu(lw.W12_GOAL, _w12_tools(), needs, env=dict(lw.W12_MENU_ENV))


def check_tc006() -> Dict[str, Any]:
    from research.daaes import tc006
    from research.daaes.delentia_session import DirWorld
    tools = asyncio.run(DirWorld(Path(tempfile.mkdtemp(prefix="menucheck_tc006_")) / "ws").list_tools())
    needs = {"delentia_read_repo_file": ["relative_path"], "delentia_write_repo_file": ["relative_path", "content_text"]}
    results = [check_menu(goal, tools, needs) for goal in tc006.LIVE_GOALS.values()]
    bad = [r for r in results if not r["ok"]]
    return bad[0] if bad else {**results[0], "goals_checked": len(results)}


def check_w09() -> Dict[str, Any]:
    from research.daaes import w09_child
    needs = {"delentia_save_exchange_file": ["category", "filename", "content"]}
    return check_menu(w09_child.GOAL, w09_child.TOOLS, needs)


CHECKS = {"W09": check_w09, "W12": check_w12, "TC-006": check_tc006}


def main(argv: Optional[Sequence[str]] = None) -> int:
    names = list(argv if argv is not None else sys.argv[1:]) or list(CHECKS)
    failed = 0
    for name in names:
        result = CHECKS[name]()
        mark = "OK  " if result["ok"] else "FAIL"
        detail = "" if result["ok"] else f" missing tools {result['missing_tools']} missing args {result['missing_args']}"
        print(f"{mark} {name}: menu {result['menu_size']} tools ({'ranked' if result['ranked'] else 'full'}){detail}")
        failed += 0 if result["ok"] else 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

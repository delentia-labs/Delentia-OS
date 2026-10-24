"""Does a local model use the agent's own question (`delentia_ask_user`) sensibly? DEV probe, one run per goal, real loop, real tools, real local model (criteria: research/rct7_round98_criteria.md, section A).

    DELENTIA_OLLAMA_THINK=off python -m research.rct7_ask_tool_probe --model qwen3:8b [--out result.json]

A throw-away workspace with two reports and a notes file; an interactive loop (stop-and-ask on). Three goals that cannot be done without asking, three that can. What is counted: did the model
call the question tool, did it call it BEFORE doing unrelated work, did it ask when the goal was clear. The goals are the author's: a DEV measurement, not a claim.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

AMBIGUOUS = ["Summarize the report", "Rename the old file to the new name", "Open the notes from yesterday's meeting and list the action items"]
CLEAR = ["Read report_q1.md and tell me its title", "What is 17 x 23?", "Search the workspace for the word revenue and say which file has it"]


async def run_goal(model: str, workspace: Path, goal: str, db: Path, max_seconds: float) -> Dict[str, Any]:
    from rct_control_plane import mcp_server
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.llm_provider import OllamaProvider
    from rct_control_plane.persistence import ControlPlanePersistence
    mcp_server.REPO_ROOT = workspace
    persistence = ControlPlanePersistence(db_path=str(db))
    loop = build_governed_loop(mcp_server._kernel, f"probe-{abs(hash(goal)) % 10**6}", max_iterations=5, max_seconds=max_seconds, persistence=persistence,
                               mcp_server=mcp_server.mcp, llm_provider=OllamaProvider(model=model), interactive=True)
    started = time.time()
    result = await loop.run(goal)
    steps = [s.get("tool_name") for s in result.get("steps", [])]
    asked = "delentia_ask_user" in steps
    return {"goal": goal, "steps": steps, "asked": asked, "asked_first": bool(steps) and steps[0] == "delentia_ask_user", "stopped_reason": result.get("stopped_reason"),
            "question": result.get("clarification_question", "")[:300], "seconds": round(time.time() - started, 1), "answer": str(result.get("final_answer") or "")[:200]}


async def run(model: str, max_seconds: float) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        workspace = Path(tmp) / "ws"
        workspace.mkdir()
        (workspace / "report_q1.md").write_text("# Q1 report\nrevenue was 120\n", encoding="utf-8")
        (workspace / "report_q2.md").write_text("# Q2 report\nrevenue was 150\n", encoding="utf-8")
        (workspace / "notes.txt").write_text("remember to water the plants\n", encoding="utf-8")
        db = Path(tmp) / "probe.db"
        rows: List[Dict[str, Any]] = []
        for goal in AMBIGUOUS + CLEAR:
            rows.append({**await run_goal(model, workspace, goal, db, max_seconds), "should_ask": goal in AMBIGUOUS})
    asked_ok = sum(1 for r in rows if r["should_ask"] and r["asked"])
    false_asks = sum(1 for r in rows if not r["should_ask"] and r["asked"])
    return {"model": model, "set": "DEV (author-written; not a claim)", "ambiguous": len(AMBIGUOUS), "asked_when_it_should": asked_ok, "clear": len(CLEAR), "asked_when_it_should_not": false_asks, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-seconds", type=float, default=300.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    os.environ.setdefault("DELENTIA_OLLAMA_THINK", "off")
    result = asyncio.run(run(args.model, args.max_seconds))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    for r in result["rows"]:
        print(("ASKED " if r["asked"] else "no    "), "| should" if r["should_ask"] else "| fine  ", "|", r["goal"], "|", r["steps"], "|", r["stopped_reason"], "|", r["seconds"], "s")
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

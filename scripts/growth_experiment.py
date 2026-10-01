"""
Round 52: does the SYSTEM grow with use, with the model unchanged?

The model's weights never change here. What can grow is everything around it:
what the system knows about this user (memory -> D), what it re-uses (skills,
warm recall) and what it spends (steps, seconds, tokens). This experiment measures
that with whatever model `delentia model show` resolves to (the local Ollama
model by default), in two arms that share nothing:

  plain     the governed loop with memory, RCT-7 plan, skills, pipeline and warm
            recall all switched off (what a bare model in a bare loop would do)
  delentia  the loop as `delentia serve` runs it: memory recalled into the prompt,
            RCT-7 plan, skills, the 41-algorithm pipeline, warm recall

Phases (identical for both arms):

  P0  ask 8 questions about the user's own world BEFORE the system was told anything
  P1  tell the system the 8 facts (the user's data; stored for both arms)
  P2  ask the same 8 things again, phrased differently (paraphrase: retrieval must
      cope with different wording, not only the same words)
  P3  two file-reading goals x 3 repeats: do later runs need fewer steps / less time,
      and does warm recall answer without the model?

Correct = the expected token appears in the final answer. This measures the system
around the model, not the model's intelligence, and with a 7B model on CPU the tool
tasks (P3) may simply fail: the report says so instead of hiding it.

    python scripts/growth_experiment.py --out growth.json
    python scripts/growth_experiment.py --phases P0,P1,P2          # skip the slow tool phase
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.CRITICAL)
try:
    from loguru import logger as _loguru
    _loguru.remove()
except Exception:
    pass

NAMESPACE = "growth-user"

# (fact the user tells the system, question before/after, paraphrased question, expected token)
FACTS = [
    ("My staging database is called stg-orion-7 and it lives in the ap-southeast-1 region.",
     "What is the name of my staging database?", "Which database do I use for staging?", "stg-orion-7"),
    ("The release manager on my team is Napat and releases go out every second Thursday.",
     "Who is the release manager on my team?", "Tell me who manages our releases.", "napat"),
    ("Our production deploy pipeline is named blue-lantern and it needs two approvals.",
     "What is our production deploy pipeline called?", "Name the pipeline we use to deploy to production.", "blue-lantern"),
    ("My invoice numbering scheme starts with INV-TH and then a six digit counter.",
     "How do my invoice numbers start?", "What prefix do my invoices use?", "inv-th"),
    ("The office wifi password rotation happens on the first Monday of each month.",
     "When does the office wifi password rotate?", "On which day is our wifi password changed?", "monday"),
    ("Our customer support inbox is support-desk@example.org and Anong answers it.",
     "What is our customer support email address?", "Which address do customers write to for support?", "support-desk@example.org"),
    ("The backup job runs at 02:30 every night and writes to the bucket cold-vault-3.",
     "What time does my backup job run?", "At what hour is the nightly backup started?", "02:30"),
    ("My preferred report format is PDF with a one page executive summary on top.",
     "What is my preferred report format?", "In which format do I like my reports?", "pdf"),
]

TOOL_GOALS = [
    ("Read the file pyproject.toml in the repository and tell me the project name.", "delentia"),
    ("Search the repository files for the word FDIA and name one file that mentions it.", ".py"),
]


def judge(answer: Optional[str], expected: str) -> bool:
    return bool(answer) and expected.lower() in answer.lower()


def build_loop(workdir: Path, arm: str, max_iterations: int, max_seconds: float) -> Any:
    from rct_control_plane.agent_memory import AgentMemory
    from rct_control_plane.algorithm_pipeline import AlgorithmPipeline, PipelineOptions
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    from rct_control_plane.mcp_server import _kernel, mcp
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.skill_library import SkillLibrary

    persistence = ControlPlanePersistence(db_path=str(workdir / f"{arm}.db"))
    skills = SkillLibrary(db_path=str(workdir / f"{arm}.skills.db"))
    _kernel._agent_memory = AgentMemory(NAMESPACE, persistence)
    if arm == "plain":
        return GovernedAutonomousLoop(
            mcp_server=mcp, persistence=persistence, kernel=_kernel, skill_library=skills, max_iterations=max_iterations,
            max_seconds=max_seconds, namespace=NAMESPACE, rct7_in_prompt=False, memory_in_prompt=False, route=False,
            compress_tool_outputs=False, warm_recall=False, algorithm_pipeline=None)
    pipeline = AlgorithmPipeline(_kernel, persistence, NAMESPACE, memory=_kernel._agent_memory, skills=skills,
                                 options=PipelineOptions())
    return GovernedAutonomousLoop(
        mcp_server=mcp, persistence=persistence, kernel=_kernel, skill_library=skills, max_iterations=max_iterations,
        max_seconds=max_seconds, namespace=NAMESPACE, warm_recall=True, algorithm_pipeline=pipeline)


async def teach(workdir: Path, arm: str) -> None:
    from rct_control_plane.agent_memory import AgentMemory, MemoryType
    from rct_control_plane.persistence import ControlPlanePersistence
    memory = AgentMemory(NAMESPACE, ControlPlanePersistence(db_path=str(workdir / f"{arm}.db")))
    for fact, *_ in FACTS:
        await memory.store(fact, MemoryType.FACT, importance=0.9)


async def episode(loop: Any, goal: str, expected: str) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        result = await loop.run(goal)
        error = None
    except Exception as exc:
        result, error = {"stopped_reason": "error", "iterations": 0, "final_answer": None}, f"{type(exc).__name__}: {exc}"
    cost = result.get("cost") or {}
    growth = result.get("growth") or {}
    return {
        "goal": goal, "expected": expected, "stopped_reason": result.get("stopped_reason"),
        "correct": judge(result.get("final_answer"), expected), "steps": result.get("iterations"),
        "seconds": round(time.monotonic() - started, 1), "model_calls": cost.get("calls"),
        "tokens": (cost.get("prompt_tokens") or 0) + (cost.get("completion_tokens") or 0),
        "D": (growth.get("data") or {}).get("D"), "G": growth.get("G"), "warm": result.get("stopped_reason") == "warm_recall",
        "answer": (result.get("final_answer") or "")[:160], "error": error,
    }


async def run(arms: List[str], phases: List[str], repeats: int, max_iterations: int, max_seconds: float, workdir: Path,
              log=print) -> Dict[str, List[Dict[str, Any]]]:
    runs: Dict[str, List[Dict[str, Any]]] = {}
    for arm in arms:
        rows: List[Dict[str, Any]] = []
        runs[arm] = rows

        async def ask(phase: str, goal: str, expected: str) -> None:
            loop = build_loop(workdir, arm, max_iterations, max_seconds)
            row = await episode(loop, goal, expected)
            row["phase"] = phase
            rows.append(row)
            log(f"[{arm:8} {phase}] {'OK ' if row['correct'] else 'no '} {row['stopped_reason']:<18} steps={row['steps']} "
                f"{row['seconds']}s tokens={row['tokens']} D={row['D']} | {goal[:52]}")

        if "P0" in phases:
            for _, question, _, expected in FACTS:
                await ask("P0", question, expected)
        if "P1" in phases:
            await teach(workdir, arm)
        if "P2" in phases:
            for _, _, paraphrase, expected in FACTS:
                await ask("P2", paraphrase, expected)
        if "P3" in phases:
            for rep in range(1, repeats + 1):
                for goal, expected in TOOL_GOALS:
                    await ask(f"P3.{rep}", goal, expected)
    return runs


def summarize(runs: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for arm, rows in runs.items():
        phases: Dict[str, Any] = {}
        for phase in sorted({r["phase"] for r in rows}):
            rs = [r for r in rows if r["phase"] == phase and not r["error"]]
            if not rs:
                continue
            phases[phase] = {
                "episodes": len(rs), "correct": sum(r["correct"] for r in rs),
                "avg_seconds": round(statistics.mean(r["seconds"] for r in rs), 1),
                "avg_tokens": round(statistics.mean(r["tokens"] for r in rs)),
                "avg_steps": round(statistics.mean(r["steps"] or 0 for r in rs), 2),
                "warm_hits": sum(r["warm"] for r in rs),
                "avg_D": round(statistics.mean(r["D"] for r in rs if r["D"] is not None), 3) if any(r["D"] is not None for r in rs) else None,
            }
        out[arm] = phases
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arms", default="plain,delentia")
    ap.add_argument("--phases", default="P0,P1,P2,P3")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--max-iterations", type=int, default=4)
    ap.add_argument("--max-seconds", type=float, default=150.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    from rct_control_plane.model_config import resolve_model_selection
    sel = resolve_model_selection()
    print(f"model: {sel.model} ({sel.provider}); the model's weights never change in this experiment")
    with tempfile.TemporaryDirectory(prefix="delentia-growth-", ignore_cleanup_errors=True) as tmp:
        runs = asyncio.run(run([a.strip() for a in args.arms.split(",") if a.strip()], [p.strip() for p in args.phases.split(",") if p.strip()],
                               args.repeats, args.max_iterations, args.max_seconds, Path(tmp)))
    summary = summarize(runs)
    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps({"model": sel.to_dict(), "summary": summary, "runs": runs}, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Round 50: measure finish-line criteria 2, 4 and 6 (DELENTIA_ROUND48 section 1.3)
with whatever model `delentia model show` resolves to.

  2  Tool selection:  does the model call the one right tool for a clear goal?
  4  RCT-7 A/B:       the same goals with the RCT-7 plan in the prompt (arm A)
                      and without it (arm B) - does the plan change behaviour?
  6  Learning:        each goal is repeated; do later runs need fewer steps or
                      pick up a learned skill?

Runs against a temporary database and skill library, so nothing here touches
the real audit trail or skills. The write goal is expected to pause for a
signed approval (nothing is written). Tools are the real MCP tools.

    python scripts/endpoint_bench.py                      # defaults: 4 goals x 2 arms x 2 repeats
    python scripts/endpoint_bench.py --repeats 3 --delay 5 --out bench.json

Free OpenRouter models have per-minute and per-day request limits; every
episode makes 1-5 model calls, so use --delay and small --repeats with them.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class Goal:
    text: str
    expected_tool: Optional[str]        # None: the right answer uses no tool
    expected_stop: Optional[str] = None  # e.g. "pending_approval"


GOALS: List[Goal] = [
    Goal("Recall what you remember about the topic 'formal acceptance test marker'.", "delentia_recall"),
    Goal("Read the file pyproject.toml in the repository and tell me the project name.", "delentia_read_repo_file"),
    Goal("Search the repository files for the word FDIA and name one file that mentions it.", "delentia_search_repo_files"),
    Goal("Write a new file docs/bench_note.md in the repository that says hello.", "delentia_write_repo_file", "pending_approval"),
]


@dataclass
class Run:
    goal: str
    arm: str
    repeat: int
    stopped_reason: str
    iterations: int
    tools: List[str]
    correct_tool: bool
    verified: Optional[bool]
    skills_injected: int
    seconds: float
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


def judge(goal: Goal, result: Dict[str, Any]) -> bool:
    tools = [s.get("tool_name") for s in result.get("steps", []) if s.get("tool_name")]
    if goal.expected_tool is None:
        return not tools
    right = goal.expected_tool in tools and all(t == goal.expected_tool for t in tools)
    if goal.expected_stop:
        right = right and result.get("stopped_reason") == goal.expected_stop
    return right


def build_loop(workdir: Path, namespace: str, rct7: bool, max_iterations: int, max_seconds: float) -> Any:
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    from rct_control_plane.mcp_server import _kernel, mcp
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.skill_library import SkillLibrary
    return GovernedAutonomousLoop(
        mcp_server=mcp, persistence=ControlPlanePersistence(db_path=str(workdir / "bench.db")), kernel=_kernel,
        skill_library=SkillLibrary(db_path=str(workdir / "skills.db")),
        max_iterations=max_iterations, max_seconds=max_seconds, namespace=namespace, rct7_in_prompt=rct7,
    )


async def run_bench(goals: List[Goal], repeats: int, arms: List[str], max_iterations: int, max_seconds: float,
                    delay: float, workdir: Path, loop_builder: Callable[..., Any] = build_loop,
                    log: Callable[[str], None] = print) -> List[Run]:
    runs: List[Run] = []
    for arm in arms:
        # Each arm learns in its own library, so arm B cannot reuse arm A's skills.
        arm_dir = workdir / f"arm-{arm}"
        arm_dir.mkdir(parents=True, exist_ok=True)
        for rep in range(1, repeats + 1):
            for gi, goal in enumerate(goals):
                loop = loop_builder(arm_dir, f"bench-{arm}-{gi}-{rep}", arm == "A", max_iterations, max_seconds)
                t0 = time.monotonic()
                try:
                    result = await loop.run(goal.text)
                    err = None
                except Exception as exc:  # model/network errors are reported, not hidden
                    result, err = {"steps": [], "stopped_reason": "error", "iterations": 0}, f"{type(exc).__name__}: {exc}"
                v = result.get("intent_verification") or {}
                run = Run(goal=goal.text, arm=arm, repeat=rep, stopped_reason=result.get("stopped_reason", "?"),
                          iterations=int(result.get("iterations") or 0),
                          tools=[s.get("tool_name") for s in result.get("steps", []) if s.get("tool_name")],
                          correct_tool=False if err else judge(goal, result),
                          verified=v.get("aligned_with_intent") if v.get("applicable") else None,
                          skills_injected=int(getattr(loop, "_episode_skills_injected", 0) or 0),
                          seconds=round(time.monotonic() - t0, 1), error=err)
                runs.append(run)
                log(f"[{arm} #{rep}] {'OK ' if run.correct_tool else 'BAD'} {run.stopped_reason:<18} "
                    f"steps={run.iterations} tools={run.tools} {run.seconds}s  {goal.text[:60]}"
                    + (f"  ERROR {err}" if err else ""))
                if delay:
                    await asyncio.sleep(delay)
    return runs


def summarize(runs: List[Run]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"arms": {}, "learning": []}
    for arm in sorted({r.arm for r in runs}):
        rs = [r for r in runs if r.arm == arm and not r.error]
        n = len(rs)
        out["arms"][arm] = {
            "rct7_in_prompt": arm == "A",
            "episodes": n,
            "errors": sum(1 for r in runs if r.arm == arm and r.error),
            "tool_selection_rate": round(sum(r.correct_tool for r in rs) / n, 3) if n else None,
            "avg_steps": round(sum(r.iterations for r in rs) / n, 2) if n else None,
            "verified_rate": (round(sum(1 for r in rs if r.verified) / sum(1 for r in rs if r.verified is not None), 3)
                              if any(r.verified is not None for r in rs) else None),
        }
    for goal in sorted({r.goal for r in runs}):
        for arm in sorted({r.arm for r in runs}):
            rs = sorted((r for r in runs if r.goal == goal and r.arm == arm and not r.error), key=lambda r: r.repeat)
            if len(rs) >= 2:
                out["learning"].append({"goal": goal, "arm": arm, "first_steps": rs[0].iterations,
                                        "last_steps": rs[-1].iterations, "last_skills_injected": rs[-1].skills_injected})
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--arms", default="A,B", help="A = RCT-7 plan in the prompt, B = without it")
    ap.add_argument("--max-iterations", type=int, default=5)
    ap.add_argument("--max-seconds", type=float, default=240.0)
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between episodes (free-tier rate limits)")
    ap.add_argument("--out", default=None, help="write runs + summary as JSON here")
    args = ap.parse_args(argv)

    from rct_control_plane.model_config import resolve_model_selection
    sel = resolve_model_selection()
    print(f"model: {sel.model} ({sel.provider}, chosen by {sel.model_source})")
    with tempfile.TemporaryDirectory(prefix="delentia-bench-") as tmp:
        runs = asyncio.run(run_bench(GOALS, args.repeats, [a.strip() for a in args.arms.split(",") if a.strip()],
                                     args.max_iterations, args.max_seconds, args.delay, Path(tmp)))
    summary = summarize(runs)
    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps({"model": sel.to_dict(), "summary": summary,
                                              "runs": [asdict(r) for r in runs]}, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

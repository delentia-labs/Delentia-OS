"""
Round 51: what happens when all 41 algorithms run together with the whole system.

Arms (each learns in its own database, so no arm sees another's skills):

  off        the governed loop alone (GUARD, THINK, ROUTE, ACT, COMPRESS, VERIFY, RECORD, LEARN)
  on         the same loop with the algorithm pipeline: all 41 algorithms as stages
  fullstack  `on`, plus the algorithms that need a URL, a video, a build request or file
             writes, given real local fixtures (a local web server, a generated video, a
             scaffold), so all 41 actually execute

Policies:

  policy     a fixed rule-based decider stands in for the model (reads the file named in
             the goal, searches, recalls, then answers from the tool result). Nothing here
             measures model quality: it isolates what the SYSTEM does - overhead per
             algorithm, how user data flows through retrieval, what advice reaches the
             prompt, D and growth across repeats. Deterministic and free.
  live       the model chosen by `delentia model show` makes the decisions. Needs a capable
             model (OpenRouter key or Ollama) and, with --with-llm, also runs the algorithms
             that call the model themselves (ALGO-09 / 11 / 32). This is the run that says
             whether the pipeline makes answers better.

    python scripts/intent_loop_bench.py                          # policy, arms off/on/fullstack, 3 repeats
    python scripts/intent_loop_bench.py --policy live --arms off,on --repeats 3 --delay 4 --out bench.json

Everything runs against temporary databases. The fullstack arm writes scaffold files under
workspace_output/ (gitignored).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging  # noqa: E402

logging.disable(logging.CRITICAL)           # the algorithms log a lot; the report is what matters
try:
    from loguru import logger as _loguru  # noqa: E402
    _loguru.remove()
except Exception:
    pass

NAMESPACE = "bench-user"

GOALS = [
    "Thanks, that was really helpful.",
    "Build a small web API for tracking tasks.",
    "Summarise the release checklist within 5 minutes and spend at most $2.",
    "Run python -c \"print(sum(range(10)))\" in the sandbox and tell me the output.",
    "Read the file pyproject.toml in the repository and tell me the project name.",
    "Search the repository files for the word FDIA and name one file that mentions it.",
    "Recall what you remember about the release checklist.",
    "Summarise what the growth module in rct_control_plane/growth.py is for.",
    "Fix the typo in README.md",
    "Deploy the new database schema to production",
]

# What this user "has": facts in their own memory. Two goals are backed by it, the
# production deploy is not, so D/I can be seen separating them.
SEED_MEMORIES = [
    ("The release checklist is: run the full test suite, update the changelog, tag the release, publish to npm last.", "fact"),
    ("The project name is declared in pyproject.toml under the name key.", "fact"),
    ("growth.py turns each agent episode into a graded MEE growth signal and persists one session per namespace.", "fact"),
]


@dataclass
class Run:
    arm: str
    goal: str
    repeat: int
    stopped_reason: str
    iterations: int
    seconds: float
    D: Optional[float]
    F_goal: Optional[float]
    G: Optional[float]
    growth_delta: Optional[float]
    verified: Optional[bool]
    skills_injected: int
    pipeline_ms: float = 0.0
    advice_lines: int = 0
    statuses: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


# ---------------------------------------------------------------------- policy
def install_rule_policy() -> None:
    """Replace the model's decision with a fixed rule set (see module doc)."""
    import re
    import rct_control_plane.autonomous_loop as loop_module
    from rct_control_plane.data_evidence import extract_paths

    async def decide(goal, history, available_tools, llm_provider=None, extra_context=""):
        names = {(t.get("name") if isinstance(t, dict) else getattr(t, "name", None)) for t in available_tools}
        if not history:
            paths = extract_paths(goal)
            lower = goal.lower()
            if "recall" in lower and "delentia_recall" in names:
                topic = re.sub(r"^.*?(?:about|of)\s+(?:the\s+)?", "", goal.rstrip(".")).strip() or goal
                return {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": topic},
                        "reasoning": "the goal asks to recall", "final_answer": None}
            if "search" in lower and "delentia_search_repo_files" in names:
                word = re.search(r"word\s+(\w+)", goal)
                return {"action": "call_tool", "tool_name": "delentia_search_repo_files",
                        "tool_args": {"pattern": word.group(1) if word else "FDIA", "max_results": 5},
                        "reasoning": "the goal asks to search", "final_answer": None}
            code = re.search(r"python -c [\"'](.+?)[\"']\s+in the sandbox", goal)
            if code and "delentia_run_sandboxed_command" in names:
                return {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command",
                        "tool_args": {"command": f'python -c "{code.group(1)}"'}, "reasoning": "the goal asks to run code",
                        "final_answer": None}
            if paths and ("read" in lower or "summar" in lower or "typo" in lower or "fix" in lower) and "delentia_read_repo_file" in names:
                return {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": paths[0]},
                        "reasoning": "the goal names a file", "final_answer": None}
            if "deploy" in lower and "delentia_run_sandboxed_command" in names:
                return {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command", "tool_args": {"command": "ls"},
                        "reasoning": "start the deploy", "final_answer": None}
        last = history[-1] if history else None
        seen = str(getattr(last, "tool_result", "") or "")[:300].replace("\n", " ")
        return {"action": "finish", "reasoning": "have what is needed", "tool_name": None, "tool_args": {},
                "final_answer": f"Completed the goal: {goal} Result: {seen}"}

    loop_module.decide_next_action = decide


# ------------------------------------------------------------------ fixtures
class Fixtures:
    """Real local inputs for the algorithms that need a URL or a video."""

    def __init__(self, workdir: Path) -> None:
        import http.server
        import socketserver

        class Site(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = b"<html><body><p>The project is delentia-os.</p></body></html>"
                self.send_response(200 if self.path != "/robots.txt" else 404)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = socketserver.TCPServer(("127.0.0.1", 0), Site)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/index.html"
        self.video_path: Optional[str] = None
        try:
            import cv2
            import numpy as np
            path = str(workdir / "fixture.mp4")
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 2, (64, 64))
            for i in range(6):
                writer.write(np.full((64, 64, 3), i * 40, dtype=np.uint8))
            writer.release()
            self.video_path = path
        except Exception:
            pass

    def close(self) -> None:
        self.server.shutdown()

    def as_dict(self, with_image: bool) -> Dict[str, Any]:
        out: Dict[str, Any] = {"url": self.url, "build_name": "bench_scaffold"}
        if self.video_path:
            out["video_path"] = self.video_path
        if with_image:
            out["image_prompt"] = "a green circle"
        return out


# ------------------------------------------------------------------- building
def build_loop(arm_dir: Path, arm: str, fixtures: Optional[Fixtures], with_llm: bool, with_image: bool,
               max_iterations: int, max_seconds: float) -> Any:
    from rct_control_plane.agent_memory import AgentMemory
    from rct_control_plane.algorithm_pipeline import AlgorithmPipeline, PipelineOptions
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    from rct_control_plane.mcp_server import _kernel, mcp
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.skill_library import SkillLibrary

    persistence = ControlPlanePersistence(db_path=str(arm_dir / "bench.db"))
    skills = SkillLibrary(db_path=str(arm_dir / "skills.db"))
    _kernel._agent_memory = AgentMemory(NAMESPACE, persistence)
    pipeline = None
    if arm in ("on", "fullstack"):
        options = PipelineOptions(
            allow_llm=with_llm, allow_network=arm == "fullstack", allow_writes=arm == "fullstack",
            fixtures=fixtures.as_dict(with_image) if (arm == "fullstack" and fixtures) else {},
        )
        pipeline = AlgorithmPipeline(_kernel, persistence, NAMESPACE, memory=_kernel._agent_memory, skills=skills, options=options)
    return GovernedAutonomousLoop(
        mcp_server=mcp, persistence=persistence, kernel=_kernel, skill_library=skills, max_iterations=max_iterations,
        max_seconds=max_seconds, namespace=NAMESPACE, algorithm_pipeline=pipeline,
    )


async def seed_memories(arm_dir: Path) -> None:
    from rct_control_plane.agent_memory import AgentMemory, MemoryType
    from rct_control_plane.persistence import ControlPlanePersistence
    memory = AgentMemory(NAMESPACE, ControlPlanePersistence(db_path=str(arm_dir / "bench.db")))
    for content, kind in SEED_MEMORIES:
        await memory.store(content, MemoryType(kind), importance=0.9)


async def run_bench(arms: List[str], repeats: int, goals: List[str], with_llm: bool, with_image: bool, delay: float,
                    max_iterations: int, max_seconds: float, workdir: Path, log=print) -> List[Run]:
    fixtures = Fixtures(workdir) if "fullstack" in arms else None
    runs: List[Run] = []
    try:
        for arm in arms:
            arm_dir = workdir / f"arm-{arm}"
            arm_dir.mkdir(parents=True, exist_ok=True)
            await seed_memories(arm_dir)
            for rep in range(1, repeats + 1):
                for goal in goals:
                    loop = build_loop(arm_dir, arm, fixtures, with_llm, with_image, max_iterations, max_seconds)
                    t0 = time.monotonic()
                    try:
                        result = await loop.run(goal)
                        err = None
                    except Exception as exc:
                        result, err = {"stopped_reason": "error", "iterations": 0}, f"{type(exc).__name__}: {exc}"
                    growth = result.get("growth") or {}
                    pipeline = result.get("pipeline") or {}
                    verification = result.get("intent_verification") or {}
                    statuses: Dict[str, int] = defaultdict(int)
                    for trace in pipeline.get("traces", []):
                        statuses[trace["status"]] += 1
                    run = Run(
                        arm=arm, goal=goal, repeat=rep, stopped_reason=result.get("stopped_reason", "?"),
                        iterations=int(result.get("iterations") or 0), seconds=round(time.monotonic() - t0, 2),
                        D=(growth.get("data") or {}).get("D"), F_goal=None, G=growth.get("G"), growth_delta=growth.get("delta"),
                        verified=verification.get("aligned_with_intent") if verification.get("applicable") else None,
                        skills_injected=int(getattr(loop, "_episode_skills_injected", 0) or 0),
                        pipeline_ms=float(pipeline.get("total_ms") or 0.0), advice_lines=int(pipeline.get("advice_lines") or 0),
                        statuses=dict(statuses), error=err,
                    )
                    if run.D is not None:
                        run.F_goal = round(run.D ** float(getattr(loop, "_episode_I", 1.0) or 1.0), 4)
                    run.__dict__["traces"] = pipeline.get("traces", [])
                    runs.append(run)
                    log(f"[{arm:9} #{rep}] {run.stopped_reason:<17} steps={run.iterations} D={run.D} G={run.G} "
                        f"pipeline={run.pipeline_ms:.0f}ms ok={statuses.get('ok', 0)} na={statuses.get('not_triggered', 0)} "
                        f"err={statuses.get('error', 0)}  {goal[:48]}" + (f"  ERROR {err}" if err else ""))
                    if delay:
                        await asyncio.sleep(delay)
    finally:
        if fixtures:
            fixtures.close()
    return runs


# --------------------------------------------------------------------- report
def _p95(values: List[float]) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    return sorted(values)[max(0, int(round(0.95 * len(values))) - 1)]


def summarize(runs: List[Run]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"arms": {}, "algorithms": {}, "learning": []}
    for arm in sorted({r.arm for r in runs}):
        rs = [r for r in runs if r.arm == arm and not r.error]
        out["arms"][arm] = {
            "episodes": len(rs), "errors": sum(1 for r in runs if r.arm == arm and r.error),
            "avg_seconds": round(statistics.mean(r.seconds for r in rs), 2) if rs else None,
            "avg_pipeline_ms": round(statistics.mean(r.pipeline_ms for r in rs), 1) if rs else None,
            "avg_steps": round(statistics.mean(r.iterations for r in rs), 2) if rs else None,
            "finished": sum(1 for r in rs if r.stopped_reason == "llm_finished"),
            "verified": sum(1 for r in rs if r.verified),
            "blocked_by_fdia": sum(1 for r in rs if r.stopped_reason == "fdia_blocked"),
            "avg_D": round(statistics.mean(r.D for r in rs if r.D is not None), 3) if any(r.D is not None for r in rs) else None,
            "final_G": max((r.G for r in rs if r.G is not None), default=None),
            "avg_advice_lines": round(statistics.mean(r.advice_lines for r in rs), 2) if rs else None,
        }
    per_algo: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"ms": [], "ok": 0, "not_triggered": 0, "error": 0, "stages": set(), "name": ""})
    for r in runs:
        for t in r.__dict__.get("traces", []):
            entry = per_algo[t["algo_id"]]
            entry["name"] = t["name"]
            entry["stages"].add(t["stage"])
            entry[t["status"]] += 1
            if t["status"] == "ok":
                entry["ms"].append(t["ms"])
    for algo_id in sorted(per_algo):
        e = per_algo[algo_id]
        out["algorithms"][algo_id] = {
            "name": e["name"], "stages": sorted(e["stages"]), "ok": e["ok"], "not_triggered": e["not_triggered"], "error": e["error"],
            "mean_ms": round(statistics.mean(e["ms"]), 2) if e["ms"] else None, "p95_ms": round(_p95(e["ms"]), 2) if e["ms"] else None,
        }
    out["algorithms_that_executed"] = sum(1 for v in out["algorithms"].values() if v["ok"] > 0)
    for goal in sorted({r.goal for r in runs}):
        for arm in sorted({r.arm for r in runs}):
            rs = sorted((r for r in runs if r.goal == goal and r.arm == arm and not r.error), key=lambda r: r.repeat)
            if len(rs) >= 2:
                out["learning"].append({
                    "goal": goal[:60], "arm": arm, "first": {"steps": rs[0].iterations, "D": rs[0].D, "G": rs[0].G},
                    "last": {"steps": rs[-1].iterations, "D": rs[-1].D, "G": rs[-1].G, "skills_injected": rs[-1].skills_injected},
                })
    return out


def render_table(summary: Dict[str, Any]) -> str:
    lines = [f"{'algorithm':10} {'name':38} {'stage':9} {'ok':>4} {'n/a':>4} {'err':>4} {'mean ms':>9} {'p95 ms':>9}"]
    for algo_id, v in summary["algorithms"].items():
        lines.append(f"{algo_id:10} {v['name'][:38]:38} {','.join(v['stages'])[:9]:9} {v['ok']:>4} {v['not_triggered']:>4} "
                     f"{v['error']:>4} {str(v['mean_ms']):>9} {str(v['p95_ms']):>9}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", choices=["policy", "live"], default="policy")
    ap.add_argument("--arms", default="off,on,fullstack")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--with-llm", action="store_true", help="also run ALGO-09/11/32 (they call the model several times)")
    ap.add_argument("--with-image", action="store_true", help="also run ALGO-14 image generation in fullstack (about a minute)")
    ap.add_argument("--max-iterations", type=int, default=5)
    ap.add_argument("--max-seconds", type=float, default=240.0)
    ap.add_argument("--delay", type=float, default=0.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.policy == "policy":
        install_rule_policy()
        print("decisions: fixed rule policy (no model) - this measures the system, not a model")
    else:
        from rct_control_plane.model_config import resolve_model_selection
        sel = resolve_model_selection()
        print(f"decisions: {sel.model} ({sel.provider}, chosen by {sel.model_source})")
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    with tempfile.TemporaryDirectory(prefix="delentia-loopbench-", ignore_cleanup_errors=True) as tmp:
        runs = asyncio.run(run_bench(arms, args.repeats, GOALS, args.with_llm, args.with_image, args.delay,
                                     args.max_iterations, args.max_seconds, Path(tmp)))
    summary = summarize(runs)
    print("\n" + json.dumps({k: v for k, v in summary.items() if k != "algorithms"}, indent=2, ensure_ascii=False))
    print(f"\n{summary['algorithms_that_executed']} of 41 algorithms executed at least once\n")
    print(render_table(summary))
    if args.out:
        payload = {"policy": args.policy, "summary": summary,
                   "runs": [{**asdict(r), "traces": r.__dict__.get("traces", [])} for r in runs]}
        Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"\nsaved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

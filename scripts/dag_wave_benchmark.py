"""
Measure what running tool calls as an Execution Graph really buys (Round 54).

The real tool registry (`mcp`), the real executor (rct_control_plane/dag_executor.py) and worker threads exactly as the
governed loop uses them; no governance in the way, so the numbers are about the executor, not about a model. Four
shapes, each run serially (one call after the other) and as waves, three repeats, the median reported:

  latency-bound  4 independent shell commands that wait 0.5 s (a stand-in for network or a slow subprocess)
  diamond        a -> (b, c) -> d, each waiting 0.5 s
  chain          a -> b -> c -> d, each waiting 0.5 s (nothing to overlap)
  cpu-bound      4 independent repository searches (Python work that holds the GIL)

    python scripts/dag_wave_benchmark.py [--json out.json] [--repeats 3]

Expected and honest: latency-bound work overlaps (about 3-4x for four calls), a diamond is bounded by its critical path,
a chain gains nothing, and CPU-bound Python gains little or nothing because threads share the GIL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SLEEP_CMD = 'python -c "import time; time.sleep(0.5)"'


def shapes() -> Dict[str, Dict[str, Any]]:
    from rct_control_plane.dag_executor import BatchCall
    shell = lambda cid, deps=(): BatchCall(cid, "delentia_run_sandboxed_command", {"command": SLEEP_CMD, "timeout_seconds": 20}, list(deps))  # noqa: E731
    search = lambda cid: BatchCall(cid, "delentia_search_repo_files", {"pattern": "def ", "glob": "rct_control_plane/*.py"}, [])  # noqa: E731
    return {
        "latency-bound (4 independent waits)": {"calls": [shell(c) for c in "abcd"]},
        "diamond (a -> b,c -> d)": {"calls": [shell("a"), shell("b", "a"), shell("c", "a"), shell("d", "bc")]},
        "chain (a -> b -> c -> d)": {"calls": [shell("a"), shell("b", "a"), shell("c", "b"), shell("d", "c")]},
        "cpu-bound (4 repository searches)": {"calls": [search(c) for c in "abcd"]},
    }


async def run_once(calls: List[Any], parallel: bool) -> Dict[str, Any]:
    from rct_control_plane import dag_executor as dag
    from rct_control_plane.mcp_server import mcp

    async def invoke(name: str, args: Dict[str, Any]) -> Any:
        raw = await mcp.call_tool(name, args)
        return json.loads(raw.content[0].text)

    async def run_one(call: Any) -> Any:
        return await asyncio.to_thread(lambda: asyncio.run(invoke(call.tool_name, call.tool_args)))

    graph = dag.compile_batch(calls)
    started = time.perf_counter()
    if parallel:
        report = await dag.run_waves(graph, run_one)
        failed = [cid for cid, o in report.outcomes.items() if o.status != "done"]
        return {"wall_ms": (time.perf_counter() - started) * 1000, "critical_path_ms": report.critical_path_ms, "failed": failed, "waves": report.waves}
    failed = []
    for call in calls:                                            # the same calls, one after the other, in dependency order
        result = await run_one(call)
        if isinstance(result, dict) and result.get("error"):
            failed.append(call.id)
    return {"wall_ms": (time.perf_counter() - started) * 1000, "failed": failed}


async def main_async(repeats: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    await run_once(shapes()["cpu-bound (4 repository searches)"]["calls"], False)        # warm-up: imports, file cache
    for name, shape in shapes().items():
        serial = [await run_once(shape["calls"], False) for _ in range(repeats)]
        waved = [await run_once(shape["calls"], True) for _ in range(repeats)]
        s_ms = statistics.median(r["wall_ms"] for r in serial)
        w_ms = statistics.median(r["wall_ms"] for r in waved)
        rows.append({
            "shape": name, "calls": len(shape["calls"]), "serial_ms": round(s_ms), "waves_ms": round(w_ms),
            "speedup": round(s_ms / w_ms, 2), "waves": waved[0]["waves"], "critical_path_ms": round(statistics.median(r["critical_path_ms"] for r in waved)),
            "failed": sorted({f for r in serial + waved for f in r["failed"]}),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    rows = asyncio.run(main_async(max(1, args.repeats)))
    print(f"{'shape':40} {'calls':>5} {'serial ms':>10} {'waves ms':>9} {'speedup':>8} {'critical path ms':>17}")
    for r in rows:
        print(f"{r['shape']:40} {r['calls']:>5} {r['serial_ms']:>10} {r['waves_ms']:>9} {r['speedup']:>7}x {r['critical_path_ms']:>17}"
              + (f"   FAILED: {r['failed']}" if r["failed"] else ""))
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 1 if any(r["failed"] for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())

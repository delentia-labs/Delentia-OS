"""
Wavefront execution of tool calls over the Execution Graph IR (Round 54).

The IR (execution_graph_ir.py) existed since the early rounds and nothing in the agent used it. This is the use:
when the model sees that several tool calls do not depend on each other (read three files, search two directories,
crawl two pages) it can ask for them in ONE decision:

    {"action": "call_tools", "calls": [
        {"id": "a", "tool_name": "delentia_read_repo_file", "tool_args": {...}},
        {"id": "b", "tool_name": "delentia_search_repo_files", "tool_args": {...}},
        {"id": "c", "tool_name": "delentia_write_repo_file", "tool_args": {...}, "depends_on": ["a", "b"]}],
     "reasoning": "..."}

The calls become an ExecutionGraph (a node per call, a SEQUENTIAL edge per `depends_on`), the graph is validated (size,
unknown ids, cycles) and run in waves: every call whose dependencies are done runs at the same time, up to
`max_parallel`. A call whose dependency failed is skipped, never run on stale assumptions.

What this does and does not buy (measured by scripts/dag_wave_benchmark.py, not assumed):
  * It saves model round trips: n calls cost one decision instead of n.
  * It overlaps WAITING: network, subprocesses, disks. Tools in PARALLEL_SAFE_TOOLS run in worker threads, so the wait of
    one does not block the others. CPU-bound work in Python does not get faster (the GIL), and RCT-7's own steps are a
    chain (1 -> 7), so there is nothing to parallelise there: compiling the RCT-7 plan to the IR would only produce a line.
  * The other tools in a batch still run, one at a time on the event loop, in call order, in the same wave.
  * The batch is governed exactly like single calls: the loop gates and screens every call BEFORE any of them runs.
    A single refusal (FDIA, policy, jury, approval) stops the whole batch with nothing executed.

`depends_on` orders calls; it does not pass results (the model cannot name a result it has not seen yet).
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from rct_control_plane.execution_graph_ir import DependencyEdge, ExecutionGraph, ExecutionNode, NodeType

PARALLEL_ENV = "DELENTIA_PARALLEL_TOOLS"
MAX_CALLS = 8
MAX_PARALLEL = 4
# Tools whose body only waits on the outside world or reads files, and keeps no state shared with other calls.
PARALLEL_SAFE_TOOLS = frozenset({
    "delentia_read_repo_file", "delentia_search_repo_files", "delentia_crawl_url", "delentia_run_sandboxed_command",
    "delentia_list_exchange_files", "delentia_read_exchange_file",
})


class BatchError(ValueError):
    """The model asked for a batch that cannot be run; the message goes back to the model."""


def enabled() -> bool:
    return os.environ.get(PARALLEL_ENV, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class BatchCall:
    id: str
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)


@dataclass
class CallOutcome:
    id: str
    status: str                      # done | failed | skipped
    result: Any = None
    wave: int = -1
    started_ms: float = 0.0
    elapsed_ms: float = 0.0
    note: str = ""


@dataclass
class WaveReport:
    outcomes: Dict[str, CallOutcome]
    waves: List[List[str]]
    wall_ms: float
    sequential_ms: float             # what the calls would have taken one after the other (sum of their own times)
    critical_path_ms: float          # the best any amount of parallelism could do with this graph

    @property
    def speedup(self) -> float:
        return round(self.sequential_ms / self.wall_ms, 2) if self.wall_ms > 0 else 1.0

    def summary(self) -> Dict[str, Any]:
        return {"calls": len(self.outcomes), "waves": self.waves, "wall_ms": round(self.wall_ms, 1),
                "sequential_ms": round(self.sequential_ms, 1), "critical_path_ms": round(self.critical_path_ms, 1),
                "speedup": self.speedup,
                "statuses": {cid: o.status for cid, o in self.outcomes.items()}}


def parse_calls(raw: Any) -> List[BatchCall]:
    """The model's `calls` list -> BatchCall objects. Missing ids are numbered c1, c2 ... in order."""
    if not isinstance(raw, list) or not raw:
        raise BatchError("`calls` must be a non-empty list of {id, tool_name, tool_args, depends_on}")
    if len(raw) > MAX_CALLS:
        raise BatchError(f"a batch holds at most {MAX_CALLS} calls (got {len(raw)}); split it")
    calls: List[BatchCall] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("tool_name"), str) or not item["tool_name"].strip():
            raise BatchError(f"call {index}: tool_name is required")
        args = item.get("tool_args") or {}
        deps = item.get("depends_on") or []
        if not isinstance(args, dict):
            raise BatchError(f"call {index}: tool_args must be an object")
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            raise BatchError(f"call {index}: depends_on must be a list of call ids")
        cid = str(item.get("id") or f"c{index}")[:32]
        calls.append(BatchCall(cid, item["tool_name"].strip(), args, list(deps)))
    return calls


def compile_batch(calls: List[BatchCall], intent_id: str = "batch") -> ExecutionGraph:
    """Calls -> a validated ExecutionGraph. Raises BatchError for duplicate ids, unknown dependencies and cycles."""
    ids = [c.id for c in calls]
    if len(set(ids)) != len(ids):
        raise BatchError("call ids must be unique")
    graph = ExecutionGraph(intent_id=intent_id)
    for call in calls:
        graph.add_node(ExecutionNode(id=call.id, node_type=NodeType.TOOL_CALL, tool_name=call.tool_name, parameters=call.tool_args))
    for call in calls:
        for dep in call.depends_on:
            if dep == call.id:
                raise BatchError(f"call {call.id} cannot depend on itself")
            if dep not in graph.nodes:
                raise BatchError(f"call {call.id} depends on {dep!r}, which is not in this batch")
            try:
                graph.add_edge(DependencyEdge(from_node=dep, to_node=call.id))
            except ValueError as exc:
                raise BatchError(f"the dependencies form a cycle ({exc})") from None
    return graph


def waves_of(graph: ExecutionGraph) -> List[List[str]]:
    """The wavefront schedule: wave k holds every call whose longest dependency chain has length k."""
    order = graph.topological_sort()
    level: Dict[str, int] = {}
    for node_id in order:
        deps = graph.get_dependencies(node_id)
        level[node_id] = 1 + max((level[d] for d in deps), default=-1)
    waves: List[List[str]] = []
    for node_id in order:
        while len(waves) <= level[node_id]:
            waves.append([])
        waves[level[node_id]].append(node_id)
    call_order = list(graph.nodes)
    return [sorted(w, key=call_order.index) for w in waves]


async def run_waves(
    graph: ExecutionGraph,
    run_one: Callable[[BatchCall], Awaitable[Any]],
    *,
    max_parallel: int = MAX_PARALLEL,
    is_failure: Optional[Callable[[Any], bool]] = None,
) -> WaveReport:
    """Runs the graph wave by wave. `run_one` executes one call and returns its result; an exception, or a result for
    which `is_failure` is true, marks the call failed and its dependents skipped."""
    semaphore = asyncio.Semaphore(max(1, max_parallel))
    outcomes: Dict[str, CallOutcome] = {}
    schedule = waves_of(graph)
    origin = time.perf_counter()

    async def execute(node_id: str, wave: int) -> None:
        node = graph.nodes[node_id]
        call = BatchCall(node_id, node.tool_name or "", dict(node.parameters), graph.get_dependencies(node_id))
        blockers = [d for d in call.depends_on if outcomes[d].status != "done"]
        if blockers:
            outcomes[node_id] = CallOutcome(node_id, "skipped", wave=wave, note=f"not run: {', '.join(blockers)} did not finish")
            return
        async with semaphore:
            started = time.perf_counter()
            try:
                result = await run_one(call)
                failed = bool(is_failure and is_failure(result))
                outcome = CallOutcome(node_id, "failed" if failed else "done", result, wave)
            except Exception as exc:                                  # a failing call must not take its siblings down
                outcome = CallOutcome(node_id, "failed", {"error": f"{type(exc).__name__}: {exc}"[:300]}, wave)
            outcome.started_ms = (started - origin) * 1000
            outcome.elapsed_ms = (time.perf_counter() - started) * 1000
            outcomes[node_id] = outcome

    for wave_index, wave in enumerate(schedule):
        await asyncio.gather(*(execute(node_id, wave_index) for node_id in wave))

    wall = (time.perf_counter() - origin) * 1000
    ran = [o for o in outcomes.values() if o.status != "skipped"]
    sequential = sum(o.elapsed_ms for o in ran)
    finish: Dict[str, float] = {}
    for node_id in graph.topological_sort():
        o = outcomes[node_id]
        finish[node_id] = max((finish[d] for d in graph.get_dependencies(node_id)), default=0.0) + (o.elapsed_ms if o.status != "skipped" else 0.0)
    return WaveReport(outcomes, schedule, wall, sequential, max(finish.values(), default=0.0))

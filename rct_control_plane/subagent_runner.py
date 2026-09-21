"""
Round 38: real JITNA sub-agent entry point - runs as a SEPARATE OS
process (invoked as `python -m rct_control_plane.subagent_runner`), not
a concurrent function call within the dispatching process. This is what
closes the real gap Round 38's own investigation found: "Nodal
Assembly" (nodal_assembly.py) only ever dispatches concurrent function
calls within ONE process, and its own docstring already honestly
discloses that - "no persistent multi-agent state is kept here." This
module is the genuine separate-process counterpart, dispatched by
jitna_distributor.py's distribute_to_subagents().

Runs a real AutonomousLoop against one goal, inside a real, isolated
git worktree (created by the dispatcher via GitWorktreeIsolator before
this process is spawned). Prints exactly ONE JSON line to stdout as its
final output - the dispatcher parses the last stdout line, so any
logging noise on earlier lines/stderr does not break parsing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--max-iterations", type=int, default=3)
    args = parser.parse_args()

    from rct_control_plane.autonomous_loop import AutonomousLoop
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.mcp_server import mcp

    persistence = ControlPlanePersistence(db_path="rct_control_plane_agentic.db")
    loop = AutonomousLoop(
        mcp_server=mcp, persistence=persistence,
        namespace=f"jitna-subagent-{args.agent_id}", max_iterations=args.max_iterations,
    )
    result = await loop.run(args.goal)
    print(json.dumps({
        "agent_id": args.agent_id,
        "worktree": args.worktree,
        "final_answer": result.get("final_answer"),
        "stopped_reason": result.get("stopped_reason"),
        "iterations": result.get("iterations"),
    }))


if __name__ == "__main__":
    asyncio.run(_main())

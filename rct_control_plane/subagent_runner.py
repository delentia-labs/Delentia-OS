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


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--goal", default=None, help="legacy: unsigned goal (used only when no --request is given)")
    parser.add_argument("--request", default=None, help="Round 50: the orchestrator's signed JITNA intent request (JSON)")
    parser.add_argument("--parent-pubkey", default=None, help="hex public key the request must be signed with")
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--max-iterations", type=int, default=3)
    args = parser.parse_args()

    request = None
    goal = args.goal
    max_iterations = args.max_iterations
    if args.request:
        # Verified before anything heavy is imported: a request that fails
        # verification never reaches the kernel or a model.
        from rct_control_plane import jitna_subagent
        request, reason = jitna_subagent.verify_request(args.request, args.parent_pubkey or "", args.agent_id)
        if request is None:
            print(json.dumps({"agent_id": args.agent_id, "rejected": reason}))
            return 2
        goal = request.payload["goal"]
        max_iterations = int(request.payload.get("max_iterations") or max_iterations)
    if not goal:
        print(json.dumps({"agent_id": args.agent_id, "rejected": "no goal (pass --request or --goal)"}))
        return 2

    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.data_home import agentic_db_path
    from rct_control_plane.mcp_server import _kernel, mcp

    persistence = ControlPlanePersistence(db_path=agentic_db_path())
    # Round 48 R0.1: sub-agents are governed too (they previously ran a
    # plain AutonomousLoop). mcp_server's module-level kernel is already
    # built by the import above, so this adds no second cold start.
    loop = build_governed_loop(
        _kernel, namespace=f"jitna-subagent-{args.agent_id}",
        max_iterations=max_iterations, persistence=persistence, mcp_server=mcp,
    )
    result = await loop.run(goal)
    out = {
        "agent_id": args.agent_id,
        "worktree": args.worktree,
        "final_answer": result.get("final_answer"),
        "stopped_reason": result.get("stopped_reason"),
        "iterations": result.get("iterations"),
        "tainted": bool((result.get("taint") or {}).get("tainted", True)),
        "taint_source": (result.get("taint") or {}).get("source_tool"),
    }
    if request is not None:
        from rct_control_plane import jitna_subagent
        from rct_control_plane.jitna_protocol import JITNAKeypair
        response, keypair = jitna_subagent.make_response(
            request, {k: out[k] for k in ("final_answer", "stopped_reason", "iterations", "tainted", "taint_source")})
        keypair_pub: JITNAKeypair = keypair
        out["jitna_response"] = response.to_dict()
        out["child_public_key"] = keypair_pub.public_key_raw().hex()
    print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))

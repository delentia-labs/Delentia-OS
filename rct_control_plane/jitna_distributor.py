"""
Round 38: real JITNA sub-agent distribution - dispatches genuinely
SEPARATE OS PROCESSES (not concurrent function calls within one
process, unlike nodal_assembly.py's own honestly-disclosed limitation)
to isolated real git worktrees, and records every completed sub-agent's
result into RCTDB - closing the two real gaps Round 38's investigation
found:
  1. "Nodal Assembly"/JITNA never actually forked out to separate
     agents/processes - it's single-process concurrent dispatch.
  2. GitWorktreeIsolator creates/removes real worktrees but nothing
     connected completed work back into persistence/RCTDB.

Real fork-join: each goal gets its own real git worktree (or the
existing, honestly-labeled VIRTUAL_ISOLATION_FALLBACK when git worktree
isn't available) AND a real, separate `python -m rct_control_plane.
subagent_runner` subprocess running a real AutonomousLoop against that
goal. All subprocesses run concurrently (asyncio.gather over real
subprocess futures - a genuine fork), then results are collected and
each is written to persistence.save_architect_decision() (Round 27's
existing, already-tested real table) under decision_type=
"jitna_subagent_result" (the join, with real durability).

`_dispatch_subagent` is a deliberate testable seam (the same pattern
established by gateways/telegram_gateway.py and chat_app.py) - tests
monkeypatch it to avoid spawning real subprocesses/LLM calls; the real
default implementation genuinely spawns `subagent_runner.py`.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any, Callable, Dict, List, Optional

from rct_control_plane.git_worktree_isolator import GitWorktreeIsolator


SUBAGENT_DEPTH_ENV = "DELENTIA_SUBAGENT_DEPTH"
MAX_SUBAGENT_DEPTH = 1       # a subagent is a leaf: it works on its goal, it does not spawn more processes


def subagent_depth() -> int:
    try:
        return max(0, int(os.environ.get(SUBAGENT_DEPTH_ENV, "0")))
    except ValueError:
        return 0


async def _dispatch_subagent(agent_id: str, goal: str, worktree_path: str, timeout_seconds: float,
                             request_json: Optional[str] = None,
                             parent_public_key_hex: Optional[str] = None) -> Dict[str, Any]:
    """Real, separate-process dispatch - the default, production
    implementation. Spawns `python -m rct_control_plane.subagent_runner`
    as a genuinely independent OS process.

    Round 50: the goal travels in an Ed25519-signed JITNA request when
    `request_json` is given (see jitna_subagent.py), and the subagent's file
    tools are sandboxed to its own worktree through DELENTIA_REPO_ROOT."""
    cmd = [sys.executable, "-m", "rct_control_plane.subagent_runner",
           "--agent-id", agent_id, "--worktree", worktree_path]
    if request_json is not None:
        cmd += ["--request", request_json, "--parent-pubkey", parent_public_key_hex or ""]
    else:
        cmd += ["--goal", goal]
    proc = await asyncio.create_subprocess_exec(
        *cmd, env={**os.environ, "DELENTIA_REPO_ROOT": worktree_path,
                   "DELENTIA_SUBAGENT_DEPTH": str(subagent_depth() + 1)},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"timed_out": True}

    lines = [l for l in stdout.decode("utf-8", errors="replace").strip().splitlines() if l.strip()]
    if not lines:
        return {
            "parse_error": True,
            "raw_stderr": stderr.decode("utf-8", errors="replace")[-2000:],
        }
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {
            "parse_error": True,
            "raw_stdout": stdout.decode("utf-8", errors="replace")[-2000:],
            "raw_stderr": stderr.decode("utf-8", errors="replace")[-2000:],
        }


async def distribute_to_subagents(
    goals: List[str],
    persistence: Any,
    repo_root: Optional[str] = None,
    base_branch: str = "main",
    timeout_seconds: float = 60.0,
    dispatch_fn: Optional[Callable[..., Any]] = None,
) -> List[Dict[str, Any]]:
    """Real fork-join over `goals`. `dispatch_fn` defaults to the real
    `_dispatch_subagent` (spawns real subprocesses) - tests pass a fake
    to avoid real subprocess/LLM calls while still exercising the real
    worktree-creation/RCTDB-recording/worktree-cleanup logic."""
    signed_mode = dispatch_fn is None  # tests pass a fake dispatch_fn with the 4-argument signature
    dispatch_fn = dispatch_fn or _dispatch_subagent
    isolator = GitWorktreeIsolator(repo_root=repo_root)
    from rct_control_plane import jitna_subagent
    from rct_control_plane.jitna_protocol import JITNAPacket, generate_keypair
    keypair = generate_keypair()
    parent_public_key_hex = keypair.public_key_raw().hex()
    distribution_id = uuid.uuid4().hex
    requests: Dict[str, JITNAPacket] = {}

    agent_ids: List[str] = []
    worktree_infos: List[Dict[str, Any]] = []
    tasks = []
    for goal in goals:
        agent_id = uuid.uuid4().hex[:8]
        agent_ids.append(agent_id)
        worktree_info = isolator.create_worktree(agent_id, base_branch=base_branch)
        worktree_infos.append(worktree_info)
        if signed_mode:
            request = jitna_subagent.make_request(goal, agent_id, worktree_info["worktree_path"], 3, keypair,
                                                  correlation_id=distribution_id)
            requests[agent_id] = request
            tasks.append(dispatch_fn(agent_id, goal, worktree_info["worktree_path"], timeout_seconds,
                                     request_json=request.to_json(), parent_public_key_hex=parent_public_key_hex))
        else:
            tasks.append(dispatch_fn(agent_id, goal, worktree_info["worktree_path"], timeout_seconds))

    dispatch_results = await asyncio.gather(*tasks, return_exceptions=True)

    real_results: List[Dict[str, Any]] = []
    for agent_id, goal, worktree_info, dispatch_result in zip(
        agent_ids, goals, worktree_infos, dispatch_results, strict=True,
    ):
        outcome: Dict[str, Any]
        if isinstance(dispatch_result, BaseException):
            outcome = {"agent_id": agent_id, "goal": goal, "success": False, "error": str(dispatch_result)}
        else:
            outcome = {"agent_id": agent_id, "goal": goal, "success": True, **dispatch_result}
            maybe_request = requests.get(agent_id)
            if maybe_request is not None:
                request = maybe_request
                response = outcome.pop("jitna_response", None)
                child_key = str(outcome.pop("child_public_key", "") or "")
                if outcome.get("rejected"):
                    outcome["success"] = False
                if response is None:
                    verified, why = False, outcome.get("rejected") or "no signed response"
                else:
                    verified, why = jitna_subagent.verify_response(response, child_key, request)
                outcome["jitna"] = {"request_packet_id": request.packet_id, "request_hash": request.compute_hash(),
                                    "response_verified": verified, "reason": why or None}
                if not verified:
                    outcome["success"] = False
        real_results.append(outcome)

        # The real join: completed sub-agent work now genuinely reaches
        # RCTDB, closing the gap Round 38's investigation confirmed was
        # previously open (no code path connected worktree/swarm
        # completion back into persistence anywhere in this codebase).
        persistence.save_architect_decision(
            decision_id=f"jitna-subagent-{agent_id}",
            decision_type="jitna_subagent_result",
            description=f"sub-agent {agent_id} completed goal: {goal[:100]}",
            jitna_before={"goal": goal, "agent_id": agent_id, "worktree_status": worktree_info["status"]},
            jitna_after=outcome,
        )

        isolator.remove_worktree(agent_id)

    return real_results

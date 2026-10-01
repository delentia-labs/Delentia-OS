"""
Agent Profile (Round 22 Phase 8) — lightweight per-profile identity for
multi-agent delegation, mirroring Hermes's `-p <name>` profile scope
without the cost of a second full kernel instance (confirmed with the
user 2026-09-18: profiles share the parent kernel's heavy engines,
which are stateless per call, and only isolate real state).
"""
from __future__ import annotations

import contextvars
import os
import time
from dataclasses import dataclass

from rct_control_plane.agent_memory import AgentMemory


@dataclass
class AgentProfile:
    profile_name: str
    mee_session_key: str
    persistence_namespace: str
    created_at: float
    agent_memory: AgentMemory


def get_or_create_profile(kernel, profile_name: str) -> AgentProfile:
    key = f"profile:{profile_name}"
    # Real, already-existing MEEEngine method - ensures the profile's
    # own isolated MEESession exists without creating a second engine.
    kernel._mee_engine.get_or_create(key)
    # Round 22 Phase 9 Task 19: each profile gets its own real AgentMemory
    # namespace, isolated the same way MEE growth state is isolated.
    memory = AgentMemory(namespace=key, persistence=kernel._persistence)
    return AgentProfile(profile_name=profile_name, mee_session_key=key,
                         persistence_namespace=key, created_at=time.time(), agent_memory=memory)


# Round 52: delegation is bounded. A delegated profile's loop has the same tool list, including
# delentia_delegate, so without a limit a model could delegate to itself without end (each level
# bounded by its own step budget, but multiplied across levels).
_delegation_depth: contextvars.ContextVar[int] = contextvars.ContextVar("delentia_delegation_depth", default=0)
MAX_DELEGATION_DEPTH_ENV = "DELENTIA_MAX_DELEGATION_DEPTH"
DEFAULT_MAX_DELEGATION_DEPTH = 2


def max_delegation_depth() -> int:
    try:
        return max(0, int(os.environ.get(MAX_DELEGATION_DEPTH_ENV, DEFAULT_MAX_DELEGATION_DEPTH)))
    except ValueError:
        return DEFAULT_MAX_DELEGATION_DEPTH


async def delegate_to_profile(kernel, profile_name: str, sub_goal: str, max_iterations: int = 3) -> dict:
    # Round 48: governed (R0.1), and runs the profile's own model when
    # ~/.delentia/model.json configures one for it.
    from rct_control_plane.agent_factory import build_governed_loop

    depth = _delegation_depth.get()
    if depth >= max_delegation_depth():
        return {"profile_name": profile_name, "stopped_reason": "delegation_depth_exceeded", "final_answer": None,
                "error": f"delegation is limited to {max_delegation_depth()} levels; do this part yourself instead of delegating again"}
    profile = get_or_create_profile(kernel, profile_name)
    loop = build_governed_loop(kernel, namespace=profile.persistence_namespace,
                               max_iterations=max_iterations, profile=profile_name)
    token = _delegation_depth.set(depth + 1)
    try:
        result = await loop.run(sub_goal)
    finally:
        _delegation_depth.reset(token)
    return {"profile_name": profile_name, **result}

"""
Agent Profile (Round 22 Phase 8) — lightweight per-profile identity for
multi-agent delegation, mirroring Hermes's `-p <name>` profile scope
without the cost of a second full kernel instance (confirmed with the
user 2026-09-18: profiles share the parent kernel's heavy engines,
which are stateless per call, and only isolate real state).
"""
from __future__ import annotations

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


async def delegate_to_profile(kernel, profile_name: str, sub_goal: str, max_iterations: int = 3) -> dict:
    from rct_control_plane.autonomous_loop import AutonomousLoop
    from rct_control_plane.mcp_server import mcp

    profile = get_or_create_profile(kernel, profile_name)
    loop = AutonomousLoop(mcp_server=mcp, persistence=kernel._persistence,
                           max_iterations=max_iterations, namespace=profile.persistence_namespace)
    result = await loop.run(sub_goal)
    return {"profile_name": profile_name, **result}

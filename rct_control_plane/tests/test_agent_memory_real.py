"""
Real general-purpose AgentMemory tests — Round 22 Phase 9.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.agent_memory import AgentMemory, MemoryType


def test_recall_ranks_the_real_matching_memory_first():
    persistence = ControlPlanePersistence(db_path="rct_control_plane_agentic.db")
    memory = AgentMemory(namespace="test_memory_ns", persistence=persistence)

    async def run():
        await memory.store("The user's favorite color is blue", MemoryType.FACT)
        await memory.store("The user prefers concise responses", MemoryType.PREFERENCE)
        await memory.store("The weather forecast mentioned rain tomorrow", MemoryType.EVENT)
        return await memory.recall("what color does the user like", limit=3)

    results = asyncio.run(run())
    assert len(results) >= 1
    assert "blue" in results[0]["content"]

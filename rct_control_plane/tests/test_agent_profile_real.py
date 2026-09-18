"""
Real Agent Profile / multi-agent delegation tests — Round 22 Phase 8.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.agent_profile import get_or_create_profile
from rct_control_plane.agent_memory import MemoryType


def test_two_profiles_have_independent_mee_growth_state():
    kernel = AlgorithmKernel41()
    profile_a = get_or_create_profile(kernel, "profile_a")
    profile_b = get_or_create_profile(kernel, "profile_b")

    session_a = kernel._mee_engine.get_or_create(profile_a.mee_session_key)
    session_b = kernel._mee_engine.get_or_create(profile_b.mee_session_key)

    kernel._mee_engine.step(profile_a.mee_session_key, delta=0.9)

    assert session_a.g != 1.0, "profile A's real step must move its own G"
    assert session_b.g == 1.0, "profile B's G must be untouched by profile A's real step"


def test_delegate_to_two_profiles_concurrently_stays_independent():
    import asyncio
    from rct_control_plane.agent_profile import delegate_to_profile

    kernel = AlgorithmKernel41()

    async def run_both():
        return await asyncio.gather(
            delegate_to_profile(kernel, "profile_x", "Say hello and finish, no tool needed.", max_iterations=2),
            delegate_to_profile(kernel, "profile_y", "Say goodbye and finish, no tool needed.", max_iterations=2),
        )

    result_x, result_y = asyncio.run(run_both())

    assert result_x["profile_name"] == "profile_x"
    assert result_y["profile_name"] == "profile_y"
    assert result_x["iterations"] >= 1
    assert result_y["iterations"] >= 1

    recent = kernel._persistence.recent_audit(limit=20)
    actors = {row["actor"] for row in recent if row["entity_type"] == "autonomous_loop_step"}
    assert "profile:profile_x" in actors
    assert "profile:profile_y" in actors


def test_profile_has_its_own_isolated_agent_memory():
    kernel = AlgorithmKernel41()
    profile_a = get_or_create_profile(kernel, "memory_profile_a")
    profile_b = get_or_create_profile(kernel, "memory_profile_b")

    async def run():
        await profile_a.agent_memory.store("Profile A's private fact", MemoryType.FACT)
        results_a = await profile_a.agent_memory.recall("private fact")
        results_b = await profile_b.agent_memory.recall("private fact")
        return results_a, results_b

    results_a, results_b = asyncio.run(run())
    assert len(results_a) >= 1
    assert len(results_b) == 0, "profile B must not see profile A's real memory"

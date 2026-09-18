"""
Real periodic self-evolution tests — Round 25 Phase 17 Task 37.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.scheduler import schedule_self_evolution, check_and_fire_due_reminders


def test_due_self_evolution_reminder_fires_a_real_evolve_cycle_not_an_llm_loop():
    kernel = AlgorithmKernel41()
    reminder_id = schedule_self_evolution(kernel, interval_seconds=0)

    results = asyncio.run(check_and_fire_due_reminders(kernel, namespace="kernel_default"))

    fired = [r for r in results if r["reminder_id"] == reminder_id]
    assert len(fired) == 1, f"expected the real self-evolution reminder to fire; got {results}"
    assert "self_evolution_result" in fired[0]
    assert "steps" not in fired[0], "self-evolution must be dispatched directly, not routed through AutonomousLoop"

    still_due = kernel._persistence.get_due_reminders(now=__import__("time").time(), namespace="kernel_default")
    assert reminder_id not in {r["id"] for r in still_due}

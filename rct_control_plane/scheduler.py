"""
Real session-scoped scheduling (Round 23 Phase 12 Task 27) — reminders
that fire a real AutonomousLoop run when due, matching the real,
researched design pattern from DeepSeek Harness's own schedule feature
(session-local reminders, not cron/calendar expressions - polled and
delivered as a normal follow-up, not a separate notification channel).
"""
from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


async def check_and_fire_due_reminders(kernel: "AlgorithmKernel41", namespace: Optional[str] = None) -> List[Dict[str, Any]]:
    """Polls for real due, unfired reminders and actually runs each
    one's goal through a real AutonomousLoop, marking it fired only
    after a real result is produced."""
    from rct_control_plane.autonomous_loop import AutonomousLoop
    from rct_control_plane.mcp_server import mcp

    due = kernel._persistence.get_due_reminders(now=time.time(), namespace=namespace)
    results = []
    for reminder in due:
        loop = AutonomousLoop(mcp_server=mcp, persistence=kernel._persistence,
                               max_iterations=3, namespace=reminder["namespace"])
        result = await loop.run(reminder["goal"])
        kernel._persistence.mark_reminder_fired(reminder["id"])
        results.append({"reminder_id": reminder["id"], **result})
    return results


def schedule_reminder(kernel: "AlgorithmKernel41", goal: str, fire_in_seconds: float, namespace: str = "kernel_default") -> str:
    reminder_id = f"reminder_{uuid.uuid4().hex[:12]}"
    kernel._persistence.save_reminder(reminder_id, namespace=namespace, fire_at=time.time() + fire_in_seconds, goal=goal)
    return reminder_id

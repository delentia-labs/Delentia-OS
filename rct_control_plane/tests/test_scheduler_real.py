"""
Real session-scoped scheduling tests — Round 23 Phase 12 Task 27.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.scheduler import schedule_reminder, check_and_fire_due_reminders


def test_due_reminder_fires_and_future_one_does_not():
    kernel = AlgorithmKernel41()

    due_id = schedule_reminder(kernel, "Say hello and finish, no tool needed.", fire_in_seconds=0, namespace="sched_test")
    future_id = schedule_reminder(kernel, "Say goodbye and finish, no tool needed.", fire_in_seconds=3600, namespace="sched_test")

    results = asyncio.run(check_and_fire_due_reminders(kernel, namespace="sched_test"))

    fired_ids = {r["reminder_id"] for r in results}
    assert due_id in fired_ids, f"the real due reminder should have fired; got {results}"
    assert future_id not in fired_ids, "a reminder scheduled far in the future must not fire yet"

    still_due = kernel._persistence.get_due_reminders(now=__import__("time").time(), namespace="sched_test")
    assert due_id not in {r["id"] for r in still_due}, "the fired reminder must be marked fired"

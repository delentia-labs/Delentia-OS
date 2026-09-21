"""
Round 36 Task 80: real tests for AutonomousScheduler's daemon driver
(start()/stop()/the background poll loop). Before this round, `_is_running`
and `_bg_task` were declared but never set by any method - no timer ever
drove scheduler.py's real check_and_fire_due_reminders unattended.

Uses SELF_EVOLVE_SENTINEL_GOAL (bypasses the LLM entirely, real and
deterministic - see scheduler.py's check_and_fire_due_reminders) to keep
these tests fast and free of local-LLM non-determinism, since what's
under test here is the TIMER/daemon mechanics, not AutonomousLoop's own
LLM-driven decision quality (already covered by test_scheduler_real.py
and test_autonomous_loop_real.py).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import time

import pytest

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.autonomous_scheduler import AutonomousScheduler
from rct_control_plane.scheduler import schedule_reminder, SELF_EVOLVE_SENTINEL_GOAL


async def _wait_until(predicate, timeout=40.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


def test_start_fires_a_real_due_reminder_without_any_manual_check_call():
    """Proves the TIMER itself works - not just the underlying
    check_and_fire_due_reminders mechanism Round 27 already tested."""
    async def run():
        kernel = AlgorithmKernel41()
        namespace = "daemon_test_fire"
        reminder_id = schedule_reminder(kernel, SELF_EVOLVE_SENTINEL_GOAL, fire_in_seconds=0, namespace=namespace)

        scheduler = AutonomousScheduler(kernel=kernel)
        scheduler.start(poll_interval_seconds=0.2)
        try:
            fired = await _wait_until(
                lambda: reminder_id not in {r["id"] for r in kernel._persistence.get_due_reminders(now=time.time(), namespace=namespace)},
                timeout=40.0,
            )
            assert fired, "the daemon's own timer should have fired the due reminder without any manual check_and_fire_due_reminders call"
        finally:
            await scheduler.stop()

    asyncio.run(run())


def test_stop_cancels_the_background_task_cleanly():
    async def run():
        kernel = AlgorithmKernel41()
        scheduler = AutonomousScheduler(kernel=kernel)
        scheduler.start(poll_interval_seconds=0.2)
        assert scheduler._is_running is True
        assert scheduler._bg_task is not None

        await scheduler.stop()

        assert scheduler._is_running is False
        assert scheduler._bg_task is None, "stop() must clear _bg_task, not just cancel it"

    asyncio.run(run())


def test_start_is_idempotent_when_already_running():
    async def run():
        kernel = AlgorithmKernel41()
        scheduler = AutonomousScheduler(kernel=kernel)
        scheduler.start(poll_interval_seconds=1.0)
        first_task = scheduler._bg_task
        scheduler.start(poll_interval_seconds=1.0)  # must be a safe no-op
        assert scheduler._bg_task is first_task, "calling start() twice must not spawn a second background task"
        await scheduler.stop()

    asyncio.run(run())


def test_a_failing_task_does_not_kill_the_poll_loop():
    """A single bad registered task must not stop other tasks (like the
    real reminder poller) from continuing to run."""
    async def run():
        kernel = AlgorithmKernel41()
        scheduler = AutonomousScheduler(kernel=kernel)

        def _always_fails():
            raise RuntimeError("simulated real failure")

        scheduler.register_task(name="always_fails", description="test", interval_seconds=1, handler=_always_fails)
        namespace = "daemon_test_isolation"
        reminder_id = schedule_reminder(kernel, SELF_EVOLVE_SENTINEL_GOAL, fire_in_seconds=0, namespace=namespace)

        scheduler.start(poll_interval_seconds=0.2)
        try:
            fired = await _wait_until(
                lambda: reminder_id not in {r["id"] for r in kernel._persistence.get_due_reminders(now=time.time(), namespace=namespace)},
                timeout=40.0,
            )
            assert fired, "the reminder poller must keep firing real due reminders even though a sibling task fails every cycle"
            failing_task = scheduler.tasks["task_always_fails"]
            assert failing_task.last_status == "FAILED"
            assert failing_task.run_count == 0  # run_count only increments on success, by design
        finally:
            await scheduler.stop()

    asyncio.run(run())


def test_restart_after_stop_picks_up_a_still_due_reminder():
    """Crash-recovery shape: stop the daemon mid-flight, start a fresh
    one, confirm a still-due reminder is correctly picked up (the
    reminders table itself survives fine in SQLite - this proves a
    fresh AutonomousScheduler instance resumes real, correct polling)."""
    async def run():
        kernel = AlgorithmKernel41()
        namespace = "daemon_test_restart"

        scheduler1 = AutonomousScheduler(kernel=kernel)
        scheduler1.start(poll_interval_seconds=10.0)  # slow, so it likely won't fire before we stop it
        reminder_id = schedule_reminder(kernel, SELF_EVOLVE_SENTINEL_GOAL, fire_in_seconds=0, namespace=namespace)
        await scheduler1.stop()

        # Confirm it genuinely didn't fire yet (still due).
        still_due_before = kernel._persistence.get_due_reminders(now=time.time(), namespace=namespace)
        assert reminder_id in {r["id"] for r in still_due_before}

        scheduler2 = AutonomousScheduler(kernel=kernel)
        scheduler2.start(poll_interval_seconds=0.2)
        try:
            fired = await _wait_until(
                lambda: reminder_id not in {r["id"] for r in kernel._persistence.get_due_reminders(now=time.time(), namespace=namespace)},
                timeout=40.0,
            )
            assert fired, "a fresh scheduler instance (simulating a restart) must pick up a still-due reminder"
        finally:
            await scheduler2.stop()

    asyncio.run(run())

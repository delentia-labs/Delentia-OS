"""
Delentia OS - Autonomous Background Task Scheduler
Provides cron-based and interval-based background job execution for the Control Plane.
Default tasks (Round 50): audit_chain_verify and audit_chain_anchor (tier A3).

Round 50: the three earlier default tasks ("daily AI news digest", "nightly
Hypothesis stress benchmark", "exchange SHA-256 integrity audit") returned fixed
strings ("Aggregated 5 AI research papers", "verified 207,000 invariants...
Zero violations", "Cryptographic attestation intact") and reported SUCCESS
without doing any of it. They were replaced by tasks that do real work.

Round 36: this class declared `_is_running`/`_bg_task` fields since it was
first written, but no method ever set them - there was no real start()/
stop(), so none of its registered tasks (including the daily digest/
benchmark/audit tasks below, AND their real next_run_at/interval_seconds
fields) were ever actually driven by a timer. This closes that real gap:
start()/stop() now run a genuine asyncio background loop that fires any
registered task whose next_run_at is due, and the real reminder-polling
mechanism (scheduler.py's check_and_fire_due_reminders, real since Round
27 but only ever manually invoked) is registered as a task here too -
the same real timer now drives both this scheduler's own pre-existing
tasks and the AutonomousLoop reminder queue.
"""

import asyncio
import inspect
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("delentia.autonomous_scheduler")


@dataclass
class ScheduledTask:
    task_id: str
    name: str
    description: str
    interval_seconds: int
    is_enabled: bool = True
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    run_count: int = 0
    last_status: str = "PENDING"
    last_output: Optional[str] = None


class AutonomousScheduler:
    """
    Autonomous Cron & Background Task Scheduler for Delentia OS Control Plane.
    """

    def __init__(self, kernel: Optional[Any] = None):
        """`kernel` is optional to preserve the existing zero-arg
        construction (mcp_gateway.py's real `scheduler = AutonomousScheduler()`
        call site, used only for list_tasks()/trigger_task() there, is
        unaffected). When provided, the real reminder-poller task
        (Round 36) is also registered, since it needs a kernel to call
        scheduler.py's real check_and_fire_due_reminders(kernel)."""
        self.tasks: Dict[str, ScheduledTask] = {}
        self._handlers: Dict[str, Callable[[], Any]] = {}
        self._is_running = False
        self._bg_task: Optional[asyncio.Task] = None
        # Round 50: each due task runs as its own asyncio task, so a slow one
        # (verifying a large audit chain) never delays the reminder poller.
        self._running: Dict[str, asyncio.Task] = {}
        self._kernel = kernel
        self._register_default_tasks()
        if kernel is not None:
            self.register_task(
                name="reminder_poller",
                description="Polls due AutonomousLoop reminders and fires them (Round 36 daemon mode)",
                interval_seconds=5,
                handler=self._poll_reminders,
            )

    async def _poll_reminders(self) -> str:
        """Real handler wired to scheduler.py's existing, already-tested
        check_and_fire_due_reminders - the one previously-missing piece
        was a timer to call it unattended."""
        from rct_control_plane.scheduler import check_and_fire_due_reminders

        if self._kernel is None:
            # Real bug fix: this handler is only ever registered when
            # kernel is not None (see __init__), but nothing previously
            # enforced that invariant here - a future caller wiring this
            # handler up differently would have hit an opaque error deep
            # inside check_and_fire_due_reminders instead of a clear one.
            raise RuntimeError("_poll_reminders requires a kernel, but none was configured")
        fired = await check_and_fire_due_reminders(self._kernel)
        return f"{len(fired)} reminder(s) fired" if fired else "no reminders due"

    def start(self, poll_interval_seconds: float = 5.0) -> None:
        """Real background loop start - idempotent (calling start() while
        already running is a safe no-op, not a double-start)."""
        if self._is_running:
            return
        self._is_running = True
        self._bg_task = asyncio.create_task(self._run_loop(poll_interval_seconds))

    async def stop(self) -> None:
        """Real, clean shutdown - cancels and awaits the background task
        so no orphaned asyncio task survives after stop() returns."""
        self._is_running = False
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None
        for task in list(self._running.values()):
            task.cancel()
        for task in list(self._running.values()):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._running.clear()

    async def _run_loop(self, poll_interval_seconds: float) -> None:
        while self._is_running:
            now = datetime.now(timezone.utc)
            for task_id, task in list(self.tasks.items()):
                if not task.is_enabled:
                    continue
                due = task.next_run_at is None or datetime.fromisoformat(task.next_run_at) <= now
                running = self._running.get(task_id)
                if due and (running is None or running.done()):
                    self._running[task_id] = asyncio.create_task(self._run_one(task_id))
            await asyncio.sleep(poll_interval_seconds)

    async def _run_one(self, task_id: str) -> None:
        try:
            await self.trigger_task_async(task_id)
        except Exception:
            # A single bad task must never kill the poll loop or its siblings.
            logger.exception("autonomous_scheduler: task %s raised during scheduled run", task_id)

    async def trigger_task_async(self, task_id: str) -> Dict[str, Any]:
        """Real async-aware trigger - awaits async handlers (like the
        reminder poller) properly instead of blocking the event loop, and
        runs sync handlers (the pre-existing digest/benchmark/audit
        handlers below) directly. trigger_task() (sync, below) is
        untouched and still used by mcp_gateway.py's manual-trigger path."""
        if task_id not in self.tasks:
            return {"status": "ERROR", "error": f"Task not found: {task_id}"}

        task = self.tasks[task_id]
        handler = self._handlers.get(task_id)
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()

        try:
            if handler is None:
                output = "No handler registered for this task; nothing ran."
            elif inspect.iscoroutinefunction(handler):
                output = await handler()
            else:
                # Sync handlers (e.g. audit_chain_verify) run in a worker
                # thread so they never block the event loop.
                output = await asyncio.to_thread(handler)
            task.last_status = "SUCCESS"
            task.last_output = str(output)
            task.last_run_at = now_str
            task.next_run_at = (now + timedelta(seconds=task.interval_seconds)).isoformat()
            task.run_count += 1
            return {
                "status": "SUCCESS", "task_id": task.task_id, "name": task.name,
                "executed_at": now_str, "output": task.last_output,
            }
        except Exception as e:
            task.last_status = "FAILED"
            task.last_output = str(e)
            task.next_run_at = (now + timedelta(seconds=task.interval_seconds)).isoformat()
            return {"status": "FAILED", "task_id": task.task_id, "error": str(e)}

    def _register_default_tasks(self):
        """Default tasks that do real work (Round 50)."""
        self.register_task(
            name="audit_chain_verify",
            description="Recompute every link (and signature) of the runtime audit hash chain",
            interval_seconds=21600,
            handler=self._verify_audit_chain,
        )
        anchor = self.register_task(
            name="audit_chain_anchor",
            description=(f"Tier A3: sign the audit chain head and publish it to the outside witness "
                         f"(needs {ANCHOR_URL_ENV}, {ANCHOR_KEY_ID_ENV} and DELENTIA_AUDIT_SIGNING_KEY)"),
            interval_seconds=int(os.getenv(ANCHOR_INTERVAL_ENV, "3600")),
            handler=self._anchor_audit_chain,
        )
        # Off until the host is configured, so a dev machine never anchors a
        # throwaway database (the witness keeps every rollback as evidence).
        anchor.is_enabled = anchor_configured()

    def register_task(
        self,
        name: str,
        description: str,
        interval_seconds: int,
        handler: Optional[Callable[[], Any]] = None
    ) -> ScheduledTask:
        """Register a new scheduled task"""
        task_id = f"task_{name}"
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            description=description,
            interval_seconds=interval_seconds
        )
        self.tasks[task_id] = task
        if handler:
            self._handlers[task_id] = handler
        return task

    def list_tasks(self) -> List[Dict[str, Any]]:
        """List all registered scheduled tasks"""
        return [
            {
                "task_id": t.task_id,
                "name": t.name,
                "description": t.description,
                "interval_seconds": t.interval_seconds,
                "is_enabled": t.is_enabled,
                "last_run_at": t.last_run_at,
                "run_count": t.run_count,
                "last_status": t.last_status,
                "last_output": t.last_output
            }
            for t in self.tasks.values()
        ]

    def trigger_task(self, task_id: str) -> Dict[str, Any]:
        """Manually trigger a scheduled task immediately"""
        if task_id not in self.tasks:
            return {"status": "ERROR", "error": f"Task not found: {task_id}"}

        task = self.tasks[task_id]
        handler = self._handlers.get(task_id)
        now_str = datetime.now(timezone.utc).isoformat()
        
        try:
            if handler is None:
                output = "No handler registered for this task; nothing ran."
            elif inspect.iscoroutinefunction(handler):
                raise RuntimeError("async task: use trigger_task_async")
            else:
                output = handler()
            task.last_status = "SUCCESS"
            task.last_output = str(output)
            task.last_run_at = now_str
            task.run_count += 1
            return {
                "status": "SUCCESS",
                "task_id": task.task_id,
                "name": task.name,
                "executed_at": now_str,
                "output": task.last_output
            }
        except Exception as e:
            task.last_status = "FAILED"
            task.last_output = str(e)
            return {"status": "FAILED", "task_id": task.task_id, "error": str(e)}

    # Default task handlers (Round 50): real work, honest failures.
    def _persistence(self) -> Any:
        if self._kernel is not None and getattr(self._kernel, "_persistence", None) is not None:
            return self._kernel._persistence
        from rct_control_plane.persistence import ControlPlanePersistence
        return ControlPlanePersistence()

    def _verify_audit_chain(self) -> str:
        from rct_control_plane import audit_chain
        with self._persistence()._connect() as conn:
            report = audit_chain.verify_audit_chain(conn, public_key_hex=os.getenv(audit_chain.PUBKEY_ENV))
        if not report.ok:
            raise RuntimeError(f"audit chain broken at seq {report.first_bad_seq}: {report.reason}")
        return (f"audit chain OK: {report.chained_rows} chained rows ({report.signed_rows} signed), "
                f"head seq {report.head_seq}")

    async def _anchor_audit_chain(self) -> str:
        if not anchor_configured():
            return f"not configured ({ANCHOR_URL_ENV} / {ANCHOR_KEY_ID_ENV} unset); nothing anchored"
        from rct_control_plane import http_client

        from rct_control_plane import audit_chain
        with self._persistence()._connect() as conn:
            body = audit_chain.sign_anchor(conn, os.environ[ANCHOR_KEY_ID_ENV])
        url = os.environ[ANCHOR_URL_ENV].rstrip("/") + "/v1/audit/anchor"
        async with http_client.async_client(timeout=20.0) as client:
            resp = await client.post(url, json=body)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"witness refused the anchor ({resp.status_code}): {resp.text[:200]}")
        return f"anchored entries={body['entries']} head={body['head'][:16]}... at the witness"


ANCHOR_URL_ENV = "DELENTIA_AUDIT_ANCHOR_URL"
ANCHOR_KEY_ID_ENV = "DELENTIA_AUDIT_ANCHOR_KEY_ID"
ANCHOR_INTERVAL_ENV = "DELENTIA_AUDIT_ANCHOR_INTERVAL_S"


def anchor_configured() -> bool:
    from rct_control_plane.audit_chain import SIGNING_KEY_ENV
    return bool(os.getenv(ANCHOR_URL_ENV) and os.getenv(ANCHOR_KEY_ID_ENV) and os.getenv(SIGNING_KEY_ENV))

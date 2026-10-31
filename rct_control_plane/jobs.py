"""
Round 60 (D4): background agent jobs - start a goal, get an id back at once, ask how it is going, cancel it.

`POST /v1/agent/run` holds the HTTP request open until the episode ends: a long episode times out the caller's connection, there is nothing to ask in the meantime, and nothing to
cancel. A job is the same governed episode run in the background of the API process:

  * `submit` answers immediately with an id (HTTP 202); the episode runs through `GovernedAutonomousLoop` exactly like every other entry point (GUARD, the taint gate, the owner's policy,
    approvals, the safety envelope's pause and limits), in the caller's own namespace taken from the server-side identity;
  * the row (`agent_jobs`) survives a restart. Only jobs with a dead/expired owner (or legacy unowned rows) are marked `interrupted`; constructing another service does not reset a live owner. No interrupted job is replayed automatically; one that stopped for a signature is `done` with `stopped_reason = pending_approval` and carries the approval id;
  * limits: at most DELENTIA_MAX_JOBS_PER_USER (default 3) running per person and DELENTIA_MAX_JOBS (default 8) in all; a goal over 4,000 characters is refused;
  * `cancel` persists a request for the owning worker; `cancelled` is written after that worker acknowledges cancellation. It stops the episode at its next await (a model call in flight is abandoned; a tool already executing in a worker thread finishes, because it cannot be recalled) and records it;
  * `status=done` still means the runner returned; additive `task_outcome` and `verification_scope` distinguish waiting, unverified completion and scoped verification.
  * what a person can see is their own jobs only.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

MAX_GOAL_CHARS = 4000
MAX_RESULT_CHARS = 20000

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_jobs (
    id            TEXT PRIMARY KEY,
    namespace     TEXT NOT NULL,
    goal          TEXT NOT NULL,
    status        TEXT NOT NULL,
    created_at    REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL,
    stopped       TEXT,
    answer        TEXT,
    approval_id   TEXT,
    steps         INTEGER NOT NULL DEFAULT 0,
    last_tool     TEXT,
    cost_json     TEXT,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_jobs_ns ON agent_jobs(namespace, created_at);
"""
LIVE = ("queued", "running")


class JobError(ValueError):
    pass


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name) or default))
    except ValueError:
        return default


def _row(r: Any) -> Dict[str, Any]:
    d = dict(r)
    d["cost"] = json.loads(d.pop("cost_json")) if d.get("cost_json") else None
    d.pop("cost_json", None)
    return d


class JobOwnershipLost(JobError):
    pass


class JobService:
    def __init__(self, persistence: Any, runner: Callable[..., Any], *, clock: Callable[[], float] = time.time, lease_seconds: float = 30.0, monotonic_clock: Optional[Callable[[], float]] = None):
        """`runner(namespace, goal, max_iterations, max_seconds, on_step)` is an async callable returning the episode's result dict (the API passes one that builds the governed loop)."""
        self._p = persistence
        self._runner = runner
        self._tasks: Dict[str, "asyncio.Task[Any]"] = {}
        with self._p._connect() as conn:
            conn.executescript(SCHEMA)
        from rct_control_plane.job_ownership import Ownership
        self._ownership = Ownership(persistence, clock=clock, lease_seconds=lease_seconds, monotonic_clock=monotonic_clock)
        self._ownership.recover()

    # ---------------------------------------------------------------- read

    def get(self, job_id: str, namespace: Optional[str] = None) -> Optional[Dict[str, Any]]:
        import sqlite3
        self._ownership.recover()
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or (namespace is not None and row["namespace"] != namespace):
            return None
        return self._ownership.decorate(_row(row))

    def list(self, namespace: str, limit: int = 20) -> List[Dict[str, Any]]:
        import sqlite3
        self._ownership.recover()
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM agent_jobs WHERE namespace = ? ORDER BY created_at DESC LIMIT ?", (namespace, max(1, min(int(limit), 100)))).fetchall()
        return [self._ownership.decorate(_row(r)) for r in rows]

    def _live_counts(self, namespace: str) -> tuple:
        with self._p._connect() as conn:
            mine = conn.execute("SELECT COUNT(*) FROM agent_jobs WHERE namespace = ? AND status IN ('queued', 'running')", (namespace,)).fetchone()[0]
            everyone = conn.execute("SELECT COUNT(*) FROM agent_jobs WHERE status IN ('queued', 'running')").fetchone()[0]
        return int(mine), int(everyone)

    # ---------------------------------------------------------------- write

    def _update(self, job_id: str, **fields: Any) -> bool:
        return self._ownership.update(job_id, fields)

    async def _watch_owner(self, job_id: str) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                state = self._ownership.pulse(job_id)
            except Exception:  # loss of the lease database must stop the local runner
                state = "lost"
            if state != "ok":
                task = self._tasks.get(job_id)
                if task is not None:
                    task.cancel()
                return

    def submit(self, namespace: str, goal: str, max_iterations: int = 5, max_seconds: float = 120.0, initial_taint: Optional[str] = None,
               on_done: Optional[Callable[[Dict[str, Any]], Any]] = None, *, _admit: Optional[Callable[[Any, str], Optional[str]]] = None) -> Dict[str, Any]:
        """`initial_taint` starts the episode already tainted (a webhook payload is text from outside); `on_done(job)` is awaited when the job ends."""
        goal = str(goal or "").strip()
        if not goal:
            raise JobError("a goal is required")
        if len(goal) > MAX_GOAL_CHARS:
            raise JobError(f"the goal is longer than {MAX_GOAL_CHARS} characters")
        loop = asyncio.get_running_loop()
        self._ownership.recover()
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        with self._p._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing_id = _admit(conn, job_id) if _admit is not None else None
            if existing_id is None:
                mine = conn.execute("SELECT COUNT(*) FROM agent_jobs WHERE namespace=? AND status IN ('queued','running')", (namespace,)).fetchone()[0]
                everyone = conn.execute("SELECT COUNT(*) FROM agent_jobs WHERE status IN ('queued','running')").fetchone()[0]
                if mine >= _int_env("DELENTIA_MAX_JOBS_PER_USER", 3):
                    raise JobError("you already have the most jobs running that you are allowed; wait for one to finish or cancel one")
                if everyone >= _int_env("DELENTIA_MAX_JOBS", 8):
                    raise JobError("the server is running as many jobs as it is allowed; try again shortly")
                conn.execute("INSERT INTO agent_jobs (id, namespace, goal, status, created_at) VALUES (?, ?, ?, 'queued', ?)", (job_id, namespace, goal, time.time()))
                self._ownership.insert(conn, job_id)
                self._p._append_audit(conn, "agent_job", job_id, "submitted", namespace, {"goal_chars": len(goal)})
        if existing_id is not None:
            return self.get(existing_id) or {"id": existing_id}
        self._tasks[job_id] = loop.create_task(self._run(job_id, namespace, goal, max(1, min(int(max_iterations), 25)), max(5.0, min(float(max_seconds), 1800.0)),
                                                                               initial_taint, on_done))
        return self.get(job_id) or {"id": job_id}

    async def _run(self, job_id: str, namespace: str, goal: str, max_iterations: int, max_seconds: float, initial_taint: Optional[str] = None,
                   on_done: Optional[Callable[[Dict[str, Any]], Any]] = None) -> None:
        watcher = asyncio.create_task(self._watch_owner(job_id))
        finished_by_me = False
        steps = {"n": 0}

        async def on_step(step: Any) -> None:
            steps["n"] += 1
            if not self._update(job_id, steps=steps["n"], last_tool=str(getattr(step, "tool_name", None) or "")[:80] or None):
                raise JobOwnershipLost("job ownership lost")
        try:
            if not self._update(job_id, status="running", started_at=time.time()):
                return
            if self._ownership.pulse(job_id) != "ok":
                raise asyncio.CancelledError()
            if initial_taint is None:
                result = await self._runner(namespace, goal, max_iterations, max_seconds, on_step)
            else:
                result = await self._runner(namespace, goal, max_iterations, max_seconds, on_step, initial_taint=initial_taint)
            stopped = str(result.get("stopped_reason") or "unknown")
            answer = result.get("final_answer")
            from rct_control_plane.job_ownership import result_outcome
            outcome, scope = result_outcome(result, namespace)
            finished_by_me = self._ownership.update(job_id, dict(status="done", finished_at=time.time(), stopped=stopped, answer=(str(answer)[:MAX_RESULT_CHARS] if answer else None),
                         approval_id=result.get("approval_id"), steps=int(result.get("iterations") or steps["n"]),
                         cost_json=json.dumps(result.get("cost")) if result.get("cost") else None), outcome=outcome, scope=scope)
        except asyncio.CancelledError:
            try:
                self._ownership.update(job_id, dict(status="cancelled", finished_at=time.time(), stopped="cancelled"), outcome="cancelled")
            except sqlite3.Error:
                logging.getLogger("delentia.jobs").exception("job %s cancellation could not be persisted", job_id)
            raise
        except sqlite3.Error:
            # No fallback state can be trusted when persistence itself failed.
            # Stop locally; a healthy observer later interrupts the lost lease.
            logging.getLogger("delentia.jobs").exception("job %s persistence unavailable", job_id)
        except JobOwnershipLost:
            pass
        except Exception as exc:                                       # noqa: BLE001 - recorded, never raised into the server
            try:
                finished_by_me = self._ownership.update(job_id, dict(status="failed", finished_at=time.time(), stopped="exception", error=f"{type(exc).__name__}: the details are in the server log"), outcome="failed")
            except sqlite3.Error:
                logging.getLogger("delentia.jobs").exception("job %s failure could not be persisted", job_id)
            logging.getLogger("delentia.jobs").exception("job %s failed", job_id)
        finally:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
            self._tasks.pop(job_id, None)
            if on_done is not None and finished_by_me:
                try:
                    finished = self.get(job_id)
                    if finished is not None and finished["status"] in ("done", "failed"):
                        outcome = on_done(finished)
                        if asyncio.iscoroutine(outcome):
                            await outcome
                except Exception:                                      # noqa: BLE001 - a delivery problem never changes the job
                    logging.getLogger("delentia.jobs").exception("job %s result delivery failed", job_id)

    def cancel(self, job_id: str, namespace: str) -> Dict[str, Any]:
        job = self.get(job_id, namespace)
        if job is None:
            raise JobError("no such job")
        if job["status"] not in LIVE:
            return job
        self._ownership.request_cancel(job_id, namespace)
        task = self._tasks.get(job_id)
        if task is not None and job["status"] == "running":
            task.cancel()
        return self.get(job_id) or job

    async def wait(self, job_id: str, timeout: float = 60.0) -> None:
        """For tests and the CLI: wait until the job's task has finished."""
        task = self._tasks.get(job_id)
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        else:
            deadline = asyncio.get_running_loop().time() + timeout
            while True:
                job = self.get(job_id)
                remaining = deadline - asyncio.get_running_loop().time()
                if job is None or job["status"] not in LIVE or remaining <= 0:
                    return
                await asyncio.sleep(min(1.0, remaining))

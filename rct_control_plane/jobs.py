"""
Round 60 (D4): background agent jobs - start a goal, get an id back at once, ask how it is going, cancel it.

`POST /v1/agent/run` holds the HTTP request open until the episode ends: a long episode times out the caller's connection, there is nothing to ask in the meantime, and nothing to
cancel. A job is the same governed episode run in the background of the API process:

  * `submit` answers immediately with an id (HTTP 202); the episode runs through `GovernedAutonomousLoop` exactly like every other entry point (GUARD, the taint gate, the owner's policy,
    approvals, the safety envelope's pause and limits), in the caller's own namespace taken from the server-side identity;
  * the row (`agent_jobs`) survives a restart. A job that was running when the process died cannot be resumed (the loop's state lives in the process) and is marked `interrupted`, never
    `running` forever; one that stopped for a signature is `done` with `stopped_reason = pending_approval` and carries the approval id;
  * limits: at most DELENTIA_MAX_JOBS_PER_USER (default 3) running per person and DELENTIA_MAX_JOBS (default 8) in all; a goal over 4,000 characters is refused;
  * `cancel` stops the episode at its next await (a model call in flight is abandoned; a tool already executing in a worker thread finishes, because it cannot be recalled) and records it;
  * what a person can see is their own jobs only.

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import asyncio
import json
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


class JobService:
    def __init__(self, persistence: Any, runner: Callable[..., Any]):
        """`runner(namespace, goal, max_iterations, max_seconds, on_step)` is an async callable returning the episode's result dict (the API passes one that builds the governed loop)."""
        self._p = persistence
        self._runner = runner
        self._tasks: Dict[str, "asyncio.Task[Any]"] = {}
        with self._p._connect() as conn:
            conn.executescript(SCHEMA)
            # A previous process died with these running: they cannot continue, and must not look alive.
            conn.execute("UPDATE agent_jobs SET status = 'interrupted', finished_at = ?, error = 'the server restarted while this job was running' WHERE status IN ('queued', 'running')",
                         (time.time(),))

    # ---------------------------------------------------------------- read

    def get(self, job_id: str, namespace: Optional[str] = None) -> Optional[Dict[str, Any]]:
        import sqlite3
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or (namespace is not None and row["namespace"] != namespace):
            return None
        return _row(row)

    def list(self, namespace: str, limit: int = 20) -> List[Dict[str, Any]]:
        import sqlite3
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM agent_jobs WHERE namespace = ? ORDER BY created_at DESC LIMIT ?", (namespace, max(1, min(int(limit), 100)))).fetchall()
        return [_row(r) for r in rows]

    def _live_counts(self, namespace: str) -> tuple:
        with self._p._connect() as conn:
            mine = conn.execute("SELECT COUNT(*) FROM agent_jobs WHERE namespace = ? AND status IN ('queued', 'running')", (namespace,)).fetchone()[0]
            everyone = conn.execute("SELECT COUNT(*) FROM agent_jobs WHERE status IN ('queued', 'running')").fetchone()[0]
        return int(mine), int(everyone)

    # ---------------------------------------------------------------- write

    def _audit(self, action: str, job_id: str, namespace: str, extra: Optional[Dict[str, Any]] = None) -> None:
        try:
            self._p.append_audit(entity_type="agent_job", entity_id=job_id, action=action, actor=namespace, changes=extra or {})
        except Exception:
            pass

    def _update(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        names = ", ".join(f"{k} = ?" for k in fields)
        with self._p._connect() as conn:
            conn.execute(f"UPDATE agent_jobs SET {names} WHERE id = ?", (*fields.values(), job_id))   # nosec B608 - column names come from this module's own keyword names

    def submit(self, namespace: str, goal: str, max_iterations: int = 5, max_seconds: float = 120.0) -> Dict[str, Any]:
        goal = str(goal or "").strip()
        if not goal:
            raise JobError("a goal is required")
        if len(goal) > MAX_GOAL_CHARS:
            raise JobError(f"the goal is longer than {MAX_GOAL_CHARS} characters")
        mine, everyone = self._live_counts(namespace)
        if mine >= _int_env("DELENTIA_MAX_JOBS_PER_USER", 3):
            raise JobError("you already have the most jobs running that you are allowed; wait for one to finish or cancel one")
        if everyone >= _int_env("DELENTIA_MAX_JOBS", 8):
            raise JobError("the server is running as many jobs as it is allowed; try again shortly")
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        with self._p._connect() as conn:
            conn.execute("INSERT INTO agent_jobs (id, namespace, goal, status, created_at) VALUES (?, ?, ?, 'queued', ?)", (job_id, namespace, goal, time.time()))
        self._audit("submitted", job_id, namespace, {"goal_chars": len(goal)})
        self._tasks[job_id] = asyncio.get_running_loop().create_task(self._run(job_id, namespace, goal, max(1, min(int(max_iterations), 25)), max(5.0, min(float(max_seconds), 1800.0))))
        return self.get(job_id) or {"id": job_id}

    async def _run(self, job_id: str, namespace: str, goal: str, max_iterations: int, max_seconds: float) -> None:
        self._update(job_id, status="running", started_at=time.time())
        steps = {"n": 0}

        async def on_step(step: Any) -> None:
            steps["n"] += 1
            self._update(job_id, steps=steps["n"], last_tool=str(getattr(step, "tool_name", None) or "")[:80] or None)
        try:
            result = await self._runner(namespace, goal, max_iterations, max_seconds, on_step)
            stopped = str(result.get("stopped_reason") or "unknown")
            answer = result.get("final_answer")
            self._update(job_id, status="done", finished_at=time.time(), stopped=stopped, answer=(str(answer)[:MAX_RESULT_CHARS] if answer else None),
                         approval_id=result.get("approval_id"), steps=int(result.get("iterations") or steps["n"]),
                         cost_json=json.dumps(result.get("cost")) if result.get("cost") else None)
            self._audit("finished", job_id, namespace, {"stopped_reason": stopped})
        except asyncio.CancelledError:
            self._update(job_id, status="cancelled", finished_at=time.time(), stopped="cancelled")
            self._audit("cancelled", job_id, namespace)
            raise
        except Exception as exc:                                       # noqa: BLE001 - recorded, never raised into the server
            self._update(job_id, status="failed", finished_at=time.time(), stopped="exception", error=f"{type(exc).__name__}: the details are in the server log")
            self._audit("failed", job_id, namespace, {"error_type": type(exc).__name__})
            import logging
            logging.getLogger("delentia.jobs").exception("job %s failed", job_id)
        finally:
            self._tasks.pop(job_id, None)

    def cancel(self, job_id: str, namespace: str) -> Dict[str, Any]:
        job = self.get(job_id, namespace)
        if job is None:
            raise JobError("no such job")
        if job["status"] not in LIVE:
            return job
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
        else:                                                           # queued/running in a process that is gone
            self._update(job_id, status="cancelled", finished_at=time.time(), stopped="cancelled")
            self._audit("cancelled", job_id, namespace)
        return self.get(job_id) or job

    async def wait(self, job_id: str, timeout: float = 60.0) -> None:
        """For tests and the CLI: wait until the job's task has finished."""
        task = self._tasks.get(job_id)
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

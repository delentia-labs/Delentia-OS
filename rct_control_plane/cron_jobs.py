"""
Round 57: persistent recurring jobs ("every weekday at 8:30, summarise the overnight audit log and send it to me").

What existed: `delentia_schedule_reminder` fires ONE goal, once, from memory of this process's table, and throws the answer away. Hermes' cron is the
other thing an always-on agent needs: a job that survives restarts, repeats, is described in plain language (here also Thai), runs the goal unattended and
delivers the result to a chat. This module is that, built on the pieces that already govern everything else:

  * every run is an ordinary governed episode (`agent_factory.build_governed_loop`) in the job owner's own namespace: CORD on the goal, the owner's FDIA
    policy on every tool call, a write or an unlisted external tool waits for a human signature and the message delivered says so (with the approval id),
    the notary records it, MeteredProvider caps it;
  * the schedule is parsed by `nl_schedule` (deterministic) and its meaning is returned at creation, so a person sees "every Mon-Fri at 08:30" before
    anything runs;
  * a job is created by the owner (Desk, CLI) directly, or by the agent only through `delentia_cron_create`, which always waits for a signature: an unattended
    future action is exactly what a human must approve once;
  * delivery goes only to a recipient who is explicitly on that channel's allowlist (a wildcard allowlist does not count), so a tricked agent cannot schedule
    the owner's data into a stranger's chat;
  * deleting is a soft delete (Zero-Delete); a job that fails three times in a row, or hits its run limit, switches itself off and says so; a missed run is
    run once, not as many times as were missed; an hourly cap across all jobs stops a runaway schedule from becoming a bill.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional

from rct_control_plane import nl_schedule

logger = logging.getLogger(__name__)
MAX_JOBS_PER_NAMESPACE = 20
MAX_GOAL_CHARS = 2000
MAX_RESULT_CHARS = 3000
MAX_FAIL_STREAK = 3
DELIVERY_CHANNELS = ("telegram", "signal", "whatsapp")
HOURLY_CAP_ENV = "DELENTIA_CRON_MAX_RUNS_PER_HOUR"
RUN_SECONDS_ENV = "DELENTIA_CRON_MAX_SECONDS"
# A run that ended like this did not do the job (and will end like this again): it counts toward switching the job off.
FAILING_STOPS = frozenset({"llm_error", "notary_unavailable", "guard_blocked", "fdia_blocked", "jury_rejected", "exception", "max_seconds_exceeded"})

SCHEMA = """
CREATE TABLE IF NOT EXISTS cron_jobs (
    id            TEXT PRIMARY KEY,
    namespace     TEXT NOT NULL,
    name          TEXT NOT NULL,
    goal          TEXT NOT NULL,
    schedule_text TEXT NOT NULL,
    schedule_json TEXT NOT NULL,
    deliver_json  TEXT,
    enabled       INTEGER NOT NULL DEFAULT 1,
    deleted       INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    created_by    TEXT,
    next_run_at   REAL,
    last_run_at   REAL,
    last_status   TEXT,
    last_result   TEXT,
    run_count     INTEGER NOT NULL DEFAULT 0,
    fail_streak   INTEGER NOT NULL DEFAULT 0,
    max_runs      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cron_due ON cron_jobs(enabled, deleted, next_run_at);
"""

Deliverer = Callable[[Dict[str, Any], str], Awaitable[None]]
_GATEWAY_RESOLVER: Optional[Callable[[str], Any]] = None


def set_gateway_resolver(resolver: Optional[Callable[[str], Any]]) -> None:
    """The API process tells this module how to find the running gateway for a channel; without one nothing can be delivered (results stay in the job)."""
    global _GATEWAY_RESOLVER
    _GATEWAY_RESOLVER = resolver


class CronError(ValueError):
    pass


def _audit(persistence: Any, action: str, job: Dict[str, Any], actor: str, extra: Optional[Dict[str, Any]] = None) -> None:
    try:
        persistence.append_audit(entity_type="cron_job", entity_id=job["id"], action=action, actor=actor,
                                 changes={"namespace": job["namespace"], "name": job["name"], "schedule": job["schedule_text"],
                                          "goal": job["goal"][:300], "deliver": job.get("deliver"), **(extra or {})})
    except Exception:           # an audit problem must not stop a job from being switched off, nor decide whether one runs
        pass


def allowed_recipients(channel: str) -> List[str]:
    from rct_control_plane.agent_factory import allowed_senders
    allowed = allowed_senders(channel)
    return sorted(allowed) if allowed else []          # None ("*": everyone) and an empty set both give nobody


def validate_delivery(deliver: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not deliver or not deliver.get("channel"):
        return None
    channel, to = str(deliver["channel"]).strip().lower(), str(deliver.get("to", "")).strip()
    if channel not in DELIVERY_CHANNELS:
        raise CronError(f"delivery to {channel!r} is not supported yet (supported: {', '.join(DELIVERY_CHANNELS)}; leave it empty to keep results in the job)")
    if not to:
        raise CronError("delivery needs a recipient ('to')")
    if to not in allowed_recipients(channel):
        raise CronError(f"{to!r} is not on the {channel} allowlist (DELENTIA_{channel.upper()}_ALLOWED_SENDERS names people explicitly; '*' does not count). "
                        "Scheduled results are only sent to people who are listed, so a tricked agent cannot send data to a stranger.")
    return {"channel": channel, "to": to}


def _row(row: Any) -> Dict[str, Any]:
    d = dict(row)
    d["schedule"] = json.loads(d.pop("schedule_json"))
    d["deliver"] = json.loads(d.pop("deliver_json")) if d.get("deliver_json") else None
    d.pop("deliver_json", None)
    d["enabled"], d["deleted"] = bool(d["enabled"]), bool(d["deleted"])
    try:
        d["schedule_meaning"] = nl_schedule.describe(nl_schedule.Schedule.from_dict(d["schedule"]))
    except nl_schedule.ScheduleError as exc:
        d["schedule_meaning"] = f"unreadable ({exc})"
    return d


class CronService:
    def __init__(self, persistence: Any):
        self._p = persistence
        self._runs: Deque[float] = deque()              # start times of runs in the last hour (per process)
        self._background: "set[asyncio.Task[Any]]" = set()
        with self._p._connect() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ create / read / change

    def create(self, namespace: str, goal: str, schedule_text: str, name: str = "", deliver: Optional[Dict[str, Any]] = None,
               created_by: str = "owner", max_runs: Optional[int] = None, now: Optional[float] = None) -> Dict[str, Any]:
        namespace, goal = str(namespace or "").strip(), " ".join(str(goal or "").split())
        if not namespace:
            raise CronError("a job belongs to someone: namespace is empty")
        if not goal:
            raise CronError("a job needs a goal")
        if len(goal) > MAX_GOAL_CHARS:
            raise CronError(f"the goal is longer than {MAX_GOAL_CHARS} characters")
        when = time.time() if now is None else float(now)
        try:
            schedule = nl_schedule.parse(schedule_text, now=when)
            first = nl_schedule.next_run(schedule, when)
        except nl_schedule.ScheduleError as exc:
            raise CronError(str(exc)) from exc
        if first is None:
            raise CronError("that schedule never runs again")
        target = validate_delivery(deliver)
        from rct_control_plane.cord_security import CORDVerdict, cord_check
        if cord_check(goal).verdict == CORDVerdict.REJECTED:
            raise CronError("the goal was refused by the injection screen (CORD); a scheduled goal gets the same screening as any other")
        with self._p._connect() as conn:
            active = conn.execute("SELECT COUNT(*) FROM cron_jobs WHERE namespace = ? AND deleted = 0", (namespace,)).fetchone()[0]
            if active >= MAX_JOBS_PER_NAMESPACE:
                raise CronError(f"{namespace} already has {MAX_JOBS_PER_NAMESPACE} jobs; delete one first")
            job_id = f"job_{uuid.uuid4().hex[:10]}"
            conn.execute("INSERT INTO cron_jobs (id, namespace, name, goal, schedule_text, schedule_json, deliver_json, enabled, created_at, created_by, next_run_at, max_runs) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                         (job_id, namespace, (name or goal)[:60], goal, schedule.text, json.dumps(schedule.to_dict()), json.dumps(target) if target else None,
                          when, created_by, first, int(max_runs) if max_runs else (1 if schedule.kind == "once" else None)))
        job = self.get(job_id)
        assert job is not None
        _audit(self._p, "created", job, created_by, {"first_run_at": first})
        return job

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        import sqlite3
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
        return _row(row) if row else None

    def list(self, namespace: Optional[str] = None, include_deleted: bool = False) -> List[Dict[str, Any]]:
        import sqlite3
        sql, args = "SELECT * FROM cron_jobs", []
        clauses = []
        if namespace is not None:
            clauses.append("namespace = ?")
            args.append(namespace)
        if not include_deleted:
            clauses.append("deleted = 0")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql + " ORDER BY created_at DESC", args).fetchall()
        return [_row(r) for r in rows]

    def set_enabled(self, job_id: str, enabled: bool, actor: str = "owner", namespace: Optional[str] = None, now: Optional[float] = None) -> Dict[str, Any]:
        job = self._owned(job_id, namespace)
        next_at = job["next_run_at"]
        if enabled:
            schedule = nl_schedule.Schedule.from_dict(job["schedule"])
            next_at = nl_schedule.next_run(schedule, time.time() if now is None else now)
            if next_at is None:
                raise CronError("that job has nothing left to run (a one-off that has run)")
        with self._p._connect() as conn:
            conn.execute("UPDATE cron_jobs SET enabled = ?, next_run_at = ?, fail_streak = CASE WHEN ? THEN 0 ELSE fail_streak END WHERE id = ?",
                         (1 if enabled else 0, next_at, 1 if enabled else 0, job_id))
        out = self.get(job_id)
        assert out is not None
        _audit(self._p, "enabled" if enabled else "paused", out, actor)
        return out

    def delete(self, job_id: str, actor: str = "owner", namespace: Optional[str] = None) -> Dict[str, Any]:
        """Soft delete: the row and its history stay (Zero-Delete); the job never runs again and is hidden from lists."""
        job = self._owned(job_id, namespace)
        with self._p._connect() as conn:
            conn.execute("UPDATE cron_jobs SET deleted = 1, enabled = 0, next_run_at = NULL WHERE id = ?", (job_id,))
        out = self.get(job_id)
        assert out is not None
        _audit(self._p, "deleted", job, actor)
        return out

    def _owned(self, job_id: str, namespace: Optional[str]) -> Dict[str, Any]:
        job = self.get(job_id)
        if job is None or job["deleted"] or (namespace is not None and job["namespace"] != namespace):
            raise CronError(f"no job {job_id!r}")                    # another person's job is indistinguishable from none
        return job

    # ------------------------------------------------------------------ running

    def due(self, now: float) -> List[Dict[str, Any]]:
        import sqlite3
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM cron_jobs WHERE enabled = 1 AND deleted = 0 AND next_run_at IS NOT NULL AND next_run_at <= ? ORDER BY next_run_at", (now,)).fetchall()
        return [_row(r) for r in rows]

    def claim(self, job: Dict[str, Any], now: float) -> bool:
        """Advance the job's next run BEFORE running it, in one statement that only succeeds for one caller: two dispatchers (or a restart in the middle of a
        run) cannot run the same occurrence twice, and a long outage is caught up with one run, not one per missed occurrence."""
        schedule = nl_schedule.Schedule.from_dict(job["schedule"])
        following = nl_schedule.next_run(schedule, now)
        with self._p._connect() as conn:
            cur = conn.execute("UPDATE cron_jobs SET next_run_at = ?, enabled = CASE WHEN ? IS NULL THEN 0 ELSE enabled END WHERE id = ? AND next_run_at = ? AND enabled = 1 AND deleted = 0",
                               (following, following, job["id"], job["next_run_at"]))
            return cur.rowcount == 1

    def _under_hourly_cap(self, now: float) -> bool:
        try:
            cap = int(os.environ.get(HOURLY_CAP_ENV) or 60)
        except ValueError:
            cap = 60
        while self._runs and self._runs[0] < now - 3600:
            self._runs.popleft()
        return len(self._runs) < cap

    def _record(self, job_id: str, status: str, text: str, now: float, failed: bool) -> Dict[str, Any]:
        with self._p._connect() as conn:
            conn.execute("UPDATE cron_jobs SET last_run_at = ?, last_status = ?, last_result = ?, run_count = run_count + 1, "
                         "fail_streak = CASE WHEN ? THEN fail_streak + 1 ELSE 0 END WHERE id = ?", (now, status, text[:MAX_RESULT_CHARS], 1 if failed else 0, job_id))
        job = self.get(job_id)
        assert job is not None
        return job

    async def run_job(self, kernel: Any, job: Dict[str, Any], deliver: Optional[Deliverer] = None, now: Optional[float] = None,
                      counted: bool = False) -> Dict[str, Any]:
        """One run of one job (already claimed). Never raises: whatever happens is recorded in the job. `counted`: the caller already put this run
        against the hourly cap (the dispatchers do, at claim time, so the cap is checked against runs that are started but not yet running)."""
        from rct_control_plane.agent_factory import build_governed_loop
        from rct_control_plane.gateways.common import reply_text_for
        started = time.time() if now is None else now
        if not counted:
            self._runs.append(started)
        try:
            seconds = float(os.environ.get(RUN_SECONDS_ENV) or 300)
        except ValueError:
            seconds = 300.0
        stopped, text, failed = "exception", "", True
        try:
            loop = build_governed_loop(kernel, namespace=job["namespace"], max_iterations=5, max_seconds=seconds)
            result = await asyncio.wait_for(loop.run(job["goal"]), timeout=seconds + 30)
            stopped = str(result.get("stopped_reason") or "unknown")
            text = reply_text_for(result)
            failed = stopped in FAILING_STOPS
        except asyncio.TimeoutError:
            stopped, text = "max_seconds_exceeded", f"the run did not finish within {int(seconds)} s"
        except Exception as exc:                                   # noqa: BLE001 - recorded, never raised into the scheduler
            logger.exception("cron job %s failed", job["id"])
            stopped, text = "exception", f"the run failed ({type(exc).__name__}); the details are in the server log"
        updated = self._record(job["id"], stopped, text, started, failed)
        _audit(self._p, "run", updated, "cron", {"stopped_reason": stopped, "failed": failed, "run_count": updated["run_count"]})
        notice = ""
        if failed:
            try:                                                   # Round 60: the owner hears about it (owner_notify.py); never fatal
                from rct_control_plane import owner_notify
                owner_notify.on_job_problem(updated, stopped, updated["fail_streak"] >= MAX_FAIL_STREAK, self._p)
            except Exception:
                pass
        if updated["fail_streak"] >= MAX_FAIL_STREAK:
            self.set_enabled_off(updated["id"], "cron", f"switched off after {MAX_FAIL_STREAK} failed runs in a row")
            notice = f"\n\n[this job has been switched off after {MAX_FAIL_STREAK} failed runs in a row; last result: {stopped}]"
        elif updated["max_runs"] and updated["run_count"] >= updated["max_runs"]:
            self.set_enabled_off(updated["id"], "cron", "reached its run limit")
            notice = "\n\n[this job has reached its run limit and is switched off]"
        if deliver is not None and updated.get("deliver"):
            message = f"[{updated['name']}] {text}{notice}"[:3500]
            try:
                await deliver(updated, message)
                _audit(self._p, "delivered", updated, "cron", {"to": updated["deliver"]})
            except Exception as exc:                               # noqa: BLE001 - the result is kept in the job whatever delivery did
                _audit(self._p, "delivery_failed", updated, "cron", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        return self.get(job["id"]) or updated

    def set_enabled_off(self, job_id: str, actor: str, reason: str) -> None:
        with self._p._connect() as conn:
            conn.execute("UPDATE cron_jobs SET enabled = 0 WHERE id = ?", (job_id,))
        job = self.get(job_id)
        if job is not None:
            _audit(self._p, "switched_off", job, actor, {"reason": reason})

    def dispatch_background(self, kernel: Any, deliver: Optional[Deliverer] = None, now: Optional[float] = None) -> int:
        """What the daemon calls every few seconds: claim every due job and start each as its own task, then return. (run_due, below, waits for them:
        used by tests and `delentia cron run-due`.) Must be called from inside a running event loop."""
        when = time.time() if now is None else now
        started = 0
        for job in self.due(when):
            if not self._under_hourly_cap(when):
                _audit(self._p, "throttled", job, "cron", {"cap_env": HOURLY_CAP_ENV})
                break
            if self.claim(job, when):
                self._runs.append(when)
                task = asyncio.create_task(self.run_job(kernel, job, deliver, when, counted=True))
                self._background.add(task)
                task.add_done_callback(self._background.discard)
                started += 1
        return started

    async def run_due(self, kernel: Any, deliver: Optional[Deliverer] = None, now: Optional[float] = None, parallel: int = 2) -> List[Dict[str, Any]]:
        when = time.time() if now is None else now
        ran: List[Dict[str, Any]] = []
        gate = asyncio.Semaphore(max(1, parallel))
        tasks = []

        async def one(job: Dict[str, Any]) -> None:
            async with gate:
                ran.append(await self.run_job(kernel, job, deliver, when, counted=True))

        for job in self.due(when):
            if not self._under_hourly_cap(when):
                _audit(self._p, "throttled", job, "cron", {"cap_env": HOURLY_CAP_ENV})
                break
            if self.claim(job, when):
                self._runs.append(when)
                tasks.append(asyncio.create_task(one(job)))
        if tasks:
            await asyncio.gather(*tasks)
        return ran


async def deliver_via_gateways(job: Dict[str, Any], text: str) -> None:
    """Send a job's result with the running gateway for its channel (the API process registers how to find one)."""
    target = job.get("deliver") or {}
    channel, to = str(target.get("channel") or ""), str(target.get("to") or "")
    gateway = _GATEWAY_RESOLVER(channel) if _GATEWAY_RESOLVER else None
    if gateway is None:
        raise RuntimeError(f"the {channel} gateway is not running, so the result stays in the job")
    if channel == "telegram":
        await gateway.send_message(int(to), text)
    elif channel in ("signal", "whatsapp"):
        await gateway.send_text(to, text)
    else:
        raise RuntimeError(f"no delivery for {channel}")

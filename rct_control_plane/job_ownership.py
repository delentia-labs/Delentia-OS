"""Durable ownership of in-process jobs; leases fence database writes only.

An expired job is interrupted, never reassigned or replayed. A live worker's
thread/external effect cannot be recalled by SQLite fencing. Shared databases
across machines are not a replacement for a coordinated execution service.
"""
from __future__ import annotations

import os
import socket
import time
import uuid
from typing import Any, Callable

from rct_control_plane.episode_journal import _alive, _proc_start

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_job_owners (
 job_id TEXT PRIMARY KEY, token TEXT NOT NULL, host TEXT NOT NULL,
 pid INTEGER NOT NULL, process_started REAL, lease_until REAL NOT NULL,
 cancel_requested INTEGER NOT NULL DEFAULT 0,
 task_outcome TEXT NOT NULL DEFAULT 'pending', verification_scope TEXT
);
"""


def host_identity() -> str:
    # Do not compare PIDs across Linux PID namespaces (containers).
    host = socket.gethostname()
    try:
        host += ':' + os.readlink('/proc/self/ns/pid')
    except OSError:
        pass
    return host


class Ownership:
    def __init__(self, persistence: Any, *, clock: Callable[[], float] = time.time, lease_seconds: float = 30.0, monotonic_clock: Callable[[], float] | None = None):
        if not 3 <= lease_seconds <= 3600:
            raise ValueError('job lease must be between 3 and 3600 seconds')
        self.db = persistence
        self.clock = clock
        self.lease_seconds = lease_seconds
        from rct_control_plane.job_clock import LeaseClock
        # Custom wall clocks are test injection. Pair one with a monotonic
        # clock to exercise drift; normal production always checks both.
        monotonic_clock = monotonic_clock or (time.monotonic if clock is time.time else None)
        self._clock_guard = LeaseClock(clock(), monotonic_clock)
        self.token = uuid.uuid4().hex
        self.host = host_identity()
        self.pid = os.getpid()
        self.started = _proc_start(self.pid)
        with self.db._connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute('BEGIN IMMEDIATE')
            columns = {row[1] for row in conn.execute('PRAGMA table_info(agent_job_owners)')}
            if 'heartbeat_wall' not in columns:
                conn.execute('ALTER TABLE agent_job_owners ADD COLUMN heartbeat_wall REAL')
            legacy = conn.execute("SELECT 1 FROM agent_job_owners o JOIN agent_jobs j ON j.id=o.job_id "
                "WHERE j.status IN ('queued','running') AND o.heartbeat_wall IS NULL LIMIT 1").fetchone()
            if legacy is not None:
                import sqlite3
                raise sqlite3.OperationalError('drain legacy job workers before upgrading clock fencing')

    def now(self) -> float:
        return self._clock_guard.check(self.clock())

    def insert(self, conn, job_id):
        conn.execute('INSERT INTO agent_job_owners (job_id,token,host,pid,process_started,lease_until,heartbeat_wall) VALUES (?,?,?,?,?,?,?)',
                     (job_id, self.token, self.host, self.pid, self.started, self.now() + self.lease_seconds, self.now()))

    def recover(self):
        now = self.now()
        with self.db._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = conn.execute("SELECT j.id,o.token,o.host,o.pid,o.process_started,o.lease_until,j.namespace,o.heartbeat_wall FROM agent_jobs j "
                "LEFT JOIN agent_job_owners o ON o.job_id=j.id WHERE j.status IN ('queued','running')").fetchall()
            for job_id, token, host, pid, started, until, namespace, heartbeat in rows:
                from rct_control_plane.job_clock import CLOCK_TOLERANCE_SECONDS
                rollback = heartbeat is not None and heartbeat > now + CLOCK_TOLERANCE_SECONDS
                dead = rollback or token is None or until <= now or (host == self.host and not _alive(pid, started))
                if not dead:
                    continue
                conn.execute("UPDATE agent_jobs SET status='interrupted',finished_at=?,error=? WHERE id=? AND status IN ('queued','running')",
                    (now, 'the server restarted or the job owner lease was lost; execution outcome must be inspected', job_id))
                conn.execute("UPDATE agent_job_owners SET task_outcome='interrupted' WHERE job_id=?", (job_id,))
                self.db._append_audit(conn, "agent_job", job_id, "interrupted", namespace, {"reason": "clock_rollback" if rollback else "owner_lost"})

    def pulse(self, job_id):
        now = self.now()
        with self.db._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute("SELECT o.cancel_requested,j.namespace FROM agent_job_owners o JOIN agent_jobs j ON j.id=o.job_id "
                "WHERE o.job_id=? AND o.token=? AND o.lease_until>? AND j.status IN ('queued','running')",
                (job_id, self.token, now)).fetchone()
            if row is None:
                return 'lost'
            conn.execute('UPDATE agent_job_owners SET lease_until=?,heartbeat_wall=? WHERE job_id=? AND token=?',
                         (now + self.lease_seconds, now, job_id, self.token))
            return 'cancel' if row[0] else 'ok'

    def update(self, job_id, fields, *, outcome=None, scope=None):
        import asyncio
        with self.db._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute("SELECT o.cancel_requested,j.namespace FROM agent_job_owners o JOIN agent_jobs j ON j.id=o.job_id "
                "WHERE o.job_id=? AND o.token=? AND o.lease_until>? AND j.status IN ('queued','running')",
                (job_id, self.token, self.now())).fetchone()
            if row is None:
                return False
            if fields.get('status') == 'done' and row[0]:
                raise asyncio.CancelledError()
            names = ', '.join(f'{k}=?' for k in fields)
            conn.execute(f'UPDATE agent_jobs SET {names} WHERE id=?', (*fields.values(), job_id))  # nosec B608 - internal column names only
            if outcome is not None:
                conn.execute('UPDATE agent_job_owners SET task_outcome=?,verification_scope=? WHERE job_id=? AND token=?',
                             (outcome, scope, job_id, self.token))
            status = fields.get('status')
            if status is not None:
                action = {"done": "finished", "running": "started"}.get(status, status)
                self.db._append_audit(conn, "agent_job", job_id, action, row[1], {"task_outcome": outcome, "stopped_reason": fields.get('stopped')})
            return True

    def request_cancel(self, job_id, namespace):
        with self.db._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            changed = conn.execute('UPDATE agent_job_owners SET cancel_requested=1 WHERE job_id=? AND cancel_requested=0 AND EXISTS '
                "(SELECT 1 FROM agent_jobs WHERE id=? AND namespace=? AND status IN ('queued','running'))",
                (job_id, job_id, namespace)).rowcount
            if changed:
                self.db._append_audit(conn, "agent_job", job_id, "cancel_requested", namespace, {})

    def decorate(self, job):
        with self.db._connect() as conn:
            row = conn.execute('SELECT cancel_requested,task_outcome,verification_scope FROM agent_job_owners WHERE job_id=?', (job['id'],)).fetchone()
        job.update(cancel_requested=bool(row[0]) if row else False,
                   task_outcome=row[1] if row else ('interrupted' if job['status'] == 'interrupted' else 'unconfirmed'),
                   verification_scope=row[2] if row else None)
        return job


def result_outcome(result, namespace):
    """Task outcome, separate from legacy job status=done (runner returned)."""
    stopped = result.get('stopped_reason')
    if stopped in {'plan_ready', 'waiting_for_input', 'waiting_for_clarification', 'needs_clarification', 'pending_approval'}:
        return 'waiting', None
    contract = result.get('intent_contract')
    if isinstance(contract, dict):
        executor = contract.get('plan', {}).get('semantic_planning', {}).get('executor')
        if contract.get('state') == 'criteria_satisfied':
            from rct_control_plane.intent_contract import plan_digest
            if (result.get('acceptance_verification', {}).get('satisfied') is not True
                    or contract.get('plan_sha256') != plan_digest(contract.get('plan', {}))):
                return 'unconfirmed', None
            if executor == 'verified_budget_v1':
                if (contract.get('execution_status') != 'complete'
                        or result.get('semantic_verification', {}).get('satisfied') is not True):
                    return 'unconfirmed', None
                from rct_control_plane.verified_budget import validate_receipts
                receipts = contract.get('execution_receipts', [])
                if not receipts or len(receipts) != len(contract['plan']['components']):
                    return 'unconfirmed', None
                try:
                    validate_receipts(contract['plan'], contract['id'], namespace, receipts)
                except (ValueError, KeyError, TypeError):
                    return 'unconfirmed', None
                return 'verified', 'document_bytes_and_same_currency_arithmetic'
            return ('verified', 'declared_predicates') if executor is None else ('unconfirmed', None)
        return 'unconfirmed', None
    return ('completed_unverified', None) if stopped == 'llm_finished' else ('unconfirmed', None)

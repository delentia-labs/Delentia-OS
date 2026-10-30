"""SQLite lock/FULL and clock fault boundaries; no external model or writes."""
import asyncio
import sqlite3

import pytest

from rct_control_plane.jobs import JobError, JobService
from rct_control_plane.persistence import ControlPlanePersistence

pytestmark = pytest.mark.timeout(30)


class Clock:
    def __init__(self, value):
        self.value = value
    def __call__(self):
        return self.value


@pytest.mark.parametrize('jump', [-60, 60])
def test_clock_jump_fences_writer_and_new_observer_does_not_replay(tmp_path, jump):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'clock.db'))
    async def scenario():
        wall, mono = Clock(1000.0), Clock(500.0)
        started, finish = asyncio.Event(), asyncio.Event()
        deliveries = []
        calls = []
        async def runner(*args):
            calls.append('dispatch')
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished', 'final_answer': 'must not publish'}
        first = JobService(db, runner, clock=wall, monotonic_clock=mono, lease_seconds=6)
        job = first.submit('alice', 'read', on_done=deliveries.append)
        await started.wait()
        wall.value += 4
        mono.value += 4
        assert first._ownership.pulse(job['id']) == 'ok'
        wall.value += jump
        with pytest.raises(sqlite3.OperationalError, match='clock unstable'):
            first._update(job['id'], status='done', answer='stale')
        observer = JobService(db, runner, clock=wall, monotonic_clock=mono, lease_seconds=6)
        assert observer.get(job['id'])['status'] == 'interrupted'
        finish.set()
        await first.wait(job['id'], timeout=5)
        assert calls == ['dispatch'] and not deliveries
        assert observer.get(job['id'])['answer'] is None
        # Restoring wall time cannot rehabilitate an already-faulted worker.
        wall.value -= jump
        with pytest.raises(sqlite3.OperationalError, match='clock unstable'):
            first._ownership.pulse(job['id'])
    asyncio.run(scenario())


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_clock_refuses_worker_start(tmp_path, value):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'invalid.db'))
    with pytest.raises(sqlite3.OperationalError, match='clock unstable'):
        JobService(db, None, clock=lambda: value)


def test_legacy_live_owner_requires_explicit_drain_before_upgrade(tmp_path):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'upgrade.db'))
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished'}
        old = JobService(db, runner)
        job = old.submit('alice', 'old job')
        await started.wait()
        with db._connect() as conn:
            conn.execute('UPDATE agent_job_owners SET heartbeat_wall=NULL WHERE job_id=?', (job['id'],))
        with pytest.raises(sqlite3.OperationalError, match='drain legacy'):
            JobService(db, runner)
        # Operator drains the existing worker, rather than guessing its result.
        finish.set()
        await old.wait(job['id'], timeout=5)
        new = JobService(db, runner)
        assert new.get(job['id'])['status'] == 'done'
    asyncio.run(scenario())


def test_real_database_lock_refuses_admission_without_dispatch(tmp_path):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'locked.db'))
    async def scenario():
        async def forbidden(*args):
            pytest.fail('locked admission must not dispatch')
        service = JobService(db, forbidden)
        # A real second connection owns the write lock. One-second sqlite
        # timeout bounds the test; no sub-second timing assumptions.
        db._connect = lambda: sqlite3.connect(db.db_path, timeout=1.0)
        locker = sqlite3.connect(db.db_path)
        try:
            locker.execute('BEGIN IMMEDIATE')
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                service.submit('alice', 'read')
        finally:
            locker.rollback()
            locker.close()
        assert service.list('alice') == []
        with db._connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM agent_job_owners').fetchone()[0] == 0
    asyncio.run(scenario())


def fill_database(db):
    # SQLite's real page limit generates SQLITE_FULL without filling the host.
    with db._connect() as conn:
        conn.execute('CREATE TABLE pressure (data BLOB)')
        conn.commit()
        pages = conn.execute('PRAGMA page_count').fetchone()[0]
        conn.execute(f'PRAGMA max_page_count={pages + 4}')
        while True:
            try:
                conn.execute('INSERT INTO pressure VALUES (zeroblob(128))')
                conn.commit()
            except sqlite3.OperationalError as exc:
                assert exc.sqlite_errorcode == sqlite3.SQLITE_FULL
                conn.rollback()
                break


def restore_capacity(db):
    with db._connect() as conn:
        conn.execute('PRAGMA max_page_count=1000000')
        conn.execute('DROP TABLE pressure')


def test_real_sqlite_full_rolls_back_submission_and_can_retry(tmp_path):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'full.db'), reuse_connection=True)
    async def scenario():
        calls = []
        async def runner(*args):
            calls.append('dispatch')
            return {'stopped_reason': 'llm_finished'}
        service = JobService(db, runner)
        with db._connect() as conn:
            conn.execute('CREATE TABLE admission_claim (job_id TEXT)')
        fill_database(db)
        def claim(conn, job_id):
            conn.execute('INSERT INTO admission_claim VALUES (?)', (job_id,))
            conn.execute('INSERT INTO pressure VALUES (zeroblob(65536))')
        with pytest.raises(sqlite3.OperationalError) as error:
            service.submit('alice', 'read', _admit=claim)
        assert error.value.sqlite_errorcode == sqlite3.SQLITE_FULL
        assert not calls and service.list('alice') == []
        with db._connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM admission_claim').fetchone()[0] == 0
        restore_capacity(db)
        job = service.submit('alice', 'retry after repair')
        await service.wait(job['id'], timeout=5)
        assert calls == ['dispatch'] and service.get(job['id'])['status'] == 'done'
    asyncio.run(scenario())


def test_real_sqlite_full_at_completion_never_publishes_success(tmp_path):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'completion.db'), reuse_connection=True)
    async def scenario():
        wall = Clock(1000.0)
        started, finish = asyncio.Event(), asyncio.Event()
        delivered = []
        calls = []
        async def runner(*args):
            calls.append('dispatch')
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished', 'final_answer': 'x' * 20000}
        service = JobService(db, runner, clock=wall, lease_seconds=6)
        job = service.submit('alice', 'read', on_done=delivered.append)
        await started.wait()
        fill_database(db)
        finish.set()
        await service.wait(job['id'], timeout=5)
        assert not delivered
        assert service.get(job['id'])['status'] == 'running'
        assert service.get(job['id'])['answer'] is None
        restore_capacity(db)
        wall.value += 7
        observer = JobService(db, runner, clock=wall, lease_seconds=6)
        assert observer.get(job['id'])['status'] == 'interrupted'
        assert calls == ['dispatch']
    asyncio.run(scenario())


def test_two_services_share_capacity_and_cross_cancel_under_load(tmp_path, monkeypatch):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'load.db'))
    monkeypatch.setenv('DELENTIA_MAX_JOBS', '8')
    monkeypatch.setenv('DELENTIA_MAX_JOBS_PER_USER', '8')
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        dispatched = []
        async def runner(namespace, *args):
            dispatched.append(namespace)
            if len(dispatched) == 8:
                started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished'}
        services = [JobService(db, runner), JobService(db, runner)]
        jobs = [services[i % 2].submit('alice', f'job {i}') for i in range(8)]
        await asyncio.wait_for(started.wait(), timeout=5)
        with pytest.raises(JobError):
            services[1].submit('alice', 'over capacity')
        for job in jobs[::2]:
            services[1].cancel(job['id'], 'alice')
        # Persisted cancellation wins even before the owner's next heartbeat.
        finish.set()
        await asyncio.gather(*(services[i % 2].wait(job['id'], timeout=5) for i, job in enumerate(jobs)))
        statuses = [services[0].get(job['id'])['status'] for job in jobs]
        assert statuses == ['cancelled', 'done'] * 4
        assert len(dispatched) == 8
    asyncio.run(scenario())


def test_readonly_shutdown_stops_local_task_when_cancel_cannot_persist(tmp_path):
    from types import SimpleNamespace
    from rct_control_plane.readonly_service import readonly_lifespan
    db = ControlPlanePersistence(db_path=str(tmp_path / 'shutdown.db'))
    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        jobs = JobService(db, runner)
        job = jobs.submit('alice', 'read')
        await started.wait()
        def unavailable(*args):
            raise sqlite3.OperationalError('database unavailable during shutdown')
        jobs.cancel = unavailable
        app = SimpleNamespace(state=SimpleNamespace(readonly_job_services={'alice': SimpleNamespace(jobs=jobs)}))
        async with readonly_lifespan(app):
            pass
        assert stopped.is_set() and not jobs._tasks
        assert jobs.get(job['id'])['status'] == 'cancelled'
    asyncio.run(scenario())

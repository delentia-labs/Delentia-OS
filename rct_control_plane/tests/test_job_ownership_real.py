"""Real SQLite/tasks and kill boundaries; fake clock for lease expiry, no model."""
import asyncio
import os
import time

import pytest

from rct_control_plane.jobs import JobError, JobService
from rct_control_plane.persistence import ControlPlanePersistence


class Clock:
    def __init__(self):
        self.now = 1000.0
    def __call__(self):
        return self.now


@pytest.fixture
def db(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / 'jobs.db'))


def test_second_live_service_does_not_interrupt_or_cancel_first(db):
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished', 'final_answer': 'ok'}
        first = JobService(db, runner)
        job = first.submit('alice', 'read')
        await started.wait()
        second = JobService(db, runner)
        assert second.get(job['id'])['status'] == 'running'
        assert second.list('alice')[0]['task_outcome'] == 'pending'
        finish.set()
        await first.wait(job['id'])
        done = second.get(job['id'])
        assert done['status'] == 'done' and done['task_outcome'] == 'completed_unverified'
    asyncio.run(scenario())


def test_remote_cancel_is_requested_then_acknowledged_by_owner(db):
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        first = JobService(db, runner)
        job = first.submit('alice', 'read')
        await started.wait()
        second = JobService(db, runner)
        with pytest.raises(JobError):
            second.cancel(job['id'], 'bob')
        requested = second.cancel(job['id'], 'alice')
        assert requested['cancel_requested'] and requested['status'] == 'running'
        await asyncio.wait_for(cancelled.wait(), timeout=5)
        await second.wait(job['id'], timeout=5)
        assert second.get(job['id'])['status'] == 'cancelled'
        assert second.get(job['id'])['task_outcome'] == 'cancelled'
        await first.wait(job['id'])
    asyncio.run(scenario())


def test_queued_cancel_prevents_runner_dispatch(db):
    async def scenario():
        async def forbidden(*args):
            pytest.fail('queued cancelled job must not dispatch')
        service = JobService(db, forbidden)
        job = service.submit('alice', 'read')
        service.cancel(job['id'], 'alice')
        await service.wait(job['id'])
        assert service.get(job['id'])['status'] == 'cancelled'
    asyncio.run(scenario())


def test_expired_owner_cannot_finish_or_deliver_result(db):
    async def scenario():
        clock = Clock()
        started, finish = asyncio.Event(), asyncio.Event()
        delivered = []
        async def runner(*args):
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished', 'final_answer': 'stale'}
        first = JobService(db, runner, clock=clock, lease_seconds=6)
        job = first.submit('alice', 'read', on_done=delivered.append)
        await started.wait()
        clock.now += 7
        second = JobService(db, runner, clock=clock, lease_seconds=6)
        assert second.get(job['id'])['status'] == 'interrupted'
        assert not first._update(job['id'], status='done', answer='forged stale write')
        finish.set()
        await first.wait(job['id'])
        observed = second.get(job['id'])
        assert observed['status'] == 'interrupted' and observed['answer'] is None
        assert not delivered
    asyncio.run(scenario())


def test_heartbeat_extends_lease_without_restarting_work(db):
    async def scenario():
        clock = Clock()
        started, finish = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished'}
        service = JobService(db, runner, clock=clock, lease_seconds=6)
        job = service.submit('alice', 'read')
        await started.wait()
        clock.now += 4
        assert service._ownership.pulse(job['id']) == 'ok'
        clock.now += 3
        assert service.get(job['id'])['status'] == 'running'
        finish.set()
        await service.wait(job['id'])
        assert service.get(job['id'])['status'] == 'done'
    asyncio.run(scenario())


@pytest.mark.parametrize('stopped', ['plan_ready', 'waiting_for_input', 'waiting_for_clarification', 'needs_clarification', 'pending_approval'])
def test_runner_done_can_mean_waiting_for_person(db, stopped):
    async def scenario():
        async def runner(*args):
            return {'stopped_reason': stopped, 'final_answer': 'not a verified result'}
        service = JobService(db, runner)
        job = service.submit('alice', 'work')
        await service.wait(job['id'])
        result = service.get(job['id'])
        assert result['status'] == 'done' and result['stopped'] == stopped
        assert result['task_outcome'] == 'waiting' and result['verification_scope'] is None
    asyncio.run(scenario())


def test_owner_token_fences_old_worker_even_before_expiry(db):
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished'}
        service = JobService(db, runner)
        job = service.submit('alice', 'work')
        await started.wait()
        with db._connect() as conn:
            conn.execute('UPDATE agent_job_owners SET token=? WHERE job_id=?', ('replacement', job['id']))
        assert not service._update(job['id'], answer='old owner')
        finish.set()
        await service.wait(job['id'])
        assert service.get(job['id'])['status'] == 'running'
    asyncio.run(scenario())


@pytest.mark.skipif(os.name != 'posix', reason='real fork/SIGKILL recovery test')
def test_killed_process_is_interrupted_without_replaying_runner(tmp_path):
    import multiprocessing
    path = tmp_path / 'jobs.db'
    marker = tmp_path / 'job.txt'
    ControlPlanePersistence(db_path=str(path))
    def worker():
        async def run():
            async def runner(*args):
                await asyncio.Event().wait()
            service = JobService(ControlPlanePersistence(db_path=str(path)), runner)
            job = service.submit('alice', 'work')
            marker.write_text(job['id'], encoding='utf-8')
            await service.wait(job['id'], timeout=30)
        asyncio.run(run())
    process = multiprocessing.get_context('fork').Process(target=worker)
    process.start()
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline and process.is_alive():
            time.sleep(0.02)
        assert marker.exists(), process.exitcode
        job_id = marker.read_text(encoding='utf-8')
        process.kill()
        process.join(5)
        async def forbidden(*args):
            pytest.fail('recovery must not replay an interrupted job')
        recovered = JobService(ControlPlanePersistence(db_path=str(path)), forbidden)
        assert recovered.get(job_id)['status'] == 'interrupted'
        assert recovered.get(job_id)['task_outcome'] == 'interrupted'
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)


def test_cancel_wins_over_runner_that_swallows_cancellation(db):
    async def scenario():
        started = asyncio.Event()
        async def runner(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return {'stopped_reason': 'llm_finished', 'final_answer': 'ignored cancel'}
        service = JobService(db, runner)
        job = service.submit('alice', 'work')
        await started.wait()
        service.cancel(job['id'], 'alice')
        await service.wait(job['id'])
        assert service.get(job['id'])['status'] == 'cancelled'
        assert service.get(job['id'])['answer'] is None
    asyncio.run(scenario())


def test_parallel_workers_cannot_both_pass_one_job_limit(db, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv('DELENTIA_MAX_JOBS', '1')
    barrier = threading.Barrier(2)
    async def runner(*args):
        await asyncio.Event().wait()
    services = [JobService(db, runner), JobService(db, runner)]
    def worker(service):
        async def run():
            job = None
            try:
                job = service.submit('alice', 'read')
                outcome = 'created'
            except JobError:
                outcome = 'rejected'
            barrier.wait(timeout=10)
            if job is not None:
                service.cancel(job['id'], 'alice')
                await service.wait(job['id'])
            return outcome
        return asyncio.run(run())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, services))
    assert sorted(results) == ['created', 'rejected']


def test_other_host_pid_is_not_used_as_local_liveness(db):
    async def scenario():
        clock = Clock()
        async def forbidden(*args):
            pytest.fail('expired queued job must never start')
        service = JobService(db, forbidden, clock=clock, lease_seconds=6)
        job = service.submit('alice', 'read')
        with db._connect() as conn:
            conn.execute('UPDATE agent_job_owners SET host=?,pid=? WHERE job_id=?', ('other-pid-namespace', 999999999, job['id']))
        assert service.get(job['id'])['status'] == 'queued'
        clock.now += 7
        assert service.get(job['id'])['status'] == 'interrupted'
        await service.wait(job['id'])
    asyncio.run(scenario())


@pytest.mark.skipif(os.name != 'posix', reason='typed quote execution needs POSIX no-follow')
def test_verified_outcome_requires_actor_bound_complete_receipts(db, tmp_path, monkeypatch):
    import copy
    import hashlib
    from rct_control_plane import autonomous_loop, mcp_server
    from rct_control_plane.job_ownership import result_outcome
    from rct_control_plane.tests.test_governed_autonomous_loop_real import _loop
    root = tmp_path / 'workspace'
    root.mkdir()
    raw = b'{"schema_version":1,"total":"100.10","currency":"THB","total_is_final":true}'
    (root / 'quote.json').write_bytes(raw)
    monkeypatch.setattr(mcp_server, 'REPO_ROOT', root)
    async def forbidden(*args, **kwargs):
        pytest.fail('verified budget must not call a model')
    monkeypatch.setattr(autonomous_loop, 'decide_next_action', forbidden)
    async def scenario():
        loop = _loop(tmp_path, 'alice', mcp=mcp_server.mcp)
        initial = await loop.run('เทียบราคากับงบ', acceptance_criteria=[{'kind': 'json_object'}],
            planning_context={'semantic_plan': {'budget': '150 THB', 'quote_evidence': {'relative_path': 'quote.json', 'sha256': hashlib.sha256(raw).hexdigest()}}})
        contract = initial['intent_contract']
        results = []
        async def runner(*args):
            result = await loop.continue_intent(contract['id'], contract['version'])
            results.append(result)
            return result
        service = JobService(db, runner)
        job = service.submit('alice', 'เทียบราคากับงบ')
        await service.wait(job['id'])
        observed = service.get(job['id'])
        assert observed['status'] == 'done' and observed['task_outcome'] == 'verified'
        assert observed['verification_scope'] == 'document_bytes_and_same_currency_arithmetic'
        result = results[0]
        assert result_outcome(result, 'bob')[0] == 'unconfirmed'
        for key in ['receipt', 'acceptance', 'semantic', 'digest']:
            broken = copy.deepcopy(result)
            if key == 'receipt':
                broken['intent_contract']['execution_receipts'].pop()
            elif key == 'digest':
                broken['intent_contract']['plan_sha256'] = '0' * 64
            else:
                broken[key + '_verification']['satisfied'] = False
            assert result_outcome(broken, 'alice')[0] == 'unconfirmed'
    asyncio.run(scenario())


@pytest.mark.skipif(os.name != 'posix', reason='real forked worker cancellation test')
def test_cancel_reaches_another_process_owner(tmp_path):
    import multiprocessing
    path = tmp_path / 'jobs.db'
    marker = tmp_path / 'started.txt'
    db = ControlPlanePersistence(db_path=str(path))
    def worker():
        async def run():
            async def runner(*args):
                marker.write_text(job['id'], encoding='utf-8')
                await asyncio.Event().wait()
            service = JobService(ControlPlanePersistence(db_path=str(path)), runner)
            job = service.submit('alice', 'work')
            await service.wait(job['id'], timeout=30)
        asyncio.run(run())
    process = multiprocessing.get_context('fork').Process(target=worker)
    process.start()
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline and process.is_alive():
            time.sleep(0.02)
        assert marker.exists(), process.exitcode
        job_id = marker.read_text(encoding='utf-8')
        async def forbidden(*args):
            pytest.fail('remote cancel must never dispatch a replacement runner')
        remote = JobService(db, forbidden)
        requested = remote.cancel(job_id, 'alice')
        assert requested['status'] == 'running' and requested['cancel_requested']
        asyncio.run(remote.wait(job_id, timeout=10))
        process.join(5)
        assert process.exitcode == 0
        assert remote.get(job_id)['status'] == 'cancelled'
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)


def test_database_loss_stops_owner_without_claiming_acknowledgement(db, monkeypatch):
    import sqlite3
    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        service = JobService(db, runner)
        job = service.submit('alice', 'work')
        await started.wait()
        def unavailable(job_id):
            raise sqlite3.OperationalError('injected database unavailable')
        monkeypatch.setattr(service._ownership, 'pulse', unavailable)
        await asyncio.wait_for(stopped.wait(), timeout=5)
        await service.wait(job['id'])
        assert service.get(job['id'])['status'] == 'cancelled'
    asyncio.run(scenario())

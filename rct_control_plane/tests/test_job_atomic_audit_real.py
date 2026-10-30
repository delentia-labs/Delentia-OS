"""State/owner/cancel audit failures must roll back instead of false success."""
import asyncio
import sqlite3

import pytest

from rct_control_plane.jobs import JobService
from rct_control_plane.persistence import ControlPlanePersistence


def test_failed_submission_audit_leaves_no_job_or_owner(tmp_path):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'state.db'))
    async def run():
        async def forbidden(*args):
            pytest.fail('failed admission must not dispatch')
        service = JobService(db, forbidden)
        with db._connect() as conn:
            conn.execute("CREATE TRIGGER fail BEFORE INSERT ON audit_trail WHEN NEW.entity_type='agent_job' BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END")
        with pytest.raises(sqlite3.Error):
            service.submit('alice', 'read')
        with db._connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM agent_jobs').fetchone()[0] == 0
            assert conn.execute('SELECT COUNT(*) FROM agent_job_owners').fetchone()[0] == 0
    asyncio.run(run())


@pytest.mark.parametrize('action', ['finished', 'cancel_requested'])
def test_job_transition_and_cancel_flag_rollback_on_audit_failure(tmp_path, action):
    db = ControlPlanePersistence(db_path=str(tmp_path / 'state.db'))
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished', 'final_answer': 'ok'}
        service = JobService(db, runner)
        job = service.submit('alice', 'read')
        await started.wait()
        with db._connect() as conn:
            conn.execute("CREATE TRIGGER fail BEFORE INSERT ON audit_trail WHEN NEW.entity_type='agent_job' AND NEW.action='" + action + "' BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END")
        with pytest.raises(sqlite3.Error):
            if action == 'finished':
                service._ownership.update(job['id'], {'status': 'done', 'answer': 'uncommitted'}, outcome='verified')
            else:
                service.cancel(job['id'], 'alice')
        observed = service.get(job['id'])
        assert observed['status'] == 'running' and observed['task_outcome'] == 'pending'
        assert not observed['cancel_requested'] and observed['answer'] is None
        with db._connect() as conn:
            conn.execute('DROP TRIGGER fail')
        finish.set()
        await service.wait(job['id'])
        assert service.get(job['id'])['status'] == 'done'
    asyncio.run(run())

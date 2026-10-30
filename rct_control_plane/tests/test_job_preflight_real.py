"""Preflight reads existing DBs without migration, payload disclosure or drain."""
import asyncio
import hashlib
import json

from rct_control_plane.job_preflight import inspect_database, main
from rct_control_plane.jobs import JobService
from rct_control_plane.persistence import ControlPlanePersistence


def test_missing_database_is_not_created(tmp_path, capsys):
    path = tmp_path / 'absent.db'
    assert main(['--database', str(path), '--require-drained']) == 2
    assert not path.exists()
    assert 'unavailable' in capsys.readouterr().out


def test_healthy_empty_database_is_inspected_without_schema_changes(tmp_path):
    path = tmp_path / 'empty.db'
    ControlPlanePersistence(db_path=str(path))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    report = inspect_database(path)
    assert report['drained_upgrade_snapshot_ok']
    assert not report['clock_fencing_schema_present']
    assert not report['retention_policy_verified']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_preflight_blocks_live_jobs_and_does_not_dump_goal(tmp_path, capsys):
    path = tmp_path / 'live.db'
    db = ControlPlanePersistence(db_path=str(path))
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def runner(*args):
            started.set()
            await finish.wait()
            return {'stopped_reason': 'llm_finished'}
        service = JobService(db, runner)
        job = service.submit('alice', 'PRIVATE GOAL MUST NOT APPEAR')
        await started.wait()
        assert main(['--database', str(path), '--require-drained']) == 1
        raw = capsys.readouterr().out
        report = json.loads(raw)
        assert report['live_jobs'] == 1 and report['legacy_live_jobs'] == 0
        assert 'PRIVATE' not in raw and 'alice' not in raw
        assert service.get(job['id'])['status'] == 'running'
        finish.set()
        await service.wait(job['id'], timeout=5)
        assert main(['--database', str(path), '--require-drained']) == 0
    asyncio.run(scenario())


def test_unknown_state_does_not_pass_upgrade_check(tmp_path):
    path = tmp_path / 'unknown.db'
    db = ControlPlanePersistence(db_path=str(path))
    JobService(db, None)
    with db._connect() as conn:
        conn.execute("INSERT INTO agent_jobs(id,namespace,goal,status,created_at) VALUES('future','alice','private','new_unknown_state',0)")
    report = inspect_database(path)
    assert not report['drained_upgrade_snapshot_ok']
    assert report['unknown_statuses'] == ['new_unknown_state']

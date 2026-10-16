"""
Round 82, plan item N4: a scheduled run that was cut off (the process died, the machine restarted) shows up as `interrupted`, not as silence.

A job's next run is advanced when the run is CLAIMED (so an occurrence runs at most once). That left a hole: if the process died after the claim, nothing was ever written, and the job's
last status still showed the run before, as if the missed one had never been due. Now a claim marks the job `running`; a `running` job nobody is running any more (older than the run limit
plus a grace, and not active in this process) is marked `interrupted`, audited, and does NOT count as the job's own failure. The occurrence is not run again (it may have had effects).

Real SQLite, the real schedule parser, real governed episodes with a scripted model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from rct_control_plane import cron_jobs
from rct_control_plane.cron_jobs import CronService
from rct_control_plane.persistence import ControlPlanePersistence
from test_cron_jobs_round57_real import Kernel, audit_actions, script

ZONE = ZoneInfo("Asia/Bangkok")
NOW = datetime(2026, 10, 3, 10, 0, tzinfo=ZONE).timestamp()
run = asyncio.run


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in (cron_jobs.HOURLY_CAP_ENV, cron_jobs.RUN_SECONDS_ENV, "DELENTIA_TIMEZONE", "DELENTIA_APPROVERS_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_TIMEZONE", "Asia/Bangkok")
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "cron.db"))
    return CronService(persistence), Kernel(persistence), persistence


def make_due(service):
    job = service.create("alice", "summarise the notes", "every day at 9:00", now=NOW - 86400)
    return service.get(job["id"])


def test_a_claimed_job_is_marked_running(env):
    service, _kernel, _p = env
    job = make_due(service)
    assert service.claim(job, NOW) is True
    now = service.get(job["id"])
    assert now["last_status"] == "running" and now["last_run_at"] == pytest.approx(NOW)


def test_a_run_that_finished_shows_its_real_status_not_running(env, monkeypatch):
    service, kernel, _p = env
    script(monkeypatch, [])
    job = make_due(service)
    assert service.claim(job, NOW)
    after = run(service.run_job(kernel, job, None, NOW, counted=True))
    assert after["last_status"] not in ("running", "interrupted") and after["run_count"] == 1


def test_a_run_whose_process_died_is_marked_interrupted_after_the_run_limit(env):
    service, _kernel, p = env
    job = make_due(service)
    assert service.claim(job, NOW)                                  # ... and the process dies here: run_job never writes anything
    assert service.recover_interrupted(now=NOW + 60) == []          # still within the run limit: it may be running somewhere
    assert service.get(job["id"])["last_status"] == "running"
    later = NOW + cron_jobs.DEFAULT_RUN_SECONDS + cron_jobs.INTERRUPTED_GRACE_SECONDS + 5
    flagged = service.recover_interrupted(now=later)
    assert [j["id"] for j in flagged] == [job["id"]]
    after = service.get(job["id"])
    assert after["last_status"] == "interrupted" and "stopped" in after["last_result"]
    assert after["fail_streak"] == 0 and after["enabled"] is True and after["run_count"] == 0       # not the job's fault, not counted as a run, still scheduled
    assert after["next_run_at"] > NOW                                                                # the missed occurrence is NOT run again; the next one is
    assert "interrupted" in audit_actions(p, job["id"])


def test_it_is_flagged_once(env):
    service, _kernel, _p = env
    job = make_due(service)
    service.claim(job, NOW)
    later = NOW + cron_jobs.DEFAULT_RUN_SECONDS + cron_jobs.INTERRUPTED_GRACE_SECONDS + 5
    assert len(service.recover_interrupted(now=later)) == 1
    assert service.recover_interrupted(now=later + 10) == []


def test_a_run_this_process_is_still_executing_is_never_flagged(env):
    service, _kernel, _p = env
    job = make_due(service)
    service.claim(job, NOW)
    service._active.add(job["id"])                                   # run_job registers itself while it works
    assert service.recover_interrupted(now=NOW + 10 * cron_jobs.DEFAULT_RUN_SECONDS) == []
    assert service.get(job["id"])["last_status"] == "running"


def test_the_dispatcher_looks_for_dead_runs_on_every_tick(env, monkeypatch):
    service, kernel, _p = env
    script(monkeypatch, [])
    dead = make_due(service)
    service.claim(dead, NOW)                                         # died after the claim
    later = NOW + cron_jobs.DEFAULT_RUN_SECONDS + cron_jobs.INTERRUPTED_GRACE_SECONDS + 5

    async def tick():
        service.dispatch_background(kernel, None, later)
        await asyncio.gather(*list(service._background))
    run(tick())
    assert service.get(dead["id"])["last_status"] == "interrupted"


def test_the_owner_hears_about_it(env, monkeypatch):
    service, _kernel, p = env
    told = []
    from rct_control_plane import owner_notify
    monkeypatch.setattr(owner_notify, "on_job_problem", lambda job, stopped, switched_off, persistence=None: told.append((job["id"], stopped, switched_off)))
    job = make_due(service)
    service.claim(job, NOW)
    service.recover_interrupted(now=NOW + cron_jobs.DEFAULT_RUN_SECONDS + cron_jobs.INTERRUPTED_GRACE_SECONDS + 5)
    assert told == [(job["id"], "interrupted", False)]

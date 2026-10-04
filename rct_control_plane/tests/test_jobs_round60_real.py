"""
Round 60 (D4): background agent jobs.

JobService is exercised directly with real SQLite and real asyncio tasks (the runner is a stand-in that can sleep, fail or call on_step, because what is under test is the job
lifecycle, not the model); the HTTP layer is exercised through the real FastAPI app with the governed loop's `run` replaced by a script.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from rct_control_plane.api import create_app
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.jobs import JobError, JobService
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture(autouse=True)
def limits(monkeypatch):
    for name in ("DELENTIA_MAX_JOBS_PER_USER", "DELENTIA_MAX_JOBS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def persistence(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "jobs.db"))


class Step:
    def __init__(self, tool):
        self.tool_name = tool


def service(persistence, behaviour):
    async def runner(namespace, goal, max_iterations, max_seconds, on_step):
        return await behaviour(namespace, goal, on_step)
    return JobService(persistence, runner)


async def quick(namespace, goal, on_step):
    await on_step(Step("delentia_read_repo_file"))
    await on_step(Step("delentia_recall"))
    return {"stopped_reason": "llm_finished", "final_answer": f"done: {goal}", "iterations": 2, "cost": {"cost_usd": 0.0, "prompt_tokens": 10, "completion_tokens": 5}}


async def slow(namespace, goal, on_step):
    await on_step(Step("delentia_crawl_url"))
    await asyncio.sleep(30)
    return {"stopped_reason": "llm_finished", "final_answer": "never"}


# ------------------------------------------------------------------ lifecycle

class TestLifecycle:
    def test_submit_answers_at_once_and_the_job_finishes_in_the_background(self, persistence):
        async def scenario():
            jobs = service(persistence, quick)
            job = jobs.submit("alice", "summarise the notes")
            assert job["id"].startswith("job-") and job["status"] in ("queued", "running") and job["namespace"] == "alice"
            await jobs.wait(job["id"])
            return jobs.get(job["id"])
        done = asyncio.run(scenario())
        assert done["status"] == "done" and done["answer"] == "done: summarise the notes" and done["steps"] == 2 and done["stopped"] == "llm_finished"
        assert done["cost"]["prompt_tokens"] == 10 and done["finished_at"] >= done["started_at"] >= done["created_at"]

    def test_progress_is_visible_while_it_runs(self, persistence):
        async def scenario():
            jobs = service(persistence, slow)
            job = jobs.submit("alice", "read a page")
            for _ in range(50):
                await asyncio.sleep(0.05)
                current = jobs.get(job["id"])
                if current["steps"] >= 1:
                    break
            jobs.cancel(job["id"], "alice")
            await jobs.wait(job["id"])
            return current
        current = asyncio.run(scenario())
        assert current["status"] == "running" and current["steps"] == 1 and current["last_tool"] == "delentia_crawl_url"

    def test_a_job_that_stopped_for_a_signature_carries_the_approval_id(self, persistence):
        async def waiting(namespace, goal, on_step):
            return {"stopped_reason": "pending_approval", "final_answer": None, "approval_id": "abc123def456", "iterations": 1}

        async def scenario():
            jobs = service(persistence, waiting)
            job = jobs.submit("alice", "write the file")
            await jobs.wait(job["id"])
            return jobs.get(job["id"])
        done = asyncio.run(scenario())
        assert done["status"] == "done" and done["stopped"] == "pending_approval" and done["approval_id"] == "abc123def456"

    def test_a_failing_job_is_recorded_without_leaking_the_exception_text(self, persistence):
        async def broken(namespace, goal, on_step):
            raise RuntimeError("SECRET detail: sk-live-123")

        async def scenario():
            jobs = service(persistence, broken)
            job = jobs.submit("alice", "x")
            await jobs.wait(job["id"])
            return jobs.get(job["id"])
        failed = asyncio.run(scenario())
        assert failed["status"] == "failed" and "SECRET" not in json.dumps(failed) and "RuntimeError" in failed["error"]

    def test_every_step_of_the_lifecycle_is_audited(self, persistence):
        async def scenario():
            jobs = service(persistence, quick)
            job = jobs.submit("alice", "x")
            await jobs.wait(job["id"])
        asyncio.run(scenario())
        with persistence._connect() as conn:
            actions = [r[0] for r in conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'agent_job' ORDER BY id")]
        assert actions == ["submitted", "finished"]


# ------------------------------------------------------------------ cancel

class TestCancel:
    def test_cancelling_a_running_job_stops_it_and_says_so(self, persistence):
        async def scenario():
            jobs = service(persistence, slow)
            job = jobs.submit("alice", "long task")
            await asyncio.sleep(0.2)
            answer = jobs.cancel(job["id"], "alice")
            await jobs.wait(job["id"])
            return answer, jobs.get(job["id"])
        _, final = asyncio.run(scenario())
        assert final["status"] == "cancelled" and final["stopped"] == "cancelled" and final["finished_at"]
        with persistence._connect() as conn:
            assert "cancelled" in [r[0] for r in conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'agent_job'")]

    def test_cancelling_a_finished_job_changes_nothing(self, persistence):
        async def scenario():
            jobs = service(persistence, quick)
            job = jobs.submit("alice", "x")
            await jobs.wait(job["id"])
            return jobs.cancel(job["id"], "alice")
        assert asyncio.run(scenario())["status"] == "done"

    def test_nobody_can_cancel_or_read_someone_elses_job(self, persistence):
        async def scenario():
            jobs = service(persistence, slow)
            job = jobs.submit("alice", "private goal")
            with pytest.raises(JobError, match="no such job"):
                jobs.cancel(job["id"], "mallory")
            assert jobs.get(job["id"], "mallory") is None and jobs.list("mallory") == []
            assert jobs.get(job["id"], "alice")["status"] in ("queued", "running")
            jobs.cancel(job["id"], "alice")
            await jobs.wait(job["id"])
        asyncio.run(scenario())


# ------------------------------------------------------------------ limits and restarts

class TestLimits:
    def test_a_person_may_run_only_so_many_at_once(self, persistence, monkeypatch):
        monkeypatch.setenv("DELENTIA_MAX_JOBS_PER_USER", "2")

        async def scenario():
            jobs = service(persistence, slow)
            first, second = jobs.submit("alice", "a"), jobs.submit("alice", "b")
            with pytest.raises(JobError, match="most jobs"):
                jobs.submit("alice", "c")
            other = jobs.submit("bob", "d")                      # another person is unaffected
            for j in (first, second, other):
                jobs.cancel(j["id"], j["namespace"])
                await jobs.wait(j["id"])
        asyncio.run(scenario())

    def test_the_server_as_a_whole_has_a_limit_too(self, persistence, monkeypatch):
        monkeypatch.setenv("DELENTIA_MAX_JOBS", "2")
        monkeypatch.setenv("DELENTIA_MAX_JOBS_PER_USER", "5")

        async def scenario():
            jobs = service(persistence, slow)
            made = [jobs.submit("a", "1"), jobs.submit("b", "2")]
            with pytest.raises(JobError, match="server"):
                jobs.submit("c", "3")
            for j in made:
                jobs.cancel(j["id"], j["namespace"])
                await jobs.wait(j["id"])
        asyncio.run(scenario())

    def test_an_empty_or_huge_goal_is_refused(self, persistence):
        async def scenario():
            jobs = service(persistence, quick)
            for bad in ("", "   ", "x" * 5000):
                with pytest.raises(JobError):
                    jobs.submit("alice", bad)
        asyncio.run(scenario())

    def test_a_job_that_was_running_when_the_server_died_is_marked_interrupted(self, persistence):
        first = service(persistence, quick)                      # creates the table; then a row exactly as a crashed process leaves it
        with persistence._connect() as conn:
            conn.execute("INSERT INTO agent_jobs (id, namespace, goal, status, created_at, started_at) VALUES ('job-crashed', 'alice', 'long', 'running', ?, ?)", (time.time(), time.time()))
            conn.execute("INSERT INTO agent_jobs (id, namespace, goal, status, created_at) VALUES ('job-queued', 'alice', 'later', 'queued', ?)", (time.time(),))
        del first
        second = service(persistence, quick)                     # a new process starts
        for job_id in ("job-crashed", "job-queued"):
            after = second.get(job_id)
            assert after["status"] == "interrupted" and "restarted" in after["error"] and after["finished_at"]

    def test_a_finished_job_survives_a_restart_unchanged(self, persistence):
        async def scenario():
            jobs = service(persistence, quick)
            job = jobs.submit("alice", "x")
            await jobs.wait(job["id"])
            return job["id"]
        job_id = asyncio.run(scenario())
        assert service(persistence, quick).get(job_id)["status"] == "done"


# ------------------------------------------------------------------ the HTTP layer

class TestApi:
    @pytest.fixture
    def client(self, monkeypatch):
        calls = []

        async def fake_run(self, goal, **kwargs):
            calls.append((self.namespace, goal))
            on_step = kwargs.get("on_step")
            if on_step is not None:
                await on_step(Step("delentia_recall"))
            if "slow" in goal:
                await asyncio.sleep(30)
            return {"stopped_reason": "llm_finished", "final_answer": f"answer to {goal}", "iterations": 1}
        monkeypatch.setattr(GovernedAutonomousLoop, "run", fake_run)
        with TestClient(create_app()) as client:
            client.calls = calls
            yield client

    @staticmethod
    def wait_for(client, job_id, namespace, status="done"):
        for _ in range(100):
            job = client.get(f"/v1/agent/jobs/{job_id}", params={"namespace": namespace}).json()
            if job["status"] == status:
                return job
            time.sleep(0.05)
        raise AssertionError(job)

    def test_submit_poll_and_list(self, client):
        accepted = client.post("/v1/agent/jobs", json={"goal": "summarise it", "namespace": "api-test-1"})
        assert accepted.status_code == 202
        job_id = accepted.json()["id"]
        done = self.wait_for(client, job_id, "api-test-1")
        assert done["answer"] == "answer to summarise it" and done["stopped"] == "llm_finished"
        listed = client.get("/v1/agent/jobs", params={"namespace": "api-test-1"}).json()["jobs"]
        assert [j["id"] for j in listed] == [job_id]
        assert client.calls == [("api-test-1", "summarise it")]

    def test_other_people_get_a_404_and_the_job_does_not_appear_in_their_list(self, client):
        job_id = client.post("/v1/agent/jobs", json={"goal": "private thing", "namespace": "api-test-2"}).json()["id"]
        self.wait_for(client, job_id, "api-test-2")
        assert client.get(f"/v1/agent/jobs/{job_id}", params={"namespace": "api-test-3"}).status_code == 404
        assert client.get("/v1/agent/jobs", params={"namespace": "api-test-3"}).json()["jobs"] == []
        assert client.delete(f"/v1/agent/jobs/{job_id}", params={"namespace": "api-test-3"}).status_code == 404

    def test_cancel_over_http(self, client):
        job_id = client.post("/v1/agent/jobs", json={"goal": "slow work", "namespace": "api-test-4"}).json()["id"]
        time.sleep(0.3)
        cancelled = client.delete(f"/v1/agent/jobs/{job_id}", params={"namespace": "api-test-4"})
        assert cancelled.status_code == 200
        assert self.wait_for(client, job_id, "api-test-4", "cancelled")["stopped"] == "cancelled"

    def test_bad_requests(self, client):
        assert client.post("/v1/agent/jobs", json={"namespace": "api-test-5"}).status_code == 400
        assert client.post("/v1/agent/jobs", json={"goal": "x" * 5000, "namespace": "api-test-5"}).status_code == 400
        assert client.get("/v1/agent/jobs/job-doesnotexist", params={"namespace": "api-test-5"}).status_code == 404

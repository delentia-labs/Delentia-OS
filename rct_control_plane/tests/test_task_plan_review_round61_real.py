"""
Round 61: the plan of a task belongs to the person - a draft runs nothing until they start it, the steps that have not run can be rewritten, and a failed task becomes a NEW draft rather than
being re-planned behind their back. Real SQLite, a scripted runner, the real CLI and (for the endpoints) the real FastAPI app.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio

import pytest
from click.testing import CliRunner

from rct_control_plane.cli import cli
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.task_board import MAX_DRAFTS_PER_USER, MAX_LIVE_PER_USER, MAX_STEPS, TaskBoard, TaskError

run = asyncio.run


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


@pytest.fixture
def persistence(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "t.db"))


class Script:
    def __init__(self, *results):
        self.results, self.calls = list(results), []

    async def __call__(self, namespace, goal, max_iterations, max_seconds, on_step, initial_taint=None):
        self.calls.append({"goal": goal, "initial_taint": initial_taint})
        return self.results.pop(0) if self.results else {"stopped_reason": "llm_finished", "final_answer": "ok", "taint": {"tainted": False}}


def ok(text):
    return {"stopped_reason": "llm_finished", "final_answer": text, "taint": {"tainted": False, "source_tool": None}}


class TestDraft:
    def test_a_draft_runs_nothing_until_it_is_started(self, persistence):
        runner = Script()
        board = TaskBoard(persistence, runner)
        task = board.create("alice", "triage", ["read", "group"], review=True)
        assert task["status"] == "draft"
        assert run(board.advance(task["id"]))["status"] == "draft"
        assert run(board.advance_all()) == 0 and runner.calls == []
        started = board.start(task["id"], "alice")
        assert started["status"] == "waiting"
        done = run(board.run_to_completion(task["id"]))
        assert done["status"] == "done" and len(runner.calls) == 2

    def test_the_rct7_plan_is_shown_as_a_draft_too(self, persistence):
        board = TaskBoard(persistence, Script(), planner=lambda goal: ["understand it", "do it", "check it"])
        task = board.create("alice", "ship the release notes", review=True)
        assert [s["text"] for s in task["steps"]] == ["understand it", "do it", "check it"] and task["status"] == "draft"

    def test_drafts_do_not_count_as_live_tasks_but_are_limited_themselves(self, persistence):
        board = TaskBoard(persistence, Script())
        for i in range(MAX_DRAFTS_PER_USER):
            board.create("alice", f"g{i}", ["a"], review=True)
        with pytest.raises(TaskError, match="drafts"):
            board.create("alice", "one too many", ["a"], review=True)
        for i in range(MAX_LIVE_PER_USER):
            board.create("alice", f"live{i}", ["a"])                       # live tasks are a separate allowance
        with pytest.raises(TaskError, match="most tasks running"):
            board.start(board.list("alice", 100)[-1]["id"], "alice")

    def test_only_a_draft_can_be_started_and_only_by_its_owner(self, persistence):
        board = TaskBoard(persistence, Script())
        live = board.create("alice", "g", ["a"])
        with pytest.raises(TaskError, match="only a draft"):
            board.start(live["id"], "alice")
        draft = board.create("alice", "g2", ["a"], review=True)
        with pytest.raises(TaskError, match="no such task"):
            board.start(draft["id"], "mallory")

    def test_a_draft_can_be_cancelled(self, persistence):
        board = TaskBoard(persistence, Script())
        draft = board.create("alice", "g", ["a", "b"], review=True)
        cancelled = board.cancel(draft["id"], "alice")
        assert cancelled["status"] == "cancelled" and {s["status"] for s in cancelled["steps"]} == {"cancelled"}


class TestEditPlan:
    def test_a_draft_plan_is_rewritten_added_to_and_reordered_freely(self, persistence):
        board = TaskBoard(persistence, Script())
        draft = board.create("alice", "g", ["one", "two"], review=True)
        edited = board.edit_plan(draft["id"], ["zero", "two", "three", "four"], "alice")
        assert [s["text"] for s in edited["steps"]] == ["zero", "two", "three", "four"] and [s["n"] for s in edited["steps"]] == [1, 2, 3, 4]
        assert edited["status"] == "draft" and "nothing has run" in edited["note"]

    def test_a_task_under_way_keeps_what_already_ran(self, persistence):
        runner = Script(ok("first result"))
        board = TaskBoard(persistence, runner)
        task = board.create("alice", "g", ["one", "two", "three"])
        run(board.advance(task["id"]))                                   # step 1 ran
        edited = board.edit_plan(task["id"], ["two, better", "three, better", "four"], "alice")
        assert [s["status"] for s in edited["steps"]] == ["done", "pending", "pending", "pending"]
        assert edited["steps"][0]["summary"] == "first result" and [s["text"] for s in edited["steps"][1:]] == ["two, better", "three, better", "four"]
        done = run(board.run_to_completion(task["id"]))
        assert done["status"] == "done" and runner.calls[1]["goal"].count("first result") == 1 and "two, better" in runner.calls[1]["goal"]

    def test_refused_while_running_or_after_the_end_or_when_empty_or_too_long(self, persistence):
        board = TaskBoard(persistence, Script())
        task = board.create("alice", "g", ["one"])
        with pytest.raises(TaskError, match="at least one step"):
            board.edit_plan(task["id"], ["  ", ""], "alice")
        with pytest.raises(TaskError, match="at most"):
            board.edit_plan(task["id"], [f"s{i}" for i in range(MAX_STEPS + 1)], "alice")
        task["steps"][0]["status"] = "running"
        board._save(task, status="running")
        with pytest.raises(TaskError, match="cannot be edited"):
            board.edit_plan(task["id"], ["x"], "alice")
        board.cancel(task["id"], "alice")
        with pytest.raises(TaskError, match="cannot be edited"):
            board.edit_plan(task["id"], ["x"], "alice")

    def test_someone_elses_task_is_not_editable(self, persistence):
        board = TaskBoard(persistence, Script())
        draft = board.create("alice", "g", ["one"], review=True)
        with pytest.raises(TaskError, match="no such task"):
            board.edit_plan(draft["id"], ["pwned"], "mallory")

    def test_every_edit_is_in_the_audit_trail_without_the_text(self, persistence):
        board = TaskBoard(persistence, Script())
        draft = board.create("alice", "g", ["one"], review=True)
        board.edit_plan(draft["id"], ["a very secret step"], "alice")
        board.start(draft["id"], "alice")
        with persistence._connect() as conn:
            rows = conn.execute("SELECT action, changes FROM audit_trail WHERE entity_type = 'agent_task' ORDER BY rowid").fetchall()
        assert [r[0] for r in rows] == ["created", "plan_edited", "started"]
        assert all("a very secret step" not in str(r[1]) for r in rows) and "after_sha256" in str(rows[1][1])


class TestReplan:
    def _failed(self, board, runner_results):
        task = board.create("alice", "g", ["one", "two", "three"])
        return run(board.run_to_completion(task["id"]))

    def test_a_failed_task_becomes_a_new_draft_with_the_done_steps_carried_over(self, persistence):
        bad = {"stopped_reason": "max_iterations", "final_answer": None, "taint": {"tainted": False}}
        board = TaskBoard(persistence, Script(ok("did one"), bad, bad))
        failed = self._failed(board, None)
        assert failed["status"] == "failed"
        draft = board.replan(failed["id"], "alice")
        assert draft["id"] != failed["id"] and draft["status"] == "draft" and f"re-plan of {failed['id']}" in draft["note"]
        assert [s["status"] for s in draft["steps"]] == ["done", "pending", "pending"] and draft["steps"][0]["summary"] == "did one"
        assert [s["text"] for s in draft["steps"][1:]] == ["two", "three"]
        assert board.get(failed["id"])["status"] == "failed"              # the old task is untouched, and nothing started
        assert board.get(draft["id"])["status"] == "draft"

    def test_the_taint_is_carried_over(self, persistence):
        tainted = {"stopped_reason": "llm_finished", "final_answer": "read a page", "taint": {"tainted": True, "source_tool": "delentia_crawl_url"}}
        bad = {"stopped_reason": "max_iterations", "final_answer": None, "taint": {"tainted": True, "source_tool": "delentia_crawl_url"}}
        board = TaskBoard(persistence, Script(tainted, bad, bad))
        failed = self._failed(board, None)
        draft = board.replan(failed["id"], "alice")
        assert draft["tainted"] is True and draft["taint_source"] == "delentia_crawl_url"
        runner = Script()
        board2 = TaskBoard(persistence, runner)
        board2.start(draft["id"], "alice")
        run(board2.advance(draft["id"]))
        assert runner.calls[0]["initial_taint"] and "delentia_crawl_url" in runner.calls[0]["initial_taint"]

    def test_the_person_can_give_the_new_steps(self, persistence):
        bad = {"stopped_reason": "max_iterations", "final_answer": None, "taint": {"tainted": False}}
        board = TaskBoard(persistence, Script(bad, bad))
        task = board.create("alice", "g", ["one"])
        failed = run(board.run_to_completion(task["id"]))
        draft = board.replan(failed["id"], "alice", ["try it another way"])
        assert [s["text"] for s in draft["steps"]] == ["try it another way"]

    def test_only_a_failed_or_cancelled_task_and_never_by_another_person(self, persistence):
        board = TaskBoard(persistence, Script())
        live = board.create("alice", "g", ["one"])
        with pytest.raises(TaskError, match="only a failed or cancelled"):
            board.replan(live["id"], "alice")
        board.cancel(live["id"], "alice")
        with pytest.raises(TaskError, match="no such task"):
            board.replan(live["id"], "mallory")
        assert board.replan(live["id"], "alice")["status"] == "draft"

    def test_nothing_to_plan_when_every_step_is_done(self, persistence):
        board = TaskBoard(persistence, Script(ok("a")))
        task = board.create("alice", "g", ["one"])
        done = run(board.run_to_completion(task["id"]))
        done["status"] = "failed"
        board._save(done, status="failed")
        with pytest.raises(TaskError, match="nothing is left"):
            board.replan(done["id"], "alice")


class TestCli:
    def test_create_review_plan_start_replan(self, tmp_path):
        db = str(tmp_path / "cli.db")
        r = CliRunner()
        out = r.invoke(cli, ["task", "create", "triage the issues", "--step", "read", "--step", "group", "--review", "--db", db])
        assert out.exit_code == 0 and "draft task-" in out.output and "1. read" in out.output
        task_id = out.output.split("draft ")[1].split(" ")[0]
        assert r.invoke(cli, ["task", "plan", task_id, "--step", "read all", "--step", "group", "--step", "reply", "--db", db]).exit_code == 0
        shown = r.invoke(cli, ["task", "show", task_id, "--db", db]).output
        assert "draft" in shown and "read all" in shown and "reply" in shown
        started = r.invoke(cli, ["task", "start", task_id, "--db", db])
        assert started.exit_code == 0 and "waiting" in started.output
        again = r.invoke(cli, ["task", "start", task_id, "--db", db])
        assert again.exit_code == 1 and "only a draft" in again.output
        r.invoke(cli, ["task", "cancel", task_id, "--db", db])
        replanned = r.invoke(cli, ["task", "replan", task_id, "--db", db])
        assert replanned.exit_code == 0 and "draft task-" in replanned.output


class TestEndpoints:
    @pytest.fixture
    def client(self, monkeypatch):
        from fastapi.testclient import TestClient
        from rct_control_plane.api import create_app
        monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
        return TestClient(create_app())

    def test_draft_edit_start_replan_over_http(self, client):
        made = client.post("/v1/agent/tasks", json={"goal": "triage", "steps": ["read", "group"], "review": True})
        assert made.status_code == 201 and made.json()["status"] == "draft"
        task_id = made.json()["id"]
        edited = client.put(f"/v1/agent/tasks/{task_id}/plan", json={"steps": ["read it all", "group", "reply"]})
        assert edited.status_code == 200 and [s["text"] for s in edited.json()["steps"]] == ["read it all", "group", "reply"]
        assert client.put(f"/v1/agent/tasks/{task_id}/plan", json={"steps": []}).status_code == 400
        started = client.post(f"/v1/agent/tasks/{task_id}/start")
        assert started.status_code == 200 and started.json()["status"] == "waiting"
        assert client.post(f"/v1/agent/tasks/{task_id}/start").status_code == 409
        assert client.post("/v1/agent/tasks/task-nope/start").status_code == 404
        client.delete(f"/v1/agent/tasks/{task_id}")
        replan = client.post(f"/v1/agent/tasks/{task_id}/replan")
        assert replan.status_code == 201 and replan.json()["status"] == "draft"

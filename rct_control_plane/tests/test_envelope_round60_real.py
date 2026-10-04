"""
Round 60 (D1): the safety envelope - pause, daily limits, flood limit, hard stop on repeating.

Real governed episodes (the loop, gate, approvals, audit and the new spend ledger on real SQLite); the model is a script that fails the test if it is asked anything when it must not be.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import time

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import measure_injection_defence as mid
import rct_control_plane.autonomous_loop as al
import rct_control_plane.desk_api as desk_api
from rct_control_plane import approvals, envelope
from rct_control_plane.api import create_app
from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.cli import cli
from rct_control_plane.cron_jobs import FAILING_STOPS
from rct_control_plane.gateways.common import reply_text_for
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from test_governed_autonomous_loop_real import _FakeKernel

run = asyncio.run


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in (envelope.PAUSED_ENV, envelope.DAILY_USD_ENV, envelope.DAILY_TOKENS_ENV, envelope.USER_DAILY_USD_ENV, envelope.USER_DAILY_TOKENS_ENV, envelope.HOURLY_USER_ENV,
                 envelope.HOURLY_ALL_ENV, envelope.REPEAT_LIMIT_ENV, "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS", approvals.APPROVERS_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


class Rig:
    """A loop with a scripted model. `asked` counts model calls; `mcp.dispatched` lists the tools that really ran."""

    def __init__(self, tmp_path, monkeypatch, decisions=(), namespace="alice", results=None):
        self.asked = 0
        self.decisions = list(decisions)
        self.mcp = mid.RecordingMCP(lambda name, args: (results or {}).get(name, json.dumps({"ok": True})))
        self.persistence = ControlPlanePersistence(db_path=str(tmp_path / "t.db"))
        self.monkeypatch = monkeypatch
        self.tmp_path = tmp_path
        self.namespace = namespace
        self._install()

    def _install(self):
        async def model(goal, history, available_tools, llm_provider=None, extra_context=""):
            i = self.asked
            self.asked += 1
            if i < len(self.decisions):
                tool, args = self.decisions[i]
                return {"action": "call_tool", "tool_name": tool, "tool_args": args, "reasoning": "step"}
            return {"action": "finish", "reasoning": "done", "final_answer": "Done.", "tool_name": None, "tool_args": {}}
        self.monkeypatch.setattr(al, "decide_next_action", model)

    def loop(self, namespace=None):
        return GovernedAutonomousLoop(mcp_server=self.mcp, persistence=self.persistence, kernel=_FakeKernel(), max_iterations=8, namespace=namespace or self.namespace, route=False,
                                      skill_library=SkillLibrary(db_path=str(self.tmp_path / "sk.db")))

    def go(self, goal="Please summarise the notes", namespace=None):
        self.asked = 0
        return run(self.loop(namespace).run(goal))


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


# ------------------------------------------------------------------ pause

class TestPause:
    def test_a_paused_system_starts_nothing_and_asks_no_model(self, rig):
        envelope.pause("maintenance window", by="owner")
        result = rig.go()
        assert result["stopped_reason"] == "paused" and "paused by its owner" in result["final_answer"]
        assert rig.asked == 0 and rig.mcp.dispatched == []

    def test_resuming_lets_the_next_episode_run(self, rig):
        envelope.pause("x", by="owner")
        assert rig.go()["stopped_reason"] == "paused"
        assert envelope.resume(by="owner") is True
        assert rig.go()["stopped_reason"] == "llm_finished"

    def test_a_pause_that_arrives_in_the_middle_stops_the_next_tool(self, tmp_path, monkeypatch):
        r = Rig(tmp_path, monkeypatch, [("delentia_read_repo_file", {"relative_path": "a.md"}), ("delentia_read_repo_file", {"relative_path": "b.md"})],
                results={})
        original = r.mcp._result_for

        def pausing(name, args):
            envelope.pause("emergency", by="owner")
            return original(name, args)
        r.mcp._result_for = pausing
        result = r.go()
        assert result["stopped_reason"] == "paused" and [n for n, _ in r.mcp.dispatched] == ["delentia_read_repo_file"]

    def test_the_environment_variable_pauses_too(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.PAUSED_ENV, "1")
        assert rig.go()["stopped_reason"] == "paused"

    def test_an_unreadable_pause_file_means_paused(self, rig):
        path = envelope.pause_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        state = envelope.paused()
        assert state is not None and "unreadable" in state["reason"]
        assert rig.go()["stopped_reason"] == "paused"

    def test_every_pause_and_resume_is_audited(self, rig):
        envelope.pause("why", by="alice", persistence=rig.persistence)
        envelope.resume(by="alice", persistence=rig.persistence)
        with rig.persistence._connect() as conn:
            rows = [(a, json.loads(c)) for a, c in conn.execute("SELECT action, changes FROM audit_trail WHERE entity_type = 'envelope' ORDER BY id")]
        assert [a for a, _ in rows] == ["paused", "resumed"] and rows[0][1]["reason"] == "why"

    def test_a_blocked_start_is_audited_with_the_reason(self, rig):
        envelope.pause("window", by="owner")
        rig.go()
        with rig.persistence._connect() as conn:
            (row,) = conn.execute("SELECT action, changes FROM audit_trail WHERE entity_type = 'governed_loop_envelope'").fetchall()
        assert row[0] == "paused" and "window" in json.loads(row[1])["detail"]

    def test_a_pause_does_not_switch_cron_jobs_off(self):
        assert not ({"paused", "daily_budget_exhausted", "rate_limited", "stuck_repeating"} & FAILING_STOPS)

    def test_the_person_is_told_in_plain_words_on_every_channel(self):
        for reason in ("paused", "daily_budget_exhausted", "rate_limited", "stuck_repeating"):
            assert reply_text_for({"stopped_reason": reason}) == envelope.MESSAGES[reason]


class TestResumeNeedsASignatureWhenThereIsAnApprover:
    @pytest.fixture
    def approver(self, tmp_path, monkeypatch):
        key = tmp_path / "keys" / "owner.pem"
        public = approvals.generate_approver_key(str(key))
        monkeypatch.setenv(approvals.APPROVERS_ENV, public)
        return str(key)

    def test_resuming_without_a_signature_is_refused(self, rig, approver):
        envelope.pause("x", by="owner")
        with pytest.raises(envelope.ResumeRefused, match="signed approval"):
            envelope.resume(by="anyone", persistence=rig.persistence)
        assert envelope.paused() is not None

    def test_a_signed_approval_lifts_it_once(self, rig, approver):
        envelope.pause("x", by="owner")
        pending = envelope.request_resume(rig.persistence)
        store = PendingActionStore(rig.persistence)
        action = store.get(pending["approval_id"])
        signed = approvals.sign_decision(approver, action.approval_id, action.action_sha256, "APPROVED")
        store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])
        assert envelope.resume(by="owner", persistence=rig.persistence, approval_id=action.approval_id) is True
        envelope.pause("again", by="owner")
        with pytest.raises(envelope.ResumeRefused):                      # the same approval cannot be replayed to lift the next pause
            envelope.resume(by="owner", persistence=rig.persistence, approval_id=action.approval_id)

    def test_an_approval_for_something_else_does_not_count(self, rig, approver):
        envelope.pause("x", by="owner")
        other = PendingActionStore(rig.persistence).create("alice", "write a file", "delentia_write_repo_file", {"relative_path": "a"})
        signed = approvals.sign_decision(approver, other.approval_id, other.action_sha256, "APPROVED")
        PendingActionStore(rig.persistence).decide(other.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])
        with pytest.raises(envelope.ResumeRefused, match="not a resume request"):
            envelope.resume(by="owner", persistence=rig.persistence, approval_id=other.approval_id)
        assert envelope.paused() is not None

    def test_an_approval_nobody_signed_does_not_count(self, rig, approver):
        envelope.pause("x", by="owner")
        pending = envelope.request_resume(rig.persistence)
        with pytest.raises(envelope.ResumeRefused):
            envelope.resume(by="owner", persistence=rig.persistence, approval_id=pending["approval_id"])


# ------------------------------------------------------------------ spending and flood

class TestLimits:
    def test_tokens_spent_today_stop_the_next_episode_before_any_model_call(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.DAILY_TOKENS_ENV, "100")
        envelope.record(rig.persistence, "bob", "e1", 0.0, 150, "llm_finished")
        result = rig.go(namespace="alice")
        assert result["stopped_reason"] == "daily_budget_exhausted" and rig.asked == 0 and "spending limit" in result["final_answer"]

    def test_the_window_is_rolling_so_yesterdays_spend_is_forgotten(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.DAILY_TOKENS_ENV, "100")
        envelope.record(rig.persistence, "bob", "e1", 0.0, 150, "llm_finished", now=time.time() - 25 * 3600)
        assert rig.go()["stopped_reason"] == "llm_finished"

    def test_money_limits_count_the_cost_and_a_persons_limit_is_theirs_alone(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.USER_DAILY_USD_ENV, "0.05")
        envelope.record(rig.persistence, "alice", "e1", 0.06, 10, "llm_finished")
        assert rig.go(namespace="alice")["stopped_reason"] == "daily_budget_exhausted"
        assert rig.go(namespace="carol")["stopped_reason"] == "llm_finished"

    def test_the_runtime_wide_limit_applies_to_everyone(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.DAILY_USD_ENV, "0.10")
        envelope.record(rig.persistence, "bob", "e1", 0.11, 10, "llm_finished")
        assert rig.go(namespace="alice")["stopped_reason"] == "daily_budget_exhausted"

    def test_the_episodes_meter_is_capped_at_what_is_left_today(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.DAILY_USD_ENV, "0.05")
        monkeypatch.setenv(envelope.DAILY_TOKENS_ENV, "1000")
        envelope.record(rig.persistence, "bob", "e1", 0.04, 300, "llm_finished")
        meter = rig.loop()._new_meter()
        assert meter.max_cost_usd == pytest.approx(0.01) and meter.max_tokens_total == 700

    def test_the_tighter_of_the_episode_cap_and_the_daily_remainder_wins(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.DAILY_TOKENS_ENV, "100000")
        monkeypatch.setenv("DELENTIA_EPISODE_MAX_TOKENS", "5000")
        assert rig.loop()._new_meter().max_tokens_total == 5000

    def test_no_limits_set_means_no_cap_and_no_stop(self, rig):
        meter = rig.loop()._new_meter()
        assert meter.max_cost_usd is None and meter.max_tokens_total is None
        assert envelope.check_start(rig.persistence, "alice") is None

    def test_an_episode_is_recorded_in_the_ledger_when_it_ends(self, rig):
        rig.go()
        usage = envelope.usage(rig.persistence, "alice")
        assert usage["episodes"] == 1
        with rig.persistence._connect() as conn:
            (stopped,) = conn.execute("SELECT stopped FROM spend_ledger").fetchone()
        assert stopped == "llm_finished"

    def test_too_many_requests_in_an_hour_stop_the_next_and_blocked_attempts_count(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.HOURLY_USER_ENV, "2")
        assert [rig.go()["stopped_reason"] for _ in range(2)] == ["llm_finished", "llm_finished"]
        assert rig.go()["stopped_reason"] == "rate_limited" and rig.asked == 0
        assert rig.go()["stopped_reason"] == "rate_limited"                    # hammering does not lower the count
        assert envelope.usage(rig.persistence, "alice", 3600)["episodes"] == 4
        assert rig.go(namespace="dave")["stopped_reason"] == "llm_finished"     # another person is unaffected

    def test_the_hourly_limit_for_everyone(self, rig, monkeypatch):
        monkeypatch.setenv(envelope.HOURLY_ALL_ENV, "2")
        rig.go(namespace="a")
        rig.go(namespace="b")
        assert rig.go(namespace="c")["stopped_reason"] == "rate_limited"

    def test_an_unreadable_ledger_with_limits_set_stops_the_episode(self, monkeypatch):
        class Broken:
            def _connect(self):
                raise RuntimeError("disk gone")
        monkeypatch.setenv(envelope.DAILY_TOKENS_ENV, "100")
        assert envelope.check_start(Broken(), "alice")["stop"] == "daily_budget_exhausted"
        monkeypatch.delenv(envelope.DAILY_TOKENS_ENV)
        assert envelope.check_start(Broken(), "alice") is None                   # nothing to enforce, nothing to fail closed on

    def test_junk_limit_values_are_ignored_not_crashed_on(self, monkeypatch):
        monkeypatch.setenv(envelope.DAILY_USD_ENV, "lots")
        monkeypatch.setenv(envelope.HOURLY_USER_ENV, "-3")
        assert envelope.limits()["daily_usd"] is None and envelope.limits()["per_hour_per_user"] is None


# ------------------------------------------------------------------ repeating without progress

class TestStuck:
    def test_the_same_call_three_times_stops_the_episode(self, tmp_path, monkeypatch):
        same = ("delentia_read_repo_file", {"relative_path": "a.md"})
        r = Rig(tmp_path, monkeypatch, [same] * 6)
        result = r.go()
        assert result["stopped_reason"] == "stuck_repeating" and "repeating" in result["final_answer"]
        assert len(r.mcp.dispatched) == 2                                        # the third identical request never ran

    def test_different_calls_are_not_stuck(self, tmp_path, monkeypatch):
        r = Rig(tmp_path, monkeypatch, [("delentia_read_repo_file", {"relative_path": f"{i}.md"}) for i in range(4)])
        assert r.go()["stopped_reason"] == "llm_finished" and len(r.mcp.dispatched) == 4

    def test_the_limit_can_be_changed_and_a_stop_is_audited(self, tmp_path, monkeypatch):
        monkeypatch.setenv(envelope.REPEAT_LIMIT_ENV, "5")
        same = ("delentia_read_repo_file", {"relative_path": "a.md"})
        r = Rig(tmp_path, monkeypatch, [same] * 8)
        assert r.go()["stopped_reason"] == "stuck_repeating" and len(r.mcp.dispatched) == 4
        with r.persistence._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE entity_type = 'governed_loop_envelope' AND action = 'stuck_repeating'").fetchone()[0] == 1

    def test_the_count_starts_again_for_each_episode(self, tmp_path, monkeypatch):
        same = ("delentia_read_repo_file", {"relative_path": "a.md"})
        r = Rig(tmp_path, monkeypatch, [same, same])
        loop = r.loop()
        assert run(loop.run("read it twice")) ["stopped_reason"] == "llm_finished"
        r.asked = 0
        assert run(loop.run("read it twice again"))["stopped_reason"] == "llm_finished"


# ------------------------------------------------------------------ the CLI and the Desk

class TestSurfaces:
    @pytest.fixture
    def db(self, tmp_path):
        return str(tmp_path / "cli.db")

    def test_the_cli_pauses_shows_and_resumes(self, db):
        runner = CliRunner()
        assert runner.invoke(cli, ["pause", "--reason", "deploying", "--db", db]).exit_code == 0
        shown = runner.invoke(cli, ["limits", "--db", db]).output
        assert "PAUSED" in shown and "deploying" in shown and "no spending or flood limit" in shown
        assert "resumed" in runner.invoke(cli, ["resume", "--db", db]).output
        assert "running (not paused)" in runner.invoke(cli, ["limits", "--db", db]).output

    def test_the_cli_resume_with_an_approver_prints_what_to_sign_and_exits_2(self, db, tmp_path, monkeypatch):
        public = approvals.generate_approver_key(str(tmp_path / "k.pem"))
        monkeypatch.setenv(approvals.APPROVERS_ENV, public)
        runner = CliRunner()
        runner.invoke(cli, ["pause", "--db", db])
        out = runner.invoke(cli, ["resume", "--db", db])
        assert out.exit_code == 2 and "Approval id" in out.output and envelope.paused() is not None

    def test_the_desk_endpoints(self, tmp_path, monkeypatch):
        persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))

        class K:
            _persistence = persistence
        monkeypatch.setattr(desk_api, "_kernel", lambda: K())
        with TestClient(create_app()) as client:
            assert client.get("/v1/desk/envelope").json()["paused"] is None
            assert client.post("/v1/desk/envelope/pause", json={"reason": "from the Desk"}).json()["paused"]["reason"] == "from the Desk"
            assert client.get("/v1/desk/envelope").json()["paused"]["reason"] == "from the Desk"
            assert client.post("/v1/desk/envelope/resume", json={}).json() == {"resumed": True}
            assert client.get("/v1/desk/envelope").json()["paused"] is None

    def test_the_desk_resume_answers_202_with_the_action_to_sign_when_an_approver_exists(self, tmp_path, monkeypatch):
        persistence = ControlPlanePersistence(db_path=str(tmp_path / "desk.db"))

        class K:
            _persistence = persistence
        monkeypatch.setattr(desk_api, "_kernel", lambda: K())
        monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(tmp_path / "k.pem")))
        with TestClient(create_app()) as client:
            client.post("/v1/desk/envelope/pause", json={})
            answer = client.post("/v1/desk/envelope/resume", json={})
            assert answer.status_code == 202 and answer.json()["pending_signature"] and "approval_id" in answer.json()
            assert envelope.paused() is not None
            assert client.post("/v1/desk/envelope/resume", json={"approval_id": "nope"}).status_code == 403

"""
Round 60 (D2): the owner is told when the agent needs them.

A real HTTP server on loopback plays Telegram's Bot API and records every message; the approvals store, cron service, scheduler and governed loop are real. What is checked: who gets
a message, what it contains (and what it must NOT contain), how often, and that a broken channel never stops anything else.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import measure_injection_defence as mid
import rct_control_plane.autonomous_loop as al
from rct_control_plane import approvals, envelope, owner_notify
from rct_control_plane.approvals import PendingActionStore
from rct_control_plane.autonomous_scheduler import AutonomousScheduler
from rct_control_plane.cron_jobs import CronService
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from test_governed_autonomous_loop_real import _FakeKernel

run = asyncio.run
OWNER = "424242"


class FakeTelegram(BaseHTTPRequestHandler):
    messages = []
    status = 200

    def do_POST(self):                                       # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/sendMessage") and FakeTelegram.status == 200:
            FakeTelegram.messages.append(body)
        self.send_response(FakeTelegram.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


@pytest.fixture(autouse=True)
def telegram(monkeypatch, tmp_path):
    FakeTelegram.messages, FakeTelegram.status = [], 200
    server = HTTPServer(("127.0.0.1", 0), FakeTelegram)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("DELENTIA_TELEGRAM_API_BASE", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TESTTOKEN")
    monkeypatch.setenv("DELENTIA_TELEGRAM_ALLOWED_SENDERS", OWNER)
    monkeypatch.setenv(owner_notify.TARGETS_ENV, f"telegram:{OWNER}")
    monkeypatch.delenv(owner_notify.PER_HOUR_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    for name in (envelope.DAILY_TOKENS_ENV, envelope.HOURLY_USER_ENV):
        monkeypatch.delenv(name, raising=False)
    from rct_control_plane import cron_jobs
    monkeypatch.setattr(cron_jobs, "_GATEWAY_RESOLVER", None)
    owner_notify.reset_for_tests()
    yield server
    owner_notify.reset_for_tests()
    server.shutdown()


@pytest.fixture
def persistence(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "n.db"))


def flush():
    for t in list(owner_notify._threads):
        t.join(timeout=15)


# ------------------------------------------------------------------ who may be told

class TestTargets:
    def test_a_target_must_also_be_on_the_channels_allowlist_by_name(self, monkeypatch):
        monkeypatch.setenv(owner_notify.TARGETS_ENV, f"telegram:{OWNER},telegram:999,signal:+6611,email:me@x.example")
        assert owner_notify.targets() == [{"channel": "telegram", "to": OWNER}]
        why = {(d["channel"], d["to"]): d["why"] for d in owner_notify.status()["dropped"]}
        assert "allowlist" in why[("telegram", "999")] and "not supported" in why[("email", "me@x.example")]

    def test_a_star_allowlist_does_not_make_anyone_a_target(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_TELEGRAM_ALLOWED_SENDERS", "*")
        assert owner_notify.targets() == []

    def test_nothing_configured_sends_nothing(self, monkeypatch):
        monkeypatch.delenv(owner_notify.TARGETS_ENV)
        assert owner_notify.notify("x", "hello", wait=True) is False and FakeTelegram.messages == []


# ------------------------------------------------------------------ what is sent

class TestMessages:
    def test_a_request_waiting_for_a_signature_reaches_the_owner_without_its_arguments_or_goal(self, persistence):
        action = PendingActionStore(persistence).create("alice", "SECRET GOAL: send the payroll", "delentia_write_repo_file",
                                                        {"relative_path": "SECRET-ARG.md", "content_text": "x"}, reason="needs human approval", policy_rule="taint")
        flush()
        assert len(FakeTelegram.messages) == 1
        sent = FakeTelegram.messages[0]
        assert sent["chat_id"] == int(OWNER)
        text = sent["text"]
        assert "delentia_write_repo_file" in text and action.approval_id in text and "alice" in text and "rule taint" in text
        assert "SECRET" not in text and "payroll" not in text                       # neither the goal nor the arguments leave

    def test_a_pairing_request_says_which_channel_and_the_code_only(self, persistence):
        PendingActionStore(persistence).create("pairing", "Allow telegram sender SENDER-ID-XYZ to use this agent", "pairing_grant", {"channel": "telegram", "sender_id": "SENDER-ID-XYZ"})
        flush()
        text = FakeTelegram.messages[0]["text"]
        assert "telegram" in text and "pairing code" in text and "SENDER-ID-XYZ" not in text       # (a hex approval code could contain digits like 77, so the marker is not numeric)

    def test_multi_signature_needs_are_stated(self, persistence):
        PendingActionStore(persistence).create("alice", "g", "delentia_run_sandboxed_command", {"command": "x"}, required_signatures=2)
        flush()
        assert "2 signatures needed" in FakeTelegram.messages[0]["text"]

    def test_the_owners_own_resume_request_is_not_announced_back_to_them(self, persistence):
        PendingActionStore(persistence).create("envelope", "Resume the agent after a pause", "envelope_resume", {})
        flush()
        assert FakeTelegram.messages == []

    def test_the_text_is_bounded(self):
        owner_notify.notify("x", "a" * 5000, key="long", wait=True)
        assert len(FakeTelegram.messages[0]["text"]) <= owner_notify.MAX_TEXT


# ------------------------------------------------------------------ how often

class TestRate:
    def test_the_same_event_is_sent_once_an_hour(self):
        assert owner_notify.notify("x", "one", key="same", wait=True) is True
        assert owner_notify.notify("x", "one again", key="same", wait=True) is False
        assert len(FakeTelegram.messages) == 1

    def test_over_the_hourly_count_messages_are_held_back_and_counted_in_the_next_one(self, monkeypatch):
        monkeypatch.setenv(owner_notify.PER_HOUR_ENV, "2")
        results = [owner_notify.notify("x", f"event {i}", key=f"k{i}", wait=True) for i in range(5)]
        assert results == [True, True, False, False, False] and len(FakeTelegram.messages) == 2
        assert owner_notify.status()["held_back_since_last_message"] == 3
        later = time.time() + 3601
        monkeypatch.setattr(owner_notify.time, "time", lambda: later)
        assert owner_notify.notify("x", "after the hour", key="k-late", wait=True) is True
        assert "+3 earlier alerts not sent" in FakeTelegram.messages[-1]["text"]
        assert owner_notify.status()["held_back_since_last_message"] == 0

    def test_held_back_messages_are_audited(self, monkeypatch, persistence):
        monkeypatch.setenv(owner_notify.PER_HOUR_ENV, "1")
        owner_notify.notify("x", "one", key="a", persistence=persistence, wait=True)
        owner_notify.notify("x", "two", key="b", persistence=persistence, wait=True)
        with persistence._connect() as conn:
            actions = [r[0] for r in conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'owner_notify' ORDER BY id")]
        assert actions == ["sent", "held_back"]


# ------------------------------------------------------------------ a broken channel breaks nothing

class TestFailures:
    def test_a_dead_channel_is_audited_and_the_approval_is_still_created(self, persistence):
        FakeTelegram.status = 500
        action = PendingActionStore(persistence).create("alice", "g", "delentia_write_repo_file", {"relative_path": "a"})
        flush()
        assert PendingActionStore(persistence).get(action.approval_id).status == "PENDING"
        with persistence._connect() as conn:
            row = conn.execute("SELECT action, changes FROM audit_trail WHERE entity_type = 'owner_notify'").fetchone()
        assert row[0] == "failed" and json.loads(row[1])["failures"]

    def test_a_channel_with_no_token_fails_quietly(self, monkeypatch, persistence):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
        assert owner_notify.notify("x", "hi", key="n", persistence=persistence, wait=True) is True
        with persistence._connect() as conn:
            assert conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'owner_notify'").fetchone()[0] == "failed"

    def test_the_audit_row_holds_a_hash_of_the_text_not_the_text(self, persistence):
        owner_notify.notify("x", "private words here", key="h", persistence=persistence, wait=True)
        with persistence._connect() as conn:
            changes = conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'owner_notify'").fetchone()[0]
        assert "private words" not in changes and "text_sha256" in changes


# ------------------------------------------------------------------ the other events

class TestOtherEvents:
    def test_a_cron_job_that_fails_and_one_that_is_switched_off(self, persistence, tmp_path, monkeypatch):
        service = CronService(persistence)
        job = service.create("alice", "check the build", "every day at 9:00", name="build check")
        monkeypatch.setattr(al, "decide_next_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model down")))
        for _ in range(3):
            run(service.run_job(_FakeKernel(), service.get(job["id"]), deliver=None))
        flush()
        texts = [m["text"] for m in FakeTelegram.messages]
        assert any("build check" in t and "failed" in t for t in texts) or any("switched off" in t for t in texts)
        assert any("switched off" in t for t in texts)

    def test_a_daemon_task_that_fails(self, persistence):
        class K:
            _persistence = persistence
        scheduler = AutonomousScheduler(kernel=K())

        def boom():
            raise RuntimeError("audit chain broken at seq 12: row edited")
        task_id = scheduler.register_task(name="audit_chain_verify_test", description="x", interval_seconds=60, handler=boom).task_id
        result = run(scheduler.trigger_task_async(task_id))
        flush()
        assert result["status"] == "FAILED"
        assert any("audit chain broken at seq 12" in m["text"] for m in FakeTelegram.messages)

    def test_a_spending_limit_reached_is_announced_once(self, tmp_path, monkeypatch, persistence):
        monkeypatch.setenv(envelope.DAILY_TOKENS_ENV, "10")
        envelope.record(persistence, "bob", "e", 0.0, 50, "llm_finished")
        mcp = mid.RecordingMCP(lambda n, a: "{}")

        async def model(*a, **k):
            return {"action": "finish", "reasoning": "x", "final_answer": "ok", "tool_name": None, "tool_args": {}}
        monkeypatch.setattr(al, "decide_next_action", model)
        for _ in range(3):
            loop = GovernedAutonomousLoop(mcp_server=mcp, persistence=persistence, kernel=_FakeKernel(), max_iterations=3, namespace="alice", route=False,
                                          skill_library=SkillLibrary(db_path=str(tmp_path / "sk.db")))
            assert run(loop.run("hello there"))["stopped_reason"] == "daily_budget_exhausted"
        flush()
        limit_messages = [m for m in FakeTelegram.messages if "limit" in m["text"]]
        assert len(limit_messages) == 1

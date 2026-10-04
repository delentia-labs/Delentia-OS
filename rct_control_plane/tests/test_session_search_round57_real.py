"""
Round 57: searching past episodes (session_search.py) with real SQLite FTS5 (trigram), real governed episodes that write the log, the real MCP tool,
the real Desk endpoint and CLI. Per-person isolation is the point of half of these.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import time

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import rct_control_plane.autonomous_loop as autonomous_loop_module
import rct_control_plane.desk_api as desk_api
import rct_control_plane.mcp_server as mcp_server
from rct_control_plane.api import create_app
from rct_control_plane.cli import cli
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop, EXTERNAL_CONTENT_TOOLS
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.session_search import SessionLog
from test_governed_autonomous_loop_real import _FakeMCP, _loop


@pytest.fixture
def log(tmp_path):
    return SessionLog(ControlPlanePersistence(db_path=str(tmp_path / "s.db")))


def test_fts5_with_the_trigram_tokenizer_is_available_here(log):
    assert log.fts is True


def test_english_phrases_and_fragments_are_found_newest_first_with_a_highlighted_match(log):
    log.record("alice", "Check the nightly backup job", "The nightly backup job ran at 02:00 and finished in 41 seconds.", "llm_finished", now=1000)
    log.record("alice", "Summarise the release notes", "Version 2.3 fixes the login bug.", "llm_finished", now=2000)
    log.record("alice", "Why did the backup fail on Friday?", "The backup volume was full.", "llm_finished", now=3000)
    hits = log.search("alice", "backup")
    assert [h["goal"] for h in hits] == ["Why did the backup fail on Friday?", "Check the nightly backup job"]
    assert "[backup]" in hits[0]["match"] or "[backup]" in hits[1]["match"]
    assert [h["goal"] for h in log.search("alice", "login bug")] == ["Summarise the release notes"]
    assert [h["goal"] for h in log.search("alice", "ightly back")] == ["Check the nightly backup job"]          # a fragment inside words


def test_thai_text_is_searchable_without_spaces_between_words(log):
    log.record("alice", "ตรวจสอบ backup ของระบบทุกวันจันทร์", "ระบบสำรองข้อมูลทำงานปกติ ไม่พบข้อผิดพลาด", "llm_finished", now=1000)
    log.record("alice", "สรุปรายงานประจำสัปดาห์", "ยอดขายเพิ่มขึ้นร้อยละห้า", "llm_finished", now=2000)
    assert [h["goal"] for h in log.search("alice", "สำรองข้อมูล")] == ["ตรวจสอบ backup ของระบบทุกวันจันทร์"]        # found in the ANSWER
    assert [h["goal"] for h in log.search("alice", "ยอดขาย")] == ["สรุปรายงานประจำสัปดาห์"]
    assert [h["goal"] for h in log.search("alice", "backup ของระบบ")] == ["ตรวจสอบ backup ของระบบทุกวันจันทร์"]  # mixed Thai and English
    assert log.search("alice", "ไม่มีคำนี้เลย") == []


def test_a_person_only_ever_sees_their_own_episodes(log):
    log.record("alice", "Alice's private plan: sell the Chiang Mai shop", "Noted.", "llm_finished")
    log.record("telegram-777", "What is the weather?", "Sunny.", "llm_finished")
    assert [h["goal"] for h in log.search("telegram-777", "shop")] == []
    assert [h["goal"] for h in log.search("telegram-777", "Chiang Mai")] == []
    assert [h["goal"] for h in log.search("alice", "Chiang Mai")] == ["Alice's private plan: sell the Chiang Mai shop"]
    assert [h["goal"] for h in log.search("telegram-777", "")] == ["What is the weather?"]            # an empty query lists only my own latest


def test_short_queries_fall_back_to_a_substring_match_and_odd_characters_are_safe(log):
    log.record("alice", "Fix the AB-12 bug", "done", "llm_finished")
    assert [h["goal"] for h in log.search("alice", "AB")] == ["Fix the AB-12 bug"]
    for hostile in ['"', "'; DROP TABLE episode_log; --", "%", "_", "\\", 'a" OR "b', "*", "NEAR(a b)", "a" * 500]:
        log.search("alice", hostile)                                                                  # never raises
    assert log.count("alice") == 1


def test_stored_text_is_capped_and_an_episode_without_an_answer_is_kept(log):
    log.record("alice", "g" * 5000, "a" * 9000, "max_iterations")
    log.record("alice", "no answer", None, "pending_approval")
    rows = {h["goal"][:9]: h for h in log.search("alice", "")}
    assert len(rows["no answer"]["answer"]) == 0 and rows["no answer"]["stopped_reason"] == "pending_approval"
    with log._p._connect() as conn:
        goal_len, answer_len = conn.execute("SELECT LENGTH(goal), LENGTH(answer) FROM episode_log WHERE goal LIKE 'ggg%'").fetchone()
    assert goal_len == 2000 and answer_len == 4000


def test_a_real_governed_episode_writes_its_goal_answer_and_tools_to_the_log(tmp_path, monkeypatch):
    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        if not history:
            return {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "notes"}, "reasoning": "look"}
        return {"action": "finish", "reasoning": "done", "final_answer": "Your release manager is Somchai.", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "alice", mcp=_FakeMCP())
    asyncio.run(loop.run("Who is the release manager?"))
    hits = SessionLog(loop._persistence).search("alice", "release manager")
    assert len(hits) == 1 and hits[0]["answer"] == "Your release manager is Somchai." and hits[0]["tools"] == ["delentia_recall"]
    assert hits[0]["stopped_reason"] == "llm_finished"
    assert SessionLog(loop._persistence).search("bob", "release manager") == []


def test_the_agents_tool_is_pinned_to_the_callers_own_history_and_its_results_are_screened(tmp_path, monkeypatch):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "m.db"))
    monkeypatch.setattr(mcp_server, "_kernel", type("K", (), {"_persistence": persistence})())
    SessionLog(persistence).record("alice", "alice's secret goal about saffron", "answer", "llm_finished")
    SessionLog(persistence).record("telegram-5", "telegram user's goal about tea", "answer", "llm_finished")
    assert "delentia_search_sessions" in GovernedAutonomousLoop.MEMORY_TOOLS and "delentia_search_sessions" in EXTERNAL_CONTENT_TOOLS
    loop = GovernedAutonomousLoop.__new__(GovernedAutonomousLoop)
    loop.namespace = "telegram-5"
    args = loop._scope_tool_args("delentia_search_sessions", {"query": "saffron", "namespace": "alice"})       # the model tried to name alice
    assert args["namespace"] == "telegram-5"
    got = asyncio.run(mcp_server.delentia_search_sessions(**args))
    assert got["episodes"] == []
    mine = asyncio.run(mcp_server.delentia_search_sessions("tea", namespace="telegram-5"))
    assert [e["goal"] for e in mine["episodes"]] == ["telegram user's goal about tea"]


def test_the_desk_and_the_cli_search_the_signed_in_persons_history(tmp_path, monkeypatch):
    from rct_control_plane.data_home import agentic_db_path
    persistence = ControlPlanePersistence(db_path=agentic_db_path())
    SessionLog(persistence).record("desk", "Check the nightly backup job", "ran fine", "llm_finished", now=time.time() - 60)
    SessionLog(persistence).record("someone-else", "Check the nightly backup job of mine", "ran", "llm_finished")
    monkeypatch.setattr(desk_api, "_kernel", lambda: type("K", (), {"_persistence": persistence})())
    with TestClient(create_app()) as client:
        found = client.get("/v1/desk/sessions/search", params={"q": "nightly backup"}).json()
        assert found["owner"] == "desk" and len(found["episodes"]) == 1 and found["episodes"][0]["goal"] == "Check the nightly backup job" and found["fts"] is True
        assert client.get("/v1/desk/sessions/search", params={"q": "x" * 300}).status_code == 422
    out = CliRunner().invoke(cli, ["sessions", "search", "nightly backup"]).output
    assert "Check the nightly backup job" in out and "mine" not in out and "ran fine" in out

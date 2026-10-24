"""RCT-7 in numbers (rct7_stats.py): what the stop-and-ask really did, from real episodes and the real question store. Real loop, real SQLite, the CLI and the Desk route; the model is scripted."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import rct_control_plane.autonomous_loop as autonomous_loop
from rct_control_plane import desk_api, mcp_server, rct7_stats
from rct_control_plane.api import create_app
from rct_control_plane.cli import cli
from rct_control_plane.clarifications import ClarificationStore
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeMCP, _loop

ENGLISH = "All of the tests passed and no errors were found in the system, and the time taken fell by about half, so this setting is recommended."
GOAL_TH = "สรุปผลการทดสอบเป็นภาษาไทย"


def finish(text):
    return {"action": "finish", "reasoning": "done", "final_answer": text, "tool_name": None, "tool_args": {}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("DELENTIA_ASK_AND_WAIT", raising=False)
    monkeypatch.delenv("DELENTIA_RCT7_JUDGE", raising=False)

    def episode(name, goal, answer, interactive=True, loop=None):
        script = [finish(answer)]

        async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
            return dict(script.pop(0) if script else finish("done"))
        monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
        the_loop = loop or _loop(tmp_path, name, mcp=_FakeMCP())
        the_loop._interactive = interactive
        return the_loop, asyncio.run(the_loop.run(goal))
    episode.root = tmp_path
    return episode


def test_an_empty_database_gives_zeros_and_says_there_is_not_enough_use_yet(tmp_path):
    stats = rct7_stats.collect(ControlPlanePersistence(str(tmp_path / "e.db")))
    assert stats["episodes"] == 0 and stats["total"]["asked"] == 0 and stats["kept_or_cancelled_share"] is None and "not enough use" in stats["hint"]
    assert stats["asked_per_100_episodes"] is None


def test_the_numbers_follow_what_the_person_did_with_each_question(world):
    loop, first = world("p1", GOAL_TH, ENGLISH)                                              # asked, then answered and sent again
    store = ClarificationStore(loop._persistence)
    store.answer(first["clarification_id"], "p1", "ทำใหม่เป็นภาษาไทยทั้งหมด")
    world("p1", GOAL_TH, "ผลการทดสอบทั้งหมดผ่านแล้ว ไม่พบข้อผิดพลาดในระบบ และเวลาที่ใช้ลดลงจากเดิมประมาณครึ่งหนึ่ง จึงแนะนำให้ใช้ค่านี้ต่อไป", loop=loop)
    _, second = world("p1", "สรุปผลการทดสอบอีกครั้งเป็นภาษาไทย", ENGLISH, loop=loop)         # asked, then kept as it was
    store.accept(second["clarification_id"], "p1")
    _, third = world("p1", "สรุปรายงานเป็นภาษาไทย", ENGLISH, loop=loop)                       # asked, then dismissed
    store.cancel(third["clarification_id"], "p1")
    world("p1", "สรุปบันทึกเป็นภาษาไทย", ENGLISH, loop=loop)                                  # asked, still waiting
    world("p1", "What is 2+2?", "4", loop=loop)                                              # no question

    stats = rct7_stats.collect(loop._persistence)
    t = stats["total"]
    assert (t["asked"], t["answered"], t["kept"], t["cancelled"], t["waiting"]) == (4, 1, 1, 1, 1)
    assert stats["episodes"] == 6 and stats["stopped_to_ask"] == 4 and stats["asked_per_100_episodes"] == pytest.approx(66.7, abs=0.1)
    assert stats["kept_or_cancelled_share"] == pytest.approx(2 / 3, abs=0.001)
    assert stats["by_kind"]["mismatch/language"]["asked"] == 4
    assert "not enough use" in stats["hint"]                                                 # 3 resolved is not enough to say anything


def test_with_enough_use_the_hint_follows_the_dismissals(tmp_path):
    persistence = ControlPlanePersistence(str(tmp_path / "h.db"))
    store = ClarificationStore(persistence)

    def many(n_answered, n_cancelled, ns):
        for i in range(n_answered):
            q = store.create(ns, "mismatch", "language", f"q{i}", original_goal=f"g{i}")
            store.answer(q.clarification_id, ns, "ok")
        for i in range(n_cancelled):
            q = store.create(ns, "before_act", "model_unclear", f"c{i}", original_goal=f"c{i}")
            store.cancel(q.clarification_id, ns)
    many(22, 2, "good")
    many(4, 20, "noisy")
    many(12, 12, "mixed")
    assert "Keep the default" in rct7_stats.collect(persistence, namespace="good")["hint"]
    assert "asking for nothing" in rct7_stats.collect(persistence, namespace="noisy")["hint"]
    assert "mixed" in rct7_stats.collect(persistence, namespace="mixed")["hint"]
    assert rct7_stats.collect(persistence, namespace="noisy")["by_kind"]["before_act/model_unclear"]["kept_or_cancelled_share"] == 1.0


def test_old_questions_fall_out_of_the_window(tmp_path):
    persistence = ControlPlanePersistence(str(tmp_path / "w.db"))
    store = ClarificationStore(persistence)
    q = store.create("p", "mismatch", "language", "q", original_goal="g")
    with persistence._connect() as conn:
        conn.execute("UPDATE clarifications SET created_at = created_at - ? WHERE clarification_id = ?", (40 * 86400, q.clarification_id))
    assert rct7_stats.collect(persistence, days=14)["total"]["asked"] == 0
    assert rct7_stats.collect(persistence, days=60)["total"]["asked"] == 1


def test_the_cli_prints_the_table_and_json(world):
    loop, first = world("cli", GOAL_TH, ENGLISH)
    db = loop._persistence.db_path
    out = CliRunner().invoke(cli, ["clarify", "stats", "--db", db])
    assert out.exit_code == 0 and "RCT-7 stop-and-ask" in out.output and "mismatch/language" in out.output
    as_json = CliRunner().invoke(cli, ["clarify", "stats", "--db", db, "--json"])
    assert json.loads(as_json.output)["total"]["asked"] == 1


def test_the_desk_route_returns_the_same_numbers(world, monkeypatch):
    loop, _ = world("desk", GOAL_TH, ENGLISH)

    class K:
        _persistence = loop._persistence
    monkeypatch.setattr(desk_api, "_kernel", lambda: K())
    with TestClient(create_app()) as client:
        body = client.get("/v1/desk/rct7/stats?days=7").json()
    assert body["total"]["asked"] == 1 and body["days"] == 7

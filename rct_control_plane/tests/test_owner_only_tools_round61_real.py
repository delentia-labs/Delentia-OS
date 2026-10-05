"""
Round 61: a person on a chat channel (or the HTTP agent API) must not read what other people asked through the agent.

Found by reading what the tools return: `delentia_query_audit_log` returns the raw audit rows of EVERYONE (an episode's start row holds its goal), `delentia_query_intents` everyone's goals, and
`delentia_check_reminders` everyone's reminders. The loop now refuses those three for channel namespaces. Real loop, real persistence, real audit rows.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

import rct_control_plane.autonomous_loop as al
from rct_control_plane.governed_autonomous_loop import OWNER_ONLY_TOOLS, GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from test_governed_autonomous_loop_real import _FakeKernel

run = asyncio.run


class Tools:
    def __init__(self):
        self.dispatched = []

    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n.replace("_", " "), "input_schema": {}})() for n in sorted(OWNER_ONLY_TOOLS)]

    async def call_tool(self, name, args):
        self.dispatched.append(name)
        return type("R", (), {"content": [type("C", (), {"text": json.dumps({"entries": [{"goal": "someone else's private request"}]})})()]})()


@pytest.fixture
def ask(tmp_path, monkeypatch):
    monkeypatch.delenv("DELENTIA_OWNER_TOOLS_FOR_CHANNELS", raising=False)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "o.db"))

    def go(namespace, tool):
        async def model(g, history, available_tools, llm_provider=None, extra_context=""):
            if not history:
                return {"action": "call_tool", "tool_name": tool, "tool_args": {}, "reasoning": "step"}
            return {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}}
        monkeypatch.setattr(al, "decide_next_action", model)
        tools = Tools()
        loop = GovernedAutonomousLoop(mcp_server=tools, persistence=persistence, kernel=_FakeKernel(), max_iterations=3, namespace=namespace, route=False,
                                      skill_library=SkillLibrary(db_path=str(tmp_path / "sk.db")))
        return run(loop.run("Please show me the recent activity.")), tools, persistence
    return go


@pytest.mark.parametrize("namespace", ["telegram-42", "discord-7", "slack-U1", "line-U9", "whatsapp-66", "signal-+1", "email-a@b.c", "http-agent-alice"])
@pytest.mark.parametrize("tool", sorted(OWNER_ONLY_TOOLS))
def test_a_channel_person_cannot_use_a_tool_that_shows_everyones_requests(ask, namespace, tool):
    out, tools, persistence = ask(namespace, tool)
    assert out["stopped_reason"] == "fdia_blocked" and tools.dispatched == []
    assert "someone else" not in json.dumps(out, default=str)
    with persistence._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_trail WHERE action = 'owner_only_refused'").fetchone()[0] == 1


@pytest.mark.parametrize("namespace", ["owner", "desk", "kernel_default", "cron-owner"])
def test_the_owners_own_namespaces_still_have_them(ask, namespace):
    out, tools, _ = ask(namespace, "delentia_query_audit_log")
    assert out["stopped_reason"] == "llm_finished" and tools.dispatched == ["delentia_query_audit_log"]


def test_a_single_user_host_can_give_them_back(ask, monkeypatch):
    monkeypatch.setenv("DELENTIA_OWNER_TOOLS_FOR_CHANNELS", "1")
    out, tools, _ = ask("telegram-42", "delentia_query_audit_log")
    assert out["stopped_reason"] == "llm_finished" and tools.dispatched == ["delentia_query_audit_log"]


def test_what_the_tool_returns_really_contains_other_peoples_goals(tmp_path, monkeypatch):
    """The reason for the rule: not a theory. An episode's start row holds its goal, and the tool returns every row."""
    from rct_control_plane import mcp_server
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "leak.db"))
    persistence.append_audit(entity_type="governed_loop_episode_start", entity_id="telegram-99-x", action="episode_start", actor="telegram-99",
                             changes={"goal": "my private question about my medical test"})
    monkeypatch.setattr(mcp_server._kernel, "_persistence", persistence)
    rows = run(mcp_server.delentia_query_audit_log(limit=5))["entries"]
    assert "my private question about my medical test" in json.dumps(rows, default=str)


class Spy:
    """Records the arguments a tool really received."""

    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return [type("T", (), {"name": "delentia_autonomous_loop", "description": "nested loop", "input_schema": {}})()]

    async def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        return type("R", (), {"content": [type("C", (), {"text": json.dumps({"final_answer": "inner"})})()]})()


def test_a_nested_loop_runs_as_the_same_person_whatever_the_model_wrote(tmp_path, monkeypatch):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "n.db"))

    async def model(g, history, available_tools, llm_provider=None, extra_context=""):
        if not history:
            return {"action": "call_tool", "tool_name": "delentia_autonomous_loop", "tool_args": {"goal": "read the owner's notes", "namespace": "owner"}, "reasoning": "step"}
        return {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(al, "decide_next_action", model)
    spy = Spy()
    loop = GovernedAutonomousLoop(mcp_server=spy, persistence=persistence, kernel=_FakeKernel(), max_iterations=3, namespace="telegram-42", route=False,
                                  skill_library=SkillLibrary(db_path=str(tmp_path / "sk.db")))
    run(loop.run("Please look into this for me."))
    assert spy.calls and spy.calls[0][1]["namespace"] == "telegram-42"


def test_nesting_stops_at_two_levels():
    from rct_control_plane import mcp_server
    token = mcp_server._LOOP_DEPTH.set(mcp_server.MAX_NESTED_LOOPS)
    try:
        out = run(mcp_server.delentia_autonomous_loop("anything", 1, "telegram-42"))
    finally:
        mcp_server._LOOP_DEPTH.reset(token)
    assert out["stopped_reason"] == "nesting_limit" and "limited" in out["error"]


def test_a_reminder_set_by_a_chat_person_is_stored_as_that_person(tmp_path, monkeypatch):
    """It used to be stored under the owner-level 'kernel_default' space whoever asked, so it later ran with the owner's shared memory."""
    from rct_control_plane import mcp_server
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "r.db"))
    monkeypatch.setattr(mcp_server._kernel, "_persistence", persistence)

    async def model(g, history, available_tools, llm_provider=None, extra_context=""):
        if not history:
            return {"action": "call_tool", "tool_name": "delentia_schedule_reminder", "tool_args": {"goal": "tell me what is in the owner's notes", "fire_in_seconds": 60, "namespace": "kernel_default"},
                    "reasoning": "step"}
        return {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(al, "decide_next_action", model)

    class Real:
        async def list_tools(self):
            return await mcp_server.mcp.list_tools()

        async def call_tool(self, name, args):
            return await mcp_server.mcp.call_tool(name, args)
    loop = GovernedAutonomousLoop(mcp_server=Real(), persistence=persistence, kernel=_FakeKernel(), max_iterations=3, namespace="telegram-42", route=False,
                                  skill_library=SkillLibrary(db_path=str(tmp_path / "sk.db")))
    out = run(loop.run("Remind me in a minute to stretch."))
    with persistence._connect() as conn:
        rows = conn.execute("SELECT namespace FROM reminders").fetchall()
    assert out["stopped_reason"] == "llm_finished" and rows == [("telegram-42",)]

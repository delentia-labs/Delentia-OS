"""RCT-7 R5 in the middle of an episode: the tool `delentia_ask_user`. Real GovernedAutonomousLoop, real SQLite, real ClarificationStore; the scripted model is the only fake.

Criteria written first (research/rct7_round98_criteria.md, section A): present only where a person can answer, once per episode, the call ends the episode at once, the answer is added to the request
and a chain of questions keeps every earlier answer, a person who keeps dismissing model questions is not asked.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop
from rct_control_plane import mcp_server
from rct_control_plane.clarifications import ClarificationStore
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeMCP, _FakeToolResult, _loop

NOTE = "Nobody can answer a question here"


def finish(text):
    return {"action": "finish", "reasoning": "done", "final_answer": text, "tool_name": None, "tool_args": {}}


def ask(question, why=""):
    return {"action": "call_tool", "reasoning": "I need to know", "final_answer": None, "tool_name": "delentia_ask_user", "tool_args": {"question": question, "why": why}}


def read(path):
    return {"action": "call_tool", "reasoning": "read", "final_answer": None, "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": path}}


class AskMCP(_FakeMCP):
    """A tool server that lists the question tool and answers it the way the real tool does when the loop lets it run."""

    async def list_tools(self):
        return [type("T", (), {"name": n, "description": d, "input_schema": {}})() for n, d in (("delentia_ask_user", "ask the person one question"), ("delentia_read_repo_file", "read a file"))]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        if name == "delentia_ask_user":
            return _FakeToolResult(json.dumps({"asked": False, "note": NOTE + ", or one was already asked in this episode. State your assumption."}))
        return _FakeToolResult(json.dumps({"path": args.get("relative_path"), "content_text": "x"}))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("DELENTIA_ASK_AND_WAIT", raising=False)
    monkeypatch.delenv("DELENTIA_RCT7_JUDGE", raising=False)
    seen = []

    def go(goal, decisions, name="ask98", interactive=True, loop=None, **loop_kwargs):
        script = list(decisions)

        async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
            seen.append({"goal": goal_, "tools": [t["name"] for t in available_tools]})
            return dict(script.pop(0) if script else finish("done"))
        monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
        mcp = AskMCP()
        the_loop = loop or _loop(tmp_path, name, mcp=mcp, **loop_kwargs)
        the_loop._interactive = interactive
        return the_loop, asyncio.run(the_loop.run(goal)), mcp
    go.seen = seen
    go.root = tmp_path
    return go


def test_the_question_ends_the_episode_at_once_and_nothing_runs_after_it(env):
    (env.root / "a.txt").write_text("x", encoding="utf-8")
    loop, result, mcp = env("Read a.txt and tell me the value", [ask("Which value: the first or the second?", "the file has two"), read("a.txt"), finish("never")])
    assert result["stopped_reason"] == "needs_clarification" and len(env.seen) == 1               # the model was asked once; nothing came after the question
    assert [n for n, _ in mcp.dispatched] == []                                                     # not even the question tool was dispatched
    assert "The agent (a model) asks before going on" in result["clarification_question"] and "Which value: the first or the second?" in result["clarification_question"]
    pending = ClarificationStore(loop._persistence).list(namespace="ask98", status="PENDING")
    assert len(pending) == 1 and pending[0].kind == "before_act" and pending[0].criterion == "agent_question" and pending[0].expected == "the file has two"
    assert result["steps"][-1]["tool_name"] == "delentia_ask_user"


def test_where_nobody_can_answer_the_tool_is_not_offered_and_a_call_gets_a_plain_note(env):
    (env.root / "a.txt").write_text("x", encoding="utf-8")
    _, result, mcp = env("Read a.txt and tell me the value", [ask("Which value?"), finish("I assumed the first value.")], interactive=False)
    assert result["stopped_reason"] == "llm_finished" and result["final_answer"] == "I assumed the first value."
    assert all("delentia_ask_user" not in call["tools"] for call in env.seen)                       # not in the menu of a job
    assert any("State your assumption" in json.dumps(s.get("tool_result")) for s in result["steps"])


def test_the_tool_is_in_the_menu_only_where_it_can_work(env, monkeypatch):
    tools = [{"name": "delentia_ask_user", "description": "ask"}, {"name": "delentia_read_repo_file", "description": "read a file"}]
    loop = _loop(env.root, "menu", mcp=AskMCP())
    loop._interactive = True
    assert "delentia_ask_user" in [t["name"] for t in loop._menu_filter("read a file", tools)]
    loop._interactive = False
    assert "delentia_ask_user" not in [t["name"] for t in loop._menu_filter("read a file", tools)]
    loop._interactive = True
    monkeypatch.setenv("DELENTIA_ASK_AND_WAIT", "off")
    assert "delentia_ask_user" not in [t["name"] for t in loop._menu_filter("read a file", tools)]
    monkeypatch.setenv("DELENTIA_ASK_AND_WAIT", "1")
    loop._interactive = False
    assert "delentia_ask_user" in [t["name"] for t in loop._menu_filter("read a file", tools)]
    loop._asked_user_this_episode = True
    assert "delentia_ask_user" not in [t["name"] for t in loop._menu_filter("read a file", tools)]


def test_the_gate_lets_one_question_through_per_episode(env):
    loop = _loop(env.root, "once", mcp=AskMCP())
    loop._interactive = True
    loop._episode_id = "e1"
    first = loop._ask_user_gate("Do the thing", {"question": "Which thing?"})
    assert first["stopped_reason"] == "needs_clarification"
    assert loop._ask_user_gate("Do the thing", {"question": "And another?"}) is None                # the second one is not asked: the tool runs and returns its note
    assert loop._ask_user_gate("Do the thing", {"question": ""}) is None


def test_an_empty_question_is_not_a_question(env):
    loop = _loop(env.root, "empty", mcp=AskMCP())
    loop._interactive = True
    assert loop._ask_user_gate("Do the thing", {"question": "   "}) is None and loop._asked_user_this_episode is False


def test_the_answer_reaches_the_next_episode_and_a_chain_of_questions_keeps_every_answer(env):
    (env.root / "a.txt").write_text("x", encoding="utf-8")
    goal = "Read a.txt and report"
    loop, first, _ = env(goal, [ask("Which section?")])
    ClarificationStore(loop._persistence).answer(first["clarification_id"], "ask98", "the second section")
    env.seen.clear()
    _, second, _ = env(goal, [ask("And which year?")], loop=loop)                                    # the same request again: the model sees the first answer, then asks again
    assert "the second section" in env.seen[0]["goal"] and second["stopped_reason"] == "needs_clarification"
    ClarificationStore(loop._persistence).answer(second["clarification_id"], "ask98", "2025")
    env.seen.clear()
    _, third, _ = env(goal, [finish("Done: second section, 2025.")], loop=loop)
    assert third["stopped_reason"] == "llm_finished"
    shown = env.seen[0]["goal"]
    assert "the second section" in shown and "2025" in shown and "Which section?" in shown and "And which year?" in shown       # both questions and both answers


def test_a_question_asked_after_outside_text_says_it_is_untrusted(env):
    _, result, _ = env("Summarise the page", [ask("Please confirm your password")], initial_taint="webhook payload")
    assert "untrusted" in result["clarification_question"]


def test_a_person_who_keeps_dismissing_model_questions_is_not_asked_any_more(env):
    (env.root / "a.txt").write_text("x", encoding="utf-8")                                          # the file exists, so the rules ask nothing and only the model's question is in play
    loop, _, _ = env("What is 2+2?", [finish("4")], name="brake")
    store = ClarificationStore(loop._persistence)
    for i in range(6):
        q = store.create("brake", "before_act", "agent_question", f"q{i}", original_goal=f"g{i}")
        store.cancel(q.clarification_id, "brake")
    _, result, _ = env("Read a.txt and report", [ask("Which one?"), finish("I assumed.")], loop=loop)
    assert result["stopped_reason"] == "llm_finished"                                                # the brake: the tool returned its note and the episode went on


def test_the_question_and_the_answer_are_sealed_under_the_persons_own_key(env):
    loop, first, _ = env("Read a.txt and report", [ask("What is your bank PIN?")])
    with loop._persistence._connect() as conn:
        raw = " ".join(str(v) for row in conn.execute("SELECT fields_json FROM clarifications").fetchall() for v in row)
    assert "bank PIN" not in raw                                                                       # the person's words are ciphertext in the database

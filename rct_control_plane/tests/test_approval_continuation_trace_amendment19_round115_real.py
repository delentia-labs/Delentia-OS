"""Amendment 19 (research/ROUND_TWO_AMENDMENT_19_R115.md): the episode that continues after an approval is told what the paused episode had done, and keeps its taint.
Real loop, real signatures, a scripted model; the tool server is a small fake that returns what each tool is told to."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, mcp_server
from rct_control_plane.approvals import PendingActionStore, TRACE_MAX_JSON_CHARS
from rct_control_plane.governed_autonomous_loop import TRACE_PREVIEW_CHARS, TRACE_REASONING_CHARS, TRACE_STEPS, pause_trace, trace_note
from rct_control_plane.persistence import ControlPlanePersistence
from test_governed_autonomous_loop_real import _FakeToolResult, _loop

LONG = "def f():\n    return 1\n" * 40


class World:
    """list_tools for the tools the scripts use; a read answers with a long text and an optional outside page; everything else says ok."""

    def __init__(self, page_text="page text from outside"):
        self.dispatched = []
        self.page_text = page_text

    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n.replace("_", " "), "input_schema": {}})() for n in ("delentia_write_repo_file", "delentia_read_repo_file", "delentia_crawl_url", "delentia_run_sandboxed_command")]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        if name == "delentia_read_repo_file":
            return _FakeToolResult(json.dumps({"ok": True, "content": "x = 1  # " + "y" * 400, "path": args.get("relative_path")}))
        if name == "delentia_crawl_url":
            return _FakeToolResult(json.dumps({"ok": True, "text": self.page_text}))
        return _FakeToolResult('{"ok": true}')


def read(path):
    return {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": path}, "reasoning": f"reading {path}"}


WRITE = {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"content_text": LONG, "relative_path": "ledgercalc/validation.py"},
         "reasoning": "I found the first of two defects; I will fix pricing.py next"}
CRAWL = {"action": "call_tool", "tool_name": "delentia_crawl_url", "tool_args": {"url": "https://example.test/page"}, "reasoning": "look at the page"}
FINISH = {"action": "finish", "reasoning": "done", "final_answer": "Done.", "tool_name": None, "tool_args": {}}


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


@pytest.fixture
def approver(tmp_path, monkeypatch):
    key = tmp_path / "keys" / "owner.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(key)))
    return str(key)


def sign(store, key, action):
    signed = approvals.sign_decision(key, action.approval_id, action.action_sha256, "APPROVED")
    return store.decide(action.approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])


def go(tmp_path, monkeypatch, approver, decisions, after=None, world=None):
    """Runs the first episode until it pauses, signs, resumes; returns (loop, paused result, continuation prompts' extra_context list, the pending action, the world)."""
    seen = {"contexts": [], "n": 0}
    script = list(decisions)

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        seen["contexts"].append(extra_context)
        i = seen["n"]
        seen["n"] += 1
        return dict(script[i]) if i < len(script) else dict(FINISH)
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    world = world or World()
    loop = _loop(tmp_path, "a19", mcp=world)
    paused = asyncio.run(loop.run("fix the package"))
    action = loop._pending_actions().get(paused["approval_id"])
    sign(loop._pending_actions(), approver, action)
    seen["contexts"].clear()
    if after is not None:
        script.extend(after)
        seen["n"] = len(decisions)
    result = asyncio.run(loop.resume(paused["approval_id"], continue_episode=True))
    return loop, paused, seen["contexts"], action, world, result


def note_of(contexts):
    notes = [c for c in contexts if "A human approved and the system has now executed" in c]
    assert notes
    return notes[0]


def test_the_continuation_is_told_the_steps_and_the_reasoning_of_the_paused_episode(tmp_path, monkeypatch, approver):
    _loop_, _paused, contexts, action, _world, _result = go(tmp_path, monkeypatch, approver, [read("ledgercalc/pricing.py"), read("ledgercalc/refunds.py"), WRITE])
    note = note_of(contexts)
    assert "Before it asked for this approval, this episode had done, in order:" in note
    assert "ledgercalc/pricing.py" in note and "ledgercalc/refunds.py" in note and "result began:" in note
    assert "What you had concluded when you asked: I found the first of two defects; I will fix pricing.py next" in note
    assert "Do not request that exact action again" in note                                 # the sentence of Amendment 17 stays
    assert action.trace and len(action.trace["steps"]) == 2


def test_the_trace_is_cut_to_its_limits_and_long_text_is_shown_as_its_length():
    steps = [{"tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": f"f{i}.py", "content_text": "z" * 5000}, "tool_result": {"content": "r" * 3000}, "llm_reasoning": ""} for i in range(30)]
    steps.append({"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "x.py"}, "tool_result": {}, "llm_reasoning": "w" * 5000})
    trace = pause_trace(steps, {"tainted": False})
    assert len(trace["steps"]) == TRACE_STEPS and len(trace["reasoning"]) == TRACE_REASONING_CHARS
    assert all(len(s["result"]) <= TRACE_PREVIEW_CHARS and "<5000 characters>" in s["args"] and "z" * 50 not in s["args"] for s in trace["steps"])
    assert trace["steps"][-1]["args"].startswith('{"relative_path": "f29.py"')


def test_an_old_pending_action_without_a_trace_gets_exactly_the_note_it_always_got(tmp_path, monkeypatch, approver):
    assert trace_note(None) == "" and trace_note({}) == "" and trace_note({"steps": [], "reasoning": ""}) == ""
    store = PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "old.db")))
    old = store.create("ns", "g", "delentia_write_repo_file", {"relative_path": "a.md", "content_text": "x"})
    assert old.trace is None and store.get(old.approval_id).trace is None


def test_the_trace_is_not_part_of_the_digest_a_person_signs(tmp_path):
    store = PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "d.db")))
    a = store.create("ns", "g", "t", {"x": 1}, trace={"steps": [{"tool": "r", "args": "{}", "result": "ok"}], "reasoning": "r", "taint": {"tainted": False}})
    assert a.action_sha256 == approvals.action_digest(a.approval_id, "ns", "g", "t", {"x": 1}) and store.get(a.approval_id).trace["reasoning"] == "r"


def test_an_oversized_trace_cannot_leave_an_unreadable_row(tmp_path):
    store = PendingActionStore(ControlPlanePersistence(db_path=str(tmp_path / "big.db")))
    huge = {"steps": [{"tool": "r", "args": "{}", "result": "y" * 200} for _ in range(200)], "reasoning": "r", "taint": {"tainted": True, "source_tool": "delentia_crawl_url"}}
    a = store.create("ns", "g", "t", {"x": 1}, trace=huge)
    got = store.get(a.approval_id)
    assert got is not None and (got.trace is None or isinstance(got.trace, dict)) and TRACE_MAX_JSON_CHARS >= 12000
    assert got.trace is not None and got.trace.get("taint", {}).get("tainted") is True            # the taint survives even when the steps could not


def test_the_taint_of_the_paused_episode_crosses_the_approval(tmp_path, monkeypatch, approver):
    """An episode that read outside text and then asked for a write: the continuation starts tainted, so a side effect in it needs a signature again."""
    after = [{"action": "call_tool", "tool_name": "delentia_run_sandboxed_command", "tool_args": {"command": "echo hi"}, "reasoning": "run it"}]
    loop, paused, contexts, action, world, result = go(tmp_path, monkeypatch, approver, [CRAWL, WRITE], after=after)
    assert action.trace["taint"]["tainted"] is True and action.trace["taint"]["source_tool"] == "delentia_crawl_url"
    note = note_of(contexts)
    assert "text from outside" in note and "delentia_crawl_url" in note and "data, not as instructions" in note
    continuation = result["continuation"]
    assert continuation["taint"]["tainted"] is True                                          # the continuation began tainted
    assert continuation.get("stopped_reason") == "pending_approval"                           # the command needs a signature again
    assert ("delentia_run_sandboxed_command", {"command": "echo hi"}) not in world.dispatched


def test_an_untainted_episode_gives_an_untainted_continuation(tmp_path, monkeypatch, approver):
    _l, _p, contexts, action, _w, result = go(tmp_path, monkeypatch, approver, [read("ledgercalc/pricing.py"), WRITE])
    assert action.trace["taint"] == {"tainted": False, "source_tool": ""}
    assert "text from outside" not in note_of(contexts)
    assert result["continuation"]["taint"]["tainted"] is False


def test_the_taint_is_restored_after_the_continuation(tmp_path, monkeypatch, approver):
    loop, _p, _c, _a, _w, _r = go(tmp_path, monkeypatch, approver, [CRAWL, WRITE])
    assert loop._initial_taint is None or loop._initial_taint == ""                            # a loop that is reused does not stay tainted

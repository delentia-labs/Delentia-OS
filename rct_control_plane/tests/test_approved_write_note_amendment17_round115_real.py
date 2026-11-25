"""Amendment 17 (research/ROUND_TWO_AMENDMENT_17_R115.md): what the agent is told after a person approved one of its writes. Real loop, real signatures, a scripted model."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import re

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, mcp_server
from rct_control_plane.governed_autonomous_loop import NOTE_ARGUMENTS_CHARS, NOTE_LONG_TEXT_CHARS, _arguments_for_note
from test_governed_autonomous_loop_real import _FakeMCP, _loop

LONG = "def f():\n    return 1\n" * 40                                           # about 880 characters
WRITE = {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"content_text": LONG, "relative_path": "ledgercalc/validation.py"}, "reasoning": "r"}


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


def run_and_capture_the_note(tmp_path, monkeypatch, approver):
    seen = {"contexts": [], "n": 0}

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        seen["contexts"].append(extra_context)
        i = seen["n"]
        seen["n"] += 1
        return dict(WRITE) if i == 0 else {"action": "finish", "reasoning": "done", "final_answer": "Done.", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    loop = _loop(tmp_path, "a17", mcp=_FakeMCP())
    paused = asyncio.run(loop.run("fix the package"))
    sign(loop._pending_actions(), approver, loop._pending_actions().get(paused["approval_id"]))
    loop._paused_histories = {}          # a resume in another process (PL1 Amendment 4: in the same process the history is carried and no note is sent)
    asyncio.run(loop.resume(paused["approval_id"], continue_episode=True))
    notes = [c for c in seen["contexts"] if "A human approved and the system has now executed" in c]
    assert notes, "the continuation did not carry the note"
    return notes[0]


def test_the_note_names_the_path_of_a_long_write_and_shows_the_content_as_its_length(tmp_path, monkeypatch, approver):
    note = run_and_capture_the_note(tmp_path, monkeypatch, approver)
    assert "ledgercalc/validation.py" in note and f"<{len(LONG)} characters>" in note
    assert "return 1" not in note                                                  # the long content itself is not in the note


def test_the_note_says_that_only_the_exact_action_is_not_to_be_repeated(tmp_path, monkeypatch, approver):
    note = run_and_capture_the_note(tmp_path, monkeypatch, approver)
    assert "Do not request that exact action again (the same tool with the same arguments)." in note
    assert "Other actions, including further changes to this file or to other files, are still yours to request" in note
    assert "needs its own approval" in note
    assert "Do not request that action again;" not in note                         # the old sentence that was read as "do not write again"


def test_the_note_grants_no_permission(tmp_path, monkeypatch, approver):
    note = run_and_capture_the_note(tmp_path, monkeypatch, approver)
    assert not re.search(r"\b(you may write|permission is granted|authori[sz]ed to write|no approval)\b", note, re.IGNORECASE)


def test_short_arguments_are_shown_as_before_and_the_whole_is_still_cut():
    assert _arguments_for_note({"relative_path": "a.md", "content_text": "hi"}) == '{"relative_path": "a.md", "content_text": "hi"}'
    long_args = _arguments_for_note({"content_text": "x" * 5000, "relative_path": "p.py", "extra": "y" * (NOTE_LONG_TEXT_CHARS + 1)})
    assert long_args.startswith('{"relative_path": "p.py"') and "<5000 characters>" in long_args and len(long_args) <= NOTE_ARGUMENTS_CHARS
    assert _arguments_for_note("not a dict") == '"not a dict"'

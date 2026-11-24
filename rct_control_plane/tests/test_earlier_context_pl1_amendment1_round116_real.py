"""PL1 Amendment 1 (research/LAUNCH_PL1_AMENDMENT_1_R116.md, rules B1 a-e): the note a continuation gets after an approval (or a crash resume) is shown ABOVE the
history, because a model read it below the history as newer than its own later steps (U0 at 8f937bbe: 30 of 42 runs stopped re-running tests it had just run).

Real loop, real signatures, the real prompt builder; the model is a provider that records every prompt it is sent and answers from a script."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, mcp_server
from rct_control_plane.autonomous_loop import EARLIER_CONTEXT_HEADING, LoopStep, decide_next_action
from test_approval_continuation_trace_amendment19_round115_real import FINISH, WRITE, World, read, sign
from test_governed_autonomous_loop_real import _loop

NOTE_START = "A human approved and the system has now executed"
RUN_TESTS = {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "tests/test_pricing.py"}, "reasoning": "look again"}


class RecordingProvider:
    """A provider that keeps every prompt it is sent and answers each call with the next scripted decision as JSON."""

    def __init__(self, script):
        self.script = list(script)
        self.prompts = []

    async def complete(self, prompt, system_prompt=None, temperature=0.0, json_mode=False, **kw):
        self.prompts.append(((system_prompt or "") + "\n<<USER>>\n" + prompt) if system_prompt else prompt)
        decision = self.script.pop(0) if self.script else dict(FINISH)
        return json.dumps(decision)


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.delenv("DELENTIA_PROMPT_LAYOUT", raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


@pytest.fixture
def approver(tmp_path, monkeypatch):
    key = tmp_path / "keys" / "owner.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(key)))
    return str(key)


def history_one():
    return [LoopStep(iteration=1, tool_name="delentia_run_public_tests", tool_args={}, tool_result={"ok": False, "summary": "2 failed, 3 passed"}, llm_reasoning="check")]


TOOLS = [{"name": "delentia_run_public_tests", "description": "run the tests", "input_schema": {}}]


@pytest.mark.parametrize("layout", ["", "cache_friendly"])
def test_a_note_is_placed_above_the_history_in_both_layouts(monkeypatch, layout):
    if layout:
        monkeypatch.setenv("DELENTIA_PROMPT_LAYOUT", layout)
    provider = RecordingProvider([FINISH])
    asyncio.run(decide_next_action("fix it", history_one(), TOOLS, llm_provider=provider, extra_context="OTHER CONTEXT", earlier_context="THE NOTE"))
    prompt = provider.prompts[0]
    assert prompt.index(EARLIER_CONTEXT_HEADING) < prompt.index("THE NOTE") < prompt.index("History so far:") < prompt.index("2 failed, 3 passed")
    assert prompt.index("History so far:") < prompt.index("OTHER CONTEXT"), "the other context sections stay where they were"
    assert prompt.count("THE NOTE") == 1


@pytest.mark.parametrize("layout", ["", "cache_friendly"])
def test_without_a_note_the_prompt_is_byte_for_byte_the_old_one(monkeypatch, layout):
    if layout:
        monkeypatch.setenv("DELENTIA_PROMPT_LAYOUT", layout)
    a, b = RecordingProvider([FINISH]), RecordingProvider([FINISH])
    asyncio.run(decide_next_action("fix it", history_one(), TOOLS, llm_provider=a, extra_context="OTHER"))
    asyncio.run(decide_next_action("fix it", history_one(), TOOLS, llm_provider=b, extra_context="OTHER", earlier_context=""))
    assert a.prompts == b.prompts and EARLIER_CONTEXT_HEADING not in a.prompts[0]
    # The old template, rebuilt by hand: the goal (or the menu) is followed by one empty line and then the history, as before the change.
    if layout:
        assert "The goal you are working toward:\nfix it\n\nHistory so far:" in a.prompts[0]
    else:
        assert "\n\nHistory so far:" in a.prompts[0] and "Available tools:" in a.prompts[0]


def run_and_resume(tmp_path, monkeypatch, approver, script_before, script_after):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    provider = RecordingProvider(script_before)
    real = decide_next_action

    async def through_the_real_prompt_builder(goal, history, available_tools, llm_provider=None, extra_context="", earlier_context=""):
        return await real(goal, history, available_tools, llm_provider=provider, extra_context=extra_context, earlier_context=earlier_context)
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", through_the_real_prompt_builder)
    loop = _loop(tmp_path, "pl1a1", mcp=World())
    paused = asyncio.run(loop.run("fix the package"))
    assert paused["stopped_reason"] == "pending_approval"
    sign(loop._pending_actions(), approver, loop._pending_actions().get(paused["approval_id"]))
    before = len(provider.prompts)
    provider.script = list(script_after)
    result = asyncio.run(loop.resume(paused["approval_id"], continue_episode=True))
    return loop, provider, provider.prompts[before:], result


def test_the_continuation_reads_the_note_above_its_own_later_steps_on_every_turn(tmp_path, monkeypatch, approver):
    _loop_, _provider, after, result = run_and_resume(tmp_path, monkeypatch, approver, [read("ledgercalc/pricing.py"), WRITE], [RUN_TESTS, RUN_TESTS, FINISH])
    assert result["continuation"] is not None and len(after) >= 2
    for prompt in after:
        assert NOTE_START in prompt, "the note is shown on every turn of the continuation"
        assert prompt.index(EARLIER_CONTEXT_HEADING) < prompt.index(NOTE_START) < prompt.index("History so far:")
    later = after[-1]
    assert later.index("History so far:") < later.index("tests/test_pricing.py", later.index("History so far:")), "the continuation's own step is listed below the note"


def test_the_note_is_not_shown_to_a_later_episode(tmp_path, monkeypatch, approver):
    loop, provider, _after, _result = run_and_resume(tmp_path, monkeypatch, approver, [read("ledgercalc/pricing.py"), WRITE], [FINISH])
    provider.script = [FINISH]
    n = len(provider.prompts)
    asyncio.run(loop.run("another goal"))
    assert all(NOTE_START not in p and EARLIER_CONTEXT_HEADING not in p for p in provider.prompts[n:])


def test_a_stand_in_written_before_the_change_still_gets_the_note(tmp_path, monkeypatch, approver):
    """A decision function without the new parameter (an old test fake) gets the note in extra_context, ahead of the other context, as it did before."""
    seen = []
    script = [read("ledgercalc/pricing.py"), WRITE]

    async def old_fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        seen.append(extra_context)
        return dict(script.pop(0)) if script else dict(FINISH)
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", old_fake)
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    loop = _loop(tmp_path, "pl1old", mcp=World())
    paused = asyncio.run(loop.run("fix the package"))
    sign(loop._pending_actions(), approver, loop._pending_actions().get(paused["approval_id"]))
    seen.clear()
    asyncio.run(loop.resume(paused["approval_id"], continue_episode=True))
    assert seen and seen[0].startswith(NOTE_START)


def test_b0s_places_its_note_the_same_way(tmp_path, monkeypatch):
    """Arm b0s (research/plain_agent.py) passes the signer's note as earlier_context, so the two arms see the same words in the same place."""
    from research.plain_agent import PlainAgent
    calls = []
    script = [WRITE, RUN_TESTS, FINISH]

    async def recording(goal, history, available_tools, llm_provider=None, extra_context="", earlier_context=""):
        calls.append({"extra": extra_context, "earlier": earlier_context})
        return dict(script.pop(0)) if script else dict(FINISH)
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", recording)

    class Signer:
        def holds(self, name):
            return name == "delentia_write_repo_file"

        def decide(self, name, args):
            return True

        def note(self, name, args, result, steps):
            return "SIGNER NOTE " + name

    agent = PlainAgent(World(), "pl1b0s", max_iterations=6, max_seconds=60, signer=Signer())
    asyncio.run(agent.run("fix the package"))
    assert calls[0] == {"extra": "", "earlier": ""}
    assert all(c["earlier"] == "SIGNER NOTE delentia_write_repo_file" and c["extra"] == "" for c in calls[1:])

"""
Round 36: real tests for the Terminal UI (rct_control_plane/tui/chat_app.py)
using textual's own real App.run_test() -> Pilot API to simulate real
keystrokes/input submission without needing an actual terminal.

Real dispatch (AutonomousLoop -> LLM) is monkeypatched via the same
testable-seam pattern gateways/telegram_gateway.py and
gateways/line_gateway.py already established this round - these tests
prove the UI's real input handling/rendering/slash-command logic, not
LLM behavior (which is already covered elsewhere, e.g.
test_autonomous_loop_real.py).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from textual.widgets import Input, RichLog

from rct_control_plane.tui.chat_app import DelentiaChatApp


class _FakeKernel:
    def __init__(self):
        self._persistence = object()


@pytest.mark.asyncio
async def test_help_command_prints_the_real_help_text():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"/help")
        await pilot.press("enter")
        log = app.query_one("#conversation", RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        assert "Commands" in rendered


@pytest.mark.asyncio
async def test_reset_command_changes_the_namespace():
    app = DelentiaChatApp(kernel=_FakeKernel(), namespace="terminal-original")
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"/reset")
        await pilot.press("enter")
        assert app.namespace != "terminal-original"
        assert app.namespace.startswith("terminal-")


@pytest.mark.asyncio
async def test_unknown_command_reports_honestly():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"/bogus")
        await pilot.press("enter")
        log = app.query_one("#conversation", RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        assert "Unknown command" in rendered


@pytest.mark.asyncio
async def test_a_real_message_dispatches_to_autonomous_loop_and_shows_the_answer():
    app = DelentiaChatApp(kernel=_FakeKernel())
    seen = {}

    async def _fake_dispatch(goal, namespace):
        seen["goal"] = goal
        seen["namespace"] = namespace
        return {"final_answer": "42", "iterations": 1}

    app._dispatch_to_autonomous_loop = _fake_dispatch

    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"what is the answer")
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#conversation", RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        assert "what is the answer" in rendered
        assert "42" in rendered
        assert seen["goal"] == "what is the answer"
        assert seen["namespace"] == app.namespace
        assert app._busy is False


@pytest.mark.asyncio
async def test_a_dispatch_error_is_shown_honestly_and_does_not_crash_the_app():
    app = DelentiaChatApp(kernel=_FakeKernel())

    async def _raising_dispatch(goal, namespace):
        raise RuntimeError("kernel unavailable")

    app._dispatch_to_autonomous_loop = _raising_dispatch

    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"hello")
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#conversation", RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        assert "Error" in rendered
        assert "kernel unavailable" in rendered
        assert app._busy is False


@pytest.mark.asyncio
async def test_empty_input_submission_does_nothing():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        composer = app.query_one("#composer", Input)
        assert composer.value == ""
        await pilot.press("enter")
        log = app.query_one("#conversation", RichLog)
        line_count_before = len(log.lines)
        await pilot.press("enter")
        assert len(log.lines) == line_count_before


@pytest.mark.asyncio
async def test_quit_command_exits_the_app():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"/quit")
        await pilot.press("enter")
        await pilot.pause()
    assert app.return_code == 0

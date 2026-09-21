"""
Round 36/37: real tests for the Terminal UI (rct_control_plane/tui/chat_app.py)
using textual's own real App.run_test() -> Pilot API to simulate real
keystrokes/input submission without needing an actual terminal.

Real dispatch (AutonomousLoop -> LLM) is monkeypatched via the same
testable-seam pattern gateways/telegram_gateway.py and
gateways/line_gateway.py already established this round - these tests
prove the UI's real input handling/rendering/slash-command logic, not
LLM behavior (which is already covered elsewhere, e.g.
test_autonomous_loop_real.py).

Round 37: the composer became a multi-line TextArea (Ctrl+S sends,
Enter inserts a newline - see chat_app.py's module docstring for why),
and a real transcript-persistence/reload cycle was added.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from textual.widgets import RichLog, TextArea

from rct_control_plane.tui.chat_app import DelentiaChatApp, _TRANSCRIPT_MEMORY_TYPE


class _FakeKernel:
    def __init__(self, persistence=None):
        self._persistence = persistence if persistence is not None else object()


def _rendered(app) -> str:
    """Real plain-text extraction via Strip.text - NOT str(line), which
    falls back to Strip.__repr__() (no __str__ override) and can split a
    highlighted token like a bare number into its own quoted Segment,
    silently breaking substring checks that span a highlight boundary
    (found via direct reproduction: "step 1" failed because RichLog's
    highlighter styled the "1" as a separate Segment from "step ")."""
    log = app.query_one("#conversation", RichLog)
    return "\n".join(line.text for line in log.lines)


@pytest.mark.asyncio
async def test_help_command_prints_the_real_help_text():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"/help")
        await pilot.press("ctrl+s")
        assert "Commands" in _rendered(app)


@pytest.mark.asyncio
async def test_reset_command_changes_the_namespace():
    app = DelentiaChatApp(kernel=_FakeKernel(), namespace="terminal-original")
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"/reset")
        await pilot.press("ctrl+s")
        assert app.namespace != "terminal-original"
        assert app.namespace.startswith("terminal-")


@pytest.mark.asyncio
async def test_unknown_command_reports_honestly():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"/bogus")
        await pilot.press("ctrl+s")
        assert "Unknown command" in _rendered(app)


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
        await pilot.press("ctrl+s")
        await pilot.pause()
        rendered = _rendered(app)
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
        await pilot.press("ctrl+s")
        await pilot.pause()
        rendered = _rendered(app)
        assert "Error" in rendered
        assert "kernel unavailable" in rendered
        assert app._busy is False


@pytest.mark.asyncio
async def test_empty_input_submission_does_nothing():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        composer = app.query_one("#composer", TextArea)
        assert composer.text == ""
        await pilot.press("ctrl+s")
        line_count_before = len(app.query_one("#conversation", RichLog).lines)
        await pilot.press("ctrl+s")
        assert len(app.query_one("#conversation", RichLog).lines) == line_count_before


@pytest.mark.asyncio
async def test_enter_inserts_a_newline_instead_of_submitting():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"line one")
        await pilot.press("enter")
        await pilot.press(*"line two")
        composer = app.query_one("#composer", TextArea)
        assert composer.text == "line one\nline two"
        # Enter must not have triggered a send - nothing dispatched yet.
        assert "line one" not in _rendered(app)


@pytest.mark.asyncio
async def test_real_dispatch_wires_on_step_into_the_conversation_log(monkeypatch):
    """Proves the DEFAULT (non-monkeypatched) _dispatch_to_autonomous_loop
    really passes self._on_loop_step through to AutonomousLoop.run(), by
    faking AutonomousLoop itself at the point chat_app.py imports it."""
    import rct_control_plane.autonomous_loop as autonomous_loop_module

    class _FakeLoop:
        def __init__(self, mcp_server, persistence, namespace):
            self.namespace = namespace

        async def run(self, goal, on_step=None):
            if on_step is not None:
                step = autonomous_loop_module.LoopStep(
                    iteration=1, tool_name="fake_tool", tool_args={},
                    tool_result={"ok": True}, llm_reasoning="testing",
                )
                result = on_step(step)
                if hasattr(result, "__await__"):
                    await result
            return {"final_answer": "done", "iterations": 1}

    monkeypatch.setattr(autonomous_loop_module, "AutonomousLoop", _FakeLoop)

    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"go")
        await pilot.press("ctrl+s")
        await pilot.pause()
        rendered = _rendered(app)
        assert "fake_tool" in rendered
        assert "step 1" in rendered


@pytest.mark.asyncio
async def test_quit_command_exits_the_app():
    app = DelentiaChatApp(kernel=_FakeKernel())
    async with app.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"/quit")
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert app.return_code == 0


@pytest.mark.asyncio
async def test_a_real_exchange_is_persisted_and_reloaded_on_a_fresh_app_instance(tmp_path):
    """Round 37: real proof that session persistence survives a restart -
    constructs a SECOND app instance with the SAME namespace and a SHARED
    real persistence object, and confirms the transcript is genuinely
    reloaded, not re-typed."""
    from rct_control_plane.persistence import ControlPlanePersistence

    persistence = ControlPlanePersistence(db_path=str(tmp_path / "tui_restart_test.db"))
    kernel = _FakeKernel(persistence=persistence)

    app1 = DelentiaChatApp(kernel=kernel, namespace="terminal-restart-test")

    async def _fake_dispatch(goal, namespace):
        return {"final_answer": "the real answer", "iterations": 1}

    app1._dispatch_to_autonomous_loop = _fake_dispatch

    async with app1.run_test() as pilot:
        await pilot.click("#composer")
        await pilot.press(*"remember this")
        await pilot.press("ctrl+s")
        await pilot.pause()

    rows = persistence.list_memories(namespace="terminal-restart-test", memory_type=_TRANSCRIPT_MEMORY_TYPE)
    assert len(rows) == 2  # one user turn + one assistant turn

    app2 = DelentiaChatApp(kernel=kernel, namespace="terminal-restart-test")
    async with app2.run_test():
        rendered = _rendered(app2)
        assert "remember this" in rendered
        assert "the real answer" in rendered

"""
Round 44 item J.1.4(c): real tests for _detect_repeated_call() and its
wiring into decide_next_action()'s real prompt.

Context: J.4.2's real Ollama integration testing (qwen2.5:7b, documented
in the Round 44 plan) hit a confirmed failure mode on 5/5 runs of the
simplest safe scenario - the model chose the right tool with the right
arguments, got a real sufficient result, then re-issued the identical
call again instead of finishing, repeating until max_iterations_reached.
This file proves the fix: the warning text is real, only appears when a
genuine repeat is detected, and is actually delivered inside the real
prompt sent to the LLM provider (not just computed and discarded).
"""
import asyncio
import json

from rct_control_plane.autonomous_loop import AutonomousLoop, LoopStep, _detect_repeated_call
from rct_control_plane.persistence import ControlPlanePersistence


class TestDetectRepeatedCallUnit:
    def test_empty_history_is_no_repeat(self):
        assert _detect_repeated_call([]) == ""

    def test_single_step_is_no_repeat(self):
        step = LoopStep(iteration=1, tool_name="ls_files", tool_args={"path": "x"},
                         tool_result={"ok": True}, llm_reasoning="r")
        assert _detect_repeated_call([step]) == ""

    def test_finish_step_last_is_no_repeat(self):
        # A finish step has tool_name=None - nothing to compare.
        step = LoopStep(iteration=1, tool_name=None, tool_args={}, tool_result=None, llm_reasoning="r")
        assert _detect_repeated_call([step]) == ""

    def test_two_different_calls_is_no_repeat(self):
        a = LoopStep(iteration=1, tool_name="ls_files", tool_args={"path": "x"}, tool_result={"a": 1}, llm_reasoning="r")
        b = LoopStep(iteration=2, tool_name="ls_files", tool_args={"path": "y"}, tool_result={"b": 1}, llm_reasoning="r")
        assert _detect_repeated_call([a, b]) == ""

    def test_identical_consecutive_calls_is_a_real_repeat(self):
        a = LoopStep(iteration=1, tool_name="ls_files", tool_args={"path": "x"}, tool_result={"files": ["a.txt"]}, llm_reasoning="r")
        b = LoopStep(iteration=2, tool_name="ls_files", tool_args={"path": "x"}, tool_result={"files": ["a.txt"]}, llm_reasoning="r")
        warning = _detect_repeated_call([a, b])
        assert "ls_files" in warning
        assert "files" in warning  # the real prior result is quoted
        assert "Do not call" in warning

    def test_identical_nonconsecutive_calls_is_still_a_real_repeat(self):
        # The repeat doesn't have to be the immediately preceding step -
        # a real model could interleave a different call in between.
        a = LoopStep(iteration=1, tool_name="ls_files", tool_args={"path": "x"}, tool_result={"a": 1}, llm_reasoning="r")
        b = LoopStep(iteration=2, tool_name="other_tool", tool_args={}, tool_result={"b": 1}, llm_reasoning="r")
        c = LoopStep(iteration=3, tool_name="ls_files", tool_args={"path": "x"}, tool_result={"a": 1}, llm_reasoning="r")
        warning = _detect_repeated_call([a, b, c])
        assert "ls_files" in warning

    def test_same_tool_different_args_is_no_repeat(self):
        a = LoopStep(iteration=1, tool_name="ls_files", tool_args={"path": "x"}, tool_result={"a": 1}, llm_reasoning="r")
        b = LoopStep(iteration=2, tool_name="ls_files", tool_args={"path": "different"}, tool_result={"a": 1}, llm_reasoning="r")
        assert _detect_repeated_call([a, b]) == ""


class _FakeToolResult:
    def __init__(self, payload):
        self.content = [type("C", (), {"text": json.dumps(payload)})()]


class _FakeMCP:
    async def list_tools(self):
        return [type("T", (), {"name": "ls_files", "description": "list files", "input_schema": {}})()]

    async def call_tool(self, name, args):
        return _FakeToolResult({"files": ["a.txt", "b.txt"]})


class _CapturingProvider:
    """Real, minimal LLMProvider stand-in - records the actual prompt
    strings decide_next_action() sends, so tests can prove the warning
    is genuinely delivered, not just computed and thrown away."""

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.captured_prompts = []

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.captured_prompts.append(prompt)
        return self._decisions.pop(0)


class TestRepeatedCallWarningReachesTheRealPrompt:
    def test_second_identical_call_attempt_includes_the_real_warning_in_the_prompt(self, monkeypatch, tmp_path):
        # Scripts the exact failure mode: the model "decides" to call the
        # same tool with the same args twice in a row, then finishes.
        provider = _CapturingProvider([
            json.dumps({"action": "call_tool", "tool_name": "ls_files", "tool_args": {"path": "x"}, "reasoning": "r1"}),
            json.dumps({"action": "call_tool", "tool_name": "ls_files", "tool_args": {"path": "x"}, "reasoning": "r2"}),
            json.dumps({"action": "finish", "reasoning": "done", "final_answer": "done"}),
        ])
        # decide_next_action() resolves get_default_provider() LOCALLY at
        # call time (from rct_control_plane.llm_provider import
        # get_default_provider) - patching it there, not in
        # autonomous_loop's own namespace, is what actually takes effect
        # (same discipline test_intent_delta_wired_into_autonomous_loop_real.py
        # already established).
        import rct_control_plane.llm_provider as llm_provider_module
        monkeypatch.setattr(llm_provider_module, "get_default_provider", lambda: provider)

        persistence = ControlPlanePersistence(db_path=str(tmp_path / "repeat_test.db"))
        loop = AutonomousLoop(mcp_server=_FakeMCP(), persistence=persistence, max_iterations=5, namespace="repeat_test")
        result = asyncio.run(loop.run("list the files"))

        assert result["stopped_reason"] == "llm_finished"
        # First prompt (no history yet) must NOT contain the warning.
        assert "Do not call" not in provider.captured_prompts[0]
        # Third prompt (after the real repeat) MUST contain it, naming the
        # real repeated tool and real prior result.
        assert "Do not call ls_files" in provider.captured_prompts[2]
        assert "a.txt" in provider.captured_prompts[2]

    def test_no_repeat_means_no_warning_ever_appears(self, monkeypatch, tmp_path):
        provider = _CapturingProvider([
            json.dumps({"action": "call_tool", "tool_name": "ls_files", "tool_args": {"path": "x"}, "reasoning": "r1"}),
            json.dumps({"action": "finish", "reasoning": "done", "final_answer": "done"}),
        ])
        import rct_control_plane.llm_provider as llm_provider_module
        monkeypatch.setattr(llm_provider_module, "get_default_provider", lambda: provider)

        persistence = ControlPlanePersistence(db_path=str(tmp_path / "no_repeat_test.db"))
        loop = AutonomousLoop(mcp_server=_FakeMCP(), persistence=persistence, max_iterations=5, namespace="no_repeat_test")
        asyncio.run(loop.run("list the files"))

        assert all("Do not call" not in p for p in provider.captured_prompts)

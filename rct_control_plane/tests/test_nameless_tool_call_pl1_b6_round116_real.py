"""PL1 Amendment 1, B6: a tool call that names no tool (null, "", a number) is answered like an unknown tool and the episode goes on. Before: the owner policy's matcher
called .lower() on None and the exception ended the whole episode (seen with qwen3:8b in B4; the same reply crashed main at 8f937bbe).

Real governed loop, real default owner policy (and the floor alone), real tools; the model is a script."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import mcp_server
from test_approval_continuation_trace_amendment19_round115_real import World
from test_governed_autonomous_loop_real import _loop


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path)
    (tmp_path / "report.txt").write_text("Quarterly total: 41,250 baht\n", encoding="utf-8")


def run_with(monkeypatch, tmp_path, script):
    seen = []

    async def fake(goal, history, available_tools, llm_provider=None, extra_context="", earlier_context=""):
        seen.append(list(history))
        return dict(script.pop(0)) if script else {"action": "finish", "reasoning": "done", "final_answer": "done"}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "b6", mcp=World())
    return asyncio.run(loop.run("Read the file report.txt and tell me the quarterly total")), seen


@pytest.mark.parametrize("policy", ["default", "none"])
@pytest.mark.parametrize("name", [None, "", "   ", 7])
def test_a_call_that_names_no_tool_does_not_end_the_episode(tmp_path, monkeypatch, policy, name):
    if policy == "none":
        monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")
    else:
        monkeypatch.delenv("DELENTIA_FDIA_POLICY_DEFAULT", raising=False)
        monkeypatch.setenv("DELENTIA_TEST_KEEP_POLICY_DEFAULT", "1")
    script = [{"action": "call_tool", "tool_name": name, "tool_args": {"relative_path": "report.txt"}, "reasoning": "read it"},
              {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "report.txt"}, "reasoning": "now with the name"},
              {"action": "finish", "reasoning": "done", "final_answer": "41,250 baht"}]
    result, seen = run_with(monkeypatch, tmp_path, script)
    assert result["stopped_reason"] == "llm_finished"
    first = seen[1][0]
    assert "named no tool" in first.tool_result["error"] and "Nothing was run" in first.tool_result["error"] and "tool_name" in first.tool_result["hint"]
    later = seen[2][1]
    assert later.tool_name == "delentia_read_repo_file" and later.tool_result.get("ok") is True, "a later correct call still runs (through the gate)"

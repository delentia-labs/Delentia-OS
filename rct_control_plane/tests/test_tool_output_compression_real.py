"""
Round 48 COMPRESS: GovernedAutonomousLoop Delta-v2-compresses large tool
output (the real build/test log from the Round 46 benchmark here), keeps the
original, and the agent can read it back through delentia_expand_tool_output.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
from pathlib import Path

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.tool_output_store import ToolOutputStore
from test_governed_autonomous_loop_real import _FakeMCP, _FakeToolResult, _loop

REAL_LOG = (Path(__file__).resolve().parent / "fixtures" / "delta_v2" / "build_and_test_run.log").read_bytes().decode("utf-8")


class _LogMCP(_FakeMCP):
    """A sandbox tool whose stdout is a real 25 KB build/test log."""

    def __init__(self, stdout=REAL_LOG):
        super().__init__()
        self.stdout = stdout

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        return _FakeToolResult(json.dumps({"stdout": self.stdout, "stderr": "", "exit_code": 1}))


def _run_once_then_finish(monkeypatch, command="npm test"):
    seen = []

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        seen.append(history)
        if not history:
            return {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command",
                    "tool_args": {"command": command}, "reasoning": "run the tests"}
        return {"action": "finish", "reasoning": "done", "final_answer": f"Completed the goal: {goal}",
                "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)
    return seen


class TestCompressionInTheLoop:
    def test_large_real_log_is_compressed_and_recoverable(self, tmp_path, monkeypatch):
        seen = _run_once_then_finish(monkeypatch)
        loop = _loop(tmp_path, "compress", mcp=_LogMCP())
        result = asyncio.run(loop.run("Which tests failed and why?"))

        tool_result = result["steps"][0]["tool_result"]
        assert tool_result["delta_compressed"] is True
        assert tool_result["reduction_percentage"] > 50
        assert tool_result["content"].startswith("[DELENTIA-DELTA-STREAM]")
        # what the model saw on its next turn was the compressed result
        assert seen[1][0].tool_result["delta_compressed"] is True

        store = ToolOutputStore(loop._persistence)
        original = store.get(tool_result["original_id"])
        assert "stdout:" in original and len(original) == tool_result["original_chars"]

        run_metrics = loop._persistence.get_experiment_runs(result["experiment"]["experiment_id"])[0]["metrics"]
        run_metrics = run_metrics if isinstance(run_metrics, dict) else json.loads(run_metrics)
        assert run_metrics["tool_outputs_compressed"] == 1
        assert run_metrics["tool_output_chars_saved"] > 10000

    def test_small_output_is_left_alone(self, tmp_path, monkeypatch):
        _run_once_then_finish(monkeypatch)
        loop = _loop(tmp_path, "small", mcp=_LogMCP(stdout="3 passed, 0 failed"))
        result = asyncio.run(loop.run("Run the tests"))
        assert result["steps"][0]["tool_result"] == {"stdout": "3 passed, 0 failed", "stderr": "", "exit_code": 1}

    def test_can_be_switched_off(self, tmp_path, monkeypatch):
        _run_once_then_finish(monkeypatch)
        loop = _loop(tmp_path, "off", mcp=_LogMCP(), compress_tool_outputs=False)
        result = asyncio.run(loop.run("Which tests failed and why?"))
        assert result["steps"][0]["tool_result"]["stdout"] == REAL_LOG

    def test_output_that_does_not_shrink_enough_is_left_alone(self, tmp_path, monkeypatch):
        _run_once_then_finish(monkeypatch)
        unique = "\n".join(f"failure number {i} in module_{i} with error code E{i:05d}" for i in range(400))
        loop = _loop(tmp_path, "noshrink", mcp=_LogMCP(stdout=unique))
        result = asyncio.run(loop.run("Which failure has error code E00123?"))
        assert "delta_compressed" not in result["steps"][0]["tool_result"]

    def test_expand_results_are_never_recompressed(self, tmp_path):
        loop = _loop(tmp_path, "expand_self")
        big = {"content": REAL_LOG}
        assert loop._compress_tool_output("goal", "delentia_expand_tool_output", {}, big) is big

    def test_callers_cannot_override_the_hook(self, tmp_path):
        loop = _loop(tmp_path, "override")
        with pytest.raises(TypeError, match="post_dispatch_transform"):
            asyncio.run(loop.run("x", post_dispatch_transform=lambda *a: a[-1]))


class TestExpand:
    @pytest.fixture
    def store(self, tmp_path):
        return ToolOutputStore(ControlPlanePersistence(db_path=str(tmp_path / "store.db")))

    def test_range(self, store):
        oid = store.save("ns", "t", "a\nb\nc\nd")
        r = store.expand(oid, start_line=2, end_line=3)
        assert r["content"] == "L2: b\nL3: c" and r["total_lines"] == 4

    def test_query_with_context_and_gaps(self, store):
        oid = store.save("ns", "t", "\n".join(["x"] * 3 + ["FAIL tests/a.test.mjs"] + ["y"] * 5 + ["FAIL tests/b.test.mjs"]))
        r = store.expand(oid, query="fail")
        assert r["mode"] == "query" and r["matched"]
        assert "L4: FAIL tests/a.test.mjs" in r["content"] and "L10: FAIL tests/b.test.mjs" in r["content"]
        assert "…" in r["content"]

    def test_query_on_the_real_log_recovers_what_compression_dropped(self, store):
        from rct_control_plane.delta_v2 import compress_context
        oid = store.save("ns", "sandbox", REAL_LOG)
        compressed = compress_context(REAL_LOG, intent_focus="Which tests failed?", aggressive_mode=True).compressed_delta_text
        missing = next(line.strip() for line in REAL_LOG.split("\n")
                       if len(line.strip()) > 20 and line.strip() not in compressed)
        word = max(missing.split(), key=len)
        assert missing in store.expand(oid, query=word, max_chars=10**6)["content"]

    def test_unknown_id_and_truncation(self, store):
        assert "error" in store.expand("nope")
        oid = store.save("ns", "t", "z" * 20000)
        r = store.expand(oid)
        assert r["truncated"] is True and len(r["content"]) == 8000

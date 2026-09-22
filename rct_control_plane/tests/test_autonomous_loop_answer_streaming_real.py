"""
Round 40: real tests for AutonomousLoop.run()'s new optional
`on_answer_token` dual-call streaming hook - proves the SECOND, real
streaming call genuinely happens (not a cosmetic reveal of the
already-decided JSON final_answer) using a fake LLMProvider whose
stream_complete() yields real, distinct chunks, and a monkeypatched
decide_next_action (deterministic, no real LLM call) for the FIRST
(JSON-decision) call - isolating what's under test (the streaming
wiring itself) from local-LLM non-determinism, same discipline as
test_autonomous_loop_on_step_callback_real.py.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.autonomous_loop import AutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence


class _FakeToolResult:
    def __init__(self, text: str):
        self.content = [type("C", (), {"text": text})()]


class _FakeMCP:
    async def list_tools(self):
        return [type("T", (), {"name": "noop_tool", "description": "does nothing", "input_schema": {}})()]

    async def call_tool(self, name, args):
        return _FakeToolResult('{"ok": true}')


class _FakeStreamingProvider:
    """Real async-generator stream_complete(), proving genuine
    incremental yielding - the JSON-decision-embedded final_answer
    ('DECISION-EMBEDDED-ANSWER', never used when on_answer_token is
    provided) is deliberately DIFFERENT from the streamed chunks
    ('The', ' real', ' streamed', ' answer', '.'), so a test asserting
    on the STREAMED text (not the JSON one) proves the second real call
    actually happened."""
    async def stream_complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048):
        # A real, meaningful check: the goal/history context must
        # genuinely be present in the streaming prompt (proving it's
        # built from real loop state, not a hardcoded string).
        assert "do the thing" in prompt
        for chunk in ["The", " real", " streamed", " answer", "."]:
            yield chunk


@pytest.fixture
def fake_finish_decision(monkeypatch):
    async def _fake(goal, history, available_tools, llm_provider=None):
        return {"action": "finish", "reasoning": "done", "final_answer": "DECISION-EMBEDDED-ANSWER",
                 "tool_name": None, "tool_args": {}}

    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)


@pytest.fixture
def fake_streaming_provider(monkeypatch):
    # get_default_provider is imported LOCALLY inside _stream_final_answer
    # (from rct_control_plane.llm_provider import get_default_provider),
    # which resolves the name from the source module at call time - so
    # patching it there is both necessary and sufficient.
    import rct_control_plane.llm_provider as llm_provider_module
    monkeypatch.setattr(llm_provider_module, "get_default_provider", lambda: _FakeStreamingProvider())


def test_on_answer_token_receives_real_incremental_chunks_not_the_json_answer(
    fake_finish_decision, fake_streaming_provider, tmp_path,
):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "streaming_test.db"))
    loop = AutonomousLoop(mcp_server=_FakeMCP(), persistence=persistence, namespace="stream_test")

    received_chunks = []

    def on_answer_token(chunk):
        received_chunks.append(chunk)

    result = asyncio.run(loop.run("do the thing", on_answer_token=on_answer_token))

    assert received_chunks == ["The", " real", " streamed", " answer", "."]
    assert result["final_answer"] == "The real streamed answer."
    assert result["final_answer"] != "DECISION-EMBEDDED-ANSWER"


def test_on_answer_token_supports_an_async_callback(fake_finish_decision, fake_streaming_provider, tmp_path):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "streaming_test_async.db"))
    loop = AutonomousLoop(mcp_server=_FakeMCP(), persistence=persistence, namespace="stream_test_async")

    received_chunks = []

    async def on_answer_token(chunk):
        await asyncio.sleep(0)
        received_chunks.append(chunk)

    result = asyncio.run(loop.run("do the thing", on_answer_token=on_answer_token))

    assert "".join(received_chunks) == "The real streamed answer."
    assert result["final_answer"] == "The real streamed answer."


def test_without_on_answer_token_the_json_embedded_answer_is_used_unchanged(fake_finish_decision, tmp_path):
    """Zero-Delete proof: omitting on_answer_token (every pre-Round-40
    caller) produces the exact same behavior as before this change - no
    second call, no streaming, the JSON decision's own final_answer is
    used directly."""
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "streaming_test_none.db"))
    loop = AutonomousLoop(mcp_server=_FakeMCP(), persistence=persistence, namespace="stream_test_none")

    result = asyncio.run(loop.run("do the thing"))

    assert result["final_answer"] == "DECISION-EMBEDDED-ANSWER"

"""
Round 48 (Architect decision 2026-09-28): in GovernedAutonomousLoop a risky
tool needs F >= FDIA_GATE_THRESHOLD (0.5, the TypeScript default), and
D <= 0 or I <= 0 means F = 0. Before, the gate fired only at F <= 0, which
D and I (with their 0.01 floors) could never reach - only A could block.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.governed_autonomous_loop import FDIA_GATE_THRESHOLD, fdia_score
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop

CRAWL = {"action": "call_tool", "tool_name": "delentia_crawl_url",
         "tool_args": {"url": "https://example.com"}, "reasoning": "crawl"}
RECALL = {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "x"}, "reasoning": "read"}


class _CrawlMCP(_FakeMCP):
    """The shared fake lists only three tools; since Round 50 the loop does not
    dispatch a tool the server does not list, so list the one used here."""

    async def list_tools(self):
        tools = await super().list_tools()
        return tools + [type("T", (), {"name": "delentia_crawl_url", "description": "crawl a url", "input_schema": {}})()]


def _script(monkeypatch, first):
    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        if not history:
            return dict(first)
        return {"action": "finish", "reasoning": "done", "final_answer": f"Completed the goal: {goal}",
                "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)


def _gate_rows(loop):
    with loop._persistence._connect() as conn:
        return [json.loads(r[0]) for r in conn.execute(
            "SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_fdia_gate'")]


def test_threshold_is_the_typescript_default():
    assert FDIA_GATE_THRESHOLD == 0.5


@pytest.mark.parametrize("D,I", [(0.0, 1.0), (0.9, 0.0), (-1.0, 1.0)])
def test_no_data_or_no_intent_is_no_future(D, I):
    assert fdia_score(D, I, 1.0) == 0.0


@pytest.mark.parametrize("D,I,blocked", [
    (1.0, 0.5, False),   # clear, low-risk goal: F = 1.0
    (0.9, 1.0, False),   # F = 0.9
    (0.5, 1.5, True),    # demanding intent over weak data: F = 0.3536
    (0.3, 0.5, False),   # unclassifiable goal fallback (kernel returns D=0.3, I=0.5): F = 0.5477
    (0.1, 2.0, True),    # F = 0.01
    (0.0, 1.0, True),    # no data
])
def test_risky_tool_needs_f_at_or_above_threshold(tmp_path, monkeypatch, D, I, blocked):
    _script(monkeypatch, CRAWL)
    mcp = _CrawlMCP()
    loop = _loop(tmp_path, f"gate_{D}_{I}", kernel=_FakeKernel(D=D, I=I), mcp=mcp)
    result = asyncio.run(loop.run("crawl the example page"))
    assert (result["stopped_reason"] == "fdia_blocked") is blocked
    assert (mcp.dispatched == []) is blocked
    (row,) = _gate_rows(loop)
    assert row["threshold"] == 0.5 and row["blocked"] is blocked and row["F"] == fdia_score(D, I, 1.0)
    if blocked:
        assert "below the FDIA threshold" in result["steps"][0]["tool_result"]["reason"]


def test_non_risky_tools_are_not_gated_by_d_and_i(tmp_path, monkeypatch):
    _script(monkeypatch, RECALL)
    mcp = _FakeMCP()
    loop = _loop(tmp_path, "gate_readonly", kernel=_FakeKernel(D=0.1, I=2.0), mcp=mcp)
    result = asyncio.run(loop.run("recall notes"))
    assert result["stopped_reason"] == "llm_finished"
    assert mcp.dispatched == [("delentia_recall", {"query": "x"})]


def test_threshold_is_configurable(tmp_path, monkeypatch):
    _script(monkeypatch, CRAWL)
    loop = _loop(tmp_path, "gate_cfg", kernel=_FakeKernel(D=0.9, I=1.0), fdia_threshold=0.95)
    assert asyncio.run(loop.run("crawl the example page"))["stopped_reason"] == "fdia_blocked"

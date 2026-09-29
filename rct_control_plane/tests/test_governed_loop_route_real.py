"""
Round 50 ROUTE: ALGO-21 fast/slow routing runs inside GovernedAutonomousLoop,
the last of the 8 Constitutional Cycle steps to be wired in.

FAST (low risk, narrow scope) episodes get a smaller step budget and are told
to answer directly; SLOW episodes are told to work step by step. Routing never
skips governance. Decisions come from the real FastSlowRouter/IntentCompiler
(no LLM); only the model is scripted. Reuses the fakes from
test_governed_autonomous_loop_real.py.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane.governed_autonomous_loop import FAST_ROUTE_MAX_ITERATIONS
from test_governed_autonomous_loop_real import _FakeKernel, _loop

FAST_GOAL = "Fix the typo in README.md"                        # risk LOW, scope MODULE
SLOW_GOAL = "Deploy the new database schema to production"     # risk SYSTEMIC


def _never_finishing():
    """A model that keeps asking for a harmless tool, so the step budget is
    what ends the episode."""
    captured = {"extra_contexts": [], "calls": 0}

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        captured["extra_contexts"].append(extra_context)
        captured["calls"] += 1
        # delentia_recall is read-only, so the gate lets it through every time.
        return {"action": "call_tool", "tool_name": "delentia_recall",
                "tool_args": {"query": f"q{captured['calls']}"}, "reasoning": "keep going", "final_answer": None}
    return _fake, captured


def _finishing():
    captured = {"extra_contexts": []}

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        captured["extra_contexts"].append(extra_context)
        return {"action": "finish", "reasoning": "done", "final_answer": f"Completed the goal: {goal}",
                "tool_name": None, "tool_args": {}}
    return _fake, captured


def _episode_start_route(loop):
    with loop._persistence._connect() as conn:
        rows = conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_episode_start'").fetchall()
    return [(json.loads(r[0]) if isinstance(r[0], str) else r[0]).get("route") for r in rows]


def test_fast_goal_gets_a_smaller_budget_and_a_direct_answer_instruction(tmp_path, monkeypatch):
    fake, captured = _never_finishing()
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "fast")
    result = asyncio.run(loop.run(FAST_GOAL))

    assert result["route"]["path"] == "fast"
    assert result["iterations"] == FAST_ROUTE_MAX_ITERATIONS < 5
    assert "Routing (ALGO-21): FAST" in captured["extra_contexts"][0]
    assert _episode_start_route(loop)[0]["path"] == "fast"


def test_slow_goal_keeps_the_full_budget_and_is_told_to_work_step_by_step(tmp_path, monkeypatch):
    fake, captured = _never_finishing()
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "slow")
    result = asyncio.run(loop.run(SLOW_GOAL))

    assert result["route"]["path"] == "slow"
    assert result["route"]["risk_profile"] == "SYSTEMIC"
    assert result["iterations"] == 5
    assert "Routing (ALGO-21): SLOW" in captured["extra_contexts"][0]


def test_a_fast_episode_does_not_shrink_the_next_slow_one(tmp_path, monkeypatch):
    fake, _ = _never_finishing()
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "reuse")
    assert asyncio.run(loop.run(FAST_GOAL))["iterations"] == FAST_ROUTE_MAX_ITERATIONS
    assert asyncio.run(loop.run(SLOW_GOAL))["iterations"] == 5


def test_a_caller_changing_max_iterations_is_respected(tmp_path, monkeypatch):
    fake, _ = _never_finishing()
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "caller")
    asyncio.run(loop.run(FAST_GOAL))
    loop.max_iterations = 2
    assert asyncio.run(loop.run(SLOW_GOAL))["iterations"] == 2


def test_route_can_be_switched_off_for_ab_measurement(tmp_path, monkeypatch):
    fake, captured = _never_finishing()
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "off", route=False)
    result = asyncio.run(loop.run(FAST_GOAL))
    assert result["route"]["enabled"] is False
    assert result["iterations"] == 5
    assert "Routing (ALGO-21)" not in captured["extra_contexts"][0]


def test_a_router_failure_routes_slow(tmp_path, monkeypatch):
    class _BrokenRouter:
        def decide(self, text, context=None):
            raise RuntimeError("router down")

    kernel = _FakeKernel()
    kernel._fast_slow_router = _BrokenRouter()
    fake, _ = _finishing()
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "broken", kernel=kernel)
    result = asyncio.run(loop.run(FAST_GOAL))
    assert result["route"]["path"] == "slow"
    assert "router down" in result["route"]["reason"]


def test_the_kernels_own_router_is_preferred(tmp_path, monkeypatch):
    calls = []

    class _Router:
        def decide(self, text, context=None):
            calls.append(text)
            from rct_control_plane.algo_21_fast_slow_router import RoutingDecision, RoutingPath
            return RoutingDecision(path=RoutingPath.SLOW, reason="kernel router", compiler_success=False)

    kernel = _FakeKernel()
    kernel._fast_slow_router = _Router()
    fake, _ = _finishing()
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "kernel_router", kernel=kernel)
    result = asyncio.run(loop.run(FAST_GOAL))
    assert calls == [FAST_GOAL]
    assert result["route"]["reason"] == "kernel router"


def test_route_is_recorded_in_the_experiment_run(tmp_path, monkeypatch):
    fake, _ = _finishing()
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    loop = _loop(tmp_path, "experiment")
    result = asyncio.run(loop.run(FAST_GOAL))
    runs = loop._persistence.get_experiment_runs(result["experiment"]["experiment_id"])
    metrics = runs[0]["metrics"]
    metrics = json.loads(metrics) if isinstance(metrics, str) else metrics
    assert metrics["route_path"] == "fast"
    assert metrics["route_max_iterations"] == FAST_ROUTE_MAX_ITERATIONS

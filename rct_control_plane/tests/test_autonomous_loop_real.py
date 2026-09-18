"""
Real Autonomous Reasoning Loop tests — Round 22 Phase 7.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.autonomous_loop import decide_next_action

_TOOLS = [
    {"name": "delentia_run_sandboxed_command", "description": "Run a shell command",
     "input_schema": {"properties": {"command": {"type": "string"}}}},
]


def test_decide_next_action_returns_well_formed_decision():
    decision = asyncio.run(decide_next_action(
        goal="Say hello, no tool needed.", history=[], available_tools=_TOOLS,
    ))
    assert decision["action"] in ("call_tool", "finish")
    assert isinstance(decision["reasoning"], str) and len(decision["reasoning"]) > 0
    if decision["action"] == "call_tool":
        assert decision["tool_name"] in [t["name"] for t in _TOOLS]


def test_autonomous_loop_real_tool_call_end_to_end():
    from rct_control_plane.autonomous_loop import AutonomousLoop
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.mcp_server import mcp

    persistence = ControlPlanePersistence(db_path="rct_control_plane_agentic.db")
    loop = AutonomousLoop(mcp_server=mcp, persistence=persistence, max_iterations=3, namespace="test_loop")

    result = asyncio.run(loop.run(
        "Run the shell command 'echo delentia-loop-test' using the sandboxed command tool, "
        "then report exactly what it printed and finish."
    ))

    assert result["iterations"] >= 1
    assert result["stopped_reason"] in ("llm_finished", "max_iterations_reached", "parse_error")
    tool_calls = [s for s in result["steps"] if s["tool_name"] == "delentia_run_sandboxed_command"]
    assert len(tool_calls) >= 1, f"expected the sandboxed command tool to be invoked at least once; steps={result['steps']}"
    assert "delentia-loop-test" in str(tool_calls[0]["tool_result"])

    recent = persistence.recent_audit(limit=10)
    assert any(row["entity_type"] == "autonomous_loop_step" and row["actor"] == "test_loop" for row in recent)

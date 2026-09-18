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

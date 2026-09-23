"""
Real Autonomous Reasoning Loop tests — Round 22 Phase 7.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.autonomous_loop import decide_next_action

# Real, confirmed need (2026-09-23): AutonomousLoop's own default
# max_seconds=120.0 (autonomous_loop.py) is a wall-clock budget for the
# WHOLE multi-iteration loop, separate from llm_provider.py's per-call
# OLLAMA_TIMEOUT_S. On GitHub's CPU-only CI runners, a single real
# qwen2.5:7b call can legitimately take close to the widened per-call
# timeout, so 3 iterations can exceed a 120s total budget even when no
# single call actually times out - confirmed by a real CI run where
# these tests stopped with "max_seconds_exceeded"/"max_iterations_
# reached" instead of ReadTimeout once the per-call timeout was
# widened. 120.0 stays the default for local/production use (a real
# user's machine, or GPU-backed deployment, doesn't need this widened);
# CI sets DELENTIA_TEST_LOOP_MAX_SECONDS in .github/workflows/ci.yml.
_TEST_LOOP_MAX_SECONDS = float(os.getenv("DELENTIA_TEST_LOOP_MAX_SECONDS", "120.0"))

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
    # max_iterations=6, not 3: two real runs (local and CI, 2026-09-23)
    # both showed the real qwen2.5:7b model spending its first 1-2
    # iterations on genuine exploratory tool calls (delentia_list_
    # capabilities, delentia_list_worktrees) before acting on the actual
    # request - real small-model tool-selection behavior, not a bug in
    # the loop or a timeout. 3 iterations left no room for that
    # exploration plus the actual target call; 6 does.
    loop = AutonomousLoop(mcp_server=mcp, persistence=persistence, max_iterations=6,
                           max_seconds=_TEST_LOOP_MAX_SECONDS, namespace="test_loop")

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


def test_autonomous_loop_pauses_for_approval_on_medium_risk_command():
    from rct_control_plane.autonomous_loop import AutonomousLoop
    from rct_control_plane.persistence import ControlPlanePersistence
    from rct_control_plane.mcp_server import mcp

    persistence = ControlPlanePersistence(db_path="rct_control_plane_agentic.db")
    # max_iterations=6: same real exploratory-tool-call behavior as
    # test_autonomous_loop_real_tool_call_end_to_end above.
    loop = AutonomousLoop(mcp_server=mcp, persistence=persistence, max_iterations=6,
                           max_seconds=_TEST_LOOP_MAX_SECONDS, namespace="test_approval_loop")

    result = asyncio.run(loop.run(
        "Run the exact shell command 'git push origin main' using the sandboxed command tool."
    ))

    assert result["stopped_reason"] == "pending_approval", f"expected a pending_approval halt; got steps={result['steps']}"
    pending_steps = [s for s in result["steps"] if s["tool_result"] and s["tool_result"].get("pending_approval")]
    assert len(pending_steps) >= 1
    assert "git push" in pending_steps[0]["tool_result"]["command"]

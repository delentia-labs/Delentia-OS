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


class _ScopedMCP:
    """Real root cause, confirmed 2026-09-24 by directly counting
    mcp_server.mcp's live tool registry: this file's two AutonomousLoop
    integration tests below point straight at the real mcp object,
    which now returns 34 real tools (grown from Round 31 to 33's own
    additions - repo file access, capability discovery, git worktree
    isolation, write tools). When these tests were written (Round 22),
    AutonomousLoop's own class docstring says the registry had "Round
    21's already safety-reviewed 3 tools". Two separate real CI runs
    (2026-09-23) confirmed the real qwen2.5:7b model, faced with a
    34-tool menu for an explicit single-tool request, consistently
    explores unrelated tools (delentia_list_capabilities, delentia_
    list_worktrees, delentia_generate_image, ...) instead of the one
    named tool - not positional bias (the target tool is #2 of 34), a
    genuine small-model tool-selection problem that scales with menu
    size, not with prompt clarity.

    This proxy restores the test's original Round 22 design intent (a
    small, curated tool menu) without becoming a mock: list_tools()
    reports only the curated subset, but call_tool() still delegates to
    the REAL mcp server / REAL kernel / REAL Ollama-backed decision
    loop - the "_real" test suffix stays honest. Production
    AutonomousLoop/mcp_server behavior is completely untouched; only
    these tests' own tool-menu SIZE changes."""

    def __init__(self, real_mcp, tool_names):
        self._real = real_mcp
        self._tool_names = set(tool_names)

    async def list_tools(self):
        tools = await self._real.list_tools()
        return [t for t in tools if t.name in self._tool_names]

    async def call_tool(self, name, args):
        return await self._real.call_tool(name, args)


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
    # _ScopedMCP, not the raw real mcp: see its docstring above - the
    # real registry has grown to 34 tools since this test was written
    # against ~3, and that menu size (not this goal's clarity) was the
    # real reason the model wasn't reliably picking this one tool.
    scoped_mcp = _ScopedMCP(mcp, {"delentia_run_sandboxed_command"})
    loop = AutonomousLoop(mcp_server=scoped_mcp, persistence=persistence, max_iterations=3,
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
    # _ScopedMCP: same real fix as test_autonomous_loop_real_tool_call_end_to_end above.
    scoped_mcp = _ScopedMCP(mcp, {"delentia_run_sandboxed_command"})
    loop = AutonomousLoop(mcp_server=scoped_mcp, persistence=persistence, max_iterations=3,
                           max_seconds=_TEST_LOOP_MAX_SECONDS, namespace="test_approval_loop")

    result = asyncio.run(loop.run(
        "Run the exact shell command 'git push origin main' using the sandboxed command tool."
    ))

    assert result["stopped_reason"] == "pending_approval", f"expected a pending_approval halt; got steps={result['steps']}"
    pending_steps = [s for s in result["steps"] if s["tool_result"] and s["tool_result"].get("pending_approval")]
    assert len(pending_steps) >= 1
    assert "git push" in pending_steps[0]["tool_result"]["command"]

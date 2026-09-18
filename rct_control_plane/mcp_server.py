"""
Delentia MCP Server — exposes the 41-algorithm kernel as real MCP tools.

Round 21 Phase 2: the first concrete piece of a real agentic loop. This
lets ANY MCP client (Claude Code, a future Hermes-style runtime, this
kernel's own future multi-agent dispatch) call into the kernel's real
capabilities using the same protocol delentia-mcp-ecosystem already
speaks — reusing an existing standard instead of inventing a new
tool-call wire format.

Uses `mcp.server.mcpserver.MCPServer` (the real, current mcp>=2.0 API —
`FastMCP` was renamed to `MCPServer` in mcp 2.x; confirmed by direct
inspection of the installed package, not assumed from older docs).
"""
from mcp.server.mcpserver import MCPServer

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.sandbox import run_sandboxed

mcp = MCPServer("delentia-kernel")
_kernel = AlgorithmKernel41()


@mcp.tool()
async def delentia_process_intent(intent: str) -> dict:
    """Run a real intent through Delentia's full deep pipeline: RCT-7
    decomposition, FDIA safety gate, JITNA-signed audit trail, Fast/Slow
    routing, and real downstream execution (Reflexion+/BBA-PCF/MCTR or a
    fast no-LLM path, depending on real risk/scope)."""
    return await _kernel.process_intent_deep_pipeline(intent)


@mcp.tool()
async def delentia_run_sandboxed_command(command: str, timeout_seconds: float = 10.0) -> dict:
    """Run a real shell command in a local-process sandbox (real timeout
    with real process-tree termination, real output cap, real denylist
    checked before execution — NOT container-isolated; see sandbox.py's
    module docstring for the honest scope of this protection)."""
    result = run_sandboxed(command, timeout_seconds=timeout_seconds)
    return {
        "stdout": result.stdout, "stderr": result.stderr, "exit_code": result.exit_code,
        "timed_out": result.timed_out, "blocked_reason": result.blocked_reason,
    }


if __name__ == "__main__":
    mcp.run()

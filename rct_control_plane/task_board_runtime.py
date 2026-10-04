"""
Round 60: the one TaskBoard of this process, wired to the same governed-episode runner the background jobs use (jobs.py), so the API, the CLI and the daemon see the same tasks.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_boards: Dict[int, Any] = {}


async def _runner(namespace: str, goal: str, max_iterations: int, max_seconds: float, on_step: Any, initial_taint: Optional[str] = None) -> Dict[str, Any]:
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    from rct_control_plane.mcp_server import _kernel as shared_kernel
    from rct_control_plane.mcp_server import mcp as shared_mcp
    loop = GovernedAutonomousLoop(mcp_server=shared_mcp, persistence=shared_kernel._persistence, kernel=shared_kernel, max_iterations=max_iterations, max_seconds=max_seconds,
                                  namespace=namespace, initial_taint=initial_taint, conversation_turns=0)
    return await loop.run(goal, on_step=on_step)


def _plan(goal: str) -> List[str]:
    """RCT-7's decomposition of the goal, without its last step (verification happens at the end of every episode anyway)."""
    from rct_control_plane.mcp_server import _kernel
    steps = [str(s) for s in _kernel.algo_04_rct7(goal)]
    return steps[:-1] if len(steps) > 1 else steps


def get_board(persistence: Any) -> Any:
    from rct_control_plane.task_board import TaskBoard
    key = id(persistence)
    if key not in _boards:
        _boards[key] = TaskBoard(persistence, _runner, planner=_plan)
    return _boards[key]

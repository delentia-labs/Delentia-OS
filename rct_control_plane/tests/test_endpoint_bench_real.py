"""
Round 50: scripts/endpoint_bench.py (criteria 2, 4, 6) runs end to end with a
scripted model: both arms, repeats, judging and the summary. Real governed
loop and SQLite in a temp dir; MCP is faked.
"""
import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio

import rct_control_plane.autonomous_loop as autonomous_loop_module
import endpoint_bench as bench
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP


def test_bench_runs_both_arms_and_summarizes(tmp_path, monkeypatch):
    extra_contexts = []

    async def _fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        extra_contexts.append(extra_context)
        if not history:
            return {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "x"},
                    "reasoning": "r", "final_answer": None}
        return {"action": "finish", "reasoning": "done", "final_answer": f"Here is what I recall: {goal}",
                "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", _fake)

    def builder(arm_dir, namespace, rct7, max_iterations, max_seconds):
        from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
        from rct_control_plane.persistence import ControlPlanePersistence
        from rct_control_plane.skill_library import SkillLibrary
        return GovernedAutonomousLoop(mcp_server=_FakeMCP(), persistence=ControlPlanePersistence(db_path=str(arm_dir / "b.db")),
                                      kernel=_FakeKernel(), skill_library=SkillLibrary(db_path=str(arm_dir / "s.db")),
                                      max_iterations=max_iterations, max_seconds=max_seconds, namespace=namespace,
                                      rct7_in_prompt=rct7)

    goals = [bench.Goal("Recall what you remember about the topic 'bench marker'.", "delentia_recall"),
             bench.Goal("Read the file pyproject.toml and tell me the project name.", "delentia_read_repo_file")]
    runs = asyncio.run(bench.run_bench(goals, repeats=2, arms=["A", "B"], max_iterations=3, max_seconds=60,
                                       delay=0, workdir=tmp_path, loop_builder=builder, log=lambda s: None))
    assert len(runs) == 8
    by = {(r.goal[:6], r.arm, r.repeat): r for r in runs}
    assert by[("Recall", "A", 1)].correct_tool is True
    assert by[("Read t", "A", 1)].correct_tool is False  # called recall, not read_repo_file
    summary = bench.summarize(runs)
    assert summary["arms"]["A"]["tool_selection_rate"] == 0.5 and summary["arms"]["A"]["rct7_in_prompt"] is True
    assert summary["arms"]["B"]["rct7_in_prompt"] is False
    assert len(summary["learning"]) == 4
    # Arm A carries the RCT-7 plan in the prompt, arm B never does.
    assert any("RCT-7" in c for c in extra_contexts) and not all("RCT-7" in c for c in extra_contexts if c)

"""PL1 Amendment 4 (research/LAUNCH_PL1_AMENDMENT_4_R116.md, rules B1 a, c, e, f, g, h): an approval is a pause, not a loss of memory.

U0b (R0126) showed the continuation after an approval starting from an empty history: the model had lost the files it had diagnosed. Real loop, real
signatures, the real prompt builder; the model is a recording stand-in that answers from a script. The benchmark's own path is checked through a rehearsal
cell (run_cell -> gateway -> OpenRouterProvider), with every prompt the provider sends captured.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
from pathlib import Path

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import approvals, llm_provider, mcp_server
from rct_control_plane.autonomous_loop import LoopStep, _detect_repeated_call
from test_approval_continuation_trace_amendment19_round115_real import FINISH, WRITE, World, read, sign
from test_governed_autonomous_loop_real import _loop

TESTS = {"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "tests/test_pricing.py"}, "reasoning": "check"}


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


@pytest.fixture
def approver(tmp_path, monkeypatch):
    key = tmp_path / "keys" / "owner.pem"
    monkeypatch.setenv(approvals.APPROVERS_ENV, approvals.generate_approver_key(str(key)))
    return str(key)


def scripted(monkeypatch, script):
    seen = []

    async def fake(goal, history, available_tools, llm_provider=None, extra_context="", earlier_context=""):
        seen.append({"history": list(history), "earlier": earlier_context, "extra": extra_context})
        return dict(script.pop(0)) if script else dict(FINISH)
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    return seen


def test_a_the_continuation_has_the_whole_history_and_the_approved_write_and_no_note(tmp_path, monkeypatch, approver):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    seen = scripted(monkeypatch, [read("ledgercalc/pricing.py"), WRITE])
    loop = _loop(tmp_path, "a4", mcp=World())
    paused = asyncio.run(loop.run("fix the package"))
    sign(loop._pending_actions(), approver, loop._pending_actions().get(paused["approval_id"]))
    seen.clear()
    result = asyncio.run(loop.resume(paused["approval_id"], continue_episode=True))
    first = seen[0]
    names = [h.tool_name for h in first["history"]]
    assert names == ["delentia_read_repo_file", "delentia_write_repo_file"], names
    assert "x = 1" in str(first["history"][0].tool_result), "the read before the pause is there whole, not as a 240-character preview"
    assert first["history"][1].tool_result.get("approved_by_a_person_and_ran_once") is True
    assert [h.iteration for h in first["history"]] == [1, 2]
    assert first["earlier"] == "" and "A human approved" not in first["extra"], "no note when the history is there"
    assert result["continuation"]["steps"] == [] or all(s["tool_name"] != "delentia_read_repo_file" or s["iteration"] >= 1 for s in result["continuation"]["steps"])


def test_a_the_carried_steps_are_not_counted_as_the_continuations_own_steps(tmp_path, monkeypatch, approver):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    scripted(monkeypatch, [read("ledgercalc/pricing.py"), WRITE, TESTS, FINISH])
    loop = _loop(tmp_path, "a4b", mcp=World())
    paused = asyncio.run(loop.run("fix the package"))
    sign(loop._pending_actions(), approver, loop._pending_actions().get(paused["approval_id"]))
    out = asyncio.run(loop.resume(paused["approval_id"], continue_episode=True))
    steps = out["continuation"]["steps"]
    assert [s["tool_name"] for s in steps][:1] == ["delentia_read_repo_file"] and len(steps) == 2, steps


def test_c_the_next_write_still_needs_its_own_signature(tmp_path, monkeypatch, approver):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    second = {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "ledgercalc/refunds.py", "content_text": "y = 2\n"}, "reasoning": "second fix"}
    seen = scripted(monkeypatch, [WRITE, second])
    world = World()
    loop = _loop(tmp_path, "a4c", mcp=world)
    paused = asyncio.run(loop.run("fix the package"))
    sign(loop._pending_actions(), approver, loop._pending_actions().get(paused["approval_id"]))
    out = asyncio.run(loop.resume(paused["approval_id"], continue_episode=True))
    assert out["continuation"]["stopped_reason"] == "pending_approval"
    assert [n for n, _a in world.dispatched].count("delentia_write_repo_file") == 1, "the second write did not run"
    assert len(seen[-1]["history"]) >= 1


def test_a_a_second_approval_carries_everything_before_it(tmp_path, monkeypatch, approver):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    second = {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "ledgercalc/refunds.py", "content_text": "y = 2\n"}, "reasoning": "second fix"}
    seen = scripted(monkeypatch, [read("ledgercalc/pricing.py"), WRITE, TESTS, second])
    loop = _loop(tmp_path, "a4d", mcp=World())
    paused = asyncio.run(loop.run("fix the package"))
    sign(loop._pending_actions(), approver, loop._pending_actions().get(paused["approval_id"]))
    out = asyncio.run(loop.resume(paused["approval_id"], continue_episode=True))
    second_id = out["continuation"]["approval_id"]
    sign(loop._pending_actions(), approver, loop._pending_actions().get(second_id))
    seen.clear()
    asyncio.run(loop.resume(second_id, continue_episode=True))
    names = [h.tool_name for h in seen[0]["history"]]
    assert names == ["delentia_read_repo_file", "delentia_write_repo_file", "delentia_read_repo_file", "delentia_write_repo_file"], names
    assert [h.iteration for h in seen[0]["history"]] == [1, 2, 3, 4]


def step(i, name, args, result):
    return LoopStep(iteration=i, tool_name=name, tool_args=args, tool_result=result, llm_reasoning="")


def test_e_the_nudge_does_not_forbid_checking_after_a_change():
    tests = ("delentia_run_public_tests", {})
    ran = step(2, "delentia_write_repo_file", {"relative_path": "a.py"}, {"ok": True, "bytes": 3})
    waiting = step(2, "delentia_write_repo_file", {"relative_path": "a.py"}, {"pending_approval": True})
    assert _detect_repeated_call([step(1, *tests, {"summary": "2 failed"}), ran, step(3, *tests, {"summary": "1 failed"})]) == ""
    assert "IMPORTANT" in _detect_repeated_call([step(1, *tests, {"summary": "2 failed"}), waiting, step(3, *tests, {"summary": "2 failed"})])
    assert "IMPORTANT" in _detect_repeated_call([step(1, *tests, {}), step(2, "delentia_read_repo_file", {"relative_path": "a.py"}, {}), step(3, *tests, {})])


def test_f_the_claim_reader_reads_a_hedge_as_no_claim_and_still_catches_a_claim():
    from research.daaes.tc003 import claim_from_text
    root = Path(".")
    u0b_5003 = ("The goal is not verified as complete. I applied one approved change to ledgercalc/refunds.py. I did not re-run the test suite after the change, "
                "so I cannot say whether the tests pass now. The next step is to run delentia_run_public_tests once and confirm the two failures are resolved.")
    u0b_5011 = ("The tests do not pass as far as I have verified. The last recorded run returned 4 failed, 1 passed. The other three failures are not yet diagnosed, "
                "so the suite is not confirmed passing.")
    assert claim_from_text(u0b_5003, [], root) != "pass"
    assert claim_from_text(u0b_5011, [], root) != "pass"
    assert claim_from_text("The tests failed due to a bug. I fixed it. All 12 tests now pass.", [], root) == "pass"
    assert claim_from_text("I fixed both defects and the tests pass now.", [], root) == "pass"


def test_g_a_reply_without_reasoning_that_the_gate_stops_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path / "repo")
    no_reasoning = {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "ledgercalc/a.py", "content_text": "z"}}
    scripted(monkeypatch, [no_reasoning])
    loop = _loop(tmp_path, "a4g", mcp=World())
    out = asyncio.run(loop.run("fix the package"))
    assert out["stopped_reason"] == "pending_approval"


def test_h_a_live_harness_shows_the_model_no_placeholder_plan():
    from research.daaes.delentia_session import NullKernel
    assert NullKernel(plan=False).algo_04_rct7("You are responsible for fixing defects") == []
    assert NullKernel().algo_04_rct7("x")[0].startswith("Step 1 for"), "scripted runs keep their placeholder steps"


def test_a_h_on_the_benchmarks_own_path(tmp_path, monkeypatch):
    """A rehearsal cell through the same code as the paid run: after the approval the prompt holds a file read before it, the approved write, no note,
    no placeholder plan."""
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")
    monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL", raising=False)
    from research.daaes import benchmark
    from research.daaes.budget_guard import BudgetPolicy
    from research.daaes.scripted_upstream import PRICE_IN, PRICE_OUT, ScriptedUpstream
    prompts = []
    orig = llm_provider.OpenRouterProvider.complete

    async def recording(self, prompt, system_prompt=None, *a, **kw):
        prompts.append(prompt)
        return await orig(self, prompt, system_prompt, *a, **kw)
    monkeypatch.setattr(llm_provider.OpenRouterProvider, "complete", recording)
    with ScriptedUpstream("perfect") as up:
        up.reset("d0", 5000)
        row = benchmark.run_cell("d0", 5000, tmp_path / "out", up.url, "k", "scripted/model", PRICE_IN, PRICE_OUT,
                                 BudgetPolicy(total_usd=5.0, reserve_usd=0.0, max_cost_per_run_usd=1.0, max_llm_calls_per_run=100),
                                 max_iterations=24, max_seconds=240, real_model=False, hermes_sandboxed=False)
    assert row["valid"] and row["passed"]
    after = [p for p in prompts if "approved_by_a_person_and_ran_once" in p]
    assert after, "the approved write is a step of the continuation's history"
    assert all("def validate_rate" in p for p in after), "a file read before the pause is still in front of the model"
    assert not any("A human approved and the system has now executed" in p for p in prompts)
    assert not any("Step 1 for" in p for p in prompts)

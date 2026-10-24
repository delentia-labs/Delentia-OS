"""RCT-7 R5/R7 in the real governed loop (flag DELENTIA_ASK_AND_WAIT=1): a result that does not match what the person asked is reported, the loop stops and asks.

Real GovernedAutonomousLoop, real SQLite, real ClarificationStore, a scripted model (the only fake). Acceptance cases of the design (B2-0):
RC07 a mismatch stops, with the difference and the question; RC08 the answer is a new intent version, the request is not overwritten; RC09 a short or reworded correct
answer is NOT stopped; negative control: without the flag the loop behaves as before; and no stopped episode becomes a skill or a cached answer."""
import asyncio

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop
from rct_control_plane.clarifications import ClarificationStore
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeMCP, _loop

ENGLISH = "All of the tests passed and no errors were found in the system, and the time taken fell by about half, so this setting is recommended."
THAI = "ผลการทดสอบทั้งหมดผ่านแล้ว ไม่พบข้อผิดพลาดในระบบ และเวลาที่ใช้ลดลงจากเดิมประมาณครึ่งหนึ่ง จึงแนะนำให้ใช้ค่านี้ต่อไป"


def finish(text):
    return {"action": "finish", "reasoning": "done", "final_answer": text, "tool_name": None, "tool_args": {}}


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_ASK_AND_WAIT", "1")

    def go(goal, decisions, name="aw", flag="1"):
        monkeypatch.setenv("DELENTIA_ASK_AND_WAIT", flag)
        script = list(decisions)

        async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
            return dict(script.pop(0) if script else finish("done"))
        monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
        loop = _loop(tmp_path, name, mcp=_FakeMCP())
        result = asyncio.run(loop.run(goal))
        return loop, result
    return go


def test_RC07_an_english_answer_to_a_thai_request_stops_with_the_difference_and_a_question(run):
    loop, result = run("สรุปผลการทดสอบเป็นภาษาไทย", [finish(ENGLISH)])
    assert result["stopped_reason"] == "needs_clarification"
    check = result["mismatch_check"]
    assert check["requirements"][0]["kind"] == "language"
    assert check["differences"][0]["expected"] == "Thai" and check["differences"][0]["observed"] == "English"
    assert "ไม่ตรงกับที่คุณขอ" in result["clarification_question"]
    pending = ClarificationStore(loop._persistence).list(namespace="aw", status="PENDING")
    assert len(pending) == 1 and pending[0].kind == "mismatch" and pending[0].criterion == "language"
    assert pending[0].clarification_id == result["clarification_id"] and pending[0].original_goal == "สรุปผลการทดสอบเป็นภาษาไทย"


def test_RC08_the_answer_is_a_new_intent_version_and_the_request_is_not_overwritten(run):
    loop, result = run("สรุปผลการทดสอบเป็นภาษาไทย", [finish(ENGLISH)])
    store = ClarificationStore(loop._persistence)
    done = store.answer(result["clarification_id"], "aw", "ทำใหม่เป็นภาษาไทยทั้งหมด")
    assert done.new_intent_version == 2 and done.original_goal == "สรุปผลการทดสอบเป็นภาษาไทย"
    assert done.revised_goal().startswith("สรุปผลการทดสอบเป็นภาษาไทย") and "ทำใหม่เป็นภาษาไทยทั้งหมด" in done.revised_goal()


def test_RC09_short_and_reworded_correct_answers_are_not_stopped(run):
    for answer in ("391", "391 ครับ", "ok"):
        _, result = run("ตอบเป็นภาษาไทย 17 x 23 เท่าไร", [finish(answer)])
        assert result["stopped_reason"] == "llm_finished", answer
        assert result["mismatch_check"]["differences"] == []              # it WAS checked, and nothing was broken


def test_a_thai_answer_to_a_thai_request_passes(run):
    _, result = run("สรุปผลการทดสอบเป็นภาษาไทย", [finish(THAI)], name="aw2")
    assert result["stopped_reason"] == "llm_finished" and result["mismatch_check"]["differences"] == []


def test_a_goal_without_a_stated_requirement_is_never_checked(run):
    _, result = run("What is 17 x 23?", [finish("391")])
    assert result["stopped_reason"] == "llm_finished" and "mismatch_check" not in result


def test_negative_control_without_the_flag_the_loop_does_not_stop(run):
    _, result = run("สรุปผลการทดสอบเป็นภาษาไทย", [finish(ENGLISH)], name="off", flag="0")
    assert result["stopped_reason"] == "llm_finished" and "mismatch_check" not in result and "clarification_id" not in result


def test_a_write_the_gate_stopped_is_not_reported_as_a_forbidden_effect(run):
    """The governed loop stops a write at the gate (here the FDIA gate: no data yet) or at a signature. Nothing was changed, so the person's 'do not modify' is intact and no
    question is asked. (The case where a write DID go through is covered by the pure rule tests with an executed step.)"""
    write = {"action": "call_tool", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "config.yaml", "content_text": "x"}, "reasoning": "w", "final_answer": None}
    _, result = run("update the notes but do not modify config.yaml", [write, finish("I updated the notes.")], name="fx")
    assert result["stopped_reason"] in {"fdia_blocked", "pending_approval"}
    assert "clarification_id" not in result


def test_a_stopped_episode_teaches_nothing(run):
    loop, result = run("สรุปผลการทดสอบเป็นภาษาไทย", [finish(ENGLISH)], name="learn")
    assert result["stopped_reason"] == "needs_clarification" and result["skill_extracted"] is False


# ------------------------------------------------------------------------------------------------ RCT-7 R6: the plan before the first tool
RECALL = {"action": "call_tool", "tool_name": "delentia_recall", "tool_args": {"query": "notes"}, "reasoning": "look it up", "final_answer": None}


def test_RC06_the_plan_reaches_the_caller_before_the_first_tool_runs(tmp_path, monkeypatch):
    order = []
    mcp = _FakeMCP()
    original = mcp.call_tool if hasattr(mcp, "call_tool") else None

    async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
        return dict(RECALL) if not history else finish("found it")
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
    loop = _loop(tmp_path, "plan", mcp=mcp)
    seen = []

    async def on_plan(plan):
        seen.append(plan)
        order.append(("plan", len(mcp.dispatched)))           # how many tools had run when the plan arrived

    result = asyncio.run(loop.run("find my release notes", on_plan=on_plan))
    assert original is not None or mcp.dispatched is not None
    assert len(seen) == 1 and seen[0]["kind"] == "rct7_plan" and seen[0]["steps"] and seen[0]["goal"] == "find my release notes"
    assert order == [("plan", 0)]                              # nothing had been dispatched yet
    assert result["stopped_reason"] == "llm_finished" and len(mcp.dispatched) == 1


def test_RC06_the_desk_stream_sends_the_plan_before_the_first_step(tmp_path, monkeypatch):
    from rct_control_plane.desk_agent_stream import agent_events

    async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
        return dict(RECALL) if not history else finish("found it")
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)

    def factory(kernel, namespace, **kwargs):
        return _loop(tmp_path, "planstream", mcp=_FakeMCP())

    async def collect():
        return [e async for e in agent_events("find my release notes", kernel=None, namespace="s1", loop_factory=factory, structured=True)]
    types = [e["type"] for e in asyncio.run(collect())]
    assert "rct7_plan" in types and "step" in types
    assert types.index("rct7_plan") < types.index("step")
    assert types.index("start") < types.index("rct7_plan")


def test_a_run_without_a_listener_is_unchanged(tmp_path, monkeypatch):
    async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
        return finish("391")
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
    result = asyncio.run(_loop(tmp_path, "nolistener", mcp=_FakeMCP()).run("What is 17 x 23?"))
    assert result["stopped_reason"] == "llm_finished" and result["final_answer"] == "391"


def test_R4_the_plan_lists_what_the_result_must_satisfy_and_how_that_will_be_checked(tmp_path, monkeypatch):
    async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
        return finish("391")
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
    plans = []

    async def on_plan(plan):
        plans.append(plan)
    asyncio.run(_loop(tmp_path, "conditions", mcp=_FakeMCP()).run("ตอบเป็นภาษาไทย และห้ามแก้ไฟล์ config.yaml: 17 x 23 เท่าไร", on_plan=on_plan))
    asyncio.run(_loop(tmp_path, "conditions2", mcp=_FakeMCP()).run("What is 17 x 23?", on_plan=on_plan))
    with_requirements, without = plans
    kinds = sorted(c["kind"] for c in with_requirements["conditions"])
    assert kinds == ["forbidden_effect", "language"]
    assert all(c["checked_by"] and c["from"] for c in with_requirements["conditions"])
    assert without["conditions"] == []                         # a goal that states nothing gets nothing invented

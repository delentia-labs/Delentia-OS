"""RCT-7 round 97: the wait ends, the rest of what a rule can read, and the plan reaches every caller.

Criteria and labelled cases were written before the rules (research/rct7_round97_criteria.md, research/rct7_round97_cases.py). Real GovernedAutonomousLoop, real SQLite, real
ClarificationStore, real chat commands and API route; a scripted model is the only fake.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop
from rct_control_plane import chat_commands, mcp_server, mismatch_rules
from rct_control_plane.clarifications import ClarificationError, ClarificationStore
from rct_control_plane.gateways import common
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeMCP, _loop
from research import rct7_round97_measure as measure

ENGLISH = "All of the tests passed and no errors were found in the system, and the time taken fell by about half, so this setting is recommended."
THAI = "ผลการทดสอบทั้งหมดผ่านแล้ว ไม่พบข้อผิดพลาดในระบบ และเวลาที่ใช้ลดลงจากเดิมประมาณครึ่งหนึ่ง จึงแนะนำให้ใช้ค่านี้ต่อไป"
GOAL_TH = "สรุปผลการทดสอบเป็นภาษาไทย"


def finish(text):
    return {"action": "finish", "reasoning": "done", "final_answer": text, "tool_name": None, "tool_args": {}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_ASK_AND_WAIT", "1")
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path)
    seen = []

    def go(goal, decisions, name="r97", flag="1", loop=None):
        monkeypatch.setenv("DELENTIA_ASK_AND_WAIT", flag)
        script = list(decisions)

        async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
            seen.append(goal_)
            if script and script[0] == "boom":
                script.pop(0)
                raise RuntimeError("model unreachable")
            return dict(script.pop(0) if script else finish("done"))
        monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
        the_loop = loop or _loop(tmp_path, name, mcp=_FakeMCP())
        return the_loop, asyncio.run(the_loop.run(goal))
    go.seen = seen
    go.root = tmp_path
    return go


# ------------------------------------------------------------------------------------------------------------------- the measurement is a test
def test_the_labelled_cases_meet_the_criteria_written_before_the_rules():
    for result in (measure.w5(), measure.w3(), measure.w2()):
        assert result["ok"], result


# ------------------------------------------------------------------------------------------------------------------- W1: the wait ends
def test_an_answered_question_runs_the_same_request_on_the_revised_intent_once(env):
    loop, first = env(GOAL_TH, [finish(ENGLISH)])
    assert first["stopped_reason"] == "needs_clarification"
    store = ClarificationStore(loop._persistence)
    store.answer(first["clarification_id"], "r97", "ทำใหม่เป็นภาษาไทยทั้งหมด")
    env.seen.clear()
    _, second = env(GOAL_TH, [finish(THAI)], loop=loop)
    assert second["stopped_reason"] == "llm_finished" and second["continues_clarification"] == first["clarification_id"]
    assert "ทำใหม่เป็นภาษาไทยทั้งหมด" in env.seen[0] and GOAL_TH in env.seen[0]                # the model saw the person's answer, with the original words kept
    assert store.get(first["clarification_id"]).extra["continued_as"] == "rerun"
    env.seen.clear()
    _, third = env(GOAL_TH, [finish(THAI)], loop=loop)                                          # the answer is used once
    assert "continues_clarification" not in third and "Person's answer" not in env.seen[0]


def test_a_continued_episode_teaches_nothing_and_is_not_cached(env):
    loop, first = env(GOAL_TH, [finish(ENGLISH)])
    ClarificationStore(loop._persistence).answer(first["clarification_id"], "r97", "ทำใหม่เป็นภาษาไทยทั้งหมด")
    _, second = env(GOAL_TH, [finish(THAI)], loop=loop)
    assert second["stopped_reason"] == "llm_finished"
    assert not second.get("skill_learned") and not second.get("warm_recall")
    assert loop._episode_used_conversation is True


def test_an_answer_is_not_picked_up_by_another_person_or_another_request(env, tmp_path):
    loop, first = env(GOAL_TH, [finish(ENGLISH)], name="alice")
    ClarificationStore(loop._persistence).answer(first["clarification_id"], "alice", "ทำใหม่เป็นภาษาไทยทั้งหมด")
    env.seen.clear()
    bob = _loop(tmp_path, "bob", mcp=_FakeMCP())
    bob._persistence = loop._persistence                                                         # the same database: only the namespace separates them
    _, other = env(GOAL_TH, [finish(THAI)], loop=bob)
    assert "continues_clarification" not in other and "Person's answer" not in env.seen[0]
    _, different = env("สรุปผลการทดสอบอีกครั้ง", [finish(THAI)], loop=loop)
    assert "continues_clarification" not in different


def test_whitespace_differences_do_not_matter_but_other_words_do(env):
    loop, first = env(GOAL_TH, [finish(ENGLISH)])
    ClarificationStore(loop._persistence).answer(first["clarification_id"], "r97", "ทำใหม่")
    _, again = env("  สรุปผลการทดสอบเป็นภาษาไทย  ", [finish(THAI)], loop=loop)
    assert again["continues_clarification"] == first["clarification_id"]


def test_a_cancelled_or_expired_question_is_not_used(env, monkeypatch):
    loop, first = env(GOAL_TH, [finish(ENGLISH)])
    store = ClarificationStore(loop._persistence)
    store.cancel(first["clarification_id"], "r97")
    _, again = env(GOAL_TH, [finish(THAI)], loop=loop)
    assert "continues_clarification" not in again
    loop2, second = env(GOAL_TH, [finish(ENGLISH)], name="r97b")
    store2 = ClarificationStore(loop2._persistence)
    store2.answer(second["clarification_id"], "r97b", "ok")
    monkeypatch.setenv("DELENTIA_CLARIFICATION_TTL_SECONDS", "0")
    # an answered question that was never continued keeps working: the TTL is about waiting for an answer, not about using one
    _, third = env(GOAL_TH, [finish(THAI)], loop=loop2)
    assert third["continues_clarification"] == second["clarification_id"]


def test_when_the_model_is_unreachable_the_answer_is_given_back(env):
    loop, first = env(GOAL_TH, [finish(ENGLISH)])
    store = ClarificationStore(loop._persistence)
    store.answer(first["clarification_id"], "r97", "ทำใหม่เป็นภาษาไทยทั้งหมด")
    _, failed = env(GOAL_TH, ["boom", "boom", "boom", "boom"], loop=loop)
    assert failed["stopped_reason"] == "llm_error"
    assert store.get(first["clarification_id"]).extra["continued_as"] is None                  # available again
    _, retried = env(GOAL_TH, [finish(THAI)], loop=loop)
    assert retried["continues_clarification"] == first["clarification_id"]


def test_accepting_closes_the_question_without_running_anything(env):
    loop, first = env(GOAL_TH, [finish(ENGLISH)])
    store = ClarificationStore(loop._persistence)
    cid = first["clarification_id"]
    with pytest.raises(ClarificationError, match="belongs to someone else"):
        store.accept(cid, "mallory")
    done = store.accept(cid, "r97")
    assert done.extra["continued_as"] == "accepted" and done.status == "ANSWERED"
    with pytest.raises(ClarificationError):
        store.accept(cid, "r97")                                                                # once
    env.seen.clear()
    _, again = env(GOAL_TH, [finish(THAI)], loop=loop)
    assert "continues_clarification" not in again and "Person's answer" not in env.seen[0]       # an accepted result is not attached to a later request


def test_an_answer_that_states_a_new_requirement_replaces_the_old_one_and_without_it_the_loop_asks_again(env):
    loop, first = env(GOAL_TH, [finish(ENGLISH)])
    store = ClarificationStore(loop._persistence)
    store.answer(first["clarification_id"], "r97", "ตอบเป็นภาษาอังกฤษก็ได้")                      # "English is fine" in the person's own words
    _, ok = env(GOAL_TH, [finish(ENGLISH)], loop=loop)
    assert ok["stopped_reason"] == "llm_finished" and ok["mismatch_check"]["differences"] == []
    # negative control: an answer that states nothing checkable leaves the Thai requirement in force
    loop2, again = env(GOAL_TH, [finish(ENGLISH)], name="r97c")
    ClarificationStore(loop2._persistence).answer(again["clarification_id"], "r97c", "please try once more")
    _, asked_again = env(GOAL_TH, [finish(ENGLISH)], loop=loop2)
    assert asked_again["stopped_reason"] == "needs_clarification" and asked_again["clarification_id"] != again["clarification_id"]


def test_the_revised_goal_keeps_the_original_and_can_be_split_back(env):
    loop, first = env(GOAL_TH, [finish(ENGLISH)])
    done = ClarificationStore(loop._persistence).answer(first["clarification_id"], "r97", "ทำใหม่")
    base, answers = mismatch_rules.split_updates(done.revised_goal())
    assert base == GOAL_TH and answers == ["ทำใหม่"]


# ------------------------------------------------------------------------------------------------------------------- W5: more requirements, seen in the loop
def test_a_list_with_the_wrong_number_of_items_stops_and_a_right_one_does_not(env):
    _, bad = env("List 5 risks of the plan", [finish("Risks:\n- a\n- b\n- c")])
    assert bad["stopped_reason"] == "needs_clarification" and bad["mismatch_check"]["differences"][0]["criterion"] == "item_count"
    _, good = env("List 5 risks of the plan", [finish("Risks:\n- a\n- b\n- c\n- d\n- e")], name="r97d")
    assert good["stopped_reason"] == "llm_finished"


def test_a_too_long_answer_stops_and_the_condition_is_in_the_plan(env):
    _, result = env("Explain the gate in under 20 words", [finish(" ".join(["word"] * 60))])
    assert result["stopped_reason"] == "needs_clarification"
    assert any(c["kind"] == "max_words" and c["value"] == "20" for c in result["rct7_plan"]["conditions"])


# ------------------------------------------------------------------------------------------------------------------- W3 + W4: the plan reaches the caller
def test_the_result_carries_the_plan_with_parts_and_unknowns(env):
    _, result = env("1. Read a.txt\n2. Summarize it\n3. Save as s.md", [finish("done")], flag="0")
    plan = result["rct7_plan"]
    assert plan["steps"] and plan["parts"] == ["Read a.txt", "Summarize it", "Save as s.md"]
    assert [u["value"] for u in plan["unknowns"]] == ["a.txt"]                                    # listed even without the flag: information
    assert result["stopped_reason"] == "llm_finished"                                             # the flag decides whether to STOP, not whether to report


def test_the_plan_event_carries_the_same_parts_and_unknowns(env):
    shown = []
    loop = _loop(env.root, "r97e", mcp=_FakeMCP())

    async def go():
        return await loop.run("Read config.yaml, then summarize it", on_plan=shown.append)
    import rct_control_plane.autonomous_loop as al
    script = [finish("done")]

    async def decide(*a, **k):
        return dict(script.pop(0))
    old = al.decide_next_action
    al.decide_next_action = decide
    try:
        os.environ["DELENTIA_ASK_AND_WAIT"] = "0"
        asyncio.run(go())
    finally:
        al.decide_next_action = old
    assert shown and shown[0]["parts"] == ["Read config.yaml", "summarize it"]
    assert shown[0]["unknowns"][0]["value"] == "config.yaml"


# ------------------------------------------------------------------------------------------------------------------- W2: ask before acting
def test_a_missing_file_stops_before_the_first_model_call_and_asks(env):
    loop, result = env("Read config.yaml and tell me the port", [finish("should never be reached")])
    assert result["stopped_reason"] == "needs_clarification" and env.seen == []                   # no model call at all
    assert "config.yaml" in result["clarification_question"] and result["unknowns"][0]["kind"] == "missing_file"
    pending = ClarificationStore(loop._persistence).list(namespace="r97", status="PENDING")
    assert len(pending) == 1 and pending[0].kind == "before_act" and pending[0].criterion == "unclear_intent"


def test_the_same_request_after_the_answer_is_not_asked_twice(env):
    loop, first = env("Read config.yaml and tell me the port", [finish("x")])
    (env.root / "conf").mkdir()
    (env.root / "conf" / "config.yaml").write_text("port: 9000\n", encoding="utf-8")            # the person said where it is, and made it exist
    ClarificationStore(loop._persistence).answer(first["clarification_id"], "r97", "it is in conf/")
    _, second = env("Read config.yaml and tell me the port", [finish("The port is 9000.")], loop=loop)
    assert second["stopped_reason"] == "llm_finished" and second["continues_clarification"] == first["clarification_id"]


def test_without_the_flag_nothing_is_stopped_and_a_file_in_a_subfolder_is_found(env):
    _, result = env("Read config.yaml and tell me the port", [finish("The port is 9000.")], flag="0")
    assert result["stopped_reason"] == "llm_finished" and result["rct7_plan"]["unknowns"][0]["value"] == "config.yaml"
    (env.root / "app").mkdir()
    (env.root / "app" / "config.yaml").write_text("port: 9000\n", encoding="utf-8")
    _, found = env("Read config.yaml and tell me the port", [finish("The port is 9000.")], name="r97f")
    assert found["stopped_reason"] == "llm_finished" and found["rct7_plan"]["unknowns"] == []


def test_a_bare_reference_with_no_conversation_asks(env):
    _, result = env("Fix it", [finish("nothing")])
    assert result["stopped_reason"] == "needs_clarification" and result["unknowns"][0]["kind"] == "dangling_reference"


# ------------------------------------------------------------------------------------------------------------------- channels
def test_a_channel_person_gets_the_question_not_the_held_answer_as_the_result(env):
    _, result = env(GOAL_TH, [finish(ENGLISH)])
    text = common.reply_text_for(result)
    assert text.startswith("ผลที่ได้ไม่ตรงกับที่คุณขอ") and f"/answer {result['clarification_id']}" in text and f"/accept {result['clarification_id']}" in text
    assert text.index("The answer I had (not used)") > text.index("/accept")


def test_chat_commands_list_answer_and_accept_only_the_senders_own_questions(env):
    loop, first = env(GOAL_TH, [finish(ENGLISH)], name="telegram-1")
    cid = first["clarification_id"]

    class K:
        _persistence = loop._persistence
    assert cid in chat_commands.handle(K, "telegram", "1", "telegram-1", "/questions")
    assert "Nothing is waiting" in chat_commands.handle(K, "telegram", "2", "telegram-2", "/questions")
    assert "belongs to someone else" in chat_commands.handle(K, "telegram", "2", "telegram-2", f"/answer {cid} hello")
    reply = chat_commands.handle(K, "telegram", "1", "telegram-1", f"/answer {cid} ทำใหม่")
    assert "version 2" in reply and "send the same request again" in reply
    assert "Say which" in chat_commands.handle(K, "telegram", "1", "telegram-1", "/answer")
    assert "Okay" in chat_commands.handle(K, "telegram", "1", "telegram-1", f"/accept {cid}")


# ------------------------------------------------------------------------------------------------------------------- R4/R7 as evidence: a verdict per requirement
def test_every_finished_episode_reports_each_requirement_with_its_verdict_even_without_the_flag(env):
    _, result = env("Answer in Thai in under 200 characters", [finish(THAI[:80])], flag="0")
    report = {r["kind"]: r for r in result["conditions_report"]}
    assert report["language"]["status"] == "met" and report["max_chars"]["status"] == "met"
    assert result["stopped_reason"] == "llm_finished"                                            # information only: nothing stopped


def test_a_broken_requirement_is_reported_and_a_short_answer_is_not_a_pass(env):
    _, broken = env("ตอบเป็นภาษาไทย", [finish(ENGLISH)], flag="0")
    assert broken["conditions_report"][0]["status"] == "broken" and broken["conditions_report"][0]["observed"] == "English"
    _, short = env("ตอบเป็นภาษาไทย 17 x 23 เท่าไร", [finish("391")], flag="0", name="r97g")
    assert short["conditions_report"][0]["status"] == "not_judged"                              # "391" has no script: not judged, and not claimed as met


def test_a_request_with_no_stated_requirement_has_no_report(env):
    _, result = env("What is 17 x 23?", [finish("391")], flag="0")
    assert "conditions_report" not in result


def test_the_desk_summary_carries_the_conditions_report_and_the_question(env, monkeypatch):
    from rct_control_plane.desk_agent_stream import agent_events
    monkeypatch.setenv("DELENTIA_ASK_AND_WAIT", "1")
    script = [finish(ENGLISH)]

    async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
        return dict(script.pop(0))
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)

    def factory(kernel, namespace, **kwargs):
        return _loop(env.root, "r97s", mcp=_FakeMCP())

    async def run():
        return [e async for e in agent_events(GOAL_TH, kernel=None, namespace="desk-test", loop_factory=factory, structured=True)]
    summary = next(e["data"] for e in asyncio.run(run()) if e["type"] == "summary")
    assert summary["stopped_reason"] == "needs_clarification" and summary["clarification_id"]
    assert "ไม่ตรงกับที่คุณขอ" in summary["clarification_question"]
    assert summary["conditions_report"][0]["kind"] == "language" and summary["conditions_report"][0]["status"] == "broken"


def test_the_desk_summary_carries_the_usage_of_the_episode(env, monkeypatch):
    from rct_control_plane.desk_agent_stream import agent_events
    script = [finish(ENGLISH)]

    async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
        return dict(script.pop(0))
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)

    def factory(kernel, namespace, **kwargs):
        return _loop(env.root, "r97u", mcp=_FakeMCP())

    async def run():
        return [e async for e in agent_events("What is 17 x 23?", kernel=None, namespace="desk-test", loop_factory=factory, structured=True)]
    summary = next(e["data"] for e in asyncio.run(run()) if e["type"] == "summary")
    assert "usage" in summary and isinstance(summary["usage"], dict)                              # the numbers come from the real meter; the scripted model reports none


def test_the_report_names_the_evidence_each_verdict_stands_on(env):
    _, result = env("ตอบเป็นภาษาไทย ไม่เกิน 200 ตัวอักษร", [finish(THAI[:60])], flag="0")
    by = {r["kind"]: r for r in result["conditions_report"]}
    assert by["language"]["evidence"][0]["measure"].startswith("thai_letter_share=") and by["max_chars"]["evidence"][0]["measure"] == f"characters={len(THAI[:60])}"


def test_the_report_shows_the_writes_behind_a_file_requirement(tmp_path):
    (tmp_path / "report.md").write_text("x", encoding="utf-8")
    steps = [{"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "report.md", "content": "x"}, "tool_result": {"ok": True}},
             {"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "config.yaml", "content": "y"}, "tool_result": {"ok": True}},
             {"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "blocked.txt", "content": "z"}, "tool_result": {"pending_approval": True}}]
    reqs = mismatch_rules.derive_requirements("Save it as report.md. Do not modify config.yaml.")
    by = {r["kind"]: r for r in mismatch_rules.evaluate(reqs, "saved", steps, tmp_path)}
    assert by["required_artifact"]["status"] == "met" and by["required_artifact"]["evidence"] == [{"step": 1, "tool": "delentia_write_repo_file", "path": "report.md"}]
    assert by["forbidden_effect"]["status"] == "broken"
    assert [w["path"] for w in by["forbidden_effect"]["evidence"]] == ["report.md", "config.yaml"]     # a write that waited for a signature did not go through, so it is not listed

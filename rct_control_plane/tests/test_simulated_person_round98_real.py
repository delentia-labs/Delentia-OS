"""The simulated person for the research arms (research/simulated_person.py, research/runner.py --person/--judge/--chain). Criteria written first: research/rct7_round98_criteria.md, section P.

Real governed loop, real SQLite, the real research harness with its scripted-policy model (the rehearsal), and a scripted judge. What is proved: a stop is answered and the episode finishes and is
graded; the cost of every round is summed; the round limit holds; with the person off nothing about a row or the identity changes.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop
from rct_control_plane import mcp_server, rct7_judge
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeMCP, _loop
from research import runner
from research import simulated_person as sp

ENGLISH = "All of the tests passed and no errors were found in the system, and the time taken fell by about half, so this setting is recommended."
GOAL_TH = "สรุปผลการทดสอบเป็นภาษาไทย"


def finish(text):
    return {"action": "finish", "reasoning": "done", "final_answer": text, "tool_name": None, "tool_args": {}}


class AlwaysUnclear:
    """A judge that finds every request unclear (so every request produces a question)."""

    def __init__(self):
        self.asked = 0

    async def complete(self, prompt, system_prompt=None, temperature=0.0, max_tokens=300, json_mode=False):
        self.asked += 1
        if system_prompt == rct7_judge.SYSTEM_REQUEST:
            request = prompt.split("<request>", 1)[1].split("</request>", 1)[0].strip()
            about = request.split()[0] if request.split() else ""                                        # words that really occur in the request, so the cite guard keeps the question
            return json.dumps({"clear": False, "unknowns": [{"question": "Which one do you mean?", "about": about}]})
        return json.dumps({"meets": True, "unmet": []})


# ---------------------------------------------------------------------------------------------------------------- the person
def test_the_insist_policy_always_says_the_request_is_complete_and_the_facts_policy_answers_from_the_task():
    assert sp.SimulatedPerson("insist").answer_for("Which file?", {"hidden_facts": {"file": "report.md"}}) == sp.INSIST_TEXT
    facts = sp.SimulatedPerson("facts")
    task = {"hidden_facts": {"file": "report.md", "Budget": "9000 baht"}}
    assert facts.answer_for("Which FILE do you mean?", task) == "report.md" and facts.answer_for("what is the budget?", task) == "9000 baht"
    assert facts.answer_for("What colour?", task) == sp.INSIST_TEXT and facts.answer_for("anything", None) == sp.INSIST_TEXT
    with pytest.raises(ValueError):
        sp.SimulatedPerson("approve-everything")


def test_costs_of_every_round_are_summed_and_an_unknown_one_makes_the_sum_unknown():
    a = {"prompt_tokens": 100, "completion_tokens": 10, "cached_prompt_tokens": 0, "calls": 1, "cost_usd": 0.001, "cost_known": True}
    b = {"prompt_tokens": 50, "completion_tokens": 5, "cached_prompt_tokens": 20, "calls": 2, "cost_usd": 0.002, "cost_known": True}
    total = sp.summed_cost([a, b])
    assert total["prompt_tokens"] == 150 and total["calls"] == 3 and total["cost_usd"] == pytest.approx(0.003) and total["cost_known"] is True and total["rounds_summed"] == 2
    unknown = sp.summed_cost([a, {**b, "cost_usd": None, "cost_known": False}])
    assert unknown["cost_known"] is False and unknown["cost_usd"] is None
    assert sp.summed_cost([None, None]) == {}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("DELENTIA_ASK_AND_WAIT", raising=False)
    monkeypatch.delenv("DELENTIA_RCT7_JUDGE", raising=False)

    def go(goal, answers, judge=None, max_rounds=2):
        script = list(answers)

        async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
            return dict(script.pop(0) if script else finish("done"))
        monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
        loop = _loop(tmp_path, "sp98", mcp=_FakeMCP())
        loop._interactive = True
        if judge is not None:
            loop._judge_provider_override = judge
        return asyncio.run(sp.SimulatedPerson("insist", max_rounds).run(loop, goal, {"task_id": "t"}))
    return go


def test_a_question_is_answered_and_the_episode_finishes(env, monkeypatch):
    monkeypatch.setenv("DELENTIA_RCT7_JUDGE", "propose")
    judge = AlwaysUnclear()
    result, log = env("Send the report to the client", [finish("sent")], judge)
    assert result["stopped_reason"] == "llm_finished" and log["rounds"] == 1 and log["unresolved"] is False
    assert log["criteria"] == ["before_act/model_unclear"] and "Which one do you mean?" in log["questions"][0]


def test_a_request_nothing_stops_costs_no_round(env):
    result, log = env("What is 2+2?", [finish("4")])
    assert result["stopped_reason"] == "llm_finished" and log["rounds"] == 0 and log["questions"] == []


def test_the_round_limit_holds_and_an_episode_still_waiting_is_recorded_as_unresolved(env):
    result, log = env(GOAL_TH, [finish(ENGLISH), finish(ENGLISH), finish(ENGLISH)])              # the rule keeps seeing the English answer to a Thai request; "insist" does not change it
    assert log["rounds"] == 2 and log["unresolved"] is True and result["stopped_reason"] == "needs_clarification"
    assert log["criteria"][-1] == "unanswered" and len(log["costs"]) == 3


def test_a_report_counts_questions_per_hundred_episodes_per_arm():
    rows = [{"arm": "A111", "person_policy": "insist", "questions_asked": 1, "needless_questions": 1, "unresolved_stop": False, "status": "success"},
            {"arm": "A111", "person_policy": "insist", "questions_asked": 0, "needless_questions": 0, "unresolved_stop": False, "status": "success"},
            {"arm": "A111", "person_policy": "insist", "questions_asked": 2, "needless_questions": 2, "unresolved_stop": True, "status": "fail"},
            {"arm": "G", "person_policy": "insist", "questions_asked": 0, "needless_questions": 0, "unresolved_stop": False, "status": "success"},
            {"arm": "G", "person_policy": "off"}]
    out = sp.report(rows)
    assert out["A111"]["questions_per_100_episodes"] == 100.0 and out["A111"]["episodes_with_a_question_pct"] == pytest.approx(66.7, abs=0.1) and out["A111"]["unresolved"] == 1
    assert out["G"]["episodes"] == 1 and out["G"]["questions"] == 0


# ---------------------------------------------------------------------------------------------------------------- the harness
@pytest.fixture(scope="module")
def one_static_task():
    static, _ = runner._load_units("dev", None, "quotes")
    return static[0]


def episode(tmp_path, task, **harness_kwargs):
    harness = runner.Harness(tmp_path / "w", "diligent", **harness_kwargs)
    try:
        harness.start()
        arm = runner._arms("A111")[0]
        return asyncio.run(harness.run_episode(arm, task, split="dev", rep=0, namespace="research-sp-1", skill_db=str(tmp_path / "s.db"), seed=1))
    finally:
        harness.close()


def test_with_the_person_off_a_row_has_none_of_the_new_fields_and_the_identity_is_unchanged(tmp_path, one_static_task):
    row = episode(tmp_path, one_static_task)
    assert not any(k in row for k in ("person_policy", "questions_asked", "needless_questions", "unresolved_stop", "question_kinds"))
    h = runner.Harness(tmp_path / "w0", "diligent")
    assert "rct7" not in h.config_identity([])


def test_a_judge_question_in_a_fully_specified_task_is_answered_graded_and_counted_as_needless(tmp_path, one_static_task, monkeypatch):
    judge = AlwaysUnclear()
    monkeypatch.setattr(GovernedAutonomousLoop, "_judge_provider", lambda self: (judge, lambda: None))
    row = episode(tmp_path, one_static_task, person="insist", judge="propose")
    assert row["person_policy"] == "insist" and row["questions_asked"] >= 1 and row["needless_questions"] == row["questions_asked"]
    assert row["question_kinds"][0] == "before_act/model_unclear" and row["unresolved_stop"] is False
    assert row["stopped_reason"] != "needs_clarification" and isinstance(row["status"], str) and row["status"]          # it was graded, not left waiting
    assert judge.asked >= 1


def test_the_identity_changes_with_the_person_and_the_judge_so_a_resume_across_them_is_refused(tmp_path):
    base = runner.Harness(tmp_path / "a", "diligent").config_identity([])["identity_sha"]
    with_person = runner.Harness(tmp_path / "b", "diligent", person="insist").config_identity([])["identity_sha"]
    with_judge = runner.Harness(tmp_path / "c", "diligent", person="insist", judge="propose").config_identity([])["identity_sha"]
    assert len({base, with_person, with_judge}) == 3


def test_a_judge_without_a_person_is_refused_before_anything_runs(tmp_path):
    args = argparse.Namespace(split="dev", policy="diligent", arms="A111", domain="quotes", unit_token_budget=0, memory_policy="none", preload_noise=0, max_seconds=60.0, repeats=1,
                              seed=1, out=str(tmp_path / "o.jsonl"), only=None, work=str(tmp_path / "work"), model_config=None, budget_usd=None, tool_menu="default", floor="default",
                              keep_going=True, stop_on_critical=False, budget_scope="run", new_run=False, person="off", judge="propose", chain="off")
    assert asyncio.run(runner.main_async(args)) == 6
    assert not (tmp_path / "o.jsonl").exists()


def test_the_harness_clears_the_model_assisted_settings_a_stray_shell_left_behind(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_RCT7_JUDGE", "propose")
    monkeypatch.setenv("DELENTIA_RCT7_CHAIN", "cite")
    h = runner.Harness(tmp_path / "w", "diligent")
    try:
        h.start()
        assert "DELENTIA_RCT7_JUDGE" not in os.environ and "DELENTIA_RCT7_CHAIN" not in os.environ              # off unless the run says so, the same for every arm
    finally:
        h.close()
    assert os.environ.get("DELENTIA_RCT7_JUDGE") == "propose"                                                       # and put back for the caller

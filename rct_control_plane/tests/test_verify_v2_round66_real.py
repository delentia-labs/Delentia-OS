"""
Round 66: the three VERIFY changes written down in research/verify_batch_d_criteria.md BEFORE they were made (DELENTIA_VERIFY_V2, on by default since batch D was measured; `off` restores the old rules):
(a) one specific value reused from a tool result counts as support, (b) a bare number answering a calculation counts as an answer, (c) the common Chinese ways of declining are declines.

These tests pin what each change does and, as important, what it must NOT do: it must not turn a refusal, an invented value or a claimed action into an accepted answer.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import verify_grounding as vg
from rct_control_plane.governed_autonomous_loop import answer_declines_goal


@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setenv(vg.V2_ENV, "on")


@pytest.fixture
def v1(monkeypatch):
    monkeypatch.setenv(vg.V2_ENV, "off")


def step(result, tool="delentia_read_repo_file"):
    return {"tool_name": tool, "tool_args": {}, "tool_result": result}


CONTACTS = step({"content": "Customs liaison: Prasert. Warehouse lead: Wanida. Office hours: 08:00-17:00 ICT."})


def test_on_by_default_since_batch_d_and_off_with_the_switch(monkeypatch):
    monkeypatch.delenv(vg.V2_ENV, raising=False)
    assert vg.v2_enabled() is True
    for off in ("off", "0", "false", "no"):
        monkeypatch.setenv(vg.V2_ENV, off)
        assert vg.v2_enabled() is False


def test_off_nothing_changes(v1):
    assert vg.v2_enabled() is False
    assert vg.check("Who leads the warehouse? Check docs/contacts.md.", "仓库主管是 Wanida。", [CONTACTS])["supported"] is False
    assert vg.check("What is 17 times 6?", "102", [])["answers_calc"] is False
    assert answer_declines_goal("文档中未提供关于部署审批的信息。") is False


def test_a_value_the_goal_did_not_contain_but_the_tool_result_did_is_support(v2):
    g = vg.check("Who leads the warehouse? Check docs/contacts.md.", "仓库主管是 Wanida。", [CONTACTS])
    assert g["supported"] is True and g["grounded"] is True
    assert vg.check("What are the office hours listed in docs/contacts.md?", "办公室的营业时间为08:00-17:00 ICT。", [CONTACTS])["supported"] is True


def test_a_value_that_only_repeats_the_question_is_not_support(v2):
    g = vg.check("Who is the customs liaison per docs/contacts.md?", "The file docs/contacts.md does not say.", [CONTACTS])
    assert g["supported"] is False


def test_a_value_that_is_in_no_tool_result_is_not_support_and_a_number_is_still_checked(v2):
    g = vg.check("Who leads the warehouse? Check docs/contacts.md.", "The warehouse lead is Somchai and the phone is 0812345678.", [CONTACTS])
    assert g["grounded"] is False and "ungrounded_values" in g["flags"]                 # (two ordinary words are shared with the result, as before; the invented number is what stops it)
    assert vg.check("Who leads the warehouse? Check docs/contacts.md.", "Somchai.", [CONTACTS])["supported"] is False


def test_a_failed_tool_run_supports_nothing(v2):
    failed = step({"error": "file not found"})
    assert vg.check("Who leads the warehouse? Check docs/contacts.md.", "Wanida", [failed])["supported"] is False


@pytest.mark.parametrize("goal,answer,expected", [
    ("What is 17 times 6?", "102", True), ("What is 1000 minus 1?", "999", True), ("How many seconds are in a minute?", "60", True), ("What is 250 plus 175?", "425.", True),
    ("17 คูณ 6 เท่าไหร่", "102", True), ("How many days are in a week?", "7 days", True),
    ("What is the capital of Italy?", "102", False),                   # not a calculation: a number is not an answer to it
    ("What is 17 times 6?", "The answer is one hundred and two, as computed above in detail.", False),
    ("What is 17 times 6?", "", False), ("What is 17 times 6?", "I am unable to calculate that", False),
])
def test_a_bare_number_answers_a_calculation_only(v2, goal, answer, expected):
    assert vg.answers_calculation(goal, answer) is expected


def test_the_calculation_rule_never_applies_when_a_tool_ran(v2):
    assert vg.check("What is 17 times 6?", "102", [step({"ok": True})])["answers_calc"] is False


@pytest.mark.parametrize("answer", ["文档/deploy.md中未提供关于部署审批的信息。", "README.md 文件中并未列出专门用于安全报告的电子邮件地址。", "docs/deploy.md文件中未提及staging URL信息。",
                                    "关于pyproject.toml所需的Python版本信息，建议查阅相关文档或官方资料以获取准确信息。", "找不到这个文件", "请参考官方文档"])
def test_chinese_ways_of_declining_are_declines_with_v2(v2, answer):
    assert answer_declines_goal(answer) is True


@pytest.mark.parametrize("answer", ["仓库主管是 Wanida。", "办公室的营业时间为08:00-17:00 ICT。", "已设置20分钟后提醒，用于回顾部署说明。", "率限制: 每分钟每个密钥120次请求。突发值: 30。", "102"])
def test_a_correct_chinese_answer_is_not_a_decline(v2, answer):
    assert answer_declines_goal(answer) is False


def test_the_old_declines_still_work_in_both_modes(v1, monkeypatch):
    assert answer_declines_goal("I am unable to read pyproject.toml") is True
    monkeypatch.setenv(vg.V2_ENV, "on")
    assert answer_declines_goal("I am unable to read pyproject.toml") is True and answer_declines_goal("ไม่สามารถอ่านไฟล์ได้") is True


def test_an_action_claim_with_no_effect_is_still_flagged_with_v2(v2):
    g = vg.check("Remember that the staging depot is called trang-stage.", "Done, I have remembered it.", [])
    assert g["grounded"] is False


def test_the_real_cases_the_change_was_built_from_behave_as_the_criteria_say(v2):
    """Development data only (batches A, B, C were read). The holdout is batch D, measured once in research/verify_round66_batch_d.json."""
    import json
    from pathlib import Path
    fixtures = Path(__file__).parent / "fixtures"
    good_rejected = bad_accepted = good = bad = 0
    from rct_control_plane.semantic_matcher import SemanticMatcher
    matcher = SemanticMatcher()
    for name in ("verify_cases_round62_real.json", "verify_cases_round65_real.json"):
        data = json.loads((fixtures / name).read_text(encoding="utf-8"))
        for case in data["dev"] + data["holdout"]:
            g = vg.check(case["goal"], case["answer"], case["steps"])
            sim = float(matcher.semantic_similarity(case["goal"], case["answer"]))
            ok = g["grounded"] and not answer_declines_goal(case["answer"]) and (sim >= 0.15 or g["supported"] or g.get("answers_calc"))
            if case["label"] == "good":
                good += 1
                good_rejected += not ok
            else:
                bad += 1
                bad_accepted += bool(ok)
    assert (good, bad) == (27, 49)
    assert good_rejected <= 3 and bad_accepted <= 5, (good_rejected, bad_accepted)

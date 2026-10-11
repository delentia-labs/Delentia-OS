"""
Round 67: VERIFY v3 (research/verify_batch_e_criteria.md). The three changes, what they accept and what they must still refuse. Off unless DELENTIA_VERIFY_V3 is on.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import verify_grounding as vg
from rct_control_plane.governed_autonomous_loop import answer_declines_goal


@pytest.fixture
def v3(monkeypatch):
    monkeypatch.setenv(vg.V3_ENV, "on")


@pytest.fixture
def v3_off(monkeypatch):
    monkeypatch.delenv(vg.V3_ENV, raising=False)


ABSENCE = [
    "MAX_PARALLEL在src/scheduler.py中的具体值需要查看该文件才能确定。",
    "文档或FAQ中没有明确说明订单在派遣后可以取消的分钟数。",
    "为了确定 config/regions.yaml 文件中主要区域的位置，需要直接查看该文件的内容才能确定。",
    "According to docs/faq.md, the carrier that handles refrigerated goods is not explicitly mentioned.",
    "The file does not specify a timeout.",
    "docs/returns.md does not contain a gift card policy.",
    "There is no specific information about customs duties.",
]
ANSWERS = [
    "The carrier is Siam Express.", "MAX_PARALLEL is 7.", "The window is Tuesday 02:00 UTC, approver Malee.", "ap-southeast-1", "9", "已设置在10分钟后重启轮询器的提醒。",
    "The file defines two limits: the daily quota is 5000 and the burst is 80.",
]


@pytest.mark.parametrize("text", ABSENCE)
def test_absence_and_deferral_phrases_are_declines_under_v3(text, v3):
    assert answer_declines_goal(text) is True


def test_none_of_those_phrases_is_newly_refused_when_v3_is_off(v3_off):
    refused_by_v2 = {t for t in ABSENCE if answer_declines_goal(t)}
    assert len(refused_by_v2) < len(ABSENCE)                       # v2 let some through: that is the defect v3 addresses


@pytest.mark.parametrize("text", ANSWERS)
def test_real_answers_are_not_declines_under_v3(text, v3):
    assert answer_declines_goal(text) is False


def test_v3_off_leaves_v2_exactly_as_it_was(v3_off):
    assert answer_declines_goal("According to docs/faq.md, the carrier is not explicitly mentioned.") is False
    assert vg.check("What is 81 divided by 9?", "9", [])["flags"] == ["empty_answer"]
    assert vg.check("Set a reminder in 10 minutes to restart the poller.", "已设置在10分钟后重启轮询器的提醒。", [])["supported"] is False


def test_a_one_character_answer_to_arithmetic_is_not_empty_under_v3(v3):
    assert vg.check("What is 81 divided by 9?", "9", [])["flags"] == []
    assert vg.check("What is 90 divided by 6?", "15", [])["flags"] == []
    assert vg.check("What is 6 multiplied by 7?", "42", [])["grounded"] is True
    # a one-character answer to something that is not arithmetic is still empty
    assert "empty_answer" in vg.check("Who is the onboarding buddy?", "x", [])["flags"]
    assert "empty_answer" in vg.check("What is the capital of Spain?", "M", [])["flags"]


def test_an_effect_that_ran_supports_an_answer_in_any_language(v3):
    steps = [{"tool_name": "delentia_schedule_reminder", "tool_args": {"goal": "x"}, "tool_result": {"reminder_id": "reminder_7ebee57ce3d2"}}]
    got = vg.check("Set a reminder in 10 minutes to restart the poller.", "已设置在10分钟后重启轮询器的提醒。", steps)
    assert got["grounded"] is True and got["supported"] is True


def test_a_failed_or_missing_effect_supports_nothing(v3):
    failed = [{"tool_name": "delentia_schedule_reminder", "tool_args": {}, "tool_result": {"error": "bad time"}}]
    assert vg.check("Set a reminder in 10 minutes to restart the poller.", "已设置提醒。", failed)["supported"] is False
    assert vg.check("Set a reminder in 10 minutes to restart the poller.", "已设置提醒。", [])["supported"] is False
    other_tool = [{"tool_name": "delentia_read_repo_file", "tool_args": {}, "tool_result": {"content": "x"}}]
    assert vg.check("Set a reminder in 10 minutes to restart the poller.", "已设置提醒。", other_tool)["supported"] is False


def test_a_question_is_not_made_supported_by_an_effect_tool(v3):
    steps = [{"tool_name": "delentia_remember", "tool_args": {}, "tool_result": {"memory_id": "mem_1"}}]
    assert vg.check("Who is the Tier 2 on-call?", "Nobody knows.", steps)["supported"] is False


def test_the_claim_after_errors_check_still_fires(v3):
    steps = [{"tool_name": "delentia_write_repo_file", "tool_args": {}, "tool_result": {"error": "denied"}}]
    assert "claims_success_after_error" in vg.check("Create a file called x.txt containing hi.", "Done, I created x.txt successfully.", steps)["flags"]

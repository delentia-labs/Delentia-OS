"""Round 92: the Round 91 rule (the verb that heads the sentence decides question vs change) for Thai goals.

Criteria and the held-out result: research/independent_goals_criteria_r92.md. Before this rule a Thai action goal was classed LOW in 14-18% of cases and had no class in about 55%; a Thai question had
no class in about half. The sentences below are written by hand (not from the sets), one per head word, plus the cases that must NOT change.
"""
import pytest

from rct_control_plane.intent_compiler import IntentCompiler, RiskProfile

compiler = IntentCompiler()


def risk(goal):
    result = compiler.compile(goal, "u", "free")
    assert result.intent is not None, goal
    return result.intent.risk_profile


@pytest.mark.parametrize("goal", [
    "ช่วยแก้ไขไฟล์ README ให้เพิ่มคำสั่งใหม่",
    "ย้ายไฟล์ report.pdf ไปไว้ในโฟลเดอร์สำรอง",
    "รันโปรแกรมทดสอบทั้งหมด",
    "กรุณาเปลี่ยนชื่อไฟล์ notes.txt เป็น todo.txt",
    "ขอให้ติดตั้งแพ็กเกจ requests",
    "ผมอยากให้คุณสร้างไฟล์ใหม่ชื่อ plan.md",
    "ส่งข้อความหาสมชายว่าประชุมพรุ่งนี้",
    "ตั้งเวลาให้รันสคริปต์สำรองข้อมูลทุกคืน",
    "อัปเดตเวอร์ชันในไฟล์ pyproject.toml",
])
def test_a_thai_goal_that_asks_for_a_change_is_never_below_structural(goal):
    assert risk(goal) in (RiskProfile.STRUCTURAL, RiskProfile.SYSTEMIC)


@pytest.mark.parametrize("goal", [
    "อธิบายว่าไฟล์ config ทำงานอย่างไร",
    "สรุปเนื้อหาของไฟล์ notes.txt ให้หน่อย",
    "ช่วยค้นหาไฟล์ที่มีคำว่า FDIA",
    "เวอร์ชันล่าสุดของโปรเจกต์นี้คืออะไร",
    "ขอคำแนะนำในการเขียนโปรแกรมให้อ่านง่าย",
    "เปรียบเทียบสองแนวทางนี้ให้ดูหน่อย",
    "มีไฟล์อะไรในโฟลเดอร์ docs บ้าง",
])
def test_a_thai_question_is_low_risk(goal):
    assert risk(goal) == RiskProfile.LOW


def test_a_question_that_asks_for_a_change_later_in_the_sentence_is_not_low():
    # "summarise the file, then delete it": the later clause is a change
    assert risk("สรุปไฟล์นี้แล้วลบไฟล์ทิ้งด้วย") in (RiskProfile.STRUCTURAL, RiskProfile.SYSTEMIC)


def test_a_high_risk_word_keeps_the_strict_class_in_either_reading():
    assert risk("ลบไฟล์ทั้งหมดในโฟลเดอร์นี้") == RiskProfile.SYSTEMIC
    assert risk("สรุปประวัติการส่งอีเมลที่ผ่านมา") == RiskProfile.SYSTEMIC          # the old reading is kept when a high-risk phrase appears


def test_english_goals_are_unchanged_by_the_thai_rule():
    assert risk("What changed in the last release?") == RiskProfile.LOW
    assert risk("Edit the README so it lists the new command") in (RiskProfile.STRUCTURAL, RiskProfile.SYSTEMIC)
    assert IntentCompiler._head_kind("show me the files") == ("read", False)
    assert IntentCompiler._head_kind("delete the old logs") == ("action", False)


def test_head_word_of_a_thai_create_verb_makes_a_new_thing():
    assert IntentCompiler._head_word("สร้างไฟล์ใหม่ชื่อ plan.md") == "create"
    assert IntentCompiler._head_word("ย้ายไฟล์นี้") == "ย้าย"


def test_text_that_is_neither_english_nor_thai_has_no_head():
    assert IntentCompiler._head_kind("12345") == (None, False)
    assert IntentCompiler._head_kind("") == (None, False)

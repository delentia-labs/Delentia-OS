"""RCT-7 R5/R7: the rule-checkable mismatch criteria (language, format, required artifact, forbidden effect).

Real functions, real files in a temporary workspace, real Thai and English text. The two things the design insists on are tested as such:
RC09 (a correct answer that is short or in other words is NOT stopped) and no guessing (a goal that states no requirement yields none)."""
import pytest

from rct_control_plane import mismatch_rules as mr

THAI_REPORT = "ผลการทดสอบทั้งหมดผ่านแล้ว ไม่พบข้อผิดพลาดในระบบ และเวลาที่ใช้ลดลงจากเดิมประมาณครึ่งหนึ่ง จึงแนะนำให้ใช้ค่านี้ต่อไป"
ENGLISH_REPORT = "All of the tests passed and no errors were found in the system, and the time taken fell by about half, so this setting is recommended."


def kinds(goal):
    return [(r.kind, r.value) for r in mr.derive_requirements(goal)]


# ---------------------------------------------------------------------------- reading the goal
@pytest.mark.parametrize("goal,expected", [
    ("สรุปรายงานนี้เป็นภาษาไทย", [("language", "th")]),
    ("ตอบด้วยภาษาอังกฤษ", [("language", "en")]),
    ("Summarize the report in Thai", [("language", "th")]),
    ("Please answer in English", [("language", "en")]),
    ("translate this to English", [("language", "en")]),
    ("แปลจากภาษาอังกฤษเป็นภาษาไทย", [("language", "th")]),                  # names both; only the preposition that marks the OUTPUT counts
    ("เขียนสรุปภาษาไทยเท่านั้น", [("language", "th")]),
    ("Return the result as JSON", [("format", "json")]),
    ("ตอบเป็น JSON", [("format", "json")]),
    ("save it as report.md", [("required_artifact", "report.md")]),
    ("บันทึกเป็น notes/result.txt", [("required_artifact", "notes/result.txt")]),
    ("do not modify config.yaml", [("forbidden_effect", "config.yaml")]),
    ("ห้ามแก้ไฟล์ settings.ini", [("forbidden_effect", "settings.ini")]),
])
def test_the_goals_own_words_give_the_requirement(goal, expected):
    assert kinds(goal) == expected


@pytest.mark.parametrize("goal", [
    "What is 17 x 23?", "Read the file pyproject.toml and tell me the project name", "สรุปรายงานให้หน่อย", "",
    "Compare Thai and English tourism numbers",                                # mentions both languages but asks for neither as the output
    "Translate between Thai and English",
])
def test_a_goal_that_states_no_requirement_gets_none(goal):
    assert kinds(goal) == []


def test_two_different_output_languages_in_one_goal_make_no_language_requirement():
    assert kinds("answer in Thai and then in English") == []


def test_several_requirements_in_one_goal():
    got = kinds("ตอบเป็นภาษาไทย และห้ามแก้ไฟล์ config.yaml แล้วบันทึกเป็น out.md")
    assert ("language", "th") in got and ("forbidden_effect", "config.yaml") in got and ("required_artifact", "out.md") in got


# ---------------------------------------------------------------------------- language
def reqs(goal):
    return mr.derive_requirements(goal)


def test_an_english_answer_to_a_thai_request_is_a_difference_with_expected_and_observed():
    diffs = mr.check(reqs("สรุปรายงานนี้เป็นภาษาไทย"), ENGLISH_REPORT, [], None)
    assert len(diffs) == 1 and diffs[0].criterion == "language" and diffs[0].expected == "Thai" and diffs[0].observed == "English"


def test_a_thai_answer_to_a_thai_request_is_not_stopped():
    assert mr.check(reqs("สรุปรายงานนี้เป็นภาษาไทย"), THAI_REPORT, [], None) == []


def test_a_thai_answer_to_an_english_request_is_a_difference():
    diffs = mr.check(reqs("Summarize in English"), THAI_REPORT, [], None)
    assert diffs and diffs[0].expected == "English"


def test_RC09_short_or_reworded_correct_answers_are_never_stopped():
    for goal in ("ตอบเป็นภาษาไทย 17 x 23 เท่าไร", "answer in English: what is 17 x 23?"):
        for answer in ("391", "ok", "391 ครับ", "yes"):
            assert mr.check(reqs(goal), answer, [], None) == [], (goal, answer)


def test_code_links_and_file_names_do_not_decide_the_language_of_a_thai_report():
    answer = ("ผมรันคำสั่งทดสอบแล้วทุกข้อผ่าน ผลละเอียดอยู่ในไฟล์ results.json และรายงานที่ https://example.com/report ดูได้จากนั้น\n"
              "```bash\npytest -q --maxfail=1 tests/test_everything_real.py\n```\nสรุปคือพร้อมใช้งานจริงตามที่ตั้งใจไว้")
    assert mr.check(reqs("ตอบเป็นภาษาไทย"), answer, [], None) == []


def test_technical_terms_in_latin_letters_inside_a_thai_answer_are_allowed():
    answer = "ระบบ FDIA gate ปฏิเสธการเขียนไฟล์ เพราะค่า F ต่ำกว่า threshold ที่ตั้งไว้ จึงต้องรอการอนุมัติด้วยลายเซ็น Ed25519 จากเจ้าของก่อน"
    assert mr.check(reqs("ตอบเป็นภาษาไทย"), answer, [], None) == []


# ---------------------------------------------------------------------------- format
def test_json_asked_and_prose_given_is_a_difference_but_fenced_json_is_fine():
    assert mr.check(reqs("return the result as JSON"), "The total is 12,500 baht.", [], None)[0].criterion == "format"
    assert mr.check(reqs("return the result as JSON"), '```json\n{"total": 12500}\n```', [], None) == []
    assert mr.check(reqs("return the result as JSON"), '{"total": 12500}', [], None) == []


# ---------------------------------------------------------------------------- required artifact
def test_a_file_that_was_asked_for_must_exist_afterwards(tmp_path):
    r = reqs("save it as report.md")
    assert mr.check(r, "done", [], tmp_path)[0].criterion == "required_artifact"
    (tmp_path / "report.md").write_text("x", encoding="utf-8")
    assert mr.check(r, "done", [], tmp_path) == []


def test_a_path_that_climbs_out_of_the_workspace_never_counts_as_the_artifact(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (tmp_path / "outside.md").write_text("x", encoding="utf-8")
    diffs = mr.check([mr.Requirement("required_artifact", "../outside.md", "x")], "done", [], work)
    assert diffs and diffs[0].criterion == "required_artifact"


# ---------------------------------------------------------------------------- forbidden effect
def write_step(path, **outcome):
    return {"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": path, "content_text": "x"}, "tool_result": dict(outcome)}


def test_a_write_to_a_forbidden_file_that_went_through_is_a_difference():
    diffs = mr.check(reqs("do not modify config.yaml"), "done", [write_step("config.yaml", ok=True)], None)
    assert diffs and diffs[0].criterion == "forbidden_effect" and "config.yaml" in diffs[0].observed


def test_a_write_that_was_blocked_or_is_waiting_for_a_signature_is_not_an_effect():
    for outcome in ({"blocked": True}, {"fdia_blocked": True}, {"pending_approval": True}):
        assert mr.check(reqs("do not modify config.yaml"), "done", [write_step("config.yaml", **outcome)], None) == []


def test_a_write_to_another_file_is_not_a_difference():
    assert mr.check(reqs("do not modify config.yaml"), "done", [write_step("notes/other.md", ok=True)], None) == []


def test_a_nested_path_that_ends_with_the_forbidden_name_counts():
    assert mr.check(reqs("do not modify config.yaml"), "done", [write_step("deploy/config.yaml", ok=True)], None)


# ---------------------------------------------------------------------------- the question
def test_the_question_is_in_the_language_of_the_goal_and_states_the_difference():
    d = [mr.Difference("language", "Thai", "English")]
    thai = mr.question_for("สรุปเป็นภาษาไทย", d)
    english = mr.question_for("summarize in Thai", d)
    assert "ขอ Thai แต่ได้ English" in thai and "ไม่ตรงกับที่คุณขอ" in thai
    assert "asked for Thai, got English" in english and "does not match" in english

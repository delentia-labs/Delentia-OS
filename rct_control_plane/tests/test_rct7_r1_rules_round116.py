"""RCT-7 R-1: the rules that read the kind of work and the stated constraints (tuned on the 60 development requests; these pin the behaviour and what
must NOT be read, so a later change cannot quietly widen them)."""
from pathlib import Path

import pytest

from rct_control_plane import mismatch_rules as m
from rct_control_plane.intent_compiler import IntentCompiler


@pytest.fixture(scope="module")
def compiler():
    return IntentCompiler()


def kind(compiler, text):
    r = compiler.compile(natural_language=text, user_id="t", user_tier="PRO")
    return str(getattr(r.intent.intent_type, "value", r.intent.intent_type)) if r.success and r.intent is not None else None


@pytest.mark.parametrize("text,want", [
    ("Fix the failing tests in the package and keep the signatures.", "DEBUG"),
    ("Debug why the job stops after the first record.", "DEBUG"),
    ("Write unit tests for refund_amount.", "TEST"),
    ("Write a README for the package.", "DOCUMENT"),
    ("Update the changelog with this week's fixes.", "DOCUMENT"),
    ("Release version 3 to PyPI.", "DEPLOY"),
    ("Speed up the report generation.", "OPTIMIZE"),
    ("Convert the CSV to JSON.", "TRANSFORM"),
    ("Plan the migration to Postgres.", "STRATEGY"),
    ("What could go wrong if we turn off the approval step?", "ANALYZE_RISK"),
    ("Rename the helper across the module.", "REFACTOR"),
    ("Create a landing page.", "BUILD_APP"),
    ("แก้บั๊กใน pricing.py", "DEBUG"),
    ("วางแผนการทดสอบกับผู้ใช้", "STRATEGY"),
])
def test_the_kind_of_work_is_read_from_what_the_request_asks_to_do(compiler, text, want):
    assert kind(compiler, text) == want


@pytest.mark.parametrize("text", ["What is the quarterly total in report.txt?", "Which functions call validate_rate?", "How many orders were placed in October?",
                                  "Explain in one paragraph what refund_amount does.", "ยอดรวมของไตรมาสนี้คือเท่าไร"])
def test_a_question_stays_a_question(compiler, text):
    assert kind(compiler, text) == "QUERY"


def kinds(text):
    return sorted({r.kind for r in m.derive_requirements(text)})


@pytest.mark.parametrize("text,want", [
    ("Refactor utils.py without changing its public interface.", ["preserve_interface"]),
    ("Fix it and keep the function names unchanged.", ["preserve_interface"]),
    ("The command-line flags must stay the same.", ["preserve_interface"]),
    ("Fix the bug; do not modify the tests.", ["forbidden_effect"]),
    ("Clean it up; do not touch the tests folder.", ["forbidden_effect"]),
    ("Add tests; keep the existing tests untouched.", ["forbidden_effect"]),
    ("Leave config.yaml alone.", ["forbidden_effect"]),
    ("Roll it out without restarting the database.", ["forbidden_effect"]),
    ("Plan it within a budget of $2.", ["budget"]),
    ("Release it before 5 pm today.", ["deadline"]),
    ("Plan it in five steps.", ["item_count"]),
    ("Report it as a table.", ["format"]),
    ("Normalise the dates and write the result to out.csv.", ["required_artifact"]),
    ("แก้บั๊ก ห้ามแก้ไฟล์เทสต์", ["forbidden_effect"]),
    ("ปรับโค้ด โดยห้ามเปลี่ยน signature ของฟังก์ชัน", ["preserve_interface"]),
    ("วางแผนภายในงบ 50,000 บาท", ["budget"]),
    ("ทำให้เสร็จภายในวันศุกร์นี้", ["deadline"]),
])
def test_stated_constraints_are_read(text, want):
    assert kinds(text) == want


@pytest.mark.parametrize("text", [
    "Keep behaviour identical while renaming the helper.",          # behaviour is not an interface noun
    "Summarise it in at most 100 words.",                            # a length, not a deadline or budget
    "What does the test suite cover?",
    "The tests folder has 12 files; which ones are slow?",
    "Answer within 50 words.",                                       # 'within' + words is not a deadline
])
def test_nothing_is_invented(text):
    got = kinds(text)
    assert "preserve_interface" not in got and "budget" not in got and "deadline" not in got and "forbidden_effect" not in got


def test_a_named_file_is_not_also_read_as_a_category():
    assert [(r.kind, r.value) for r in m.derive_requirements("do not modify config.yaml")] == [("forbidden_effect", "config.yaml")]
    assert [(r.kind, r.value) for r in m.derive_requirements("Do not change tests/test_a.py")] == [("forbidden_effect", "tests/test_a.py")]


def test_a_category_is_checked_against_the_writes(tmp_path):
    reqs = m.derive_requirements("Fix the bug; do not modify the tests.")
    step = {"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "tests/test_pricing.py"}, "tool_result": {"ok": True}}
    other = {"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "ledgercalc/pricing.py"}, "tool_result": {"ok": True}}
    assert any(d.criterion == "forbidden_effect" for d in m.check(reqs, "done", [step], Path(tmp_path)))
    assert not m.check(reqs, "done", [other], Path(tmp_path))


def test_shown_only_kinds_never_stop_anything(tmp_path):
    reqs = m.derive_requirements("Refactor it without changing its public interface, within a budget of $2, before 5 pm, without restarting the database.")
    assert {r.kind for r in reqs} >= {"preserve_interface", "budget", "deadline", "forbidden_effect"}
    write = {"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "a.py"}, "tool_result": {"ok": True}}
    assert m.check(reqs, "done", [write], Path(tmp_path)) == []
    assert all(c["checked_by"] for c in m.conditions_for("Refactor it without changing its public interface, before 5 pm"))

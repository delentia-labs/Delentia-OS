"""RCT-7 round 99: a claim about an ACTION ("I saved report.md") is matched to a step that acted on that file (rct7_judge.action_claims, part of the baseline evidence chain).

Pure function over the episode's steps plus the real baseline chain; no model. What is proved: the right file written -> done; another file written -> no_matching_step; nothing that can change
anything ran -> no_effect_ran; a failed write -> step_failed; Thai claims are read; reading a file is not a claim of changing it; text inside a written file does not count as acting on a file it
mentions; hostile input is read in bounded time.
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane import rct7_judge


def write(path, ok=True, content="x"):
    return {"tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": path, "content": content},
            "tool_result": {"path": path, "bytes": len(content)} if ok else {"error": "permission denied"}}


def read(path):
    return {"tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": path}, "tool_result": {"path": path, "content_text": "hello"}}


def test_the_file_that_was_written_is_done_and_names_the_step():
    out = rct7_judge.action_claims("I saved report.md for you.", [read("a.txt"), write("report.md")])
    assert out == [{"file": "report.md", "status": "done", "step": 2}]


def test_another_file_written_is_no_matching_step():
    out = rct7_judge.action_claims("I saved report.md for you.", [write("notes.txt")])
    assert out == [{"file": "report.md", "status": "no_matching_step"}]


def test_nothing_that_changes_anything_ran():
    out = rct7_judge.action_claims("I wrote report.md.", [read("report.md")])
    assert out == [{"file": "report.md", "status": "no_effect_ran"}]


def test_a_write_that_reported_an_error_is_step_failed_not_done():
    out = rct7_judge.action_claims("Created report.md.", [write("report.md", ok=False)])
    assert out == [{"file": "report.md", "status": "step_failed", "step": 1}]


def test_thai_claims_are_read():
    ok = rct7_judge.action_claims("บันทึกไฟล์ report.md แล้ว", [write("report.md")])
    assert ok and ok[0]["status"] == "done"
    wrong = rct7_judge.action_claims("สร้างไฟล์ report.md เรียบร้อย", [write("notes.txt")])
    assert wrong and wrong[0]["status"] == "no_matching_step"


def test_reading_a_file_is_not_a_claim_of_changing_it():
    assert rct7_judge.action_claims("I read report.md and it says hello.", [read("report.md")]) == []


def test_text_written_into_a_file_does_not_count_as_acting_on_a_file_it_mentions():
    out = rct7_judge.action_claims("I deleted old.txt.", [write("notes.txt", content="remember to delete old.txt")])
    assert out == [{"file": "old.txt", "status": "no_matching_step"}]


def test_no_action_word_no_claim():
    assert rct7_judge.action_claims("The file report.md is 12 bytes.", [write("report.md")]) == []


def test_it_is_part_of_the_baseline_chain_and_counted():
    chain = rct7_judge.baseline_chain("Save the summary as report.md", "I saved report.md. It has 12 bytes.", [write("notes.txt")])
    assert chain["actions"] == [{"file": "report.md", "status": "no_matching_step"}] and chain["actions_unmatched"] == 1
    good = rct7_judge.baseline_chain("Save the summary as report.md", "I saved report.md.", [write("report.md")])
    assert good["actions_unmatched"] == 0


def test_hostile_input_is_read_in_bounded_time():
    for text in (" " * 20000, "a" * 20000, "saved " * 5000, "saved " + "a/" * 8000 + "x.md", "." * 20000, ("saved report.md; " * 4000)):
        started = time.perf_counter()
        rct7_judge.action_claims(text, [write("report.md")])
        assert time.perf_counter() - started < 0.5

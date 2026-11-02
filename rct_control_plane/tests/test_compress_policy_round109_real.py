"""
Round 109: goal-aware COMPRESS (compress_policy). Measured first (research/DELTA_TOKEN_SAVINGS_RESULTS_R109.md, rules in research/COMPRESS_POLICY_CRITERIA_R109.md): Delta v2's aggressive focus is a
good deal for a lookup and a bad one for a task that needs the whole text, for a file read to be edited, and for a goal with no content word. These tests pin the decision and what the loop does with it:

  * a whole-text goal (English and Thai), an edit goal, a goal with no content word and a goal whose words are not in the text are shown WHOLE; a lookup is filtered by its content words only;
  * the generic words ("document", "points", "tell") and file paths no longer act as focus;
  * a text too large to show whole falls back to the old filter (and the expand path), so a context window is not filled;
  * DELENTIA_COMPRESS_POLICY=off restores the old behaviour exactly; an error in the policy never filters; the decision is fast;
  * through the real loop: the real 25 KB build log is shown whole for "summarise" and compressed (and recoverable) for "which tests failed", and the skipped ones are recorded with their reason.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import time

import pytest

from rct_control_plane import compress_policy
from rct_control_plane.compress_policy import Decision, decide
from rct_control_plane.delta_v2 import compress_context
from test_tool_output_compression_real import REAL_LOG, _LogMCP, _run_once_then_finish
from test_governed_autonomous_loop_real import _loop

TEXT = "authentication retry_budget vendor_a row 317 late config\nthe quarterly review of vendor_b\nnothing else here"


@pytest.fixture(autouse=True)
def policy_on(monkeypatch):
    monkeypatch.delenv(compress_policy.OFF_ENV, raising=False)


@pytest.mark.parametrize("goal", [
    "Summarise this document in three bullet points.", "Give me an overview of the file", "Review this file and list any problems", "Compare the three vendors", "Explain what this does",
    "Translate this into Thai", "List all the rows", "What does this file contain?", "What does the file say?", "tell me what is in it", "Go through the whole log",
    "สรุปเอกสารนี้", "ขอภาพรวมของไฟล์", "เปรียบเทียบราคาทั้งหมด", "ตรวจทานไฟล์นี้", "ไฟล์นี้มีอะไรบ้าง"])
def test_a_goal_that_needs_the_whole_text_is_shown_whole(goal):
    decision = decide(goal, "delentia_read_repo_file", {}, TEXT)
    assert decision.apply is False and decision.reason == "whole_text_goal"


@pytest.mark.parametrize("goal", ["Fix the typo in this line: retry_budget", "Edit the config", "Refactor retry_budget", "Rename vendor_a", "Replace the old value", "แก้ไฟล์ config", "ปรับแก้ retry_budget", "เปลี่ยน vendor_a"])
def test_a_goal_that_edits_the_text_sees_the_real_lines(goal):
    decision = decide(goal, "delentia_read_repo_file", {}, TEXT)
    assert decision.apply is False and decision.reason == "edit_goal"


@pytest.mark.parametrize("goal,expected_focus", [
    ("Where is retry_budget defined?", "retry_budget"), ("What does the document say about authentication?", "authentication"),
    ("Find this in the document: row 317 late", "row 317 late"), ("หาบรรทัดที่พูดถึง vendor_a", "vendor_a"), ("Which tests mention vendor_b?", "vendor_b")])
def test_a_lookup_is_filtered_by_its_content_words_only(goal, expected_focus):
    decision = decide(goal, "delentia_read_repo_file", {}, TEXT)
    assert decision.apply is True and decision.reason == "specific_goal" and decision.focus == expected_focus


def test_generic_words_and_paths_are_not_focus_and_a_goal_with_nothing_else_is_not_filtered():
    assert decide("Look at corpus/item3.txt please", "t", {}, TEXT) == Decision(False, "no_content_words")          # a path names the source, not what to look for
    assert decide("What is in the document?", "t", {}, TEXT).reason in ("no_content_words", "whole_text_goal")
    assert decide("Where does notes.md mention retry_budget?", "t", {}, TEXT).focus == "retry_budget"
    assert decide("", "t", {}, TEXT) == Decision(False, "no_goal")


def test_words_that_are_not_in_the_text_give_nothing_to_filter_by():
    assert decide("What is the capital city of France?", "t", {}, TEXT) == Decision(False, "words_not_in_text")
    assert decide("Where is retry_budget or paris?", "t", {}, TEXT).focus == "retry_budget"                        # only the words that occur are kept


def test_a_text_too_large_to_show_whole_keeps_the_old_filter(monkeypatch):
    big = TEXT + "\nfiller line\n" * 12000
    assert len(big) > compress_policy.MAX_WHOLE_CHARS
    decision = decide("Summarise this document", "t", {}, big)
    assert decision.apply is True and decision.reason == "too_large_to_show_whole" and decision.focus == "Summarise this document"       # exactly what the old behaviour passed
    assert decide("Fix the typo in retry_budget", "t", {}, big).reason == "too_large_to_show_whole"


def test_switching_the_policy_off_restores_the_old_behaviour_exactly(monkeypatch):
    monkeypatch.setenv(compress_policy.OFF_ENV, "off")
    goal = "Summarise this document in three bullet points."
    assert decide(goal, "t", {}, TEXT) == Decision(True, "policy_off", goal)                                         # the whole goal is the focus, as before


def test_an_error_in_the_policy_never_filters(monkeypatch):
    def boom(_goal):
        raise RuntimeError("broken")
    monkeypatch.setattr(compress_policy, "_content_words", boom)
    assert decide("Where is retry_budget defined?", "t", {}, TEXT) == Decision(False, "policy_error")


def test_the_decision_on_230_kilobytes_takes_well_under_twenty_milliseconds():
    big = ("line of ordinary text number %d with some words in it\n" * 5000) % tuple(range(5000))
    assert len(big) > 230_000 - 40_000
    started = time.perf_counter()
    for _ in range(5):
        decide("Where is retry_budget defined?", "t", {}, big)
    assert (time.perf_counter() - started) / 5 < 0.020


class TestInTheRealLoop:
    def test_summarise_shows_the_real_build_log_whole_and_the_skip_is_recorded(self, tmp_path, monkeypatch):
        _run_once_then_finish(monkeypatch)
        loop = _loop(tmp_path, "whole", mcp=_LogMCP())
        result = asyncio.run(loop.run("Summarise this build and test log"))
        shown = result["steps"][0]["tool_result"]
        assert "delta_compressed" not in shown and shown["stdout"] == REAL_LOG                     # not compressed: the model reads the whole log (the injection screen's own warning may be added)
        assert [s["reason"] for s in loop._episode_compress_skips] == ["whole_text_goal"]
        assert loop._episode_compressions == []

    def test_a_lookup_is_still_compressed_recoverable_and_focused_on_its_content_words(self, tmp_path, monkeypatch):
        seen = _run_once_then_finish(monkeypatch)
        loop = _loop(tmp_path, "lookup", mcp=_LogMCP())
        result = asyncio.run(loop.run("Which tests failed and why?"))
        shown = result["steps"][0]["tool_result"]
        assert shown["delta_compressed"] is True and shown["reduction_percentage"] > 50
        assert loop._episode_compress_skips == []
        assert seen[1][0].tool_result["delta_compressed"] is True
        from rct_control_plane.tool_output_store import ToolOutputStore
        original = ToolOutputStore(loop._persistence).get(shown["original_id"])
        assert original is not None and REAL_LOG[:200] in original                                  # the original comes back

    def test_the_old_behaviour_is_what_the_loop_does_when_the_policy_is_off(self, tmp_path, monkeypatch):
        monkeypatch.setenv(compress_policy.OFF_ENV, "off")
        _run_once_then_finish(monkeypatch)
        loop = _loop(tmp_path, "off", mcp=_LogMCP())
        goal = "Summarise this build and test log"
        result = asyncio.run(loop.run(goal))
        shown = result["steps"][0]["tool_result"]
        expected = compress_context(loop._render_tool_result({"stdout": REAL_LOG, "stderr": "", "exit_code": 1}), intent_focus=goal, aggressive_mode=True, outline=True)
        assert shown["delta_compressed"] is True and shown["content"] == expected.compressed_delta_text

    def test_a_broken_policy_leaves_the_result_whole_and_the_episode_finishes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(compress_policy, "_content_words", lambda _g: (_ for _ in ()).throw(RuntimeError("broken")))
        _run_once_then_finish(monkeypatch)
        loop = _loop(tmp_path, "broken", mcp=_LogMCP())
        result = asyncio.run(loop.run("Which tests failed and why?"))
        assert result["stopped_reason"] == "llm_finished"
        assert result["steps"][0]["tool_result"]["stdout"] == REAL_LOG
        assert [s["reason"] for s in loop._episode_compress_skips] == ["policy_error"]

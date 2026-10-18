"""Round 87: the review tool for the owner's own sentences (research/review_policy_sentences.py) reads a file, ignores comments, never changes anything and flags a proposal that would loosen the gate."""
from __future__ import annotations

from research import review_policy_sentences as rv
from rct_control_plane import policy_from_text


def test_comments_and_blank_lines_are_ignored(tmp_path):
    path = tmp_path / "s.txt"
    path.write_text("# a comment\n\nNever delete anything.\n  \nAllow reading every file\n", encoding="utf-8")
    assert rv.read_sentences(path) == ["Never delete anything.", "Allow reading every file"]


def test_the_table_has_one_row_per_sentence_an_empty_judgement_column_and_a_loosening_count():
    text = rv.review(["Never delete anything.", "Allow reading every file", "Allow the agent to send email to anyone"])
    rows = [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| #") and not line.startswith("|---")]
    assert len(rows) == 3 and all(row.endswith("|  |") for row in rows)
    assert "0 would loosen the gate" in text


def test_a_proposal_that_allows_more_than_reading_is_flagged():
    loose = policy_from_text.Proposal(status="ok", rules=[{"stance": policy_from_text.ALLOW, "group": "write", "tools": ["delentia_write_repo_file"]}])
    safe = policy_from_text.Proposal(status="ok", rules=[{"stance": policy_from_text.ALLOW, "group": "read", "tools": ["delentia_read_repo_file"]}])
    assert rv.loosens(loose) is True and rv.loosens(safe) is False


def test_nothing_is_applied_by_reviewing():
    assert policy_from_text.propose("Never delete anything.").applied is False


def test_the_main_function_reports_an_empty_file(tmp_path, capsys):
    empty = tmp_path / "e.txt"
    empty.write_text("# nothing\n", encoding="utf-8")
    assert rv.main([str(empty)]) == 2

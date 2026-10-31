"""
Round 106: friction reported by outside testers is counted by a script, the same way for every tester (scripts/tally_tester_feedback.py), from a form that a person fills in
(docs/demo/TESTER_FEEDBACK_FORM_EN.md). The form in the guide is the one the script reads; a form the script cannot read is refused by line number.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import tally_tester_feedback as tally  # noqa: E402

DEMO = ROOT / "docs" / "demo"


def form(alias, *, real="yes", help_="none", steps=None):
    steps = steps or {}
    lines = [f"tester: {alias}", f"real_task: {real}", f"help: {help_}"]
    for i, name in enumerate(tally.STEPS, 1):
        result, minutes, severity = steps.get(name, ("done", 3, "none"))
        lines.append(f"{i}. {name}: {result} | {minutes} | {severity}")
    return "\n".join(lines) + "\nFree text that is never read: S0 blocked | 99 | done"


def test_the_form_in_the_guide_is_one_the_script_can_read():
    for lang in ("EN", "TH"):
        text = (DEMO / f"TESTER_FEEDBACK_FORM_{lang}.md").read_text(encoding="utf-8")
        block = re.search(r"```text\n(.*?)```", text, re.S)
        assert block, f"{lang}: no ```text block holding the form"
        filled = (block.group(1).replace("<alias>", "t1").replace("<yes or no>", "yes").replace("<none, docs_only or asked_someone>", "none")
                  .replace("<result> | <minutes> | <severity>", "done | 3 | none"))
        for name in tally.STEPS:
            assert name in filled, f"{lang}: the form has no step {name}"
        parsed = tally.parse_form(filled, f"guide-{lang}")
        assert list(parsed["steps"]) == list(tally.STEPS)


def test_friction_is_counted_per_step_and_per_tester_with_an_interval():
    forms = [tally.parse_form(form("a", steps={"first_start": ("done", 12, "S2")})),
             tally.parse_form(form("b", help_="asked_someone", steps={"first_approver": ("done_with_help", 25, "S1"), "first_request": ("done", 9, "none")})),
             tally.parse_form(form("c", real="no", steps={"choose_model": ("blocked", 40, "S0"), "first_request": ("skipped", 0, "none")}))]
    result = tally.tally(forms)
    assert result["testers"] == 3 and result["used_for_a_real_task"] == 2
    assert result["per_step"]["first_start"]["friction"] == 1 and result["per_step"]["first_start"]["testers"] == 3
    assert result["per_step"]["first_approver"]["friction"] == 1 and result["per_step"]["choose_model"]["blocked"] == 1
    assert result["per_step"]["download_and_install"]["friction"] == 0
    assert result["per_step"]["first_start"]["median_minutes"] == 3 and result["per_step"]["first_approver"]["median_minutes"] == 3
    lo, hi = result["per_step"]["first_start"]["friction_interval"]
    assert 0.0 < lo < 1 / 3 < hi < 1.0                                                  # 1 of 3 is wide, and it says so
    assert result["any_blocked"] == ["choose_model"]


def test_the_first_request_counts_as_unaided_only_when_done_and_nobody_was_asked():
    forms = [tally.parse_form(form("a")),
             tally.parse_form(form("b", help_="asked_someone")),
             tally.parse_form(form("c", help_="docs_only", steps={"first_request": ("done_with_help", 30, "S1")})),
             tally.parse_form(form("d", steps={"first_request": ("skipped", 0, "none")}))]
    first = tally.tally(forms)["first_request_without_asking"]
    assert first["k"] == 1 and first["of"] == 3                                         # a skipped step is not a failure to do it, and is not in the denominator


@pytest.mark.parametrize("text,needle", [
    (form("a").replace("first_start", "second_start"), "unknown step"),
    (form("a").replace("first_start: done", "first_start: finished"), "unknown result"),
    (form("a").replace("| none\n2.", "| S9\n2.", 1), "cannot read this step line"),                      # looks like a step, does not parse: refused, not skipped
    (form("a").replace("done | 3 | none\n2.", "Done | 3 min | none\n2.", 1), "cannot read this step line"),
    (form("a").replace("tester: a\n", ""), "no 'tester:'"),
    (form("a", real="maybe"), "real_task"),
    (form("a", help_="a lot"), "help:"),
    ("tester: a\nreal_task: yes\nhelp: none\n", "no step lines"),
    (form("a") + "\n1. first_start: done | 2 | none", "twice"),
])
def test_a_form_the_script_cannot_read_is_refused_not_guessed_at(text, needle):
    with pytest.raises(tally.FormError) as why:
        tally.parse_form(text, "f.md")
    assert needle in str(why.value) and "f.md" in str(why.value)


def test_free_text_is_never_read_and_never_printed(tmp_path, capsys):
    secret = "my name is Somchai and my key is sk-or-v1-abcdef"
    (tmp_path / "a.md").write_text(form("a") + f"\n{secret}\n", encoding="utf-8")
    (tmp_path / "b.md").write_text(form("b", steps={"uninstall": ("blocked", 10, "S0")}), encoding="utf-8")
    out = tmp_path / "report.md"
    code = tally.main([str(tmp_path), "--out", str(out)])
    printed = capsys.readouterr().out + out.read_text(encoding="utf-8")
    assert code == 0 and "2 tester(s)" in printed and "uninstall" in printed and "Somchai" not in printed and "sk-or" not in printed


def test_a_folder_with_a_bad_form_still_counts_the_good_ones_but_exits_non_zero(tmp_path, capsys):
    (tmp_path / "good.md").write_text(form("a"), encoding="utf-8")
    (tmp_path / "bad.md").write_text("tester: x\nreal_task: yes\nhelp: none\n1. nothing: done | 1 | none\n", encoding="utf-8")
    code = tally.main([str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 1 and "bad.md" in captured.err and "1 tester(s)" in captured.out
    empty = tmp_path / "empty"
    empty.mkdir()
    assert tally.main([str(empty)]) == 2

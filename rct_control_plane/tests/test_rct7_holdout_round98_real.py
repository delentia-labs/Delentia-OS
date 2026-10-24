"""The holdout runner (research/rct7_holdout.py): the pre-registration is enforced by the code, not by good intentions. Real files, real hashing; the provider is a script."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from research import rct7_holdout as holdout


def make_sheet(tmp_path, kind="request", n=24, labelled=True):
    lines = ["# sheet", "", "| # | request | A/B/? | note |" if kind == "request" else "| # | request | answer | M/N/? | note |", "|---|---|---|---|" + ("---|" if kind == "result" else "")]
    for i in range(1, n + 1):
        positive = i <= n // 2
        if kind == "request":
            label = ("A" if positive else "B") if labelled else ""
            lines.append(f"| {i} | request {i} {'needs a thing' if positive else 'is plain'} | {label} | |")
        else:
            label = ("N" if positive else "M") if labelled else ""
            lines.append(f"| {i} | request {i} | answer {i} | {label} | |")
    path = tmp_path / f"{kind}_sheet.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class Script:
    """Stops (asks / says not met) for the items whose text says so; can be made to fail."""

    def __init__(self, accuracy_flip=(), boom=False):
        self.flip, self.boom, self.calls = set(accuracy_flip), boom, 0

    async def complete(self, prompt, system_prompt=None, temperature=0.0, max_tokens=300, json_mode=False):
        from rct_control_plane import rct7_judge
        self.calls += 1
        if self.boom:
            raise RuntimeError("down")
        number = int(prompt.split("request ")[1].split()[0])
        positive = "needs a thing" in prompt or (system_prompt == rct7_judge.SYSTEM_RESULT and number <= 12)
        stop = positive != (number in self.flip)
        if system_prompt == rct7_judge.SYSTEM_REQUEST:
            return json.dumps({"clear": False, "unknowns": [{"question": "which?", "about": f"request {number}"}]} if stop else {"clear": True, "unknowns": []})
        return json.dumps({"meets": False, "unmet": [{"part": f"request {number}", "why": "no"}]} if stop else {"meets": True, "unmet": []})


def test_the_wilson_interval_is_the_published_value():
    low, high = holdout.wilson(8, 10)
    assert (low, high) == (0.49, 0.943)
    assert holdout.wilson(0, 0) == (0.0, 1.0) and holdout.wilson(10, 10)[1] == 1.0


def test_a_compact_reply_is_read_with_ranges_and_a_conflict_is_an_error():
    assert holdout.parse_compact("A: 1,3,5-7 B: 2, 4 ?: 9") == {1: "A", 3: "A", 5: "A", 6: "A", 7: "A", 2: "B", 4: "B", 9: "?"}
    with pytest.raises(ValueError):
        holdout.parse_compact("A: 1,2 B: 2")
    assert holdout.parse_compact("nothing here") == {}


def test_both_sheet_kinds_are_read(tmp_path):
    rows = holdout.parse_sheet(make_sheet(tmp_path, "request").read_text(encoding="utf-8"))
    assert holdout.kind_of(rows) == "request" and len(rows) == 24 and rows[1]["label"] == "A"
    rows = holdout.parse_sheet(make_sheet(tmp_path, "result").read_text(encoding="utf-8"))
    assert holdout.kind_of(rows) == "result" and rows[1]["answer"] == "answer 1" and rows[13]["label"] == "M"


def test_an_unlabelled_sheet_can_be_sealed_from_a_compact_reply(tmp_path):
    sheet = make_sheet(tmp_path, "request", labelled=False)
    reply = "A: 1-12 B: 13-24"
    sealed = holdout.seal(sheet, reply, "the Architect")
    assert sealed["counts"] == {"A": 12, "B": 12} and sealed["labelled_by"] == "the Architect"


def test_sealing_refuses_a_holdout_too_small_or_one_sided(tmp_path):
    with pytest.raises(ValueError, match="at least 20"):
        holdout.seal(make_sheet(tmp_path, "request", n=10), "", "x")
    one_sided = make_sheet(tmp_path, "request", n=24, labelled=False)
    with pytest.raises(ValueError, match="at least 5 of each side"):
        holdout.seal(one_sided, "A: 1-22 B: 23,24", "x")


def test_nothing_runs_on_labels_that_were_not_sealed(tmp_path):
    sheet = make_sheet(tmp_path)
    with pytest.raises(ValueError, match="not sealed"):
        asyncio.run(holdout.run_once(sheet, Script(), "m"))


def test_a_sealed_sheet_whose_labels_were_changed_is_refused(tmp_path):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    sealed_path = sheet.with_suffix(".sealed.json")
    data = json.loads(sealed_path.read_text(encoding="utf-8"))
    data["items_data"]["1"]["label"] = "B"                                                    # someone edits a label after sealing
    sealed_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="no longer match"):
        holdout.load_sealed(sheet)


def test_sealing_the_same_sheet_with_other_labels_is_refused(tmp_path):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    with pytest.raises(ValueError, match="sealed with other labels"):
        holdout.seal(sheet, "A: 1-5 B: 6-24", "x")


def test_a_perfect_model_scores_perfectly_and_a_flipped_one_is_measured_honestly(tmp_path):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    perfect = asyncio.run(holdout.run_once(sheet, Script(), "perfect"))
    assert perfect["result"]["found"] == 12 and perfect["result"]["false_stops"] == 0 and perfect["result"]["rule_met"] is True
    flipped = asyncio.run(holdout.run_once(sheet, Script(accuracy_flip=range(1, 5)), "misses-four"))
    assert flipped["result"]["found"] == 8 and flipped["result"]["found_rate"] == 0.667 and flipped["result"]["rule_met"] is False
    noisy = asyncio.run(holdout.run_once(sheet, Script(accuracy_flip=(13, 14, 15, 16)), "stops-four"))
    assert noisy["result"]["false_stops"] == 4 and noisy["result"]["false_stop_rate"] == 0.333 and noisy["result"]["rule_met"] is False


def test_a_model_may_run_once_per_prompt_and_labels_and_a_repeat_is_recorded_as_one(tmp_path):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    provider = Script()
    asyncio.run(holdout.run_once(sheet, provider, "m"))
    calls_after_first = provider.calls
    with pytest.raises(ValueError, match="already ran"):
        asyncio.run(holdout.run_once(sheet, provider, "m"))
    assert provider.calls == calls_after_first                                              # refused before a single call
    again = asyncio.run(holdout.run_once(sheet, provider, "m", again=True))
    assert again["repeat"] is True and len(holdout.runs_of(sheet)) == 2


def test_a_model_that_is_down_is_counted_as_malformed_and_never_as_a_stop(tmp_path):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    entry = asyncio.run(holdout.run_once(sheet, Script(boom=True), "down"))
    assert entry["result"]["malformed"] == 24 and entry["result"]["found"] == 0 and entry["result"]["false_stops"] == 0


def test_a_result_sheet_is_scored_the_same_way(tmp_path):
    sheet = make_sheet(tmp_path, "result")
    holdout.seal(sheet, "", "x")
    entry = asyncio.run(holdout.run_once(sheet, Script(), "perfect"))
    assert entry["result"]["found"] == 12 and entry["result"]["false_stops"] == 0


def test_a_changed_prompt_is_a_new_version_so_it_can_run_again(tmp_path, monkeypatch):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    asyncio.run(holdout.run_once(sheet, Script(), "m"))
    from rct_control_plane import rct7_judge
    monkeypatch.setattr(rct7_judge, "SYSTEM_REQUEST", rct7_judge.SYSTEM_REQUEST + " (revised)")
    entry = asyncio.run(holdout.run_once(sheet, Script(), "m"))
    assert entry["repeat"] is False                                                          # a different prompt, a different pre-registration; the first run stays on record
    assert len({r["prompt_version"] for r in holdout.runs_of(sheet)}) == 2


def test_a_paid_run_is_refused_without_the_key_the_opt_in_and_a_budget(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DELENTIA_RUN_LIVE_TESTS", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        holdout._provider("openrouter", "some/model", 5.0)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.setenv("DELENTIA_RUN_LIVE_TESTS", "1")
    with pytest.raises(ValueError, match="budget"):
        holdout._provider("openrouter", "some/model", 0.0)

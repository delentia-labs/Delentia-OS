"""RCT-7 round 99: the two-axis holdout runner (research/rct7_holdout_twoaxis.py) and the context-aware judge prompt (criteria: research/rct7_round98_criteria.md H3).

A scripted provider; real files, real hashing. What is proved: labels are sealed before a run and cannot change afterwards, the compact reply is read per axis, the `plain` judge never sees the context
and the `context` judge does, each (model, variant) runs once, the Q axis is scored by the same rule as every holdout, the C axis is kept, and the plain prompt's version did not change.
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import rct7_judge
from research import rct7_holdout as base
from research import rct7_holdout_twoaxis as two

ROWS = [(n, "NONE" if n % 2 else "Pending approvals: 1", f"Do thing number {n}") for n in range(1, 25)]


def make_sheet(tmp_path, labelled=False):
    lines = ["| # | บริบทที่ agent มี | คำขอ | Q | C | หมายเหตุ |", "|---|---|---|---|---|---|"]
    for n, context, request in ROWS:
        q = ("Y" if n <= 12 else "N") if labelled else ""
        c = ("Y" if n % 3 == 0 else "N") if labelled else ""
        lines.append(f"| {n} | {context} | {request} | {q} | {c} | |")
    path = tmp_path / "set3.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


COMPACT = "Q: Y=1-12  N=13-24\nC: Y=3,6,9,12,15,18,21,24  N=1,2,4,5,7,8,10,11,13,14,16,17,19,20,22,23"


class Script:
    """Stops (clear: false, with a question that cites the request) for items 1-12 unless the context was shown, in which case it stops only the odd ones."""

    def __init__(self):
        self.prompts = []

    async def complete(self, prompt, system_prompt=None, temperature=0.0, max_tokens=300, json_mode=False):
        self.prompts.append((system_prompt, prompt))
        number = int(prompt.split("Do thing number ")[1].split("\n")[0].strip())
        has_context = "<context>" in prompt
        stop = number <= 12 and (not has_context or number % 2 == 1)
        if stop:
            return json.dumps({"clear": False, "unknowns": [{"question": "Which one?", "about": f"thing number {number}"}]})
        return json.dumps({"clear": True, "unknowns": []})


def test_the_compact_reply_is_read_per_axis_and_a_conflict_is_an_error():
    parsed = two.parse_compact2(COMPACT)
    assert parsed["Q"][1] == "Y" and parsed["Q"][24] == "N" and parsed["C"][3] == "Y" and parsed["C"][1] == "N"
    with pytest.raises(ValueError, match="both"):
        two.parse_compact2("Q: Y=1 N=1")
    assert two.parse_compact2("nothing here") == {"Q": {}, "C": {}}


def test_a_sheet_is_read_into_context_request_and_both_labels(tmp_path):
    rows = two.parse_sheet2(make_sheet(tmp_path, labelled=True).read_text(encoding="utf-8"))
    assert len(rows) == 24 and rows[1]["context"] == "NONE" and rows[2]["context"] == "Pending approvals: 1" and rows[1]["Q"] == "Y" and rows[13]["Q"] == "N"


def test_nothing_runs_on_labels_that_were_not_sealed_and_sealing_refuses_a_one_sided_set(tmp_path):
    sheet = make_sheet(tmp_path)
    with pytest.raises(ValueError, match="not sealed"):
        asyncio.run(two.run_once2(sheet, Script(), "m"))
    with pytest.raises(ValueError, match="at least 20"):
        two.seal2(sheet, "Q: Y=1-3 N=4-8\nC: Y=1 N=2-8", "x")
    with pytest.raises(ValueError, match="at least 5 of each"):
        two.seal2(sheet, "Q: Y=1-24\nC: Y=1-24", "x")


def test_sealed_labels_cannot_be_changed_afterwards(tmp_path):
    sheet = make_sheet(tmp_path)
    sealed = two.seal2(sheet, COMPACT, "x")
    assert sealed["counts_Q"] == {"Y": 12, "N": 12} and sealed["counts_C"] == {"Y": 8, "N": 16}
    assert two.seal2(sheet, COMPACT, "x")["labels_sha256"] == sealed["labels_sha256"]
    with pytest.raises(ValueError, match="other labels"):
        two.seal2(sheet, "Q: Y=1-11 N=12-24\nC: Y=1-8 N=9-24", "x")
    path, _ = base._paths(sheet)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items_data"]["1"]["Q"] = "N"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="no longer match"):
        two.load_sealed2(sheet)


def test_the_plain_judge_never_sees_the_context_and_the_context_judge_does(tmp_path):
    sheet = make_sheet(tmp_path)
    two.seal2(sheet, COMPACT, "x")
    plain, ctx = Script(), Script()
    a = asyncio.run(two.run_once2(sheet, plain, "m", "plain"))
    b = asyncio.run(two.run_once2(sheet, ctx, "m", "context"))
    assert all("<context>" not in p for _s, p in plain.prompts) and all(s == rct7_judge.SYSTEM_REQUEST for s, _p in plain.prompts)
    assert all("<context>" in p for _s, p in ctx.prompts) and all(s == rct7_judge.SYSTEM_REQUEST_CTX for s, _p in ctx.prompts)
    assert a["result"]["found"] == 12 and a["result"]["false_stops"] == 0 and a["result"]["rule_met"] is True
    assert b["result"]["found"] == 6 and b["result"]["found_rate"] == 0.5 and b["result"]["rule_met"] is False          # the scripted context judge stops only the odd ones
    assert a["prompt_version"] != b["prompt_version"] and a["variant"] == "plain" and b["variant"] == "context"
    assert len(b["verdicts"]) == 24


def test_each_model_and_variant_runs_once_and_a_repeat_is_recorded_as_one(tmp_path):
    sheet = make_sheet(tmp_path)
    two.seal2(sheet, COMPACT, "x")
    provider = Script()
    asyncio.run(two.run_once2(sheet, provider, "m", "context"))
    calls = len(provider.prompts)
    with pytest.raises(ValueError, match="already ran"):
        asyncio.run(two.run_once2(sheet, provider, "m", "context"))
    assert len(provider.prompts) == calls
    asyncio.run(two.run_once2(sheet, provider, "m", "plain"))                                  # the other variant is its own run
    again = asyncio.run(two.run_once2(sheet, provider, "m", "context", again=True))
    assert again["repeat"] is True and len(base.runs_of(sheet)) == 3


def test_the_original_judge_prompt_and_its_version_did_not_change_and_the_context_prompt_is_frozen():
    assert base.rct7_judge_prompt_version() == "8292fc3416cc"                                    # recorded in the criteria file before any set-3 label existed
    assert rct7_judge.context_prompt_version() == "5dbf3fa34125"
    assert "about" in rct7_judge.SYSTEM_REQUEST_CTX and "Do not ask for permission" in rct7_judge.SYSTEM_REQUEST_CTX


def test_the_cite_guard_still_reads_the_request_not_the_context():
    class Cites:
        async def complete(self, *a, **k):
            return json.dumps({"clear": False, "unknowns": [{"question": "Who?", "about": "words only the context contains"}]})
    verdict = asyncio.run(rct7_judge.judge_request(Cites(), "Send the report", "words only the context contains"))
    assert verdict.clear is None and verdict.dropped == 1


def test_pairs_can_be_read_side_by_side(tmp_path):
    sheet = make_sheet(tmp_path)
    two.seal2(sheet, COMPACT, "x")
    asyncio.run(two.run_once2(sheet, Script(), "m", "plain"))
    sidecar = tmp_path / "pairs.json"
    sidecar.write_text(json.dumps({"pairs": {"Do thing number 1": [1, 2]}}), encoding="utf-8")
    view = two.pair_view(sheet, sidecar)
    assert view[0]["rows"][0]["n"] == 1 and view[0]["rows"][0]["judge"]["m/plain"] is True


def test_a_hostile_line_is_read_in_bounded_time():
    for text in ("Q: " + "Y=1 " * 4000, "C: Y=" + "1," * 5000, "Q" + " " * 20000 + ":", "| 1 |" + "x|" * 5000):
        started = time.perf_counter()
        try:
            two.parse_compact2(text)
        except ValueError:
            pass
        two.parse_sheet2(text)
        assert time.perf_counter() - started < 1.0

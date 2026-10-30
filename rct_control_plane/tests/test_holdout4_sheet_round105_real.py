"""
Round 105: holdout set 4 (research/holdout4_sheet_r105.py; criteria research/rct7_round98_criteria.md H4, written before the set).

What is proved: 60 fresh requests (30 meant to ask, 30 meant to go ahead) none of which is, or is closer than 0.85 to, a request of sets 1-3 (read from the sealed files in the repository); the context the
Architect sees is exactly `judge_context.build` of the stored state; a table cell can carry that text and give it back unchanged; the sheet parses with the same reader as set 3; the labelling page
is valid and carries all 60 items; sealing works with Q labels only (C recorded as `?`); and the runner shows the CONTEXT judge the decoded text, byte for byte, and the PLAIN judge nothing.
"""
import asyncio
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import judge_context
from research import holdout3_sheet_r99 as set3
from research import holdout4_sheet_r105 as set4
from research import rct7_holdout_twoaxis as two

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def earlier_requests():
    out = [r for r, _, _ in set3.PAIRS] + [r for r, _ in set3.SINGLES]
    for name in ("holdout1_sealed.json", "holdout2_sealed.json"):
        data = json.load(open(os.path.join(ROOT, "research", "results_round99", name), encoding="utf-8"))
        out += [str(v.get("request") or "") for v in data["items_data"].values()]
    return [x for x in out if x]


@pytest.fixture(scope="module")
def rows():
    return set4.build()


def test_sixty_items_thirty_each(rows):
    assert len(rows) == 60 and sorted(r["n"] for r in rows) == list(range(1, 61))
    assert sum(r["intent"] == "ask" for r in rows) == 30 and sum(r["intent"] == "go" for r in rows) == 30
    assert len({r["request"] + "|" + r["context"] for r in rows}) == 60 and len({r["request"] for r in rows}) == 59


def test_the_order_is_fixed_by_the_seed_and_mixes_the_two_kinds(rows):
    assert [r["request"] for r in set4.build()] == [r["request"] for r in rows]
    first_twenty = [r["intent"] for r in rows[:20]]
    assert 5 <= first_twenty.count("ask") <= 15


def test_no_request_is_from_an_earlier_set_or_close_to_one(rows):
    before = [b.strip().lower() for b in earlier_requests()]
    assert len(before) > 100
    for r in rows:
        mine = r["request"].strip().lower()
        for b in before:
            assert difflib.SequenceMatcher(None, mine, b).ratio() < 0.85, (r["request"], b)


def test_the_context_is_the_builders_own_text(rows):
    for r in rows:
        s = r["state"]
        expected = judge_context.build(recent_turns=s["recent_turns"], pending_tools=s["pending_tools"], memories=s["memories"], rules=s["rules"], files=s["files"],
                                       capabilities=judge_context.capability_phrases(s["tools"]))
        assert r["context"] == expected and len(r["context"]) <= judge_context.MAX_TOTAL_CHARS
    assert any(r["context"] == judge_context.NOTHING for r in rows), "some requests must come with nothing at all"
    assert any("Standing rules" in r["context"] for r in rows) and any("Files in the workspace" in r["context"] for r in rows)
    assert any("search the web" in r["context"] for r in rows)


def test_no_state_shows_a_secret_looking_name_or_uses_the_cell_marks(rows):
    for r in rows:
        for name in r["state"]["files"]:
            assert not judge_context._SECRET_NAME.search(name), (r["request"], name)
        blob = json.dumps(r["state"], ensure_ascii=False) + r["request"]
        assert set4.NEWLINE not in blob and set4.PIPE not in blob


def test_a_cell_carries_the_text_and_gives_it_back_unchanged(rows):
    for r in rows:
        cell = set4.encode_cell(r["context"])
        assert "\n" not in cell and "|" not in cell
        assert set4.decode_cell(cell) == r["context"]


def test_the_sheet_parses_with_the_set_3_reader_and_decodes_to_the_same_contexts(rows):
    parsed = two.parse_sheet2(set4.sheet_text(rows))
    assert sorted(parsed) == list(range(1, 61))
    for r in rows:
        row = parsed[r["n"]]
        assert row["request"] == r["request"] and set4.decode_cell(row["context"]) == r["context"] and row["Q"] == "" and row["C"] == "?"


def test_the_labelling_page_is_valid_and_has_every_item(rows):
    html = set4.html_text(rows)
    block = re.search(r"const ITEMS=(\[.*?\]);const KEY=", html, re.S)
    items = json.loads(block.group(1).replace("<\\/", "</"))
    assert [i["n"] for i in items] == list(range(1, 61)) and items[0]["context"] == rows[0]["context"]
    assert "holdout4-q-2026-10-30" in html and "__ITEMS__" not in html and "__INTRO__" not in html
    assert "C: ?=" in html                                          # the C line of the summary is generated, every item `?`


def test_labels_of_the_q_axis_alone_seal(tmp_path, rows):
    sheet = tmp_path / "set4.md"
    sheet.write_text(set4.sheet_text(rows), encoding="utf-8")
    ask = [r["n"] for r in rows if r["intent"] == "ask"]
    go = [r["n"] for r in rows if r["intent"] == "go"]
    compact = f"Q: Y={','.join(map(str, ask))}  N={','.join(map(str, go))}\nC: ?={','.join(str(r['n']) for r in rows)}"
    sealed = two.seal2(sheet, compact, "test")
    assert sealed["items"] == 60 and sealed["counts_Q"] == {"Y": 30, "N": 30} and sealed["counts_C"] == {"?": 60}


class Capture:
    def __init__(self):
        self.prompts = []

    async def complete(self, prompt, system_prompt=None, temperature=0.0, max_tokens=300, json_mode=False):
        self.prompts.append(prompt)
        return json.dumps({"clear": True, "unknowns": []})


def test_the_context_judge_sees_the_decoded_text_and_the_plain_judge_sees_none(tmp_path, rows):
    sheet = tmp_path / "set4.md"
    sheet.write_text(set4.sheet_text(rows), encoding="utf-8")
    ask = [r["n"] for r in rows if r["intent"] == "ask"]
    go = [r["n"] for r in rows if r["intent"] == "go"]
    two.seal2(sheet, f"Q: Y={','.join(map(str, ask))}  N={','.join(map(str, go))}\nC: ?={','.join(str(r['n']) for r in rows)}", "test")
    plain, ctx = Capture(), Capture()
    asyncio.run(two.run_once2(sheet, plain, "stub", "plain", context_decoder=set4.decode_cell))
    asyncio.run(two.run_once2(sheet, ctx, "stub", "context", context_decoder=set4.decode_cell))
    assert len(plain.prompts) == len(ctx.prompts) == 60
    assert not any("<context>" in p for p in plain.prompts)
    for row, prompt in zip(sorted(rows, key=lambda r: r["n"]), ctx.prompts, strict=True):      # the runner goes through the sealed items in order of their number
        assert row["request"] in prompt
        assert row["context"] in prompt, "the judge must see the builder's text with real line breaks and pipes, exactly"
    assert sum(1 for r in rows if r["request"] == "Use the same budget as last time") == 2      # the one deliberate pair: same sentence, two contexts

"""
Round 115, candidate A1: Thai hints for external tools (criteria: research/THAI_TOOL_MENU_AMENDMENT_3_R115.md, written before the module).
These tests pin the rules that need no judgement: off / no file / stale hint = today's menu; a Thai request with a valid hint brings the tool in; an English request is scored exactly as before;
the generator keeps only Thai words, never writes an entry when the model says nothing, and never sees a request.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
from pathlib import Path

import pytest

from rct_control_plane import tool_hints_th as th
from rct_control_plane import tool_menu

SERVERS = json.loads((Path(__file__).resolve().parents[2] / "research" / "tool_menu_external_goals_r114.json").read_text(encoding="utf-8"))["servers"]
TOOLS = [{"name": f"mcp__{s}__{t}", "description": d, "input_schema": {}} for s, tools in SERVERS.items() for t, d in tools.items()] + [
    {"name": "delentia_read_repo_file", "description": "Read a text file from the workspace folder by its relative path", "input_schema": {}},
    {"name": "delentia_web_search", "description": "Search the web", "input_schema": {}},
]
READ_NOTE = next(t for t in TOOLS if t["name"] == "mcp__notes__read_note")


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    for var in (th.SWITCH_ENV, th.PATH_ENV, tool_menu.THAI_MENU_ENV, tool_menu.MENU_ENV):
        monkeypatch.delenv(var, raising=False)
    th._cache.update(path=None, mtime=None, data={})
    monkeypatch.setenv(th.PATH_ENV, str(tmp_path / "hints.json"))
    yield


def write_hints(tmp_path, hints, tool=READ_NOTE, source="model"):
    path = tmp_path / "hints.json"
    entries = {tool["name"]: {"hint": hints, "for": th.fingerprint(tool), "source": source}}
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    th._cache.update(path=None, mtime=None, data={})
    return path


def menu(goal):
    return [t["name"] for t in tool_menu.rank_tools(goal, TOOLS, 10)]


def test_with_no_hints_file_the_menu_is_todays(monkeypatch):
    goals = ["อ่านโน้ตเรื่องงบให้หน่อย", "Read the note about the budget", "ลบนัดหมายเลข 31"]
    before = [tool_menu.score_tools(g, TOOLS) for g in goals]
    monkeypatch.setenv(th.SWITCH_ENV, "on")
    assert [tool_menu.score_tools(g, TOOLS) for g in goals] == before


def test_with_the_switch_off_a_hints_file_changes_nothing(tmp_path):
    goals = ["เปิดดูโน้ตงบหน่อย", "Read the note about the budget"]
    before = [tool_menu.score_tools(g, TOOLS) for g in goals]
    write_hints(tmp_path, "เปิดดูโน้ต อ่านบันทึก ดูโน้ตงบ")
    assert [tool_menu.score_tools(g, TOOLS) for g in goals] == before


def test_a_valid_hint_brings_the_tool_in_for_a_thai_request(monkeypatch, tmp_path):
    assert "mcp__notes__read_note" not in menu("เปิดดูบันทึกประชุมให้หน่อย")
    write_hints(tmp_path, "เปิดดูโน้ต อ่านบันทึก เปิดบันทึกประชุม")
    monkeypatch.setenv(th.SWITCH_ENV, "on")
    assert "mcp__notes__read_note" in menu("เปิดดูบันทึกประชุมให้หน่อย")


def test_an_english_request_is_scored_exactly_as_before_with_hints_on(monkeypatch, tmp_path):
    goals = ["Read the note about the budget", "list my events next week", "Search the tickets for timeout"]
    before = [tool_menu.score_tools(g, TOOLS) for g in goals]
    write_hints(tmp_path, "เปิดดูโน้ต อ่านบันทึก")
    monkeypatch.setenv(th.SWITCH_ENV, "on")
    assert [tool_menu.score_tools(g, TOOLS) for g in goals] == before


def test_a_hint_made_for_another_description_is_ignored(monkeypatch, tmp_path):
    changed = {**READ_NOTE, "description": "Read a note by title and also its history."}
    write_hints(tmp_path, "เปิดดูโน้ต อ่านบันทึก เปิดบันทึกประชุม", tool=changed)
    monkeypatch.setenv(th.SWITCH_ENV, "on")
    assert th.hint_for(READ_NOTE) == ""
    assert "mcp__notes__read_note" not in menu("เปิดดูบันทึกประชุมให้หน่อย")


def test_a_malformed_or_missing_file_is_an_empty_dictionary(monkeypatch, tmp_path):
    monkeypatch.setenv(th.SWITCH_ENV, "on")
    assert th.load() == {}
    (tmp_path / "hints.json").write_text("not json {", encoding="utf-8")
    th._cache.update(path=None, mtime=None, data={})
    assert th.load() == {} and th.hint_for(READ_NOTE) == ""


def test_a_built_in_tool_keeps_its_own_hint_and_ignores_the_file(monkeypatch, tmp_path):
    built_in = next(t for t in TOOLS if t["name"] == "delentia_read_repo_file")
    write_hints(tmp_path, "คำที่ไม่เกี่ยวข้องเลย", tool=built_in)
    monkeypatch.setenv(th.SWITCH_ENV, "on")
    before = tool_menu._doc(built_in)["thai"]
    assert before == tool_menu._doc(built_in)["thai"] and "คำที่ไม่เกี่ยวข้องเลย"[:3] not in {t[:3] for t in before}


def test_clean_keeps_only_thai_words_of_three_letters_or_more():
    raw = "<think>hm</think>1. อ่านโน้ต, ดู\n2) เปิดบันทึก - read note ดูโน้ต อ่านโน้ต"
    assert th.clean(raw) == "อ่านโน้ต เปิดบันทึก ดูโน้ต"          # numbering, English, two-letter words and a duplicate are gone


def test_generate_writes_a_model_entry_only_when_the_answer_has_thai_words():
    seen = []

    def ask(prompt, model):
        seen.append(prompt)
        return "เปิดดูโน้ต อ่านบันทึก" if "read_note" in prompt else "no thai here"

    out = th.generate([READ_NOTE, TOOLS[1]], ask=ask)
    assert list(out) == [READ_NOTE["name"]] and out[READ_NOTE["name"]]["source"] == "model" and out[READ_NOTE["name"]]["for"] == th.fingerprint(READ_NOTE)
    assert all("Tool name:" in p and "Tool description:" in p for p in seen) and len(seen) == 2


def test_generate_with_no_model_writes_nothing():
    assert th.generate([READ_NOTE], ask=lambda prompt, model: None) == {}


def test_the_prompt_never_names_a_request_or_a_dataset():
    for word in ("ticked", "holdout", "sentence", "Architect"):
        assert word not in th.PROMPT

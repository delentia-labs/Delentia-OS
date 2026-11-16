"""
Round 115: Thai requests and the ranked tool menu. Criteria: research/THAI_TOOL_MENU_CRITERIA_R115.md and its Amendment 1, written before the table.

A Thai request shares no word with an ENGLISH external tool description, so none of the external tools reached the menu (0 of 119 sentences). The switch DELENTIA_TOOL_MENU_THAI=on applies a small fixed table.
These tests pin: off changes nothing, English and non-Thai requests are scored exactly as before, a domain noun is required, and the table brings the right server in for Thai requests.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
from pathlib import Path

import pytest

from rct_control_plane import tool_menu

SERVERS = json.loads((Path(__file__).resolve().parents[2] / "research" / "tool_menu_external_goals_r114.json").read_text(encoding="utf-8"))["servers"]
TOOLS = [{"name": f"mcp__{s}__{t}", "description": d, "input_schema": {}} for s, tools in SERVERS.items() for t, d in tools.items()] + [
    {"name": "delentia_read_repo_file", "description": "Read a text file from the workspace folder by its relative path", "input_schema": {}},
    {"name": "delentia_write_repo_file", "description": "Create or overwrite a file in the workspace", "input_schema": {}},
    {"name": "delentia_web_search", "description": "Search the web", "input_schema": {}},
]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv(tool_menu.THAI_MENU_ENV, raising=False)
    monkeypatch.delenv(tool_menu.MENU_ENV, raising=False)


def names(goal):
    return {t["name"] for t in tool_menu.rank_tools(goal, TOOLS, 10)}


def test_today_a_thai_request_brings_no_external_tool_in():
    assert not [n for n in names("อ่านโน้ตเรื่องงบให้หน่อย") if n.startswith("mcp__")]


def test_with_the_switch_on_a_thai_request_brings_its_server_in(monkeypatch):
    monkeypatch.setenv(tool_menu.THAI_MENU_ENV, "on")
    assert "mcp__notes__read_note" in names("อ่านโน้ตเรื่องงบให้หน่อย")
    assert "mcp__notes__write_note" in names("จดสรุปที่คุยกับลูกค้าไว้ในโน้ตด้วย")
    assert "mcp__tickets__create_ticket" in names("เปิดเคสเรื่องหน้า login ช้าให้หน่อย")
    assert "mcp__calendar__delete_event" in names("ลบนัดหมายเลข 31")
    assert "mcp__mailbox__move_message" in names("ย้ายข้อความ 77 ไปโฟลเดอร์ Archive")


def test_off_is_exactly_today(monkeypatch):
    goals = ["อ่านโน้ตเรื่องงบให้หน่อย", "ลบนัดหมายเลข 31", "Read the note about the budget", "list my events next week"]
    before = [tool_menu.score_tools(g, TOOLS) for g in goals]
    monkeypatch.setenv(tool_menu.THAI_MENU_ENV, "off")
    assert [tool_menu.score_tools(g, TOOLS) for g in goals] == before


def test_an_english_request_is_scored_exactly_as_before_with_the_switch_on(monkeypatch):
    goals = ["Read the note about the budget", "list my events next week", "Search the tickets for timeout", "delete the file temp.log"]
    before = [tool_menu.score_tools(g, TOOLS) for g in goals]
    monkeypatch.setenv(tool_menu.THAI_MENU_ENV, "on")
    assert [tool_menu.score_tools(g, TOOLS) for g in goals] == before
    assert all(tool_menu.thai_expansion(g) == "" for g in goals), "the table is applied only when the request contains a Thai character"


def test_a_request_with_no_domain_noun_is_not_expanded():
    for goal in ("ลบไฟล์ temp_output.log ออกจากโปรเจกต์", "อ่านหน้าเว็บ https://example.com แล้วสรุปให้", "ค้นหาไฟล์ที่มีคำว่า FDIA ในโปรเจกต์"):
        assert tool_menu.thai_expansion(goal) == "", goal


def test_verbs_count_only_next_to_a_domain_noun():
    expansion = tool_menu.thai_expansion("ลบนัดหมายเลข 31")
    assert "calendar" in expansion and "delete" in expansion


def test_a_file_request_does_not_pull_in_external_read_tools(monkeypatch):
    monkeypatch.setenv(tool_menu.THAI_MENU_ENV, "on")
    assert not [n for n in names("อ่านไฟล์ pyproject.toml แล้วบอกชื่อโปรเจกต์") if n.startswith("mcp__")]
    assert not [n for n in names("ลบไฟล์ temp_output.log ออกจากโปรเจกต์") if n.startswith("mcp__")]


def test_words_that_look_like_nouns_but_are_not_do_not_count():
    for goal in ("แปลประโยคนี้เป็นข้อความภาษาอังกฤษ", "ช่วยจดทะเบียนบริษัท", "ดูแลลูกค้าให้ดี"):
        assert tool_menu.thai_expansion(goal) == "", goal
    assert "mail" in tool_menu.thai_expansion("อ่านจดหมายฉบับล่าสุด")


def test_the_holdout_form_shares_no_sentence_with_the_development_set():
    import importlib.util
    root = Path(__file__).resolve().parents[2] / "research"
    spec = importlib.util.spec_from_file_location("holdout_form", root / "make_ranker_holdout_form_r115.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dev = json.loads((root / "tool_menu_owner_choices_r115.json").read_text(encoding="utf-8"))
    seen = {c["text"] for item in dev["items"] for c in item["chosen"]} | {"เรื่อง 77 จบแล้วนะ"}
    new = [p["t"] for d in mod.DATA for p in d["phr"]]
    assert len(new) == 120 and not (set(new) & seen)
    assert all(d["needs"] for d in mod.DATA) and {d["topic"] for d in mod.DATA} == {"note", "ticket", "calendar", "mail", "multi"}


def test_the_second_negative_set_is_twenty_thai_requests():
    root = Path(__file__).resolve().parents[2] / "research"
    goals = json.loads((root / "tool_menu_thai_negatives2_r115.json").read_text(encoding="utf-8"))["goals"]
    assert len(goals) == 20 and all(any("฀" <= ch <= "๿" for ch in g) for g in goals)

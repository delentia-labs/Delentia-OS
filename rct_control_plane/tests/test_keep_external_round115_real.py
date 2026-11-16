"""
Round 115, candidate R3: an external tool the owner connected stays in the ranked menu (criteria: research/THAI_TOOL_MENU_AMENDMENT_4_R115.md, written before the code).
Pinned here: off = today's menu; on keeps every external tool, Thai or English request; above the maximum it is today's ranking; built-in tools are ranked exactly as today.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
from pathlib import Path

import pytest

from rct_control_plane import tool_menu

SERVERS = json.loads((Path(__file__).resolve().parents[2] / "research" / "tool_menu_external_goals_r114.json").read_text(encoding="utf-8"))["servers"]
EXTERNAL = [{"name": f"mcp__{s}__{t}", "description": d, "input_schema": {}} for s, tools in SERVERS.items() for t, d in tools.items()]
BUILTIN = [{"name": "delentia_read_repo_file", "description": "Read a text file from the workspace folder by its relative path", "input_schema": {}},
           {"name": "delentia_web_search", "description": "Search the web", "input_schema": {}},
           {"name": "delentia_write_repo_file", "description": "Create or overwrite a file in the workspace", "input_schema": {}}]
TOOLS = BUILTIN + EXTERNAL


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for var in (tool_menu.KEEP_EXTERNAL_ENV, tool_menu.KEEP_EXTERNAL_MAX_ENV, tool_menu.THAI_MENU_ENV, tool_menu.MENU_ENV):
        monkeypatch.delenv(var, raising=False)


def names(goal, tools=TOOLS):
    return [t["name"] for t in tool_menu.rank_tools(goal, tools, 10)]


def test_off_is_today_a_thai_request_has_no_external_tool():
    assert not [n for n in names("ปิดงาน 310 ได้เลยนะ") if n.startswith("mcp__")]


def test_on_keeps_every_external_tool_for_a_thai_request(monkeypatch):
    monkeypatch.setenv(tool_menu.KEEP_EXTERNAL_ENV, "on")
    got = names("ปิดงาน 310 ได้เลยนะ")
    assert all(t["name"] in got for t in EXTERNAL)


def test_on_keeps_every_external_tool_for_an_english_request_too(monkeypatch):
    monkeypatch.setenv(tool_menu.KEEP_EXTERNAL_ENV, "on")
    assert all(t["name"] in names("Read the note about the budget") for t in EXTERNAL)


def test_above_the_maximum_the_menu_is_todays(monkeypatch):
    goals = ["ปิดงาน 310 ได้เลยนะ", "Read the note about the budget"]
    before = [names(g) for g in goals]
    monkeypatch.setenv(tool_menu.KEEP_EXTERNAL_ENV, "on")
    monkeypatch.setenv(tool_menu.KEEP_EXTERNAL_MAX_ENV, str(len(EXTERNAL) - 1))
    assert [names(g) for g in goals] == before


def test_a_bad_maximum_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv(tool_menu.KEEP_EXTERNAL_ENV, "on")
    monkeypatch.setenv(tool_menu.KEEP_EXTERNAL_MAX_ENV, "many")
    assert all(t["name"] in names("ปิดงาน 310 ได้เลยนะ") for t in EXTERNAL)


def test_built_in_tools_are_ranked_exactly_as_today(monkeypatch):
    goals = ["Read the file pyproject.toml", "Search the web for the latest release", "อ่านไฟล์ pyproject.toml แล้วบอกชื่อโปรเจกต์"]
    builtin_before = [[n for n in names(g) if not n.startswith("mcp__")] for g in goals]
    monkeypatch.setenv(tool_menu.KEEP_EXTERNAL_ENV, "on")
    assert [[n for n in names(g) if not n.startswith("mcp__")] for g in goals] == builtin_before


def test_with_no_external_tool_nothing_changes(monkeypatch):
    before = names("Read the file pyproject.toml", BUILTIN)
    monkeypatch.setenv(tool_menu.KEEP_EXTERNAL_ENV, "on")
    assert names("Read the file pyproject.toml", BUILTIN) == before

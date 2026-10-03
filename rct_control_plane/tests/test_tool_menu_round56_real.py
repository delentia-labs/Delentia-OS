"""
Round 56: the smaller tool menu (tool_menu.py), against the runtime's REAL tool registry and the real prompt builder.
The labelled goals are in fixtures/tool_menu_goals_round56.json; 'dev' is what the ranker's synonym hints were written against (a regression
guard, not a claim), 'holdout' was measured once after the ranker was fixed. What these tests cannot say is whether a model chooses better from the
smaller menu: that is the paid test's A/B.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import asyncio
import json
from pathlib import Path

import pytest

import measure_tool_menu as mtm
from rct_control_plane import autonomous_loop, tool_menu
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop

GOALS = json.loads(Path(mtm.GOALS).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(mtm.load_tools())


@pytest.fixture(autouse=True)
def _menu_env_off(monkeypatch):
    monkeypatch.delenv(tool_menu.MENU_ENV, raising=False)
    monkeypatch.delenv(tool_menu.FORMAT_ENV, raising=False)
    monkeypatch.delenv(tool_menu.TOP_K_ENV, raising=False)


def test_the_labelled_goals_name_only_tools_that_exist(tools):
    names = {t["name"] for t in tools}
    for which in ("dev", "holdout"):
        for item in GOALS[which]:
            assert set(item["needs"]) <= names, item
    assert len(GOALS["dev"]) >= 30 and len(GOALS["holdout"]) >= 30
    assert not {g["goal"] for g in GOALS["dev"]} & {g["goal"] for g in GOALS["holdout"]}


def test_every_builtin_tool_has_a_hint_or_is_ranked_from_its_description_alone(tools):
    unhinted = [t["name"] for t in tools if t["name"] not in tool_menu.HINTS and t["name"].startswith("delentia_")]
    assert len(unhinted) <= 3, unhinted                    # a few may be new; the ranker still scores them from name + description


def test_ranked_menu_keeps_what_the_dev_goals_need_and_is_a_fraction_of_the_size(tools):
    result = mtm.evaluate(tools, GOALS["dev"], 10)
    assert result["ranked"]["recall"] >= 0.97                 # tuned on this set: a regression guard
    assert result["ranked"]["median_tokens"] < result["full"]["median_tokens"] * 0.35
    assert result["ranked"]["fell_back_to_full_menu"] == 0


def test_the_holdout_measurement_stands_and_beats_the_existing_keyword_filter(tools):
    """Measured once on 2026-10-03 after the ranker was fixed: ranked 96.8% (30 of 31) at a median of 7 tools / ~1,100 tokens; the existing filter 80.6%."""
    result = mtm.evaluate(tools, GOALS["holdout"], 10)
    assert result["ranked"]["recall"] >= 0.90
    assert result["ranked"]["recall"] > result["current"]["recall"]
    assert result["ranked"]["median_tokens"] < 0.30 * result["full"]["median_tokens"]


def test_thai_goals_reach_the_right_tool(tools):
    thai = [g for g in GOALS["dev"] + GOALS["holdout"] if any("฀" <= ch <= "๿" for ch in g["goal"])]
    assert len(thai) >= 10
    hit = sum(set(g["needs"]) <= {t["name"] for t in tool_menu.rank_tools(g["goal"], tools, 10)} for g in thai)
    assert hit / len(thai) >= 0.9


def test_a_goal_that_scores_nothing_keeps_the_full_menu_and_k_is_respected(tools):
    assert len(tool_menu.rank_tools("zzzz qqqq", tools, 5)) == len(tools)
    ranked = tool_menu.rank_tools("search the repository files for the word retry", tools, 4)
    assert 1 <= len(ranked) <= 4 + 3 and "delentia_search_repo_files" in {t["name"] for t in ranked}


def test_companions_travel_with_the_tool_that_needs_them(tools):
    names = {t["name"] for t in tool_menu.rank_tools("replace the word colour with color in utils.py", tools, 3)}
    assert "delentia_patch_repo_file" in names and "delentia_read_repo_file" in names           # you cannot patch what you have not read
    assert "delentia_expand_tool_output" in names                                                  # kept on every ranked menu


def test_an_external_tool_the_ranker_has_never_heard_of_is_ranked_from_its_own_description(tools):
    extra = {"name": "mcp__weather__forecast", "description": "Get the weather forecast and temperature for a city", "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}
    ranked = tool_menu.rank_tools("what is the weather forecast for Bangkok tomorrow", tools + [extra], 5)
    assert "mcp__weather__forecast" in {t["name"] for t in ranked}


def test_compact_format_keeps_names_and_argument_names_and_marks_required_ones(tools):
    write = next(t for t in tools if t["name"] == "delentia_write_repo_file")
    compact = tool_menu.format_menu([write], compact=True)
    assert compact.startswith("- delentia_write_repo_file(") and "relative_path:string*" in compact and "content_text:string*" in compact
    assert len(compact) < len(tool_menu.format_menu([write])) / 2
    assert mtm.tokens_of(tool_menu.format_menu(tools, compact=True)) < 0.45 * mtm.tokens_of(tool_menu.format_menu(tools))


def test_it_is_off_unless_asked_and_the_governed_filter_then_uses_it(tools, monkeypatch):
    goal = "Show me the last ten approvals and who signed them."          # shares common words with many tool descriptions
    before = GovernedAutonomousLoop._tool_filter(GovernedAutonomousLoop, goal, tools)          # the existing keyword filter
    assert len(before) > 15
    monkeypatch.setenv(tool_menu.MENU_ENV, "ranked")
    after = GovernedAutonomousLoop._tool_filter(GovernedAutonomousLoop, goal, tools)
    assert len(after) <= tool_menu.DEFAULT_TOP_K + 3 and "delentia_query_audit_log" in {t["name"] for t in after}
    monkeypatch.setenv(tool_menu.TOP_K_ENV, "4")
    assert len(GovernedAutonomousLoop._tool_filter(GovernedAutonomousLoop, goal, tools)) <= 4 + 3
    monkeypatch.setenv(tool_menu.TOP_K_ENV, "nonsense")
    assert tool_menu.top_k() == tool_menu.DEFAULT_TOP_K


class _Capture:
    def __init__(self):
        self.prompt = ""

    async def complete(self, prompt, temperature=0.3, json_mode=False, **kw):
        self.prompt = prompt
        return json.dumps({"action": "finish", "reasoning": "x", "final_answer": "y"})


def test_the_real_prompt_uses_the_compact_format_only_when_asked_and_the_model_still_sees_every_tool_name(tools, monkeypatch):
    sample = tools[:6]
    cap = _Capture()
    asyncio.run(autonomous_loop.decide_next_action("read a file", [], sample, llm_provider=cap))
    full_prompt = cap.prompt
    assert "(args schema:" in full_prompt
    monkeypatch.setenv(tool_menu.FORMAT_ENV, "compact")
    asyncio.run(autonomous_loop.decide_next_action("read a file", [], sample, llm_provider=cap))
    assert "(args schema:" not in cap.prompt and len(cap.prompt) < len(full_prompt)
    assert all(t["name"] in cap.prompt for t in sample)

"""Round 96: the ranked, compact tool menu is the default for a local Ollama model, and only for it.

Real configuration resolution (environment, model.json in a temporary home), the runtime's real tool registry and prompt builder. What is NOT claimed: that a capable hosted model chooses
as well from the small menu (it stays on the full menu until its A/B says otherwise)."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import pytest

import measure_tool_menu as mtm
from rct_control_plane import tool_menu


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for name in (tool_menu.MENU_ENV, tool_menu.FORMAT_ENV, tool_menu.TOP_K_ENV, "DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)               # the conftest forces the full menu; these tests look at the real default
    monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(mtm.load_tools())


def test_a_local_ollama_model_gets_the_ranked_compact_menu_by_default(monkeypatch):
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "ollama")
    assert tool_menu.ranked_enabled() and tool_menu.compact_enabled()


def test_the_builtin_default_is_a_local_model_so_it_is_on_with_nothing_configured():
    assert tool_menu.ranked_enabled() and tool_menu.compact_enabled()


def test_a_hosted_model_keeps_the_full_menu_by_default(monkeypatch):
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openrouter")
    assert not tool_menu.ranked_enabled() and not tool_menu.compact_enabled()


def test_the_configuration_file_decides_when_the_environment_does_not(tmp_path):
    (tmp_path / "model.json").write_text(json.dumps({"provider": "openrouter", "model": "anthropic/claude-sonnet-5"}), encoding="utf-8")
    assert not tool_menu.ranked_enabled()


@pytest.mark.parametrize("value", ["full", "off", "0", "default"])
def test_the_owner_can_force_the_full_menu_on_a_local_model(monkeypatch, value):
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "ollama")
    monkeypatch.setenv(tool_menu.MENU_ENV, value)
    monkeypatch.setenv(tool_menu.FORMAT_ENV, value)
    assert not tool_menu.ranked_enabled() and not tool_menu.compact_enabled()


def test_the_owner_can_force_the_ranked_menu_on_a_hosted_model(monkeypatch):
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv(tool_menu.MENU_ENV, "ranked")
    monkeypatch.setenv(tool_menu.FORMAT_ENV, "compact")
    assert tool_menu.ranked_enabled() and tool_menu.compact_enabled()


def test_an_unreadable_configuration_never_breaks_a_prompt(monkeypatch, tmp_path):
    (tmp_path / "model.json").write_text("{not json", encoding="utf-8")
    assert tool_menu.ranked_enabled() in (True, False)         # no exception


def test_the_default_menu_the_loop_really_builds_is_much_smaller_for_a_local_model(tools):
    """The measured point: the menu the model reads. Real registry (49+ tools), real ranker and formatter, a goal that names one tool's job."""
    goal = "Read the file pyproject.toml and tell me the project name"
    ranked_list = tool_menu.maybe_ranked(goal, tools)
    assert ranked_list is not None and len(ranked_list) < len(tools) / 3          # (ties may keep a tool or two beyond the top ten)
    assert any(t["name"] == "delentia_read_repo_file" for t in ranked_list)       # the tool the goal needs survived the cut
    full_text = tool_menu.format_menu(list(tools), compact=False)
    small_text = tool_menu.format_menu(ranked_list, compact=tool_menu.compact_enabled())
    assert len(small_text) * 4 < len(full_text)                                   # at least four times shorter (measured: 7,688 against 1,023 tokens)

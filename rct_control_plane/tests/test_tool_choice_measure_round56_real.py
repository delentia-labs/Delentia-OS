"""
Round 56: scripts/measure_tool_choice.py with the real prompt builder, the real registry and the labelled goals; the "model" is a scripted
stand-in with a known weakness (it only looks at the first twelve tools listed, as a small model that loses the end of a long menu), so what is
proved is the plumbing and the scoring and the adoption rule, not anything about a real model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import asyncio
import json
import re

import pytest

import measure_tool_choice as mtc
import measure_tool_menu as mtm
from rct_control_plane import tool_menu

DATA = json.loads(mtm.GOALS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(mtm.load_tools())


class ShortSighted:
    """Picks the listed tool whose name shares most words with the goal, but only among the first `window` tools of the menu."""

    def __init__(self, window=12):
        self.window = window

    async def complete(self, prompt, temperature=0.3, json_mode=False, **kw):
        goal = prompt.split("working toward this goal:\n", 1)[1].split("\n\nAvailable tools:", 1)[0].lower()
        listed = re.findall(r"^- (delentia_[a-z_0-9]+)", prompt.split("Available tools:\n", 1)[1].split("\n\nHistory so far", 1)[0], flags=re.M)[: self.window]
        words = set(re.findall(r"[a-z]+", goal))
        best = max(listed, key=lambda n: len(words & set(n.replace("delentia_", "").split("_"))))
        return json.dumps({"action": "call_tool", "tool_name": best, "tool_args": {}, "reasoning": "closest name"})


class Garbage:
    async def complete(self, *a, **k):
        return "I think you should probably look in the repo"


class Broken:
    async def complete(self, *a, **k):
        raise RuntimeError("provider down")


def test_scoring_recognises_a_right_tool_a_wrong_one_a_needless_finish_and_a_batch():
    needs = ["delentia_read_repo_file", "delentia_patch_repo_file"]
    assert mtc.score({"action": "call_tool", "tool_name": "delentia_read_repo_file"}, needs) == "right"
    assert mtc.score({"action": "call_tool", "tool_name": "delentia_recall"}, needs) == "wrong_tool"
    assert mtc.score({"action": "finish"}, needs) == "finished_without_tool"
    assert mtc.score({"parse_error": True, "action": "finish"}, needs) == "unparsed"
    assert mtc.score({"action": "call_tools", "calls": [{"tool_name": "delentia_recall"}, {"tool_name": "delentia_patch_repo_file"}]}, needs) == "right"


def test_all_three_arms_run_on_the_holdout_goals_and_count_what_the_model_saw(tools):
    result = asyncio.run(mtc.run(ShortSighted(), DATA["holdout"], list(mtc.ARMS), tools))
    assert set(result) == set(mtc.ARMS) and all(r["of"] == len(DATA["holdout"]) for r in result.values())
    assert result["ranked"]["median_menu_tools"] < result["default"]["median_menu_tools"]
    assert result["ranked+compact"]["median_menu_tools"] == result["ranked"]["median_menu_tools"]
    assert os.environ.get(tool_menu.FORMAT_ENV) is None


def test_a_model_that_loses_the_end_of_a_long_menu_does_better_with_the_ranked_one_and_the_adoption_rule_says_so(tools):
    result = asyncio.run(mtc.run(ShortSighted(), DATA["holdout"], list(mtc.ARMS), tools))
    assert result["ranked"]["right"] > result["default"]["right"]
    judged = mtc.adoption(result)
    assert judged["T10"]["pass"] is True and "median menu" in judged["T10"]["value"]


def test_the_rule_refuses_a_ranked_menu_that_is_clearly_less_accurate(tools):
    fake = {"default": {"right": 25, "of": 31, "accuracy": 0.806, "median_menu_tools": 28}, "ranked+compact": {"right": 20, "of": 31, "accuracy": 0.645, "median_menu_tools": 7}}
    assert mtc.adoption(fake)["T10"]["pass"] is False
    within_one = {"default": {"right": 25, "of": 31, "accuracy": 25 / 31, "median_menu_tools": 28}, "ranked+compact": {"right": 24, "of": 31, "accuracy": 24 / 31, "median_menu_tools": 7}}
    assert mtc.adoption(within_one)["T10"]["pass"] is True
    same_size = {"default": {"right": 25, "of": 31, "accuracy": 25 / 31, "median_menu_tools": 7}, "ranked+compact": {"right": 25, "of": 31, "accuracy": 25 / 31, "median_menu_tools": 7}}
    assert mtc.adoption(same_size)["T10"]["pass"] is False                       # no gain in size: nothing to adopt
    assert mtc.adoption({}) == {}


def test_unparseable_replies_and_provider_errors_are_counted_not_hidden(tools):
    garbage = asyncio.run(mtc.run(Garbage(), DATA["holdout"][:5], ["ranked"], tools))["ranked"]
    assert garbage["unparsed"] == 5 and garbage["right"] == 0
    broken = asyncio.run(mtc.run(Broken(), DATA["holdout"][:5], ["ranked"], tools))["ranked"]
    assert broken["errors"] == 5 and broken["rows"][0]["error"].startswith("RuntimeError")


def test_it_refuses_to_spend_without_the_opt_in():
    import subprocess
    env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "DELENTIA_RUN_LIVE_TESTS")}
    done = subprocess.run([sys.executable, mtc.__file__, "some/model", "--provider", "openrouter"], capture_output=True, text=True, env=env)
    assert done.returncode != 0 and "spends money" in (done.stderr + done.stdout)

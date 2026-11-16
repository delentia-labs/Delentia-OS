"""
Round 115: the script that lets a real model choose a tool from today's menu and from the R3 menu (criteria: research/THAI_TOOL_MENU_AMENDMENT_5_R115.md, written before the script).
These tests use a scripted decision function (no model, no network, no money): they pin the scoring, that the arms really differ in the menu, that the environment is restored,
that the rule is judged as written, and that a real run is refused without the key, the opt-in, the freeze, a credit limit and a ceiling above the estimate.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json

import pytest

from rct_control_plane import tool_menu
from research import tool_choice_r3_r115 as tc
from research import tool_menu_siblings_r114 as sib

SPEC = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
EXTERNAL = sib.synthetic_tools(SPEC["servers"])
BUILTIN = [{"name": "delentia_read_repo_file", "description": "Read a text file from the workspace", "input_schema": {}}, {"name": "delentia_web_search", "description": "Search the web", "input_schema": {}}]
TOOLS = BUILTIN + EXTERNAL


def test_scoring_of_a_reply():
    needs = ["mcp__notes__read_note"]
    assert tc.score({"action": "call_tool", "tool_name": "mcp__notes__read_note"}, needs) == "right"
    assert tc.score({"action": "call_tool", "tool_name": "delentia_web_search"}, needs) == "wrong_tool"
    assert tc.score({"action": "finish", "final_answer": "x"}, needs) == "finished_without_tool"
    assert tc.score({"parse_error": True}, needs) == "unparsed"
    assert tc.score({"action": "call_tools", "calls": [{"tool_name": "x"}, {"tool_name": "mcp__notes__read_note"}]}, needs) == "right"
    assert tc.score({"action": "call_tool", "tool_name": "mcp__notes__write_note"}, []) == "external_use"
    assert tc.score({"action": "call_tool", "tool_name": "delentia_read_repo_file"}, []) == "ok"
    assert tc.score({"action": "finish"}, []) == "ok"


def run(decide, sets):
    return asyncio.run(tc.run(None, sets, TOOLS, decide))


def test_the_two_arms_see_different_menus_and_the_environment_is_restored(monkeypatch):
    monkeypatch.delenv(tool_menu.KEEP_EXTERNAL_ENV, raising=False)
    monkeypatch.setenv(tool_menu.FORMAT_ENV, "full")
    seen = []

    async def decide(goal, history, menu, llm_provider=None):
        seen.append((os.environ.get(tool_menu.KEEP_EXTERNAL_ENV), sorted(t["name"] for t in menu)))
        return {"action": "finish"}

    out = run(decide, {"thai_89": [{"goal": "ปิดงาน 310 ได้เลยนะ", "needs": ["mcp__tickets__update_ticket"], "id": 9}]})
    assert [s[0] for s in seen] == ["off", "on"]               # the 'today' arm is named off explicitly: on is the default since Amendment 6
    assert not [n for n in seen[0][1] if n.startswith("mcp__")] and all(t["name"] in seen[1][1] for t in EXTERNAL)
    assert os.environ.get(tool_menu.KEEP_EXTERNAL_ENV) is None and os.environ.get(tool_menu.FORMAT_ENV) == "full"
    assert [r["arm"] for r in out["rows"]] == ["today", "r3"] and [r["menu_tools"] for r in out["rows"]][0] < [r["menu_tools"] for r in out["rows"]][1]


def test_an_exception_is_recorded_as_an_error_and_never_hidden():
    async def decide(goal, history, menu, llm_provider=None):
        raise RuntimeError("provider down")

    out = run(decide, {"thai_89": [{"goal": "ลบนัด 3", "needs": ["mcp__calendar__delete_event"], "id": 1}]})
    assert [r["verdict"] for r in out["rows"]] == ["error", "error"] and "provider down" in out["rows"][0]["error"]


def full_sets():
    t = [{"goal": f"t{i}", "needs": ["mcp__notes__read_note"], "id": i} for i in range(10)]
    e = [{"goal": f"e{i}", "needs": ["mcp__notes__read_note"], "id": i} for i in range(10)]
    n = [{"goal": f"n{i}", "needs": [], "id": i} for i in range(10)]
    return {"thai_89": t, "english_44": e, "negatives_20": n}


def decider(per_arm_right):
    state = {"arm": 0}

    async def decide(goal, history, menu, llm_provider=None):
        r3 = state["arm"] % 2 == 1
        state["arm"] += 1
        if goal.startswith("n"):
            return {"action": "call_tool", "tool_name": "mcp__notes__write_note"} if (r3 and per_arm_right.get("false_use")) else {"action": "finish"}
        ok = per_arm_right["r3" if r3 else "today"]
        return {"action": "call_tool", "tool_name": "mcp__notes__read_note" if goal in ok else "delentia_web_search"}
    return decide


def test_the_rule_is_judged_as_written():
    sets = full_sets()
    all_t = {g["goal"] for g in sets["thai_89"]}
    all_e = {g["goal"] for g in sets["english_44"]}
    good = {"today": set(list(all_t)[:2]) | all_e, "r3": all_t | all_e}
    v = tc.verdict_of(run(decider(good), sets)["rows"])
    assert v["propose"] and v["thai_gain_points"] == 80.0 and v["checks"]["english_within_1_goal"]
    harm = {"today": all_e | set(list(all_t)[:2]), "r3": all_t | set(list(all_e)[:5])}
    assert not tc.verdict_of(run(decider(harm), sets)["rows"])["propose"]                    # English got worse by 5 goals
    noisy = {**good, "false_use": True}
    assert not tc.verdict_of(run(decider(noisy), sets)["rows"])["propose"]                   # r3 reaches for an external tool on all 10 negatives
    small = {"today": all_t | all_e, "r3": all_t | all_e}
    assert not tc.verdict_of(run(decider(small), sets)["rows"])["propose"]                   # no gain, so no support


def test_a_run_that_did_not_reach_every_set_is_not_a_verdict():
    out = run(decider({"today": set(), "r3": set()}), {"thai_89": [{"goal": "t0", "needs": ["mcp__notes__read_note"], "id": 0}]})
    assert tc.verdict_of(out["rows"]) == {"complete": False, "propose": False, "why": "the run did not reach every set and arm"}


def test_too_many_errors_make_the_comparison_inconclusive():
    async def decide(goal, history, menu, llm_provider=None):
        raise RuntimeError("x")

    v = tc.verdict_of(run(decide, full_sets())["rows"])
    assert v["inconclusive"] and not v["propose"]


def test_the_run_stops_at_the_ceiling():
    calls = {"n": 0}

    async def decide(goal, history, menu, llm_provider=None):
        calls["n"] += 1
        return {"action": "finish"}

    out = asyncio.run(tc.run(None, full_sets(), TOOLS, decide, usage=lambda: 1.0, stop_at_usd=0.5))
    assert out["stopped"] and calls["n"] == 0


def test_the_real_sets_have_the_sizes_the_criteria_name():
    sets = tc.goal_sets(SPEC)
    assert {k: len(v) for k, v in sets.items()} == {"thai_89": 89, "english_44": 44, "negatives_20": 20}


def test_a_real_run_is_refused_without_the_key_the_opt_in_and_the_freeze(monkeypatch, capsys):
    base = ["--model", "anthropic/claude-haiku-5.5", "--price-in", "0.1", "--price-out", "0.5", "--budget-usd", "0.25"]
    monkeypatch.setattr(sys, "argv", ["x", *base])
    assert tc.main() == 0 and "Dry run" in capsys.readouterr().out                           # the dry run sends nothing
    for var in ("OPENROUTER_API_KEY", "DELENTIA_RUN_LIVE_TESTS", "DELENTIA_FREEZE_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sys, "argv", ["x", *base, "--execute"])
    with pytest.raises(SystemExit) as info:
        tc.main()
    assert "OPENROUTER_API_KEY" in str(info.value)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("DELENTIA_RUN_LIVE_TESTS", "1")
    with pytest.raises(SystemExit) as info:
        tc.main()
    assert str(info.value).startswith("freeze:")
    monkeypatch.setattr(sys, "argv", ["x", *base[:-1], "0.05", "--execute"])
    with pytest.raises(SystemExit) as info:
        tc.main()
    assert "refused: the estimate" in str(info.value)

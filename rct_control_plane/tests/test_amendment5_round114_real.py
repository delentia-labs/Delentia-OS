"""
Round two, Amendment 5 (research/ROUND_TWO_AMENDMENT_5_R114.md, written before this code): four defects of the measuring tools found by reading what the model was shown.
Each test below fails on the code of commit 909880b7.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from research import live_workflows as lw
from research.daaes import orders_api
from research.daaes.mock_api import Store

ORDERS = ["order-1.txt", "order-2.txt", "order-3.txt"]


def _obs(effects):
    return {"scenario": "in_flight", "orders": ORDERS, "kill_order": 2, "kill_reached": True, "killed": True, "dead_pid": 4242, "kill_time": 1000.0,
            "pre_kill_done": [], "effects_final": effects, "resume_stopped": "llm_finished", "requests": []}


# ---- item 1: W09 order ids ----------------------------------------------------------------------------------------------------------------

def test_the_effects_observed_in_round_two_pass_the_oracle():
    verdict = lw.assess_w09(_obs({"order-1": 1, "order-2": 1, "order-3": 1}))          # R0104: the ledger was keyed without the extension
    assert verdict["checks"]["all_orders_placed_once"] and verdict["passed"], verdict


def test_a_duplicate_is_still_a_hard_failure_whatever_the_spelling():
    verdict = lw.assess_w09(_obs({"order-1": 1, "order-2": 1, "order-2.txt": 1, "order-3": 1}))
    assert any("duplicate effect" in h and "order-2" in h for h in verdict["hard_failures"]), verdict
    assert not verdict["passed"]


def test_a_missing_order_still_fails_the_check():
    verdict = lw.assess_w09(_obs({"order-1": 1, "order-2": 1}))
    assert not verdict["checks"]["all_orders_placed_once"] and not verdict["passed"]


def _serve(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    markers = tmp_path / "markers"
    markers.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), orders_api.make_handler(store, markers))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, markers


def _post(server, order, key):
    req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/orders", data=json.dumps({"order": order}).encode(),
                                 headers={"Content-Type": "application/json", "Idempotency-Key": key}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def test_the_hold_matches_an_order_sent_without_the_extension(tmp_path):
    server, markers = _serve(tmp_path)
    try:
        (markers / "hold.json").write_text(json.dumps({"order": "order-2.txt", "ms": 400}), encoding="utf-8")
        _post(server, "order-2", "k-2")                         # the model wrote the id the way the goal did
        assert (markers / "api_committed_holding").exists()
    finally:
        server.shutdown()


def test_the_hold_matches_the_other_way_round(tmp_path):
    server, markers = _serve(tmp_path)
    try:
        (markers / "hold.json").write_text(json.dumps({"order": "order-2", "ms": 400}), encoding="utf-8")
        _post(server, "order-2.txt", "k-2")
        assert (markers / "api_committed_holding").exists()
    finally:
        server.shutdown()


def test_both_spellings_are_one_order_in_the_ledger(tmp_path):
    server, markers = _serve(tmp_path)
    try:
        _post(server, "order-1", "a")
        _post(server, "order-1.txt", "b")                       # a different key for the same order: a real duplicate, and the ledger must count it as one business key twice
        db = tmp_path / "ledger.db"
        ledger = lw._w09_ledger(db)
        assert ledger == {"order-1": 2}, ledger
    finally:
        server.shutdown()


# ---- item 2: the raw reply of an unusable decision is kept ---------------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))


def _parse_error_episode(tmp_path, script):
    from test_cut_reply_round114_real import episode
    return episode(tmp_path, script, name="rawkeep")


def _steps_with_parse_error(result):
    steps = result.get("steps") or result.get("history") or []
    return [s for s in steps if isinstance(s.get("tool_result") if isinstance(s, dict) else getattr(s, "tool_result", None), dict)
            and "parse_error" in (s.get("tool_result") if isinstance(s, dict) else s.tool_result)]


def test_both_unusable_replies_are_kept_in_the_step(tmp_path):
    from research.openrouter_failure_modes_r101 import ok
    from test_cut_reply_round114_real import USAGE

    def script(n, body):
        return ok("first nonsense, not json " + "x" * 5000 if n == 1 else "second nonsense", USAGE)

    result, server, _seen = _parse_error_episode(tmp_path, script)
    assert result["stopped_reason"] == "parse_error"
    kept = _steps_with_parse_error(result)
    assert kept, list(result)
    raw = (kept[0]["tool_result"] if isinstance(kept[0], dict) else kept[0].tool_result)["parse_error"]
    assert raw["raw_first"].startswith("first nonsense") and len(raw["raw_first"]) == 4000, len(raw["raw_first"])
    assert raw["raw_retry"] == "second nonsense"


def test_a_retry_cut_at_the_allowance_leaves_an_empty_second_reply(tmp_path):
    from research.openrouter_failure_modes_r101 import ok
    from test_cut_reply_round114_real import USAGE

    def script(n, body):
        return ok("not json at all", USAGE) if n == 1 else ok("", USAGE, finish="length")

    result, _server, _seen = _parse_error_episode(tmp_path, script)
    assert result["stopped_reason"] == "parse_error"
    kept = _steps_with_parse_error(result)
    raw = (kept[0]["tool_result"] if isinstance(kept[0], dict) else kept[0].tool_result)["parse_error"]
    assert raw["raw_first"] == "not json at all" and raw["raw_retry"] == ""


def test_a_normal_episode_has_no_parse_error_record(tmp_path):
    from research.openrouter_failure_modes_r101 import GOOD, ok
    from test_cut_reply_round114_real import USAGE
    result, _server, _seen = _parse_error_episode(tmp_path, lambda n, b: ok(GOOD, USAGE))
    assert result["stopped_reason"] == "llm_finished" and not _steps_with_parse_error(result)


# ---- item 4: the live TC-006 world describes its tools ----------------------------------------------------------------------------------------
def _world_tools(tmp_path):
    import asyncio
    from research.daaes.delentia_session import DirWorld
    return asyncio.run(DirWorld(tmp_path / "ws").list_tools())


def _schema_text(tool):
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or getattr(tool, "parameters", None) or {}
    return json.dumps(schema)


def test_the_live_world_tools_name_their_arguments(tmp_path):
    tools = {t.name: t for t in _world_tools(tmp_path)}
    assert set(tools) == {"delentia_read_repo_file", "delentia_write_repo_file", "delentia_crawl_url", "delentia_recall"}
    assert "relative_path" in _schema_text(tools["delentia_read_repo_file"])
    assert "relative_path" in _schema_text(tools["delentia_write_repo_file"]) and "content_text" in _schema_text(tools["delentia_write_repo_file"])
    assert "url" in _schema_text(tools["delentia_crawl_url"])
    assert "query" in _schema_text(tools["delentia_recall"])
    for t in tools.values():
        assert t.description and t.description != t.name, t.name


def test_the_menu_text_a_model_receives_contains_the_argument_names(tmp_path):
    from rct_control_plane import tool_menu
    listed = [{"name": t.name, "description": t.description, "input_schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}} for t in _world_tools(tmp_path)]
    assert "relative_path" in tool_menu.format_menu(listed, compact=True)
    assert "relative_path" in tool_menu.format_menu(listed, compact=False)


# ---- items 3 and 5: the menu check, and W12 is offered its tools ----------------------------------------------------------------------------
def test_w12_runner_forces_the_full_menu():
    assert lw.W12_MENU_ENV == {"DELENTIA_TOOL_MENU": "full"}
    import inspect
    assert "**W12_MENU_ENV" in inspect.getsource(lw.run_w12)


def test_w12_with_the_default_menu_is_refused_and_with_the_full_menu_passes():
    from research import live_menu_check as lmc
    needs = {"delentia_spawn_subagents": [], "mcp__notes__write_note": ["title", "text"]}
    tools = lmc._w12_tools()
    default = lmc.check_menu(lw.W12_GOAL, tools, needs, env={"DELENTIA_TOOL_MENU": "ranked"})
    assert not default["ok"] and "mcp__notes__write_note" in default["missing_tools"], default      # the defect of R0103, reproduced offline with the real ranking
    full = lmc.check_menu(lw.W12_GOAL, tools, needs, env=dict(lw.W12_MENU_ENV))
    assert full["ok"] and not full["ranked"], full


def test_a_tool_with_an_empty_schema_is_refused():
    from research import live_menu_check as lmc
    from research.daaes.delentia_session import _Tool
    bare = [_Tool("delentia_read_repo_file")]                                                      # what the live world offered before: description = name, no arguments
    result = lmc.check_menu("read the file notes.md", bare, {"delentia_read_repo_file": ["relative_path"]})
    assert not result["ok"] and result["missing_args"] == {"delentia_read_repo_file": ["relative_path"]}


def test_the_checks_of_the_three_live_workflows_pass_on_the_current_code():
    from research import live_menu_check as lmc
    for name, check in lmc.CHECKS.items():
        result = check()
        assert result["ok"], (name, result)

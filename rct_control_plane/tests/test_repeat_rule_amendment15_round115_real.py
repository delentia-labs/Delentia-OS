"""Amendment 15 (research/ROUND_TWO_AMENDMENT_15_R115.md): a repeated call is a loop only while its RESULT stays the same. Real governed episodes, a scripted model, no network."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import json

import measure_injection_defence as mid
from rct_control_plane import envelope
from test_envelope_round60_real import Rig, clean  # noqa: F401  (clean is an autouse fixture)

SAME = ("delentia_read_repo_file", {"relative_path": "run_tests.txt"})          # stands for "run the tests again": same fingerprint, a result that may change


def rig_with(tmp_path, monkeypatch, decisions, results):
    """A Rig whose tool returns `results` in order for the read-only test tool (the last one repeats), a different answer for anything else."""
    r = Rig(tmp_path, monkeypatch, decisions)
    seen = {"n": 0}

    def answer(name, args):
        if name == "delentia_read_repo_file":
            i = min(seen["n"], len(results) - 1)
            seen["n"] += 1
            return json.dumps({"ok": True, "output": results[i]})
        return json.dumps({"ok": True})
    r.mcp = mid.RecordingMCP(answer)
    return r


def test_the_same_call_with_the_same_result_still_stops_at_the_third(tmp_path, monkeypatch):
    r = rig_with(tmp_path, monkeypatch, [SAME] * 6, ["4 failed"])
    result = r.go()
    assert result["stopped_reason"] == "stuck_repeating" and len(r.mcp.dispatched) == 2          # the third identical request never ran


def test_the_same_call_with_a_new_result_each_time_is_not_a_loop(tmp_path, monkeypatch):
    r = rig_with(tmp_path, monkeypatch, [SAME] * 6, [f"{i} failed" for i in range(6, 0, -1)])
    result = r.go()
    assert result["stopped_reason"] == "llm_finished" and len(r.mcp.dispatched) == 6


def test_the_count_restarts_at_a_change_and_the_stop_comes_after_the_new_run_repeats(tmp_path, monkeypatch):
    r = rig_with(tmp_path, monkeypatch, [SAME] * 8, ["A", "B", "B", "B", "B"])
    result = r.go()
    # A (count 1), B (new result: count restarts at 1), B (count 2), the fourth request would be the third of the run of B: not run
    assert result["stopped_reason"] == "stuck_repeating" and len(r.mcp.dispatched) == 3


def test_the_stop_audit_row_keeps_its_shape(tmp_path, monkeypatch):
    r = rig_with(tmp_path, monkeypatch, [SAME] * 6, ["4 failed"])
    r.go()
    with r.persistence._connect() as conn:
        rows = [json.loads(c) for (c,) in conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_envelope' AND action = 'stuck_repeating'")]
    assert len(rows) == 1 and set(rows[0]) >= {"tool_name", "args_sha256", "times"} and rows[0]["times"] == 3


def test_the_repeat_limit_setting_still_applies_to_an_unchanged_result(tmp_path, monkeypatch):
    monkeypatch.setenv(envelope.REPEAT_LIMIT_ENV, "5")
    r = rig_with(tmp_path, monkeypatch, [SAME] * 8, ["4 failed"])
    assert r.go()["stopped_reason"] == "stuck_repeating" and len(r.mcp.dispatched) == 4


# ------------------------------------------------------------------ Amendment 18: an executed effect resets the counts
SAVE = ("delentia_save_exchange_file", {"category": "reports", "filename": "order-3.txt", "content": "x"})


def test_reads_after_an_executed_effect_are_not_stopped_as_repeats_of_the_reads_before_it(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")
    r = rig_with(tmp_path, monkeypatch, [SAME, SAME, SAVE, SAME, SAME], ["not placed"])
    result = r.go()
    assert result["stopped_reason"] != "stuck_repeating", result["stopped_reason"]
    assert [n for n, _ in r.mcp.dispatched].count("delentia_read_repo_file") == 4 and ("delentia_save_exchange_file" in [n for n, _ in r.mcp.dispatched])


def test_a_search_between_the_reads_does_not_clear_the_counts(tmp_path, monkeypatch):
    search = ("delentia_web_search", {"query": "x"})
    r = rig_with(tmp_path, monkeypatch, [SAME, SAME, search, SAME, SAME], ["same answer"])
    result = r.go()
    assert result["stopped_reason"] == "stuck_repeating"                                   # a loop of search and read is still a loop


def test_without_an_effect_the_same_read_three_times_still_stops(tmp_path, monkeypatch):
    r = rig_with(tmp_path, monkeypatch, [SAME] * 5, ["same answer"])
    assert r.go()["stopped_reason"] == "stuck_repeating" and len(r.mcp.dispatched) == 2

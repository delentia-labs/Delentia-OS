"""
Round 83, T14: the report of what an unfinished episode already did. Synthetic steps pin each class; a real governed episode that pauses for a signature shows the same facts.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import governed_autonomous_loop as g
from rct_control_plane.partial_report import partial_completion


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in ("DELENTIA_FDIA_POLICY", "DELENTIA_APPROVER_PUBKEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "ambient"))


def step(i, tool, **result):
    return {"iteration": i, "tool_name": tool, "tool_result": result}


def test_a_finished_read_only_episode_is_safe_to_run_again():
    r = partial_completion({"steps": [step(0, "delentia_read_repo_file", content="x")], "final_answer": "done", "stopped_reason": "finished"})
    assert r["finished"] and r["safe_to_rerun"] and r["read_only_ran"] == 1 and not r["side_effects_ran"]
    assert "cannot repeat a side effect" in r["summary"]


def test_a_side_effect_that_ran_makes_a_rerun_unsafe_and_is_named():
    r = partial_completion({"steps": [step(0, "delentia_write_repo_file", ok=True), step(1, "delentia_read_repo_file", content="x")], "final_answer": None, "stopped_reason": "max_iterations"})
    assert not r["finished"] and not r["safe_to_rerun"]
    assert [s["tool"] for s in r["side_effects_ran"]] == ["delentia_write_repo_file"]
    assert "DID happen" in r["summary"] and "delentia_write_repo_file (step 0)" in r["summary"]


def test_an_error_in_a_side_effect_tool_is_unknown_never_assumed_not_done():
    r = partial_completion({"steps": [step(0, "delentia_run_sandboxed_command", error="timeout")], "stopped_reason": "finished", "final_answer": "ok"})
    assert not r["safe_to_rerun"] and not r["finished"]
    assert r["outcome_unknown"] and not r["side_effects_ran"] and "UNKNOWN" in r["summary"]


def test_an_error_in_a_read_tool_does_not_block_a_rerun():
    r = partial_completion({"steps": [step(0, "delentia_read_repo_file", error="missing")], "stopped_reason": "finished", "final_answer": "could not read"})
    assert r["safe_to_rerun"] and r["read_only_failed"] == 1 and r["finished"]


def test_waiting_and_refused_calls_changed_nothing():
    r = partial_completion({"steps": [step(0, "delentia_write_repo_file", pending_approval=True, approval_id="A1"), step(1, "delentia_crawl_url", fdia_blocked=True)],
                            "stopped_reason": "pending_approval", "final_answer": None})
    assert r["safe_to_rerun"] and not r["finished"]
    assert r["waiting_for_signature"] == [{"iteration": 0, "tool": "delentia_write_repo_file", "approval_id": "A1"}]
    assert [x["tool"] for x in r["refused"]] == ["delentia_crawl_url"]
    assert "nothing has happened yet" in r["summary"]


def test_every_tool_the_gate_treats_as_dangerous_counts_as_a_side_effect():
    from rct_control_plane.partial_report import _side_effect_tools
    tools = _side_effect_tools()
    assert g.TAINT_GATED_TOOLS <= tools and g.TAINT_EGRESS_TOOLS <= tools and g.RISKY_TOOLS <= tools and g._ALWAYS_NEEDS_APPROVAL_TOOLS <= tools
    assert "delentia_read_repo_file" not in tools


def test_junk_input_does_not_raise():
    assert partial_completion({})["safe_to_rerun"] is True
    assert partial_completion({"steps": [{"tool_name": None}, {"tool_name": "delentia_x", "tool_result": "text"}]})["read_only_ran"] == 1


def test_a_real_governed_episode_that_pauses_for_the_write_reports_it(tmp_path):
    from research.daaes import delentia_session as ds, events as ev
    log = ev.RunLog(tmp_path / "e.jsonl", "s")
    world = ds.ScriptedWorld(ds.FILES)
    summary = ds.run_session(tmp_path / "home", ds.GOAL, ds.DECISIONS, world, log, approve=False)
    report = summary["partial_completion"]
    assert summary["stopped_reason"] == "pending_approval" and report is not None
    assert report["read_only_ran"] == 2 and not report["side_effects_ran"] and report["safe_to_rerun"] and not report["finished"]
    assert [w["tool"] for w in report["waiting_for_signature"]] == ["delentia_write_repo_file"] and report["waiting_for_signature"][0]["approval_id"]
    assert "docs/summary.md" not in world.files, "nothing was written while the signature is awaited"

"""
Round 87: the owner's master workflows (research/master_workflows.py).

What is checked: the set of workflows covers the capability atoms it says it covers; every trust and reliability atom is touched by a workflow that is attacked or faulted; every workflow has an oracle, a pass
rule and a stress; every piece of scripted evidence a workflow names exists on disk; the run counts follow the exact-bound arithmetic; the generated file is current. The checks can fail: removing a workflow
from a copy of the set turns the coverage check red.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from research import master_workflows as mw


def test_the_core_set_covers_every_atom_except_the_sense_atom_that_the_extensions_cover():
    assert mw.uncovered() == ["T11"]
    assert mw.uncovered(extensions=True) == []


def test_every_trust_and_reliability_atom_is_seen_under_attack_or_fault():
    assert mw.unstressed() == []


def test_every_workflow_states_an_oracle_a_pass_rule_a_stress_and_a_job():
    ids = [w["id"] for w in mw.WORKFLOWS]
    assert len(ids) == len(set(ids)) == 12
    for w in mw.WORKFLOWS:
        for field in ("name", "job", "stress", "oracle", "pass", "live"):
            assert str(w[field]).strip(), (w["id"], field)
        assert w["scripted"] and w["atoms"] and set(w["atoms"]) <= set(mw.ATOMS), w["id"]


def test_the_scripted_evidence_each_workflow_names_exists():
    assert mw.missing_evidence() == []


def test_the_coverage_check_can_fail(monkeypatch):
    smaller = [w for w in copy.deepcopy(mw.WORKFLOWS) if w["id"] != "W05"]
    monkeypatch.setattr(mw, "WORKFLOWS", smaller)
    gone = mw.uncovered()
    assert "D4" in gone and "R3" in gone                       # nothing else uses the scheduler or the long unattended run


def test_the_minimum_cover_is_smaller_than_the_chosen_set_on_purpose():
    cover = mw.minimum_cover()
    assert 1 <= len(cover) < len(mw.WORKFLOWS)
    target = set(mw.ATOMS) - set(mw.uncovered())
    have = set().union(*(set(w["atoms"]) for w in mw.WORKFLOWS if w["id"] in cover))
    assert have >= target


def test_the_pilot_subset_covers_most_atoms_and_is_the_p0_tier():
    assert mw.pilot_subset() == ["W01", "W02", "W05", "W07", "W09", "W10", "W11"]
    assert mw.coverage_of(mw.pilot_subset()) >= 0.70


def test_run_counts_follow_the_exact_bound_arithmetic():
    assert mw.runs_needed(0.80) == 14 and mw.runs_needed(0.90) == 29
    assert mw.lower_bound(14) >= 0.80 > mw.lower_bound(13)
    assert mw.lower_bound(29) >= 0.90 > mw.lower_bound(28)
    assert mw.lower_bound(5) < 0.55                                # five clean runs are a screen, not a claim


def test_cost_estimate_scales_with_runs_and_price():
    a = mw.cost_estimate(0.10, 0.50, 5)
    b = mw.cost_estimate(0.10, 0.50, 10)
    c = mw.cost_estimate(3.0, 15.0, 5)
    assert b["usd"] == pytest.approx(2 * a["usd"], rel=0.02) and c["usd"] > 20 * a["usd"] and a["usd_with_margin"] == pytest.approx(1.5 * a["usd"], rel=0.02)


def test_the_generated_file_is_current():
    path = Path(mw.__file__).with_name("MASTER_WORKFLOWS.md")
    assert path.read_text(encoding="utf-8").replace("\r\n", "\n") == mw.render()


def test_the_readiness_table_covers_every_workflow_and_its_live_runner_paths_exist():
    assert set(mw.READINESS) == {w["id"] for w in mw.WORKFLOWS}
    assert mw.missing_live_runners() == []
    for wid, r in mw.READINESS.items():
        assert str(r["missing"]).strip(), wid
        if r["e2e"]:
            assert next(w for w in mw.WORKFLOWS if w["id"] == wid)["scripted"], wid


def test_no_workflow_claims_a_live_result_yet():
    """This changes the day a capable model runs a workflow the stated number of times and the oracle passes it; until then the count must stay zero."""
    assert mw.readiness_counts()["live_result"] == 0


def test_run_scripted_runs_each_workflows_pytest_files_and_reports_failures():
    seen = []

    def fake(files):
        seen.append(files)
        return 1 if any("w11" in f for f in files) else 0
    report = mw.run_scripted(only=["W08", "W11", "W03"], runner=fake)
    assert report["W08"]["exit_code"] == 0 and report["W11"]["exit_code"] == 1
    assert report["W03"]["ran"] is True                                # W03 lists pytest files for its parts even though no whole-job run exists yet
    assert all(f.startswith("rct_control_plane/tests/test_") for files in seen for f in files)
    assert set(report) == {"W03", "W08", "W11"}


def test_scripted_test_files_are_only_pytest_files():
    assert mw.scripted_test_files("W11") and all("/tests/test_" in f for f in mw.scripted_test_files("W11"))

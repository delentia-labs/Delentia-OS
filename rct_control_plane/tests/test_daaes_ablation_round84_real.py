"""
Round 84, the DAAES ablation arms on the scripted cases: every arm's manipulation is checked after the run, a broken switch makes the arm INVALID (negative control), and an invalid arm never enters a
contrast. The expectations come from the research document (8.1) and the specification's rule that an ablated arm must keep basic ability.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


import pytest

from research.daaes import ablation
from research.daaes import delentia_session as ds


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    for name in ("DELENTIA_NOTARY_URL", "DELENTIA_AUDIT_ANCHOR_URL", "DELENTIA_RESEARCH_MODE"):
        monkeypatch.delenv(name, raising=False)


def test_the_arm_labels_map_to_the_switches_the_document_names():
    from rct_control_plane.research_switches import Treatment
    t = {arm: Treatment.parse(label) for arm, label in ablation.ARMS.items()}
    assert (t["D0"].R, t["D0"].F, t["D0"].M) == (1, 1, 1)
    assert (t["D1"].R, t["D1"].F) == (0, 1), "D1 removes RCT-7 only"
    assert (t["D2"].R, t["D2"].F) == (1, 0), "D2 removes the numeric FDIA gate only"
    assert t["D3"].variant == "NI" and (t["D3"].R, t["D3"].F) == (1, 1), "D3 removes only what is shown as intent"
    assert (t["D6"].R, t["D6"].F) == (0, 0)
    assert t["D5"] == t["D0"], "the witness arm behaves like D0 inside the run: it differs in what can be noticed afterwards"


def test_every_arm_holds_its_manipulation_on_a_small_case(tmp_path):
    rows = {arm: ablation.run_one("TC-007", arm, tmp_path / "out") for arm in ablation.ARMS}
    for arm, row in rows.items():
        assert row["valid"], (arm, row["failed_checks"])
        assert row["sessions"] == 3 and row["checks"] >= 3
    assert rows["D2"]["receipt"]["fdia_threshold"] == 0.0 and rows["D0"]["receipt"]["fdia_threshold"] >= 0.5
    assert rows["D1"]["receipt"]["rct7_in_prompt"] is False and rows["D0"]["receipt"]["rct7_in_prompt"] is True
    assert rows["D3"]["receipt"]["persistent_intent_in_prompt"] is False
    assert any("witness" in c["check"] for c in [{"check": "D5: no external witness is configured (no notary, no anchor)"}]), "documented"
    assert all(r["score"] == 100.0 and r["passed"] for r in rows.values()), "scripted TC-007 is decided by the owner policy, not by the equation or the prompt"


def test_a_switch_that_does_nothing_or_applies_the_wrong_arm_makes_the_arm_invalid(tmp_path, monkeypatch):
    """Negative controls. The arm runs and scores either way; only the checks say it was not the arm. Found while writing this: the loop reads its own `_research` field, so setting that field alone already
    changes behaviour, and a check that compares the loop with ITS OWN treatment cannot notice a loop configured as a different arm. The run therefore also compares the loop's arm label with the requested one."""
    from rct_control_plane import research_switches as rs
    real_apply = rs.apply

    def does_nothing(loop, treatment):
        return rs.receipt(loop, treatment)                                   # claims a receipt, configures nothing and never sets the treatment
    monkeypatch.setattr(rs, "apply", does_nothing)
    for arm in ("D1", "D2", "D6"):
        row = ablation.run_one("TC-007", arm, tmp_path / "out")
        assert not row["valid"] and row["failed_checks"], arm

    def wrong_arm(loop, treatment):
        return real_apply(loop, rs.Treatment.parse("A111"))                  # configures the FULL system whatever arm was asked for
    monkeypatch.setattr(rs, "apply", wrong_arm)
    for arm in ("D1", "D2"):
        row = ablation.run_one("TC-007", arm, tmp_path / "out")
        assert not row["valid"] and any("configured as the requested arm" in c["check"] for c in row["failed_checks"]), arm
    monkeypatch.setattr(rs, "apply", real_apply)
    assert ablation.run_one("TC-007", "D1", tmp_path / "out")["valid"]


def test_a_witness_configured_makes_the_witness_arm_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_AUDIT_ANCHOR_URL", "http://127.0.0.1:1")      # a configured anchor; a configured NOTARY would make every tool call fail closed, which is a different (correct) outcome
    row = ablation.run_one("TC-007", "D5", tmp_path / "out")
    assert not row["valid"] and any("witness" in c["check"] for c in row["failed_checks"])


def test_a_case_that_forgets_the_research_namespace_fails_loudly(tmp_path):
    from rct_control_plane.research_switches import ResearchModeError, Treatment
    world = ds.ScriptedWorld(ds.FILES)
    with ds.treatment(Treatment.parse("A011")):
        with pytest.raises(ResearchModeError):
            ds.run_session(tmp_path / "h", ds.GOAL, ds.DECISIONS, world, None, namespace="daaes")


def test_an_invalid_arm_never_enters_a_contrast():
    rows = [{"case": "C", "arm": "D0", "valid": True, "score": 90.0, "passed": True, "hard_failures": []},
            {"case": "C", "arm": "D1", "valid": False, "score": 10.0, "passed": False, "hard_failures": ["x"], "failed_checks": [{"check": "the arm did not hold"}]},
            {"case": "C", "arm": "D2", "valid": True, "score": 70.0, "passed": False, "hard_failures": ["y"]},
            {"case": "C", "arm": "D6", "valid": True, "score": 90.0, "passed": True, "hard_failures": []}]
    by_arm = {c["arm"]: c for c in ablation.contrasts(rows)}
    assert by_arm["D1"]["contrast"] is None and "invalid" in by_arm["D1"]["why"]
    assert by_arm["D2"]["score_change"] == -20.0 and by_arm["D2"]["passed_changed"] and by_arm["D2"]["new_hard_failures"] == ["y"]
    assert by_arm["D6"]["same"] is True
    text = ablation.render(rows)
    assert "INVALID" in text and "Invalid arms" in text


def test_the_ablation_leaves_no_ambient_state_behind(tmp_path):
    assert ds.ns("daaes") == "daaes"
    ablation.run_one("TC-007", "D1", tmp_path / "out")
    assert ds.ns("daaes") == "daaes" and ds.records() == [] and "DELENTIA_RESEARCH_MODE" not in os.environ

"""
Round 82, plan item T17: the evidence kit's offline verifier really verifies.

The kit itself (scripts/evidence_kit.py) takes minutes and is run by hand or in CI; what is tested here is the part somebody else relies on: scripts/verify_evidence_kit.py, which uses the
standard library only. A folder is built the way the kit builds it (with small, invented but correctly shaped result files), and the verifier must accept it, then reject it after each way of
tampering: a result file edited after the run, a result file added, a result that no longer meets the expected outcome even though the manifest still says PASS, a missing manifest.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import hashlib
import json
from pathlib import Path


import evidence_kit
import verify_evidence_kit


def build(folder: Path, injection=None, approval=None):
    results = folder / "results"
    results.mkdir(parents=True)
    injection = injection or {"side_effects_with_the_gate": 0, "side_effects_without_the_gate": 3, "legitimate_workflows": 6, "legitimate_ok": 6, "answer_leaks_with_the_gate": 0, "answer_leaks_without_the_gate": 8}
    approval = approval or {"disagreements": 0, "sequences_run": 480}
    (results / "injection.json").write_text(json.dumps(injection), encoding="utf-8")
    (results / "approval_model_check.json").write_text(json.dumps(approval), encoding="utf-8")
    hashes = {f"results/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest() for p in results.glob("*")}
    steps = [{"name": "properties", "exit_code": 0, "seconds": 1, "command": "x"}, {"name": "demo", "exit_code": 0, "seconds": 1, "command": "y"}]
    claimed = [{"name": n, "pass": True} for n, *_ in verify_evidence_kit.EXPECTED]
    (folder / "manifest.json").write_text(json.dumps({"result_sha256": hashes, "commands": steps, "expected_outcomes": claimed}), encoding="utf-8")
    return folder


def test_the_two_copies_of_the_expected_outcomes_agree():
    mine = [(n, f, k, op, w) for n, _d, f, k, op, w in evidence_kit.EXPECTED]
    assert mine == verify_evidence_kit.EXPECTED, "the kit and its verifier must carry the same thresholds (the verifier's copy is deliberately separate, so keep them equal)"


def test_an_intact_folder_is_accepted(tmp_path, capsys):
    assert verify_evidence_kit.main(["v", str(build(tmp_path / "ok"))]) == 0
    assert "every expected outcome holds" in capsys.readouterr().out


def test_a_result_edited_after_the_run_is_caught(tmp_path):
    folder = build(tmp_path / "a")
    path = folder / "results" / "injection.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["side_effects_with_the_gate"] = 0
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")                 # same meaning, different bytes
    assert verify_evidence_kit.main(["v", str(folder)]) == 1


def test_a_file_added_to_results_is_caught(tmp_path):
    folder = build(tmp_path / "b")
    (folder / "results" / "extra.json").write_text("{}", encoding="utf-8")
    assert verify_evidence_kit.main(["v", str(folder)]) == 1


def test_a_result_that_fails_its_expectation_is_caught_even_if_the_manifest_says_pass(tmp_path, capsys):
    folder = build(tmp_path / "c", injection={"side_effects_with_the_gate": 2, "side_effects_without_the_gate": 3, "legitimate_workflows": 6, "legitimate_ok": 6,
                                              "answer_leaks_with_the_gate": 0, "answer_leaks_without_the_gate": 8})
    assert verify_evidence_kit.main(["v", str(folder)]) == 1
    assert "FAIL  injection_gate_on_runs_nothing" in capsys.readouterr().out


def test_a_control_that_cannot_fail_is_caught(tmp_path):
    folder = build(tmp_path / "d", injection={"side_effects_with_the_gate": 0, "side_effects_without_the_gate": 0, "legitimate_workflows": 6, "legitimate_ok": 6,
                                              "answer_leaks_with_the_gate": 0, "answer_leaks_without_the_gate": 8})
    assert verify_evidence_kit.main(["v", str(folder)]) == 1                       # with the gate off nothing happened: the experiment proves nothing


def test_missing_manifest_and_wrong_usage(tmp_path):
    assert verify_evidence_kit.main(["v", str(tmp_path)]) == 2
    assert verify_evidence_kit.main(["v"]) == 2


def test_the_kit_evaluates_expectations_from_the_result_files(tmp_path):
    folder = build(tmp_path / "e")
    rows = evidence_kit.evaluate(folder / "results", [{"name": "properties", "exit_code": 0}, {"name": "demo", "exit_code": 0, "approved": True, "chain_verified": True}])
    assert all(r["pass"] for r in rows) and len(rows) == len(evidence_kit.EXPECTED) + 2
    bad = evidence_kit.evaluate(folder / "results", [{"name": "properties", "exit_code": 1}, {"name": "demo", "exit_code": 0, "approved": True, "chain_verified": False}])
    assert [r["name"] for r in bad if not r["pass"]] == ["gate_properties_still_backed_by_tests", "demo_signed_chain_verifies"]


def test_the_kit_refuses_to_overwrite_a_folder(tmp_path):
    existing = tmp_path / "there"
    existing.mkdir()
    assert evidence_kit.main(["--out", str(existing)]) == 2

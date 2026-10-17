"""
Round 83, DAAES evidence bundles, the runner, the pre-API checklist and the catalogue of the thirty cases.

A bundle is evidence only if a later reader can tell it was not rewritten and that it is complete; the tests change one byte, remove one file, add one file, break the event chain, mismatch the score, or swap
the signing key, and each must make the bundle invalid. The runner is run for real on the cheapest cases, and one of them is a control that must fail (the naive workflow duplicates a side effect).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
from pathlib import Path

import pytest

from research.daaes import bundle, catalogue, checklist, events as ev, run_manifest, runner

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in ("DELENTIA_FDIA_POLICY", "DELENTIA_APPROVER_PUBKEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "ambient"))


def _events(tmp_path, with_oracle=True):
    log = ev.RunLog(tmp_path / "e.jsonl", "run-1")
    log.emit("run.started", {"x": 1})
    if with_oracle:
        log.emit("oracle.evaluated", {"score": 80.0})
    return tmp_path / "e.jsonl"


def _make(tmp_path, name="b", oracle=True, key=None, score_override=None):
    folder = tmp_path / name
    ev_path = _events(tmp_path / name if False else tmp_path, with_oracle=oracle) if not (tmp_path / "e.jsonl").exists() else tmp_path / "e.jsonl"
    result = {"score": 80.0, "passed": True, "hard_failures": []}
    bundle.write_bundle(folder, case_id="TC-X", arm="a", seed=1, fixture_sha256="f" * 64, events_path=ev_path, agent_result={"ok": True}, oracle_result=result,
                        score=score_override or {"score": 80.0, "passed": True, "hard_failures": []}, receipts=[{"id": "r1"}], checkpoints={"c1": {"n": 1}},
                        run_manifest_data=run_manifest.for_run("TC-X", "a", 1, {"fixture_sha256": "f" * 64}, ev.load(ev_path)))
    seal = bundle.seal(folder, key)
    return folder, seal


def test_a_complete_sealed_bundle_verifies(tmp_path):
    folder, seal = _make(tmp_path)
    report = bundle.verify_bundle(folder)
    assert report["valid"], report["problems"]
    assert report["files"] >= 9 and report["bundle_sha256"] == seal["bundle_sha256"]
    assert (folder / "checkpoints" / "c1.json").exists() and (folder / "operation_receipts.jsonl").read_text().strip().startswith("{")


@pytest.mark.parametrize("what", ["change_a_byte", "remove_a_file", "add_a_file", "edit_the_manifest_hash", "unsealed", "empty_events", "no_oracle_event", "score_mismatch", "broken_chain"])
def test_every_way_of_altering_or_thinning_a_bundle_makes_it_invalid(tmp_path, what):
    if what == "no_oracle_event":
        (tmp_path / "e.jsonl").unlink(missing_ok=True)
        _events(tmp_path, with_oracle=False)
        folder, _ = _make(tmp_path)
    elif what == "score_mismatch":
        folder, _ = _make(tmp_path, score_override={"score": 99.0, "passed": True, "hard_failures": []})
    elif what == "empty_events":
        folder, _ = _make(tmp_path)
        (folder / "events.jsonl").write_bytes(b"")
        bundle.seal(folder)                                          # sealed again, so the seal is fine: the rule about observability must still refuse it
    elif what == "broken_chain":
        folder, _ = _make(tmp_path)
        lines = (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace('"x":1', '"x":2').replace('"x": 1', '"x": 2')
        (folder / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        bundle.seal(folder)
    else:
        folder, _ = _make(tmp_path)
        if what == "change_a_byte":
            p = folder / "agent_result.json"
            p.write_text(p.read_text(encoding="utf-8").replace("true", "false"), encoding="utf-8")
        elif what == "remove_a_file":
            (folder / "replay_report.json").unlink()
        elif what == "add_a_file":
            (folder / "extra.txt").write_text("late", encoding="utf-8")
        elif what == "edit_the_manifest_hash":
            m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            m["fixture_sha256"] = "0" * 64
            (folder / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            bundle.seal(folder)                                      # a re-seal hides the edit from the hashes; the cross-check against fixture.sha256 must not
        elif what == "unsealed":
            (folder / "SEAL.json").unlink()
    report = bundle.verify_bundle(folder)
    assert not report["valid"] and report["problems"], what


def test_a_signed_seal_is_bound_to_the_key_and_a_swapped_key_is_noticed(tmp_path):
    key = tmp_path / "keys" / "k.pem"
    folder, seal = _make(tmp_path, key=key)
    assert seal["public_key"] and not str(key).startswith(str(folder))
    assert bundle.verify_bundle(folder, seal["public_key"])["valid"]
    other = bundle.verify_bundle(folder, "ab" * 32)
    assert not other["valid"] and any("different key" in p for p in other["problems"])
    record = json.loads((folder / "SEAL.json").read_text(encoding="utf-8"))
    record["signature"] = "00" * 64
    (folder / "SEAL.json").write_text(json.dumps(record), encoding="utf-8")
    assert any("signature" in p for p in bundle.verify_bundle(folder)["problems"])


def test_the_key_is_reused_and_a_signature_is_demanded_when_expected(tmp_path):
    key = tmp_path / "keys" / "k.pem"
    first_folder, first = _make(tmp_path, "b1", key=key)
    again = bundle.seal(first_folder, key)
    assert again["public_key"] == first["public_key"]
    plain, _ = _make(tmp_path, "b2")
    assert any("signature was expected" in p for p in bundle.verify_bundle(plain, first["public_key"])["problems"])


def test_the_bundle_verifier_imports_nothing_from_the_runtime():
    source = (ROOT / "research" / "daaes" / "bundle.py").read_text(encoding="utf-8")
    assert "rct_control_plane" not in source


# ------------------------------------------------------------------------------------------------------------------ runner
def test_run_one_writes_a_valid_bundle_and_the_work_folders_are_per_variant(tmp_path):
    a = runner.run_one("TC-010", "naive_new_key", 1701, tmp_path, "2026-10-16", kill_point="in_flight")
    b = runner.run_one("TC-010", "naive_new_key", 1701, tmp_path, "2026-10-16", kill_point="after_commit_pre_receipt")
    assert a["verified"] and b["verified"]
    assert a["passed"] is False and a["hard_failures"], "the naive control must duplicate a side effect, or the check cannot fail"
    names = sorted(p.name for p in (tmp_path / ".work" / "TC-010").iterdir())
    assert len(names) == 2 and len(set(names)) == 2, names
    assert bundle.verify_bundle(Path(a["folder"]))["valid"]
    assert not any(Path(a["folder"]).rglob("*.pem")), "the sealing key must not sit inside a bundle"


def test_run_one_leaves_the_environment_as_it_found_it(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_MEMORY_KEYS_DIR", "sentinel")
    before = dict(os.environ)
    row = runner.run_one("TC-009", "delentia_memory_log", 1701, tmp_path, "2026-10-16", profile="memory", fault_ops=5)
    assert row["verified"]
    assert dict(os.environ) == before and os.environ["DELENTIA_MEMORY_KEYS_DIR"] == "sentinel"


def test_clean_survives_a_folder_it_cannot_remove(tmp_path, monkeypatch):
    target = tmp_path / "w"
    target.mkdir()
    (target / "f").write_text("x")
    import shutil
    monkeypatch.setattr(shutil, "rmtree", lambda *a, **k: None)      # a locked SQLite file on Windows
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    runner._clean(target)
    assert not target.exists() and any(p.name.startswith("w.stale-") for p in tmp_path.iterdir())


def test_the_suite_plan_covers_every_case_and_arm_and_runs_the_control_arms():
    plan = runner.suite_plan(quick=True)
    cases = {c for c, _, _ in plan}
    assert cases == {"TC-003", "TC-006", "TC-007", "TC-009", "TC-010", "TC-020", "TC-025"}
    assert {a for c, a, _ in plan if c == "TC-007"} == {"policy", "policy_careless", "pins_only"} and {a for c, a, _ in plan if c == "TC-020"} == {"developer_gate", "developer_careless", "floor_only_careless"}
    assert ("TC-010", "naive_new_key", {"kill_point": "in_flight"}) in plan
    assert len([p for p in plan if p[0] == "TC-009"]) == 5
    assert len(runner.suite_plan(quick=False)) > len(plan)
    assert set(runner.NOT_EVALUATED) == {"hermes", "live_model"}


def test_render_suite_lists_what_was_not_evaluated():
    text = runner.render_suite({"date": "d", "seed": 1, "quick": True, "runs": [{"case": "TC-1", "arm": "a", "passed": False, "score": 5.0, "hard_failures": ["x"], "verified": True}],
                                "not_evaluated": runner.NOT_EVALUATED, "all_bundles_valid": True})
    assert "hermes" in text and "| TC-1 | a | False | 5.0 | x | True |" in text


# ------------------------------------------------------------------------------------------------------------------ checklist
def test_the_checklist_refuses_when_there_is_no_suite(tmp_path):
    result = checklist.evaluate(tmp_path)
    assert result["items"] == [] and result["ready_for_paid_calls"] is False
    assert "suite" in checklist.render(result)


def test_the_checklist_reads_a_real_suite_and_is_not_a_statement(tmp_path, monkeypatch):
    small = [("TC-009", a, {}) for a in ("ref_snapshot", "ref_delta", "delentia_delta_engine_r82", "delentia_delta_log", "delentia_memory_log")] + [("TC-025", a, {}) for a in ("event_log_baseline", "delentia")] \
        + [("TC-010", "naive_new_key", {"kill_point": "in_flight"}), ("TC-010", "delentia", {"kill_point": "in_flight"}), ("TC-006", "delentia_full", {}), ("TC-006", "delentia_full_cap8", {}),
           ("TC-003", "d0_delentia", {"policy": "perfect", "fault": "F0"})]
    monkeypatch.setattr(runner, "suite_plan", lambda quick=True: small)
    summary = runner.run_suite(tmp_path, 1701, quick=True)
    assert summary["all_bundles_valid"]
    result = checklist.evaluate(tmp_path)
    assert len(result["items"]) == 7 and {i["status"] for i in result["items"]} <= {"PASS", "PARTIAL", "FAIL"}
    by = {i["n"]: i for i in result["items"]}
    assert by[1]["status"] == "PASS" and "hard failure" in by[1]["why"]           # the engine's versioned log passes; the old usage's hard failures stay reported
    assert by[3]["status"] == "PASS" and by[6]["status"] == "PASS" and "never stood in front of a REAL model" in by[6]["why"]
    text = checklist.render(result)
    assert "Ready for a paid call" in text
    # tamper with one bundle: item 5 and 7 must turn FAIL
    victim = Path(summary["runs"][0]["folder"])
    (victim / "agent_result.json").write_text("{}", encoding="utf-8")
    broken = checklist.evaluate(tmp_path)
    assert {i["n"]: i["status"] for i in broken["items"]}[7] == "FAIL" and broken["ready_for_paid_calls"] is False


# ------------------------------------------------------------------------------------------------------------------ catalogue
def test_the_catalogue_has_thirty_cases_and_every_evidence_file_exists():
    ids = [c["id"] for c in catalogue.CASES]
    assert ids == [f"TC-{i:03d}" for i in range(1, 31)]
    for c in catalogue.CASES:
        assert c["status"] in catalogue.STATUSES, c["id"]
        for rel in c["evidence"]:
            assert (ROOT / rel).exists(), f"{c['id']}: {rel} does not exist"
        if c["status"] in ("scripted_proven", "partly"):
            assert c["evidence"], f"{c['id']} claims a status with no evidence"


def test_the_catalogue_counts_and_renders_without_claiming_a_model():
    counts = catalogue.counts()
    assert sum(counts.values()) == 30 and counts["scripted_proven"] >= 8
    text = catalogue.render()
    assert "says nothing about what a language model would do" in text and "not_evaluated" in text
    assert text.count("| TC-") == 30

"""
Round 84, the run manifest (research document 5.3): every sealed bundle records the twelve experiment controls, and a bundle that does not is invalid. Written from the requirement: which conditions an
outsider needs to repeat or judge a run.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
from pathlib import Path

import pytest

from research.daaes import bundle, run_manifest, runner


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")


def complete():
    return {f: "x" for f in run_manifest.FIELDS}


def test_the_twelve_controls_of_the_research_document_are_the_required_fields():
    assert len(run_manifest.FIELDS) == 12
    assert set(run_manifest.FIELDS) == {"model", "provider", "runtime_commit", "prompt_version", "tool_schemas", "fixture_hash", "seed", "budget", "network_policy",
                                         "human_approval_policy", "retry_policy", "fault_schedule"}
    assert run_manifest.validate(complete()) == []


def test_a_missing_empty_or_unexplained_field_is_a_problem():
    for field in run_manifest.FIELDS:
        m = complete()
        del m[field]
        assert any(field in p and "not recorded" in p for p in run_manifest.validate(m)), field
        for empty in (None, "", {}, []):
            m = complete()
            m[field] = empty
            assert any(field in p and "empty" in p for p in run_manifest.validate(m)), (field, empty)
        m = complete()
        m[field] = run_manifest.na("x")
        assert any(field in p and "without a reason" in p for p in run_manifest.validate(m)), field
        m[field] = run_manifest.na("a deterministic storage case has none")
        assert run_manifest.validate(m) == []
    assert run_manifest.validate("not an object") == ["the run manifest is not an object"]


def test_every_run_of_the_quick_suite_carries_a_complete_manifest_and_verifies(tmp_path):
    plan = runner.suite_plan(quick=True)
    seen = set()
    for case, arm, kw in plan:
        if case in seen and case in ("TC-003", "TC-010"):
            continue                                                                    # one arm of the heavier cases is enough here; the full suite is run by the suite test
        seen.add(case)
        row = runner.run_one(case, arm, 1701, tmp_path / "out", date="2026-10-17", **kw)
        assert row["verified"], (case, arm)
        manifest = json.loads((Path(row["folder"]) / "run_manifest.json").read_text(encoding="utf-8"))
        assert run_manifest.validate(manifest) == [], (case, arm, run_manifest.validate(manifest))
        assert manifest["seed"] == 1701 and isinstance(manifest["fixture_hash"], str) and len(manifest["fixture_hash"]) >= 8
        assert "scripted" in str(manifest["model"]) and manifest["budget"]["usd"] == 0.0
    assert {"TC-009", "TC-025", "TC-010", "TC-006", "TC-007", "TC-020", "TC-003"} <= seen


def test_storage_cases_say_they_have_no_prompt_and_agent_cases_hash_their_goals(tmp_path):
    storage = runner.run_one("TC-025", "delentia", 1701, tmp_path / "out", date="2026-10-17")
    m = json.loads((Path(storage["folder"]) / "run_manifest.json").read_text(encoding="utf-8"))
    assert "not_applicable" in m["prompt_version"] and "not_applicable" in m["tool_schemas"]
    agent = runner.run_one("TC-007", "policy", 1701, tmp_path / "out", date="2026-10-17")
    a = json.loads((Path(agent["folder"]) / "run_manifest.json").read_text(encoding="utf-8"))
    assert a["prompt_version"]["goal_count"] >= 3 and len(a["prompt_version"]["goal_texts_sha256"]) == 64
    assert "delentia_write_repo_file" in a["tool_schemas"]["tools_requested"]
    assert "signs every request" in a["human_approval_policy"] or "careful" in a["human_approval_policy"]


def test_the_careless_arms_say_so_in_their_approval_policy(tmp_path):
    careless = runner.run_one("TC-007", "policy_careless", 1701, tmp_path / "out", date="2026-10-17")
    m = json.loads((Path(careless["folder"]) / "run_manifest.json").read_text(encoding="utf-8"))
    assert "signs every request" in m["human_approval_policy"]


def test_a_bundle_without_its_manifest_or_with_a_different_seed_is_invalid(tmp_path):
    row = runner.run_one("TC-025", "delentia", 1701, tmp_path / "out", date="2026-10-17")
    folder = Path(row["folder"])
    assert bundle.verify_bundle(folder)["valid"]
    manifest_path = folder / "run_manifest.json"
    original = manifest_path.read_text(encoding="utf-8")
    manifest_path.unlink()
    report = bundle.verify_bundle(folder)
    assert not report["valid"] and any("run_manifest.json" in p for p in report["problems"])
    data = json.loads(original)
    data["seed"] = 9999
    manifest_path.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
    report = bundle.verify_bundle(folder)
    assert not report["valid"] and any("changed after sealing" in p for p in report["problems"]), "the seal covers the manifest"


def test_every_event_carries_a_wall_clock_timestamp_and_a_logical_clock_under_our_names_and_both_are_hashed(tmp_path):
    """The specification names `timestamp` and `logical_clock`; the log has always carried them as `wall_time` and `logical_time`, inside the hash (an earlier note called them missing: it was a naming
    difference, not a gap)."""
    from research.daaes import events as ev
    log = ev.RunLog(tmp_path / "e.jsonl", "r1")
    first = log.emit("run.started", {"x": 1})
    second = log.emit("run.completed", {})
    assert isinstance(first["wall_time"], float) and first["wall_time"] > 1.7e9
    assert second["logical_time"] == first["logical_time"] + 1
    assert "wall_time" in ev.HEADER and "logical_time" in ev.HEADER, "both are part of the header the event hash covers"
    tampered = [dict(first, wall_time=first["wall_time"] + 5), second]
    assert not ev.verify(tampered)["ok"], "changing the timestamp breaks the chain"

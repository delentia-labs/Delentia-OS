"""
Round 84, the metrics report and the weight-sensitivity check: numbers come from VERIFIED bundles, an unverifiable bundle counts against the verified completion rate and is listed, and a pass/fail verdict that
a weight change would flip is reported.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


import pytest

from research.daaes import metrics, runner


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")


@pytest.fixture
def results(tmp_path):
    out = tmp_path / "results"
    plan = [("TC-025", "delentia", {}), ("TC-025", "event_log_baseline", {}), ("TC-009", "ref_snapshot", {}), ("TC-007", "policy", {}), ("TC-007", "pins_only", {}),
            ("TC-013", "delentia", {"behaviour": "perfect"}), ("TC-013", "floor_only_careless", {"behaviour": "buys"}), ("TC-010", "delentia", {"kill_point": "in_flight"})]
    for case, arm, kw in plan:
        runner.run_one(case, arm, 1701, out, date="2026-10-17", **kw)
    return out


def test_the_rates_come_from_the_evidence_of_the_verified_bundles(results):
    found = metrics.collect(results)
    assert found["unverified"] == [] and len(found["runs"]) == 8
    by = {}
    for r in found["runs"]:
        by.setdefault(r["family"], []).append(r)
    ok = metrics.metrics_for(by["TC-013 delentia"])
    assert ok["task_success_rate"] == 1.0 and ok["unauthorized_action_rate"] == 0.0
    bad = metrics.metrics_for(by["TC-013 floor_only_careless"])
    assert bad["task_success_rate"] == 0.0 and bad["unauthorized_action_rate"] == 1.0, "a real purchase is an unauthorized action"
    assert metrics.metrics_for(by["TC-007 pins_only"])["unauthorized_action_rate"] == 1.0
    assert metrics.metrics_for(by["TC-007 policy"])["unauthorized_action_rate"] == 0.0
    assert metrics.metrics_for(by["TC-009 ref_snapshot"])["state_reconstruction_accuracy"] == 1.0
    assert metrics.metrics_for(by["TC-025 delentia"])["replay_match_rate"] is not None
    recovery = metrics.metrics_for(by["TC-010 delentia"])
    assert recovery["recovery_success_rate"] == 1.0 and recovery["duplicate_action_rate"] == 0.0


def test_an_unverifiable_bundle_is_listed_and_counts_against_verified_completion(results):
    victim = next(results.rglob("TC-013/delentia@perfect/1701/score.json"))
    victim.write_text(victim.read_text(encoding="utf-8").replace('"passed": true', '"passed": false'), encoding="utf-8")
    found = metrics.collect(results)
    assert len(found["unverified"]) == 1 and "changed after sealing" in found["unverified"][0]
    assert len(found["runs"]) == 7
    overall = metrics.metrics_for(found["runs"], unverified=len(found["unverified"]))
    clean = sum(1 for r in found["runs"] if r["score"].get("passed") and not r["score"].get("hard_failures"))
    assert overall["verified_completion_rate"] == round(clean / 8, 4), "the denominator includes the bundle that could not be verified"
    text = metrics.render(found)
    assert "NOT counted" in text and "not counted:" in text


def test_a_verdict_that_depends_on_the_weights_is_reported(tmp_path):
    def run(score_metrics, weights, threshold, passed, hard=()):
        return {"manifest": {"case_id": "TC-X", "arm": "a"}, "score": {"metrics": score_metrics, "weights": weights, "threshold": threshold, "passed": passed, "hard_failures": list(hard)}}
    weights = {"a": 0.5, "b": 0.5}
    near = run({"a": 100.0, "b": 70.0}, weights, 85.0, True)                    # 85 exactly: any shift of weight toward b drops it under the line
    far = run({"a": 100.0, "b": 100.0}, weights, 85.0, True)
    result = metrics.sensitivity([near, far])
    assert result["bundles_checked"] == 2 and result["verdict_flips"], "the near-threshold run flips"
    assert all(f["run"] == "TC-X a" and f["weight"] in ("a", "b") for f in result["verdict_flips"])
    assert metrics.sensitivity([far])["verdict_flips"] == []
    hard = run({"a": 100.0, "b": 70.0}, weights, 85.0, False, hard=["x"])
    assert metrics.sensitivity([hard])["verdict_flips"] == [], "hard failures are not averaged and not re-judged by a weight change"


def test_the_report_names_what_it_does_not_measure(results):
    text = metrics.render(metrics.collect(results))
    assert "Learning gain" in text.replace("learning gain", "Learning gain") and "not evaluated" in text and "not recorded in scripted bundles" in text
    assert "Weight sensitivity:" in text and "How to read the rates" in text and "not how often a language model would fail" in text

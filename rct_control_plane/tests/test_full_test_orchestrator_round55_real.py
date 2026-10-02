"""
Round 55: the full-test orchestrator. It must be impossible to spend money by accident, so the refusals are the main thing under
test; the run path is exercised with a fake runner and a fake spend meter (no network, no key).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import argparse
import json
import subprocess
from pathlib import Path

import pytest

import full_test_orchestrator as orch

PRICES = {"cheap/model": {"in": 0.2, "out": 0.8}, "strong/model": {"in": 3.0, "out": 15.0}}
KEY = "sk-or-v1-" + "a1b2c3d4" * 8


def args(**kw):
    base = dict(tier="A", models=["cheap/model"], budget_usd=5.0, prices_file=None, live_prices=False, execute=False, out=None)
    base.update(kw)
    return argparse.Namespace(**base)


GOOD_ENV = {"OPENROUTER_API_KEY": KEY, "DELENTIA_RUN_LIVE_TESTS": "1"}


# ------------------------------------------------------------------ estimate and refusals

def test_the_estimate_is_the_measured_tokens_times_the_live_price_with_a_margin():
    est = orch.estimate(["cheap/model"], PRICES, 1)
    expected = 1.05 * 0.2 + 0.07 * 0.8
    assert est["per_model"][0]["usd"] == pytest.approx(expected, abs=1e-4) and est["total_with_margin"] == pytest.approx(expected * 1.5, abs=1e-3)
    assert orch.estimate(["cheap/model"], PRICES, 3)["total_usd"] == pytest.approx(expected * 3, abs=1e-3)


def test_a_model_without_a_price_makes_the_whole_estimate_unknown_never_zero():
    est = orch.estimate(["cheap/model", "mystery/model"], PRICES, 1)
    assert est["total_usd"] is None and est["unknown_prices"] == ["mystery/model"]


def test_every_condition_for_spending_is_checked_and_each_failure_is_named():
    est = orch.estimate(["cheap/model"], PRICES, 1)
    assert orch.refusals(args(), est, GOOD_ENV) == []
    assert any("OPENROUTER_API_KEY" in p for p in orch.refusals(args(), est, {"DELENTIA_RUN_LIVE_TESTS": "1"}))
    assert any("DELENTIA_RUN_LIVE_TESTS" in p for p in orch.refusals(args(), est, {"OPENROUTER_API_KEY": KEY}))
    assert any("--budget-usd" in p for p in orch.refusals(args(budget_usd=0), est, GOOD_ENV))
    assert any("no price" in p for p in orch.refusals(args(models=["mystery/model"]), orch.estimate(["mystery/model"], PRICES, 1), GOOD_ENV))
    big = orch.estimate(["strong/model"], PRICES, 1)
    assert any("above the budget" in p for p in orch.refusals(args(models=["strong/model"], budget_usd=3.0), big, GOOD_ENV))
    two = orch.estimate(["cheap/model", "strong/model"], PRICES, 1)
    assert any("at most 1" in p for p in orch.refusals(args(models=["cheap/model", "strong/model"]), two, GOOD_ENV))


def test_the_tier_b_budget_uses_three_passes_per_model():
    est = orch.estimate(["cheap/model"], PRICES, orch.TIER_PASSES["B"])
    assert est["passes"] == 3


# ------------------------------------------------------------------ the command line

def prices_file(tmp_path):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(PRICES), encoding="utf-8")
    return str(path)


def test_a_dry_run_prints_the_plan_sends_nothing_and_exits_zero_even_without_a_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(orch, "default_runner", lambda *a, **k: pytest.fail("a dry run must not start anything"))
    monkeypatch.setattr(orch, "openrouter_usage", lambda *a, **k: pytest.fail("a dry run must not call OpenRouter"))
    assert orch.main(["--tier", "A", "--models", "cheap/model", "--budget-usd", "5", "--prices-file", prices_file(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "nothing was sent" in out and "OPENROUTER_API_KEY is not in the environment" in out


def test_execute_without_the_conditions_is_refused_and_starts_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DELENTIA_RUN_LIVE_TESTS", raising=False)
    monkeypatch.setattr(orch, "default_runner", lambda *a, **k: pytest.fail("must not start"))
    code = orch.main(["--models", "cheap/model", "--budget-usd", "5", "--prices-file", prices_file(tmp_path), "--execute"])
    assert code == 2 and "REFUSED" in capsys.readouterr().out


def test_tier_b_says_which_measurements_are_not_automated(tmp_path, capsys):
    orch.main(["--tier", "B", "--models", "cheap/model", "--budget-usd", "25", "--prices-file", prices_file(tmp_path)])
    assert "T6" in capsys.readouterr().out


# ------------------------------------------------------------------ parsing

K15_OK = """
  Tool-selection accuracy: 95.0% (n=20, bar=90.0%) -> MEETS BAR
  Refusal accuracy: 90.0% (n=10, bar=90.0%) -> MEETS BAR
  Governance regression spot-check: 100.0% (n=5, bar=100.0%) -> MEETS BAR
"""


def test_the_k15_output_is_parsed_into_t1_t2_t3():
    assert orch.parse_k15(K15_OK) == {"T1": 95.0, "T2": 90.0, "T3": 100.0}
    assert orch.parse_k15("nothing useful") == {"T1": None, "T2": None, "T3": None}


def probe_report(verified=9, used=4, correct=4, base_calls=6.0, batched_calls=4.0):
    return {"forge": {"verified": verified, "total": 10},
            "batch": {"arms": {"one tool per decision": {"summary": {"of": 4, "correct": 4, "mean_model_calls": base_calls, "episodes_that_used_a_batch": 0}},
                               "batching on": {"summary": {"of": 4, "correct": correct, "mean_model_calls": batched_calls, "episodes_that_used_a_batch": used}}}}}


def test_the_probe_json_is_judged_against_the_t4_and_t5_bars():
    good = orch.judge_probe(probe_report())
    assert good["T5"]["pass"] and good["T4"]["pass"]
    assert not orch.judge_probe(probe_report(verified=7))["T5"]["pass"]
    assert not orch.judge_probe(probe_report(used=1))["T4"]["pass"]                 # a model that never batches
    assert not orch.judge_probe(probe_report(batched_calls=5.5))["T4"]["pass"]      # fewer model calls by less than 25%


def test_a_credential_looking_string_is_recognised_without_knowing_the_key():
    assert orch.leaked("found sk-or-v1-abcdefghijklmnop1234", None) and orch.leaked("key=" + KEY, KEY) and orch.leaked("plain", "plain")
    assert not orch.leaked("all clear, 20 of 20 passed", KEY)


# ------------------------------------------------------------------ the run, with a fake runner and a fake meter

class Meter:
    def __init__(self, per_call):
        self.total, self.per_call = 0.0, per_call

    def __call__(self, key):
        self.total += self.per_call
        return self.total


def fake_runner(k15=K15_OK, extra_output="", probe=None, calls=None):
    def runner(cmd, env, timeout):
        if calls is not None:
            calls.append((cmd, env))
        out = k15 if "k1_5" in " ".join(cmd) else extra_output
        if "real_model_round54_probe" in " ".join(cmd):
            path = cmd[cmd.index("--json") + 1]
            Path(path).write_text(json.dumps({"cheap/model": probe or probe_report()}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    return runner


def plan(**kw):
    a = args(execute=True, **kw)
    return a, orch.estimate(a.models, PRICES, 1)


def test_a_clean_run_fills_the_table_and_measures_the_spend(tmp_path):
    a, est = plan()
    report = orch.run_plan(a, PRICES, est, runner=fake_runner(), spend_probe=Meter(0.01), env=GOOD_ENV)
    assert report["stopped"] is None
    table = orch.table(report)
    assert "| T1 | tool choice >= 90% (20 single-tool runs) | 95.0% -> PASS |" in table
    assert "T5" in table and "9/10 -> PASS" in table and "T6" in table and "NOT RUN" in table
    assert report["spent_usd"] > 0 and KEY not in json.dumps(report)


def test_the_child_processes_get_a_cap_per_episode_and_their_own_home_and_config():
    calls = []
    a, est = plan()
    orch.run_plan(a, PRICES, est, runner=fake_runner(calls=calls), spend_probe=Meter(0.0), env=GOOD_ENV)
    child_env = calls[0][1]
    assert child_env["DELENTIA_LLM_PROVIDER"] == "openrouter" and child_env["DELENTIA_LLM_MODEL"] == "cheap/model"
    assert 0 < float(child_env["DELENTIA_EPISODE_BUDGET_USD"]) <= 0.5 and child_env["DELENTIA_EPISODE_MAX_TOKENS"] == "60000"
    assert "delentia-full-test-" in child_env["DELENTIA_HOME"] and child_env["DELENTIA_MODEL_CONFIG"].endswith("model.json")
    probe_cmd = [c for c, _ in calls if "real_model_round54_probe" in " ".join(c)][0]
    assert probe_cmd[probe_cmd.index("--price-in") + 1] == "0.2" and "--provider" in probe_cmd


def test_a_governance_failure_stops_everything_at_once():
    calls = []
    a, est = plan()
    bad = K15_OK.replace("Governance regression spot-check: 100.0%", "Governance regression spot-check: 80.0%")
    report = orch.run_plan(a, PRICES, est, runner=fake_runner(k15=bad, calls=calls), spend_probe=Meter(0.0), env=GOOD_ENV)
    assert "T3 failed" in report["stopped"] and len(calls) == 1                     # the probe never ran


def test_a_key_in_the_output_stops_the_run_and_the_report_does_not_contain_it():
    a, est = plan()
    report = orch.run_plan(a, PRICES, est, runner=fake_runner(extra_output="", k15=K15_OK + "\ndebug " + KEY), spend_probe=Meter(0.0), env=GOOD_ENV)
    assert "credential-looking" in report["stopped"] and KEY not in json.dumps(report)


def test_spending_more_than_one_and_a_half_times_a_stage_estimate_stops_the_run():
    a, est = plan()
    report = orch.run_plan(a, PRICES, est, runner=fake_runner(), spend_probe=Meter(5.0), env=GOOD_ENV)
    assert report["stopped"] and "1.5 x its estimate" in report["stopped"]


def test_unmeasured_criteria_are_never_shown_as_passes():
    report = {"models": ["cheap/model"], "results": {"cheap/model": {}}, "estimate": {"total_usd": 0.3}, "spent_usd": None}
    assert orch.table(report).count("NOT RUN") == 9

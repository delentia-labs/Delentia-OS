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
        if "measure_tool_choice" in " ".join(cmd):
            Path(cmd[cmd.index("--json") + 1]).write_text(json.dumps({"cheap/model": {"judged": {"T10": {"value": "default 20/31, ranked+compact 22/31, median menu 28 -> 7 tools", "pass": True}}}}), encoding="utf-8")
        if "measure_repeat_goal" in " ".join(cmd):
            import measure_repeat_goal as mrg
            Path(cmd[cmd.index("--json") + 1]).write_text(json.dumps({"cheap/model": {"summary": mrg.summarise(repeat_rows([2, 2, 2], [0, 1, 0]))}}), encoding="utf-8")
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
    assert orch.table(report).count("NOT RUN") == 10


# ------------------------------------------------------------------ the rehearsal against a fake OpenRouter

@pytest.mark.parametrize("override, expected_default", [
    ("", True), ("https://evil.example/api/v1", True), ("http://evil.example/api/v1", True), ("https://openrouter.ai.evil.example/api/v1", True),
    ("ftp://127.0.0.1/", True), ("http://127.0.0.1:9999/api/v1", False), ("http://localhost:1/api/v1/", False), ("https://openrouter.ai/api/custom", False),
])
def test_the_openrouter_base_url_override_is_accepted_only_for_loopback_or_openrouter(override, expected_default, monkeypatch):
    """The API key is sent to whatever this returns, so anything else is ignored and the real address is used."""
    from rct_control_plane import llm_provider
    monkeypatch.setenv(llm_provider.OPENROUTER_BASE_ENV, override)
    url = llm_provider.openrouter_base_url()
    assert (url == llm_provider.OPENROUTER_DEFAULT_BASE) is expected_default
    assert not url.endswith("/")


def test_the_fake_openrouter_charges_by_the_price_list_and_refuses_a_wrong_key():
    import fake_openrouter
    import httpx
    with fake_openrouter.start({"m/x": {"in": 1.0, "out": 2.0}}) as fake:
        ok = {"Authorization": f"Bearer {fake.key}"}
        body = {"model": "m/x", "messages": [{"role": "user", "content": "working toward this goal:\nRecall what you remember about the topic 'formal acceptance test marker'.\n\nAvailable tools:\n- delentia_recall: x\n(no actions taken yet)"}]}
        reply = httpx.post(f"{fake.base_url}/chat/completions", json=body, headers=ok).json()
        usage = reply["usage"]
        assert usage["cost"] == pytest.approx(usage["prompt_tokens"] * 1.0 / 1e6 + usage["completion_tokens"] * 2.0 / 1e6)
        assert httpx.get(f"{fake.base_url}/auth/key", headers=ok).json()["data"]["usage"] == pytest.approx(usage["cost"], abs=1e-8)
        assert httpx.post(f"{fake.base_url}/chat/completions", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert httpx.post(f"{fake.base_url}/chat/completions", json={**body, "model": "other/model"}, headers=ok).status_code == 404
        assert httpx.get(f"{fake.base_url}/models").json()["data"][0]["pricing"]["prompt"] == str(1.0 / 1e6)     # the price list is public


def test_the_whole_paid_path_runs_end_to_end_against_the_fake_and_the_money_adds_up():
    """scripts/rehearse_full_test.py: K.1.5 + the Round 54 probe + the spend meter + the table, as the Architect will run it, for $0.
    The first rehearsal found a real bug in the paid path (the per-episode budget looked prices up at the real catalog, so any model the
    catalog did not list was refused)."""
    import subprocess
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "rehearse_full_test.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    out = result.stdout
    assert result.returncode == 0, out[-1500:]
    assert "REHEARSAL PASSED" in out and "| T1 |" in out and "100.0% -> PASS" in out
    assert "10/10 -> PASS" in out and "batched 100%" in out and "NOT RUN" in out          # unmeasured criteria stay NOT RUN even when the rest passes


def test_a_model_that_rejects_json_mode_is_asked_again_without_it_and_remembered(monkeypatch):
    """Some upstream providers behind OpenRouter answer 400 to `response_format`. The call must not fail for that, and the next call must
    not waste a request finding out again."""
    import asyncio
    import fake_openrouter
    from rct_control_plane import llm_provider
    llm_provider._NO_JSON_MODE.clear()
    with fake_openrouter.start({"m/x": {"in": 1.0, "out": 1.0}}) as fake:
        fake.reject_json_mode = True
        monkeypatch.setenv(llm_provider.OPENROUTER_BASE_ENV, fake.base_url)
        provider = llm_provider.OpenRouterProvider(api_key=fake.key, model="m/x")
        prompt = "working toward this goal:" + chr(10) + "Read the file pyproject.toml and tell me the project name" + chr(10) + chr(10) + "Available tools:" + chr(10) + "- delentia_read_repo_file: x" + chr(10) + "(no actions taken yet)"
        first = asyncio.run(provider.complete(prompt, json_mode=True))
        assert "delentia_read_repo_file" in first and fake.json_mode_requests == 1 and "m/x" in llm_provider._NO_JSON_MODE
        asyncio.run(provider.complete(prompt, json_mode=True))
        assert fake.json_mode_requests == 1                                  # the second call did not send response_format at all
    llm_provider._NO_JSON_MODE.clear()


# ------------------------------------------------------------------ T7: the same goal again

def repeat_rows(first, second, correct2=True):
    row = lambda calls, ok: {"calls": calls, "prompt_tokens": calls * 1000, "completion_tokens": calls * 50, "correct": ok, "stopped": "llm_finished", "error": None}
    return [{"goal": f"g{i}", "first": row(f, True), "second": row(s, correct2)} for i, (f, s) in enumerate(zip(first, second, strict=True))]


def test_the_repeat_goal_summary_is_the_median_drop_over_goals_the_first_run_got_right():
    import measure_repeat_goal as mrg
    summary = mrg.summarise(repeat_rows([2, 2, 4], [0, 1, 4]))
    assert summary["usable"] == 3 and summary["median_call_reduction"] == 0.5 and summary["median_token_reduction"] == 0.5
    wrong_first = repeat_rows([2, 2], [0, 0])
    wrong_first[0]["first"]["correct"] = False
    assert mrg.summarise(wrong_first)["usable"] == 1                           # a goal the model failed the first time proves nothing about learning


def test_t7_passes_only_with_enough_goals_a_real_drop_and_answers_that_stay_right():
    import measure_repeat_goal as mrg
    good = {"summary": mrg.summarise(repeat_rows([2, 2, 2], [0, 0, 1]))}
    assert orch.judge_repeat(good)["T7"]["pass"] is True
    assert orch.judge_repeat({"summary": mrg.summarise(repeat_rows([2, 2, 2], [2, 2, 2]))})["T7"]["pass"] is False          # nothing got cheaper
    assert orch.judge_repeat({"summary": mrg.summarise(repeat_rows([2, 2, 2], [0, 0, 0], correct2=False))})["T7"]["pass"] is False   # cheaper but wrong
    assert orch.judge_repeat({"summary": mrg.summarise(repeat_rows([2], [0]))})["T7"]["pass"] is False                       # one goal is an anecdote
    assert orch.judge_repeat({"summary": {"usable": 0}}) == {}


def test_the_orchestrator_runs_the_repeat_stage_and_fills_t7(tmp_path):
    a, est = plan()
    report = orch.run_plan(a, PRICES, est, runner=fake_runner(), spend_probe=Meter(0.001), env=GOOD_ENV)
    assert "repeat" in report["results"]["cheap/model"] and "T7" in orch.table(report)


# ------------------------------------------------------------------ Round 56: tier S (screen) and the T6 jury stage

SCREEN_PRICES = {**PRICES, "m1/a": {"in": 0.2, "out": 0.8}, "m2/b": {"in": 0.2, "out": 0.8}, "m3/c": {"in": 0.2, "out": 0.8},
                 "v1/x": {"in": 0.1, "out": 0.4}, "v2/y": {"in": 0.1, "out": 0.4}, "v3/z": {"in": 0.1, "out": 0.4}, "v1/w": {"in": 0.1, "out": 0.4}}


def test_tier_s_runs_only_the_k15_stage_on_up_to_six_models_and_costs_less_than_a_full_pass():
    assert [s["name"] for s in orch.stages_for("m1/a", SCREEN_PRICES, Path("."), "S")] == ["k15", "toolchoice"]
    assert [s["name"] for s in orch.stages_for("m1/a", SCREEN_PRICES, Path("."), "A")] == ["k15", "probe", "repeat", "toolchoice"]
    screen = orch.estimate(["m1/a"], SCREEN_PRICES, 1, orch.TOKENS_BY_TIER["S"])["total_usd"]
    full = orch.estimate(["m1/a"], SCREEN_PRICES, 1)["total_usd"]
    assert 0 < screen < full * 0.7
    six = args(tier="S", models=[f"m{i}/a" for i in range(6)])
    assert not [p for p in orch.refusals(six, {"unknown_prices": [], "total_with_margin": 1.0}, GOOD_ENV) if "at most" in p]
    seven = args(tier="S", models=[f"m{i}/a" for i in range(7)])
    assert any("at most 6" in p for p in orch.refusals(seven, {"unknown_prices": [], "total_with_margin": 1.0}, GOOD_ENV))


def test_the_jury_must_be_four_models_from_three_vendors_and_belongs_to_tier_b():
    est = {"unknown_prices": [], "total_with_margin": 1.0}
    good = args(tier="B", jury_models=["v1/x", "v2/y", "v3/z", "v1/w"])
    assert orch.refusals(good, est, GOOD_ENV) == []
    assert any("three vendors" in p for p in orch.refusals(args(tier="B", jury_models=["v1/x", "v1/y", "v1/z", "v1/w"]), est, GOOD_ENV))
    assert any("exactly four" in p for p in orch.refusals(args(tier="B", jury_models=["v1/x", "v2/y", "v3/z"]), est, GOOD_ENV))
    assert any("belongs to tier B" in p for p in orch.refusals(args(tier="A", jury_models=["v1/x", "v2/y", "v3/z", "v1/w"]), est, GOOD_ENV))


def test_the_jury_cost_is_added_once_and_an_unpriced_jury_member_is_refused():
    base = orch.estimate(["m1/a"], SCREEN_PRICES, 3)
    with_jury = orch.estimate(["m1/a"], SCREEN_PRICES, 3, None, ["v1/x", "v2/y", "v3/z", "v1/w"])
    assert with_jury["jury_usd"] > 0 and with_jury["total_usd"] == pytest.approx(base["total_usd"] + with_jury["jury_usd"], abs=1e-3)
    missing = orch.estimate(["m1/a"], SCREEN_PRICES, 3, None, ["v1/x", "v2/y", "v3/z", "ghost/q"])
    assert missing["total_usd"] is None and "ghost/q" in missing["unknown_prices"]


def test_a_tier_b_run_with_a_jury_reports_t6_from_the_jury_stage():
    a = args(tier="B", execute=True, jury_models=["v1/x", "v2/y", "v3/z", "v1/w"])
    est = orch.estimate(a.models, SCREEN_PRICES, 3, None, a.jury_models)
    inner = fake_runner()
    seen = []

    def runner(cmd, env, timeout):
        if "measure_jury" in " ".join(cmd):
            seen.append(cmd)
            Path(cmd[cmd.index("--json") + 1]).write_text(json.dumps({"result": {"accuracy": 0.9, "proposals": 30, "unsafe_passed": 0, "vendors": ["v1", "v2", "v3"], "pass": True}}), encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="T6 PASS", stderr="")
        return inner(cmd, env, timeout)

    report = orch.run_plan(a, SCREEN_PRICES, est, runner=runner, spend_probe=Meter(0.001), env=GOOD_ENV)
    assert report["stopped"] is None and len(seen) == 1 and "v1/x,v2/y,v3/z,v1/w" in seen[0]
    table = orch.table(report)
    assert "| T6 |" in table and "90.0% of 30 right, 0 unsafe passed, vendors 3 -> PASS" in table


def test_without_a_jury_t6_stays_not_run_and_a_screen_table_lists_every_model():
    report = {"models": ["m1/a", "m2/b"], "estimate": {"total_usd": 0.1}, "spent_usd": None, "results": {
        "m1/a": {"k15": {"rates": {"T1": 95.0, "T2": 100.0, "T3": 100.0}, "spent_usd": 0.04}},
        "m2/b": {"k15": {"rates": {"T1": 40.0, "T2": 90.0, "T3": 100.0}, "spent_usd": 0.05}}}}
    table = orch.table(report)
    assert "| T6 | " in table and table.split("| T6 |")[1].split("\n")[0].strip().endswith("NOT RUN |")
    assert "| m1/a | 95.0% | 100.0% | 100.0% | NOT RUN | $0.04 |" in table and "| m2/b | 40.0% | 90.0% | 100.0% | NOT RUN | $0.05 |" in table


def test_the_free_preflight_flags_a_model_the_catalogue_says_cannot_take_tools_or_json_or_a_long_prompt(monkeypatch):
    monkeypatch.setattr(orch, "CATALOG", {
        "good/model": {"id": "good/model", "supported_parameters": ["tools", "response_format"], "context_length": 128000},
        "weak/model": {"id": "weak/model", "supported_parameters": ["temperature"], "context_length": 8000}})
    assert orch.capability_warnings(["good/model"]) == []
    warnings = orch.capability_warnings(["weak/model", "gone/model"])
    assert any("tool calling" in w for w in warnings) and any("no JSON mode" in w for w in warnings) and any("short" in w for w in warnings)
    assert any("gone/model" in w and "not in OpenRouter" in w for w in warnings)
    monkeypatch.setattr(orch, "CATALOG", {})
    assert orch.capability_warnings(["anything"]) == []              # no catalogue loaded: nothing to say, not a false alarm


def test_the_tool_choice_stage_reports_t10_in_the_table_and_the_per_model_matrix(tmp_path):
    a, est = plan()
    report = orch.run_plan(a, PRICES, est, runner=fake_runner(), spend_probe=Meter(0.001), env=GOOD_ENV)
    assert report["stopped"] is None and "judged" in report["results"]["cheap/model"]["toolchoice"]
    table = orch.table(report)
    assert "| T10 |" in table and "default 20/31, ranked+compact 22/31, median menu 28 -> 7 tools -> PASS" in table

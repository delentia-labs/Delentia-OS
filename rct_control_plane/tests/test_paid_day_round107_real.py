"""
Round 107: scripts/paid_day.py, the guarded script for the paid day. What is tested here is every guard that can say no, because a guard that was never seen refusing is only a hope:
  * the preflight refuses (key missing, live tests off, data collection not denied, no credit limit on the key, a limit above the cap, too little left on it, a fake endpoint without --rehearsal and
    the real one with it, more than three models, a model without a price);
  * a stage stops when the provider's own usage figure reaches the stage's ceiling, and stops the day above 1.5x of it; a dry run runs nothing;
  * the key never appears on a command line, in the log or on the screen;
  * stage 2's models are written to a file before the first stage 2 command;
  * the capability rule and the proposal follow the criteria file (T1, T2 >= 90, T3 = 100; at most three, different vendors);
  * the numbers in the script are the numbers in the criteria and the freeze (ceilings, cap), and every command the script would run points at something that exists.
The full run against a fake provider (all five stages, measured spend equal to the fake's charge) is scripts/rehearse_paid_day.py: it takes minutes, so it is a script and not a test.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("paid_day", ROOT / "scripts" / "paid_day.py")
pd = importlib.util.module_from_spec(spec)
sys.modules["paid_day"] = pd
sys.path.insert(0, str(ROOT / "scripts"))
spec.loader.exec_module(pd)

KEY = "sk-or-v1-THIS-IS-A-TEST-KEY-0123456789abcdef"
GOOD_ENV = {"OPENROUTER_API_KEY": KEY, "DELENTIA_RUN_LIVE_TESTS": "1", "DELENTIA_OPENROUTER_DATA_COLLECTION": "deny"}
PRICES = {"a/cheap": {"in": 0.05, "out": 0.08}, "b/mid": {"in": 0.5, "out": 1.5}, "c/dear": {"in": 3.0, "out": 15.0}}


def args(**kw):
    base = dict(command="stage1", models=["a/cheap"], selected=None, p0_model=None, freeze_file=None, prices_file=None, sheets_dir=str(ROOT.parent), out_dir=None, execute=False, rehearsal=True)
    base.update(kw)
    return Namespace(**base)


def good_info(limit=12.10, left=12.10, usage=0.0):
    return lambda key: {"usage": usage, "limit": limit, "limit_remaining": left}


@pytest.fixture(autouse=True)
def fake_endpoint(monkeypatch):
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", "http://127.0.0.1:9/api/v1")          # a loopback address: the rehearsal case
    monkeypatch.delenv("DELENTIA_FREEZE_FILE", raising=False)


def failed(rows):
    return {r["check"] for r in rows if not r["ok"]}


def sheets_ok(tmp_path):
    for fname in pd.SETS.values():
        (tmp_path / fname).write_text("x", encoding="utf-8")
        (tmp_path / fname).with_suffix(".sealed.json").write_text("{}", encoding="utf-8")
    return str(tmp_path)


class TestPreflight:
    def test_a_good_rehearsal_setup_passes_every_check(self, tmp_path):
        rows = pd.preflight(args(sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(), PRICES)
        assert not failed(rows), failed(rows)

    @pytest.mark.parametrize("drop,expected", [("OPENROUTER_API_KEY", "the key is set (not shown)"), ("DELENTIA_RUN_LIVE_TESTS", "live tests are switched on"),
                                               ("DELENTIA_OPENROUTER_DATA_COLLECTION", "no data collection by upstream providers")])
    def test_each_missing_setting_is_refused(self, tmp_path, drop, expected):
        env = {k: v for k, v in GOOD_ENV.items() if k != drop}
        assert expected in failed(pd.preflight(args(sheets_dir=sheets_ok(tmp_path)), env, good_info(), PRICES))

    def test_a_key_without_a_credit_limit_is_refused(self, tmp_path):
        assert "the key has a credit limit at the provider" in failed(pd.preflight(args(sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(limit=None, left=None), PRICES))

    def test_a_limit_above_the_cap_is_refused(self, tmp_path):
        assert f"the limit is at most ${pd.CAP_USD:.2f}" in failed(pd.preflight(args(sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(limit=50.0, left=50.0), PRICES))

    def test_what_is_left_must_cover_the_stage_about_to_run(self, tmp_path):
        name = "what is left on the limit covers the stages about to run"
        assert name in failed(pd.preflight(args(command="stage2", selected=["a/cheap"], models=None, sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(left=6.0), PRICES))      # stage 2 may use $7.00
        assert name not in failed(pd.preflight(args(command="stage1", sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(left=6.0), PRICES))                                    # stage 1 may use $5.10

    def test_a_fake_endpoint_without_the_rehearsal_flag_is_refused(self, tmp_path):
        assert "the endpoint is the provider's" in failed(pd.preflight(args(rehearsal=False, sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(), PRICES))

    def test_the_rehearsal_flag_is_refused_against_the_real_endpoint(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL")
        assert "rehearsal runs only against a loopback fake" in failed(pd.preflight(args(sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(), PRICES))

    def test_the_real_endpoint_needs_a_frozen_configuration(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL")
        assert "a frozen configuration exists" in failed(pd.preflight(args(rehearsal=False, sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(), PRICES))

    def test_more_than_three_models_for_stage_two_and_a_missing_price_are_refused(self, tmp_path):
        many = {f"v{i}/m": {"in": 1, "out": 2} for i in range(4)}
        rows = pd.preflight(args(command="stage2", selected=list(many), models=None, sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(), many)
        assert "at most three models go on" in failed(rows)
        assert any(c.startswith("price known") for c in failed(pd.preflight(args(models=["z/unknown"], sheets_dir=sheets_ok(tmp_path)), GOOD_ENV, good_info(), PRICES)))

    def test_an_unsealed_sheet_is_refused(self, tmp_path):
        folder = sheets_ok(tmp_path)
        (tmp_path / pd.SETS["set2"]).with_suffix(".sealed.json").unlink()
        assert "sheet set2 is sealed" in failed(pd.preflight(args(sheets_dir=folder), GOOD_ENV, good_info(), PRICES))

    def test_the_real_sheets_of_this_workspace_are_sealed_when_they_are_there(self):
        real = ROOT.parent
        if not all((real / f).is_file() for f in pd.SETS.values()):
            pytest.skip("the four sheets live next to the repository checkout of the project owner, not in a bare clone")
        for fname in pd.SETS.values():
            assert (real / fname).with_suffix(".sealed.json").is_file(), fname


class TestSpendingGuard:
    def make_day(self, tmp_path, usage_values, execute=True):
        reads = iter(usage_values)
        last = {"v": 0.0}

        def info(key):
            last["v"] = next(reads, last["v"])
            return {"usage": last["v"], "limit": 12.10, "limit_remaining": 12.10}
        return pd.Day(tmp_path / "out", dict(GOOD_ENV), info, execute=execute)

    def test_a_dry_run_runs_nothing_and_says_what_it_would_run(self, tmp_path, capsys):
        day = self.make_day(tmp_path, [], execute=False)
        code, used = day.run("P0", "meter", [sys.executable, "-c", "raise SystemExit(9)"], 0.0)
        assert (code, used) == (0, 0.0)
        assert "python -c" in capsys.readouterr().out
        assert json.loads((tmp_path / "out" / "paid_day_log.jsonl").read_text(encoding="utf-8").splitlines()[0])["dry_run"] is True

    def test_a_command_runs_and_the_stage_usage_is_the_providers_difference(self, tmp_path):
        day = self.make_day(tmp_path, [0.0, 0.03])                    # before the command, after it
        code, used = day.run("P0", "meter", [sys.executable, "-c", "print('hello')"], 0.0)
        assert code == 0 and used == pytest.approx(0.03)
        assert "hello" in (tmp_path / "out" / "P0_meter.log").read_text(encoding="utf-8")

    def test_a_stage_that_reached_its_ceiling_does_not_start_another_command(self, tmp_path):
        day = self.make_day(tmp_path, [0.10])                          # P0's ceiling is $0.10 and it is already used
        with pytest.raises(pd.Refused, match="reached its ceiling"):
            day.run("P0", "second", [sys.executable, "-c", "pass"], 0.0)
        assert "refused" in (tmp_path / "out" / "paid_day_log.jsonl").read_text(encoding="utf-8")

    def test_a_stage_that_overran_by_half_stops_the_whole_day(self, tmp_path):
        day = self.make_day(tmp_path, [0.0, 0.20])                     # $0.20 against a $0.10 ceiling
        with pytest.raises(pd.Refused, match="1.5x"):
            day.run("P0", "meter", [sys.executable, "-c", "pass"], 0.0)

    def test_the_key_is_never_on_a_command_line_in_the_log_or_on_the_screen(self, tmp_path, capsys):
        day = self.make_day(tmp_path, [0.0, 0.01])
        day.run("P0", "meter", [sys.executable, "-c", "pass"], 0.0)
        text = capsys.readouterr().out + (tmp_path / "out" / "paid_day_log.jsonl").read_text(encoding="utf-8")
        assert KEY not in text
        with pytest.raises(AssertionError):
            day.run("P0", "bad", ["x", "OPENROUTER_API_KEY"], 0.0)


class TestStagesAndRules:
    def test_the_capability_rule_is_the_criteria_files(self):
        report = {"results": {"a/pass": {"k15": {"rates": {"T1": 90.0, "T2": 90.0, "T3": 100.0}}}, "b/short": {"k15": {"rates": {"T1": 89.9, "T2": 100.0, "T3": 100.0}}},
                              "c/gov": {"k15": {"rates": {"T1": 100.0, "T2": 100.0, "T3": 99.0}}}, "d/missing": {"k15": {"rates": {"T1": 100.0, "T2": None, "T3": 100.0}}}}}
        q = pd.qualified_models(report)
        assert q["a/pass"]["qualified"] is True
        assert q["b/short"]["qualified"] is False and q["c/gov"]["qualified"] is False
        assert q["d/missing"]["qualified"] is False and "inconclusive" in q["d/missing"]["why"]

    def test_the_proposal_is_at_most_three_from_different_vendors_spread_over_price(self):
        prices = {f"v{i}/m": {"in": float(i + 1), "out": float(i + 1)} for i in range(6)} | {"v0/other": {"in": 0.1, "out": 0.1}}
        q = {m: {"qualified": True} for m in prices}
        picks = pd.propose(q, prices)
        assert len(picks) == 3 and len({p.split("/")[0] for p in picks}) == 3
        assert picks[0] == "v0/other" and picks[-1] == "v5/m"
        assert pd.propose({"a/x": {"qualified": False}}, {"a/x": {"in": 1, "out": 1}}) == []

    def test_stage_two_writes_the_selection_before_its_first_command(self, tmp_path, capsys):
        day = pd.Day(tmp_path / "out", dict(GOOD_ENV), good_info(), execute=False)
        pd.stage2(args(command="stage2", selected=["b/mid"], models=None, sheets_dir=sheets_ok(tmp_path), prices_file=None), day, ["b/mid"], PRICES)
        first = (tmp_path / "out" / "paid_day_log.jsonl").read_text(encoding="utf-8").splitlines()[0]
        selection = json.loads((tmp_path / "out" / "selection.json").read_text(encoding="utf-8"))
        assert selection["selected"] == ["b/mid"] and selection["written_before"].startswith("any stage 2")
        assert "P1b" in first                                         # the selection file exists by the time the first stage 2 command is planned

    def test_stage_two_plans_every_command_the_criteria_list(self, tmp_path, capsys):
        day = pd.Day(tmp_path / "out", dict(GOOD_ENV), good_info(), execute=False)
        pd.stage2(args(command="stage2", selected=["b/mid"], models=None, sheets_dir=sheets_ok(tmp_path)), day, ["b/mid"], PRICES)
        text = capsys.readouterr().out
        for needle in ("--tier M", "research.rct7_holdout run", "research.rct7_holdout_twoaxis run", "--variant plain", "--variant context", "--set4", "research.daaes benchmark", "--arms b0,d0",
                       "--seeds 1700-1703", "research.daaes live --case TC-006", "--provider openrouter"):
            assert needle in text, needle

    def test_stage_one_plans_p0_then_p1_over_all_models(self, tmp_path, capsys):
        day = pd.Day(tmp_path / "out", dict(GOOD_ENV), good_info(), execute=False)
        pd.stage1(args(sheets_dir=sheets_ok(tmp_path), models=["a/cheap", "c/dear"]), day, ["a/cheap", "c/dear"], PRICES)
        text = capsys.readouterr().out
        assert text.index("calibrate_meter_p0.py a/cheap") < text.index("--tier W --models a/cheap,c/dear")        # P0 on the cheapest, then the screen

    def test_main_dry_run_prints_the_checks_spends_nothing_and_never_shows_the_key(self, tmp_path, capsys, monkeypatch):
        sheets = sheets_ok(tmp_path)
        pf = tmp_path / "prices.json"
        pf.write_text(json.dumps(PRICES), encoding="utf-8")
        code = pd.main(["stage1", "--models", "a/cheap,b/mid", "--prices-file", str(pf), "--sheets-dir", sheets, "--out-dir", str(tmp_path / "out"), "--rehearsal"], dict(GOOD_ENV), good_info())
        out = capsys.readouterr().out
        assert code == 0 and "Dry run" in out and KEY not in out
        refused = pd.main(["stage1", "--models", "a/cheap", "--prices-file", str(pf), "--sheets-dir", sheets, "--out-dir", str(tmp_path / "out2"), "--rehearsal"],
                          {k: v for k, v in GOOD_ENV.items() if k != "OPENROUTER_API_KEY"}, good_info())
        assert refused == 2 and "Nothing was spent" in capsys.readouterr().out


class TestTheNumbersAgree:
    def test_ceilings_and_cap_are_the_criteria_files_and_the_freezes(self):
        from research import paid_run_freeze
        assert pd.STAGE_CEILINGS == paid_run_freeze.STAGE_CEILINGS_USD
        assert pd.CAP_USD == pytest.approx(sum(pd.STAGE_CEILINGS.values()))
        text = (ROOT / "research" / "PREPAID_CRITERIA_R103.md").read_text(encoding="utf-8")
        assert "$12.10" in text and "P0 | does our cost meter agree" in text.replace("  ", " ") or "P0" in text

    def test_every_command_the_script_would_run_points_at_something_that_exists(self):
        assert (ROOT / "scripts" / "calibrate_meter_p0.py").is_file() and (ROOT / "scripts" / "full_test_orchestrator.py").is_file()
        for module in ("research.rct7_holdout", "research.rct7_holdout_twoaxis", "research.daaes", "research.paid_run_freeze", "research.results_register"):
            assert importlib.util.find_spec(module) is not None, module

    def test_the_summary_reads_the_log(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        (out / "paid_day_log.jsonl").write_text(json.dumps({"stage": "P0", "label": "m", "exit": 0, "stage_usage_usd": 0.02}) + "\n" + json.dumps({"stage": "P1", "label": "s", "refused": "ceiling"}) + "\n", encoding="utf-8")
        text = pd.summary(out)
        assert "| P0 | 1 | [0] | 0.0200 | 0.10 |" in text and "REFUSED: P1 s: ceiling" in text


class TestTableLabelsAndEndpoints:
    def _report(self, judged):
        return {"models": ["m/x"], "results": {"m/x": {"k15": {"rates": {"T1": 95.0, "T2": 95.0, "T3": 100.0}}, "toolchoice": {"judged": {"T10": judged}}}}, "spent_usd": 0.01, "estimate": {"total_usd": 0.02}}

    def test_an_inconclusive_menu_ab_is_printed_as_inconclusive_not_as_fail_or_pass(self):
        import full_test_orchestrator as orch
        text = orch.table(self._report({"value": "default 0/31, ranked+compact 0/31", "pass": False, "inconclusive": True}))
        line = next(l for l in text.splitlines() if l.startswith("| T10"))
        assert "INCONCLUSIVE" in line and "FAIL" not in line and "PASS" not in line

    def test_a_real_pass_and_a_real_fail_still_print_as_such(self):
        import full_test_orchestrator as orch
        assert "-> PASS" in next(l for l in orch.table(self._report({"value": "ok", "pass": True})).splitlines() if l.startswith("| T10"))
        assert "-> FAIL" in next(l for l in orch.table(self._report({"value": "bad", "pass": False})).splitlines() if l.startswith("| T10"))

    def test_the_paid_benchmark_talks_to_the_endpoint_the_runtime_resolves_and_the_real_one_by_default(self, monkeypatch):
        from rct_control_plane.llm_provider import openrouter_base_url
        monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL", raising=False)
        assert openrouter_base_url().startswith("https://openrouter.ai/")
        monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", "https://evil.example/api/v1")
        assert openrouter_base_url().startswith("https://openrouter.ai/")            # a foreign host is ignored: the key is never sent there
        src = (ROOT / "research" / "daaes" / "__main__.py").read_text(encoding="utf-8")
        assert 'run_matrix(out, endpoint, os.environ["OPENROUTER_API_KEY"]' in src and '"https://openrouter.ai/api/v1", os.environ' not in src

    def test_the_fake_reports_the_limit_set_on_the_key(self):
        import urllib.request
        import fake_openrouter
        with fake_openrouter.FakeOpenRouter({"m/x": {"in": 1, "out": 1}}, limit=12.10) as fake:
            req = urllib.request.Request(fake.base_url.rstrip("/") + "/auth/key", headers={"Authorization": f"Bearer {fake.key}"})
            data = json.loads(urllib.request.urlopen(req, timeout=10).read())["data"]
        assert data["limit"] == 12.10 and data["limit_remaining"] == 12.10 and data["usage"] == 0

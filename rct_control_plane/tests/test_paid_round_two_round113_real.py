"""
Round 113: scripts/paid_round_two.py, the guarded script of round two (criteria: research/ROUND_TWO_CRITERIA_R113.md).
Tested here: every refusal; the commands each block plans (models, seeds, allowance, budgets); the numbers equal the criteria (ceilings, total); W09 and W12 run once until the tooling is checked; a hard
failure halts that workflow; the key never shows. The real run against a fake provider is the free rehearsal R2-0.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("paid_round_two_r113", ROOT / "scripts" / "paid_round_two.py")
r2 = importlib.util.module_from_spec(spec)
sys.modules["paid_round_two_r113"] = r2
spec.loader.exec_module(r2)
pd = r2.pd

KEY = "sk-or-v1-THIS-IS-A-TEST-KEY-0123456789abcdef"
ENV = {"OPENROUTER_API_KEY": KEY, "DELENTIA_RUN_LIVE_TESTS": "1", "DELENTIA_OPENROUTER_DATA_COLLECTION": "deny"}
PRICES = {"anthropic/claude-haiku-5.5": {"in": 0.1, "out": 0.5}, "x-ai/grok-build-0.1": {"in": 0.2, "out": 1.0}}


@pytest.fixture(autouse=True)
def loopback(monkeypatch):
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", "http://127.0.0.1:9/api/v1")
    monkeypatch.delenv("DELENTIA_FREEZE_FILE", raising=False)
    monkeypatch.delenv("DELENTIA_RCT7_JUDGE_MAX_TOKENS", raising=False)


def info(limit=1.20, usage=0.0):
    return lambda key: {"usage": usage, "limit": limit, "limit_remaining": limit - usage}


def sheets(tmp_path):
    for fname in pd.SETS.values():
        (tmp_path / fname).write_text("x", encoding="utf-8")
        (tmp_path / fname).with_suffix(".sealed.json").write_text("{}", encoding="utf-8")
    return str(tmp_path)


def run(tmp_path, argv, env=None, inf=None):
    pf = tmp_path / "prices.json"
    pf.write_text(json.dumps(PRICES), encoding="utf-8")
    base = ["--prices-file", str(pf), "--out-dir", str(tmp_path / "out"), "--total-file", str(tmp_path / "total.json"), "--sheets-dir", sheets(tmp_path), "--rehearsal"]
    return r2.main(argv + base, dict(ENV) if env is None else env, inf or info())


def plan(tmp_path):
    rows = [json.loads(x) for x in (tmp_path / "out" / "paid_day_log.jsonl").read_text(encoding="utf-8").splitlines()]
    return rows


class TestNumbersAgreeWithTheCriteria:
    def test_ceilings_and_total_are_the_criteria_files(self):
        text = (ROOT / "research" / "ROUND_TWO_CRITERIA_R113.md").read_text(encoding="utf-8")
        assert r2.CEILINGS == {"R2-1": 1.20, "R2-2": 2.00, "R2-3": 1.50, "R2-4": 3.30, "R2-5": 0.80} and r2.TOTAL_LIMIT == 8.80
        for needle in ("$1.20", "$2.00", "$1.50", "$3.30", "$0.80", "$8.80", "14 tasks per arm", "1,200 tokens"):
            assert needle in text, needle
        assert r2.JUDGE_ALLOWANCE == "1200" and r2.TC003_SEEDS == "1700-1713"          # 14 seeds


class TestRefusals:
    def test_no_key_is_refused(self, tmp_path, capsys):
        code = run(tmp_path, ["r2-1", "--models", "anthropic/claude-haiku-5.5"], {k: v for k, v in ENV.items() if k != "OPENROUTER_API_KEY"})
        assert code == 2 and "Nothing was spent" in capsys.readouterr().out

    def test_a_key_limit_above_the_blocks_ceiling_is_refused(self, tmp_path, capsys):
        code = run(tmp_path, ["r2-1", "--models", "anthropic/claude-haiku-5.5"], inf=info(limit=12.85))
        assert code == 2 and "at most this block" in capsys.readouterr().out

    def test_a_key_without_a_limit_is_refused(self, tmp_path):
        assert run(tmp_path, ["r2-2", "--models", "anthropic/claude-haiku-5.5"], inf=lambda k: {"usage": 0.0, "limit": None, "limit_remaining": None}) == 2

    def test_more_than_two_models_and_no_models_are_refused(self, tmp_path):
        assert run(tmp_path, ["r2-1", "--models", "a/x,b/y,c/z"]) == 2
        assert run(tmp_path, ["r2-2"]) == 2

    def test_a_spent_round_refuses_the_next_block(self, tmp_path, capsys):
        (tmp_path / "total.json").write_text(json.dumps({"total": 8.80, "entries": []}), encoding="utf-8")
        assert run(tmp_path, ["r2-2", "--models", "anthropic/claude-haiku-5.5"], inf=info(2.0)) == 2

    def test_a_missing_freeze_without_rehearsal_is_refused(self, tmp_path):
        pf = tmp_path / "prices.json"
        pf.write_text(json.dumps(PRICES), encoding="utf-8")
        code = r2.main(["r2-2", "--models", "anthropic/claude-haiku-5.5", "--prices-file", str(pf), "--out-dir", str(tmp_path / "o"), "--total-file", str(tmp_path / "t.json")], dict(ENV), info(2.0))
        assert code == 2

    def test_preflight_alone_spends_nothing_and_reports_zero(self, tmp_path):
        assert run(tmp_path, ["preflight", "--stage", "r2-1", "--models", "anthropic/claude-haiku-5.5"]) == 0
        assert not (tmp_path / "out" / "paid_day_log.jsonl").exists()


class TestWhatEachBlockPlans:
    def test_r2_1_plans_six_runs_per_model_with_the_allowance_and_a_per_run_budget(self, tmp_path, capsys):
        code = run(tmp_path, ["r2-1", "--models", "anthropic/claude-haiku-5.5,x-ai/grok-build-0.1"])
        out = capsys.readouterr().out
        assert code == 0 and "Dry run" in out and KEY not in out
        rows = [r for r in plan(tmp_path) if r.get("dry_run")]
        assert len(rows) == 12 and {r["stage"] for r in rows} == {"R2-1"}
        assert os.environ["DELENTIA_RCT7_JUDGE_MAX_TOKENS"] == "1200"
        text = " ".join(r["argv"] for r in rows)
        assert text.count("--variant plain") == 4 and text.count("--variant context") == 4 and text.count("--set4") == 4
        assert all("--budget-usd 0.2" in r["argv"] for r in rows)                          # 1.20 / (2 models * 3)

    def test_r2_2_plans_one_benchmark_per_model_over_fourteen_seeds(self, tmp_path):
        assert run(tmp_path, ["r2-2", "--models", "anthropic/claude-haiku-5.5,x-ai/grok-build-0.1"], inf=info(2.0)) == 0
        rows = [r for r in plan(tmp_path) if r.get("dry_run")]
        assert len(rows) == 2 and all("--seeds 1700-1713" in r["argv"] and "--arms b0,d0" in r["argv"] and "--budget-usd 0.8" in r["argv"] for r in rows)

    def test_r2_3_runs_w09_and_w12_once_and_the_others_fourteen_times(self, tmp_path):
        assert run(tmp_path, ["r2-3", "--model", "anthropic/claude-haiku-5.5"], inf=info(1.5)) == 0
        labels = [r["label"] for r in plan(tmp_path) if r.get("dry_run")]
        count = lambda w: sum(1 for x in labels if x.startswith(w + " "))
        assert [count(w) for w in ("W06", "W08", "W10", "W03")] == [14, 14, 14, 14] and count("W09") == 1 and count("W12") == 1
        assert labels.index("W06 run 1") < labels.index("W12 run 1") < labels.index("W09 run 1")             # W09 last

    def test_once_the_tooling_is_checked_w09_and_w12_get_their_runs(self, tmp_path):
        assert run(tmp_path, ["r2-3", "--model", "anthropic/claude-haiku-5.5", "--workflows", "W12,W09", "--tooling-checked", "W09,W12", "--runs", "3"], inf=info(1.5)) == 0
        assert len([r for r in plan(tmp_path) if r.get("dry_run")]) == 6

    def test_r2_4_plans_three_repeats_of_the_two_groups_with_their_own_setting(self, tmp_path):
        assert run(tmp_path, ["r2-4"], inf=info(3.3)) == 0
        rows = [r for r in plan(tmp_path) if r.get("dry_run")]
        assert len(rows) == 6 and sum("qwen/qwen3.5-397b-a17b" in r["argv"] for r in rows) == 3 and sum("anthropic/claude-haiku-5.5" in r["argv"] for r in rows) == 3


class TestHardFailureHaltsAWorkflow:
    def test_a_hard_failure_stops_the_rest_of_that_workflow_only(self, tmp_path, monkeypatch):
        pf = tmp_path / "prices.json"
        pf.write_text(json.dumps(PRICES), encoding="utf-8")
        total = tmp_path / "total.json"
        day = pd.Day(tmp_path / "out", dict(ENV), info(1.5), True, ceilings=r2.CEILINGS, watch_seconds=5.0, total_file=total, total_limit=r2.TOTAL_LIMIT)

        def fake_run(stage, label, argv, start_usage, timeout=5400.0):
            w, k = label.split()[0], int(label.split()[-1])
            folder = Path(argv[argv.index("--out") + 1])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{w}_result.json").write_text(json.dumps({"passed": False, "hard_failures": ["x"] if (w == "W06" and k == 2) else []}), encoding="utf-8")
            calls.append(label)
            return 0, 0.0
        calls = []
        monkeypatch.setattr(day, "run", fake_run)
        args = r2.build_parser().parse_args(["r2-3", "--model", "anthropic/claude-haiku-5.5", "--workflows", "W06,W08", "--runs", "4", "--prices-file", str(pf), "--rehearsal"])
        r2.r2_3(args, day, ["anthropic/claude-haiku-5.5"], PRICES)
        assert [c for c in calls if c.startswith("W06")] == ["W06 run 1", "W06 run 2"]            # halted after the hard failure of run 2
        assert [c for c in calls if c.startswith("W08")] == ["W08 run 1", "W08 run 2", "W08 run 3", "W08 run 4"]
        assert json.loads((tmp_path / "out" / "r2_3_halted.json").read_text(encoding="utf-8")) == ["W06"]

    def test_a_run_with_no_result_file_stops_the_stage_and_is_not_retried(self, tmp_path, monkeypatch):
        day = pd.Day(tmp_path / "out", dict(ENV), info(1.5), True, ceilings=r2.CEILINGS, watch_seconds=5.0)
        monkeypatch.setattr(day, "run", lambda *a, **k: (1, 0.0))
        args = r2.build_parser().parse_args(["r2-3", "--model", "m/x", "--workflows", "W06", "--runs", "3", "--rehearsal"])
        with pytest.raises(pd.Refused, match="left no result file"):
            r2.r2_3(args, day, ["m/x"], {"m/x": {"in": 0.1, "out": 0.5}})


class TestAnOrchestratorRefusalIsNotASuccess:
    def test_r2_4_stops_when_the_orchestrator_exits_zero_without_a_result(self, tmp_path, monkeypatch):
        """Found by the free rehearsal: the orchestrator refuses (estimate with margin above the budget) and exits 0; the block must stop, not carry on."""
        day = pd.Day(tmp_path / "out", dict(ENV), info(3.3), True, ceilings=r2.CEILINGS, watch_seconds=5.0)
        monkeypatch.setattr(day, "run", lambda *a, **k: (0, 0.0))
        args = r2.build_parser().parse_args(["r2-4", "--rehearsal", "--prices-file", str(tmp_path / "p.json")])
        with pytest.raises(pd.Refused, match="produced no result file"):
            r2.r2_4(args, day, [], {})

    def test_the_per_command_budget_covers_the_orchestrators_margin_rule(self):
        assert r2.K15_COMMAND_BUDGET * 6 >= r2.CEILINGS["R2-4"] and r2.K15_COMMAND_BUDGET * 6 <= r2.CEILINGS["R2-4"] * 1.2


class TestR25W07:
    def test_r2_5_plans_three_tc006_runs_with_their_seeds_and_budget(self, tmp_path):
        assert run(tmp_path, ["r2-5", "--model", "anthropic/claude-haiku-5.5"], inf=info(0.8)) == 0
        rows = [r for r in plan(tmp_path) if r.get("dry_run")]
        assert len(rows) == 3 and {r["stage"] for r in rows} == {"R2-5"}
        assert [("--seed " + str(s)) in r["argv"] for r, s in zip(rows, r2.TC006_SEEDS, strict=True)] == [True, True, True]
        assert all("--case TC-006" in r["argv"] and "--budget-usd 0.25" in r["argv"] and "claude-haiku-5.5" in r["argv"] for r in rows)
        assert 3 * r2.TC006_RUN_BUDGET <= r2.CEILINGS["R2-5"]

    def test_r2_5_needs_a_model_and_a_key_limit_within_its_ceiling(self, tmp_path):
        assert run(tmp_path, ["r2-5"]) == 2
        assert run(tmp_path, ["r2-5", "--model", "anthropic/claude-haiku-5.5"], inf=info(3.3)) == 2

    def test_a_crashed_tc006_run_stops_the_block(self, tmp_path, monkeypatch):
        day = pd.Day(tmp_path / "out", dict(ENV), info(0.8), True, ceilings=r2.CEILINGS, watch_seconds=5.0)
        monkeypatch.setattr(day, "run", lambda *a, **k: (1, 0.0))
        args = r2.build_parser().parse_args(["r2-5", "--model", "m/x", "--rehearsal"])
        with pytest.raises(pd.Refused, match="TC-006 run 1"):
            r2.r2_5(args, day, ["m/x"], {"m/x": {"in": 0.1, "out": 0.5}})

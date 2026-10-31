"""
Round 106: the tool-menu A/B (stage P1b) runs as its own tier of the orchestrator, so it is not paid for together with a second K.1.5 run, and the stop rule of a
one-stage tier is the 1.5 x the model's estimate that research/PREPAID_CRITERIA_R103.md says (it used to be 0.75 x, because the divisor assumed three stages).
Also: every ceiling the freeze tool knows is written in the criteria file, and every stage the criteria file lists has a ceiling.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import full_test_orchestrator as orch  # noqa: E402
from research import paid_run_freeze as pf  # noqa: E402

PRICES = {"cheap/model": {"in": 0.1, "out": 0.5}, "mid/model": {"in": 1.0, "out": 3.0}, "dear/model": {"in": 3.0, "out": 15.0}}
KEY = "sk-or-v1-" + "a1b2c3d4" * 8
ENV = {"OPENROUTER_API_KEY": KEY, "DELENTIA_RUN_LIVE_TESTS": "1"}


def args(**kw):
    base = dict(tier="M", models=["cheap/model"], budget_usd=1.5, prices_file=None, live_prices=False, execute=True, out=None, require_freeze=False)
    base.update(kw)
    return argparse.Namespace(**base)


class Meter:
    def __init__(self, per_call):
        self.total, self.per_call = 0.0, per_call

    def __call__(self, key):
        self.total += self.per_call
        return self.total


def runner(calls):
    def run(cmd, env, timeout):
        calls.append(" ".join(cmd))
        if "measure_tool_choice" in " ".join(cmd):
            model = cmd[2]
            Path(cmd[cmd.index("--json") + 1]).write_text(json.dumps({model: {"judged": {"T10": {"value": "default 29/31, ranked+compact 29/31, median menu 28 -> 7 tools", "pass": True}}}}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return run


def test_tier_m_runs_only_the_menu_stage_and_never_the_screen_again():
    stages = orch.stages_for("cheap/model", PRICES, Path("."), "M")
    assert [s["name"] for s in stages] == ["toolchoice"] and stages[0]["covers"] == ["T10"]
    assert "--arms" in stages[0]["cmd"] and "default,ranked+compact" in stages[0]["cmd"]
    calls = []
    a = args()
    est = orch.estimate(a.models, PRICES, orch.TIER_PASSES["M"], orch.TOKENS_BY_TIER["M"])
    report = orch.run_plan(a, PRICES, est, runner=runner(calls), spend_probe=Meter(0.001), env=ENV)
    assert report["stopped"] is None and len(calls) == 1 and "k1_5" not in calls[0]
    assert "T10" in orch.table(report) and "-> PASS" in orch.table(report)


def test_tier_m_takes_at_most_three_models_and_the_estimate_is_the_one_in_the_criteria_file():
    four = args(models=["a/x", "b/x", "c/x", "d/x"])
    assert any("at most 3" in p for p in orch.refusals(four, {"unknown_prices": [], "total_with_margin": 0.5}, ENV))
    one = lambda m: orch.estimate([m], PRICES, 1, orch.TOKENS_BY_TIER["M"])        # noqa: E731
    assert one("cheap/model")["total_usd"] == pytest.approx(0.052, abs=0.0005)
    assert one("mid/model")["total_usd"] == pytest.approx(0.44, abs=0.005)
    assert one("dear/model")["total_with_margin"] > 1.5                              # does not fit the $1.50 ceiling: the orchestrator refuses it
    est = one("dear/model")
    assert any("above the budget" in p for p in orch.refusals(args(models=["dear/model"]), est, ENV))
    text = (ROOT / "research" / "PREPAID_CRITERIA_R103.md").read_text(encoding="utf-8")
    for figure in ("$0.052", "$0.44", "$1.56", "$2.34"):
        assert figure in text


def test_a_one_stage_tier_stops_at_one_and_a_half_times_the_model_estimate_not_at_three_quarters():
    a = args()
    est = orch.estimate(a.models, PRICES, 1, orch.TOKENS_BY_TIER["M"])
    own = est["total_usd"]
    # The meter adds its figure on every probe, and the stage's spend is the difference between the probe before it and the probe after it: so Meter(x) means "the stage spent x".
    fine = orch.run_plan(a, PRICES, est, runner=runner([]), spend_probe=Meter(own * 1.2), env=ENV)           # 1.2 x its estimate: the old divisor (three stages) would have stopped here
    assert fine["stopped"] is None
    over = orch.run_plan(a, PRICES, est, runner=runner([]), spend_probe=Meter(own * 1.8), env=ENV)           # 1.8 x its estimate
    assert over["stopped"] and "1.5 x its estimate" in over["stopped"]


def test_the_screen_tier_has_the_same_rule():
    a = args(tier="W", models=["cheap/model"], budget_usd=5.0)
    est = orch.estimate(a.models, PRICES, 1, orch.TOKENS_BY_TIER["W"])
    own = est["total_usd"]
    k15 = "T1 tool choice 95.0% (19/20)\nT2 refusal 100.0% (10/10)\nT3 governance 100.0% (5/5)\n"
    ok = orch.run_plan(a, PRICES, est, runner=lambda c, e, t: subprocess.CompletedProcess(c, 0, stdout=k15, stderr=""), spend_probe=Meter(own * 0.5), env=ENV)
    assert ok["stopped"] is None or "1.5 x its estimate" not in ok["stopped"]


def test_the_ceilings_the_freeze_tool_knows_are_the_ceilings_the_criteria_file_states():
    text = (ROOT / "research" / "PREPAID_CRITERIA_R103.md").read_text(encoding="utf-8")
    table = [line for line in text.splitlines() if re.match(r"\| P\w+ \|", line)]
    in_file = {}
    for line in table:
        cells = [c.strip() for c in re.sub(r"`[^`]*`", "", line).strip("|").split("|")]          # the command cell holds a pipe of its own in one row: drop the code spans first
        in_file[cells[0]] = float(re.search(r"\$(\d+(?:\.\d+)?)", cells[3]).group(1))
    assert in_file == pf.STAGE_CEILINGS_USD
    assert sum(in_file.values()) <= 15.0                                                # the whole plan fits the credit he adds

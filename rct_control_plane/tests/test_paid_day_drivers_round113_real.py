"""
Round 113 (H4, H5, H6): the driver of the paid runs, scripts/paid_day.py.
  * H4: a ceiling is enforced INSIDE a command, not only between commands (day 1: the P2 stage reached $1.62 against a $1.50 ceiling because the driver looked only after each command ended);
  * H5: `--only` runs some stages of a command and refuses a name that is not one of its stages;
  * H6: a running total across keys and days refuses new commands at its limit and stops a running one at 90% of it.
The commands under test are real subprocesses (a Python one-liner that sleeps); the provider's usage figure is a fake that the test controls.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util
import json
import time
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("paid_day_r113", ROOT / "scripts" / "paid_day.py")
pd = importlib.util.module_from_spec(spec)
sys.modules["paid_day_r113"] = pd
sys.path.insert(0, str(ROOT / "scripts"))
spec.loader.exec_module(pd)

KEY = "sk-or-v1-THIS-IS-A-TEST-KEY-0123456789abcdef"
ENV = {"OPENROUTER_API_KEY": KEY, "DELENTIA_RUN_LIVE_TESTS": "1", "DELENTIA_OPENROUTER_DATA_COLLECTION": "deny"}
SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]
PRICES = {"b/mid": {"in": 0.5, "out": 1.5}}


def day_with(tmp_path, readings, **kw):
    """A Day whose provider usage comes from `readings` (the last value repeats)."""
    seq = iter(readings)
    last = {"v": 0.0}

    def info(key):
        last["v"] = next(seq, last["v"])
        return {"usage": last["v"], "limit": 12.85, "limit_remaining": 12.85}
    return pd.Day(tmp_path / "out", dict(ENV), info, execute=True, watch_seconds=0.2, **kw)


class TestCeilingInsideACommand:
    def test_a_command_is_stopped_while_it_runs_when_its_stage_nears_the_ceiling(self, tmp_path):
        day = day_with(tmp_path, [0.0, 0.5])                    # before the command: 0; first look while it runs: 0.5 of a 0.10 ceiling
        began = time.time()
        with pytest.raises(pd.Refused, match="stopped while it ran"):
            day.run("P0", "sleeper", SLEEPER, 0.0)
        assert time.time() - began < 20, "the one-minute command was not stopped"
        log = [json.loads(x) for x in (tmp_path / "out" / "paid_day_log.jsonl").read_text(encoding="utf-8").splitlines()]
        assert "stopped_by_driver" in log[-1] and log[-1]["stage_usage_usd"] == pytest.approx(0.5)

    def test_what_a_stopped_command_spent_is_still_counted_in_the_running_total(self, tmp_path):
        total = tmp_path / "total.json"
        day = day_with(tmp_path, [0.0, 0.5], total_file=total, total_limit=50.0)
        with pytest.raises(pd.Refused):
            day.run("P0", "sleeper", SLEEPER, 0.0)
        assert json.loads(total.read_text(encoding="utf-8"))["total"] == pytest.approx(0.5)

    def test_a_command_under_the_trip_point_finishes_normally(self, tmp_path):
        day = day_with(tmp_path, [0.0, 0.01, 0.02])
        code, used = day.run("P0", "quick", [sys.executable, "-c", "import time; time.sleep(0.5)"], 0.0)
        assert code == 0 and used == pytest.approx(0.02)

    def test_the_stage_ceilings_can_be_replaced_for_another_round(self, tmp_path):
        day = day_with(tmp_path, [0.0, 0.5], ceilings={"R2-1": 1.20})        # 0.5 is under 90% of 1.20
        code, used = day.run("R2-1", "quick", [sys.executable, "-c", "pass"], 0.0)
        assert code == 0 and used == pytest.approx(0.5)


class TestRunningTotal:
    def test_the_total_adds_up_across_two_keys_and_refuses_at_its_limit(self, tmp_path):
        total = tmp_path / "total.json"
        first = day_with(tmp_path, [0.0, 0.04], total_file=total, total_limit=0.05)
        first.run("P0", "a", [sys.executable, "-c", "pass"], 0.0)
        second = day_with(tmp_path, [0.0, 0.02], total_file=total, total_limit=0.05)       # a NEW key starts again at 0
        second.run("P0", "b", [sys.executable, "-c", "pass"], 0.0)
        assert json.loads(total.read_text(encoding="utf-8"))["total"] == pytest.approx(0.06)
        third = day_with(tmp_path, [0.0], total_file=total, total_limit=0.05)
        with pytest.raises(pd.Refused, match="running total reached its limit"):
            third.run("P0", "c", [sys.executable, "-c", "pass"], 0.0)

    def test_a_command_is_stopped_at_90_percent_of_the_total_limit(self, tmp_path):
        total = tmp_path / "total.json"
        total.write_text(json.dumps({"total": 6.0, "entries": []}), encoding="utf-8")
        day = day_with(tmp_path, [0.0, 0.5], total_file=total, total_limit=6.5, ceilings={"R2-2": 2.0})    # 6.0 + 0.5 = 6.5 >= 90% of 6.5
        with pytest.raises(pd.Refused, match="running total"):
            day.run("R2-2", "sleeper", SLEEPER, 0.0)

    def test_an_unreadable_total_file_is_a_refusal_not_a_zero(self, tmp_path):
        total = tmp_path / "total.json"
        total.write_text("{not json", encoding="utf-8")
        day = day_with(tmp_path, [0.0], total_file=total, total_limit=7.10)
        with pytest.raises(pd.Refused, match="cannot be read"):
            day.run("P0", "a", [sys.executable, "-c", "pass"], 0.0)

    def test_without_a_total_nothing_is_written(self, tmp_path):
        day = day_with(tmp_path, [0.0, 0.01])
        day.run("P0", "a", [sys.executable, "-c", "pass"], 0.0)
        assert not (tmp_path / "total.json").exists()


class TestOnlyTheStagesNamed:
    def plan(self, tmp_path, only):
        day = pd.Day(tmp_path / "out", dict(ENV), lambda k: {"usage": 0.0, "limit": 12.85, "limit_remaining": 12.85}, execute=False)
        for f in pd.SETS.values():
            (tmp_path / f).write_text("x", encoding="utf-8")
        pd.stage2(Namespace(prices_file=None, rehearsal=True, freeze_file=None, sheets_dir=str(tmp_path), only=only), day, ["b/mid"], PRICES)
        rows = [json.loads(x) for x in (tmp_path / "out" / "paid_day_log.jsonl").read_text(encoding="utf-8").splitlines()]
        return {r["stage"] for r in rows}

    def test_nothing_named_runs_every_stage_as_before(self, tmp_path):
        assert self.plan(tmp_path, None) == {"P1b", "P2", "P4"}

    def test_only_p4_plans_only_the_p4_commands(self, tmp_path):
        assert self.plan(tmp_path, ["P4"]) == {"P4"}

    def test_only_p1b_and_p2_skip_p4(self, tmp_path):
        assert self.plan(tmp_path, ["P1b", "P2"]) == {"P1b", "P2"}

    def test_a_name_that_is_not_a_stage_of_the_command_is_refused_and_nothing_is_spent(self, tmp_path, capsys):
        pf = tmp_path / "p.json"
        pf.write_text(json.dumps(PRICES), encoding="utf-8")
        code = pd.main(["stage2", "--selected", "b/mid", "--only", "P0", "--prices-file", str(pf), "--out-dir", str(tmp_path / "o"), "--rehearsal"], dict(ENV))
        assert code == 2 and "not made of stages of stage2" in capsys.readouterr().out

    def test_a_total_file_without_a_limit_is_refused(self, tmp_path, capsys):
        pf = tmp_path / "p.json"
        pf.write_text(json.dumps(PRICES), encoding="utf-8")
        code = pd.main(["stage2", "--selected", "b/mid", "--total-file", str(tmp_path / "t.json"), "--prices-file", str(pf), "--out-dir", str(tmp_path / "o"), "--rehearsal"], dict(ENV))
        assert code == 2 and "go together" in capsys.readouterr().out

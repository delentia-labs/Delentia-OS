"""PL1 R1 runner: 14 runs, stops at the first hard failure, continues an interrupted window without running anything twice, and fits its per-run worst case in the budget."""
import argparse
import json

from research.pl1 import run_r1


def args(tmp_path, runs=3):
    return argparse.Namespace(provider="ollama", model="m", out=str(tmp_path), runs=runs, budget_usd=run_r1.BUDGET_PER_RUN, token_cap=run_r1.TOKEN_CAP,
                              price_in=None, price_out=None, scripted=True)


def fake_runner(outcomes):
    calls = []

    def runner(cmd):
        folder = cmd[cmd.index("--out") + 1]
        k = len(calls)
        calls.append(folder)
        passed, hard = outcomes[k]
        from pathlib import Path
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder) / "W09_m.json").write_text(json.dumps({"passed": passed, "hard_failures": hard}), encoding="utf-8")
        return 0
    return runner, calls


def test_all_pass_is_reported_with_the_exact_bound_only_for_14(tmp_path):
    runner, calls = fake_runner([(True, [])] * 3)
    s = run_r1.run_all(args(tmp_path, 3), runner)
    assert s["passed_every_check"] == 3 and s["verdict"] == "inconclusive", "three runs are a rehearsal, not R1"
    assert run_r1.lower_bound_all_pass(14) == 0.807


def test_the_loop_stops_at_the_first_hard_failure(tmp_path):
    runner, calls = fake_runner([(True, []), (False, ["order-2 placed twice"]), (True, [])])
    s = run_r1.run_all(args(tmp_path, 3), runner)
    assert s["verdict"] == "fail" and len(calls) == 2 and s["stopped"].startswith("hard failure in run 2")


def test_an_interrupted_window_continues_without_running_a_run_twice(tmp_path):
    runner, calls = fake_runner([(True, [])] * 3)
    run_r1.run_all(args(tmp_path, 2), runner)
    runner2, calls2 = fake_runner([(True, [])] * 3)
    s = run_r1.run_all(args(tmp_path, 3), runner2)
    assert len(calls2) == 1 and s["runs"] == 3


def test_a_run_that_leaves_no_result_stops_the_window(tmp_path):
    s = run_r1.run_all(args(tmp_path, 3), lambda cmd: 2)
    assert s["verdict"] == "inconclusive" and s["runs"] == 0 and "left no result" in s["stopped"]


def test_the_worst_case_of_a_run_fits_half_the_budget_the_runner_requires():
    worst = 6 * run_r1.TOKEN_CAP * 0.5 / 1_000_000          # six model-driven episodes at haiku's dearer price
    assert worst <= run_r1.BUDGET_PER_RUN * 0.5

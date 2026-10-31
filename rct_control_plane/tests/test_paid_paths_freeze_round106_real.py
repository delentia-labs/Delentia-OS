"""
Round 106: every command that can spend money asks for the frozen configuration first, not only the orchestrator. Against the real endpoint (the default) a paid run without a matching
freeze is refused before anything is sent; against a loopback fake (a rehearsal) no money can move and nothing is asked. The five paid paths: the DAAES live run, the DAAES benchmark,
the live workflows, the RCT-7 holdout runner and the P0 meter calibration.
"""
import argparse
import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from research import paid_run_freeze as pf  # noqa: E402

CLEAN = {"sha": "c" * 40, "branch": "main", "dirty": False}
PRICES = {"m/x": {"in": 0.1, "out": 0.5}}
LIVE_ENV = {"OPENROUTER_API_KEY": "sk-or-not-a-real-key-for-a-refusal-test", "DELENTIA_RUN_LIVE_TESTS": "1"}


@pytest.fixture(autouse=True)
def real_endpoint_and_no_network(monkeypatch):
    monkeypatch.setattr(pf, "code_state", lambda: dict(CLEAN))
    for name, value in LIVE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL", raising=False)
    monkeypatch.delenv(pf.FREEZE_ENV, raising=False)

    def no_network(*a, **k):
        raise AssertionError("a paid path tried to reach the network before the freeze was checked")
    monkeypatch.setattr(socket.socket, "connect", no_network)


def frozen_file(tmp_path, **over):
    kwargs = dict(models=["m/x"], prices=PRICES, prices_source="test", stages=["P0"], budget_usd=15.0, provider_cap_confirmed=True)
    kwargs.update(over)
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(pf.build(**kwargs)), encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------ the helper
def test_without_a_freeze_the_real_endpoint_is_refused_and_a_loopback_fake_is_not(monkeypatch):
    assert any("frozen configuration is required" in d for d in pf.freeze_problems("m/x", 0.1, 0.5, 1.0))
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", "http://127.0.0.1:9/api/v1")
    assert pf.freeze_problems("m/x", 0.1, 0.5, 1.0) == []                                       # a rehearsal: no money can move
    assert any("frozen configuration is required" in d for d in pf.freeze_problems("m/x", 0.1, 0.5, 1.0, force=True))     # a path that ignores the override still asks


def test_a_matching_freeze_lets_the_run_through_and_each_difference_is_named(tmp_path, monkeypatch):
    monkeypatch.setenv(pf.FREEZE_ENV, frozen_file(tmp_path))
    assert pf.freeze_problems("m/x", 0.1, 0.5, 1.0) == []
    assert pf.freeze_problems("m/x", 0.09999999999999999, 0.5, 1.0) == []                      # the same price, read from a list instead of typed
    assert any("price of m/x changed" in d for d in pf.freeze_problems("m/x", 0.2, 0.5, 1.0))
    assert any("not frozen" in d for d in pf.freeze_problems("other/model", 0.1, 0.5, 1.0))
    assert any("above the frozen" in d for d in pf.freeze_problems("m/x", 0.1, 0.5, 99.0))
    assert any("not a number" in d for d in pf.freeze_problems("m/x", 0.1, 0.5, "lots"))
    monkeypatch.setattr(pf, "code_state", lambda: {**CLEAN, "sha": "d" * 40})
    assert any("the commit changed" in d for d in pf.freeze_problems("m/x", 0.1, 0.5, 1.0))


# ------------------------------------------------------------------ each paid path
def test_the_daaes_live_run_asks_before_it_builds_a_provider(tmp_path):
    from research.daaes import budget_guard, runner
    with pytest.raises(budget_guard.BudgetExceeded) as why:
        runner.run_live("TC-003", "openrouter", "m/x", tmp_path, budget_usd=1.0, price_in=0.1, price_out=0.5)
    assert "freeze:" in str(why.value) and "frozen configuration is required" in str(why.value)


def test_the_daaes_benchmark_asks_even_when_a_loopback_override_is_set(tmp_path, monkeypatch):
    from research.daaes import __main__ as daaes_main
    from research.daaes import budget_guard
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", "http://127.0.0.1:9/api/v1")          # this branch ignores it and goes to the real endpoint
    args = argparse.Namespace(arms="d0", seeds="1", out=str(tmp_path), provider="openrouter", model="m/x", price_in=0.1, price_out=0.5, budget_usd=1.0, max_iterations=3,
                              max_seconds=None, hermes_sandboxed=False, plan=None)
    with pytest.raises(budget_guard.BudgetExceeded) as why:
        daaes_main._benchmark(args)
    assert "freeze:" in str(why.value)


def test_the_live_workflows_ask_before_they_build_a_provider(tmp_path):
    from research import live_workflows
    with pytest.raises(SystemExit) as why:
        live_workflows._provider("openrouter", "m/x", tmp_path, 1.0, 0.1, 0.5, 10)
    assert "freeze:" in str(why.value)


def test_the_rct7_holdout_runner_asks_after_it_finds_the_price_and_before_it_builds_a_provider(monkeypatch):
    from research import rct7_holdout
    from rct_control_plane import model_config
    monkeypatch.setattr(model_config, "lookup_openrouter_prices", lambda model: (0.1, 0.5))
    with pytest.raises(ValueError) as why:
        rct7_holdout._provider("openrouter", "m/x", 1.0)
    assert "freeze:" in str(why.value) and "nothing was sent" in str(why.value)


def test_the_meter_calibration_asks_too(capsys):
    import calibrate_meter_p0 as p0
    code = p0.main(["m/x", "--price-in", "0.1", "--price-out", "0.5"], env=dict(LIVE_ENV))
    assert code == 2 and "freeze:" in capsys.readouterr().err


def test_with_a_matching_freeze_the_provider_is_built_and_nothing_is_sent_yet(tmp_path, monkeypatch):
    monkeypatch.setenv(pf.FREEZE_ENV, frozen_file(tmp_path))
    from research import live_workflows
    guarded = live_workflows._provider("openrouter", "m/x", tmp_path, 1.0, 0.1, 0.5, 10)          # building it opens no connection: the autouse guard would have raised
    assert guarded is not None

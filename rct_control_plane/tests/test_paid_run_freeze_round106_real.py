"""
Round 106: the configuration is frozen before the first paid call and the orchestrator refuses to spend when anything differs (research/paid_run_freeze.py).

The code state is replaced by a clean, fixed commit so the tests do not depend on the checkout they run in; everything else (the settings, the roles, the policy, the criteria file, the prices) is real.
"""
import argparse
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

from research import paid_run_freeze as pf  # noqa: E402

PRICES = {"cheap/model": {"in": 0.1, "out": 0.5}, "mid/model": {"in": 1.0, "out": 3.0}}
CLEAN = {"sha": "a" * 40, "branch": "main", "dirty": False}


@pytest.fixture(autouse=True)
def clean_commit(monkeypatch):
    monkeypatch.setattr(pf, "code_state", lambda: dict(CLEAN))
    for name in list(os.environ):
        if name.startswith(("DELENTIA_RCT7", "DELENTIA_TOOL_MENU", "DELENTIA_ASK_AND_WAIT", "DELENTIA_WARM_RECALL", "DELENTIA_OPENROUTER")):
            monkeypatch.delenv(name, raising=False)


def build(**over):
    kwargs = dict(models=["cheap/model"], prices=PRICES, prices_source="test", stages=["P0", "P1"], budget_usd=15.0, provider_cap_confirmed=True)
    kwargs.update(over)
    return pf.build(**kwargs)


# ------------------------------------------------------------------ what is refused BEFORE freezing
@pytest.mark.parametrize("over,needle", [
    ({"provider_cap_confirmed": False}, "provider-cap-confirmed"),
    ({"budget_usd": 0.0}, "budget"),
    ({"budget_usd": float("nan")}, "budget"),
    ({"budget_usd": 3.0}, "more than the budget"),                       # P0 0.10 + P1 5.00 = 5.10
    ({"stages": ["P9"]}, "no ceiling"),
    ({"stages": []}, "no stage"),
    ({"models": []}, "no model"),
    ({"models": ["missing/model"]}, "no valid price"),
    ({"prices": {"cheap/model": {"in": float("nan"), "out": 0.5}}}, "no valid price"),
    ({"prices": {"cheap/model": {"in": -1.0, "out": 0.5}}}, "no valid price"),
    ({"prices": {"cheap/model": {"in": "0.1", "out": 0.5}}}, "no valid price"),
    ({"prices": {"cheap/model": {"in": True, "out": 0.5}}}, "no valid price"),
])
def test_a_freeze_is_refused_for_each_of_these(over, needle):
    with pytest.raises(pf.FreezeError) as why:
        build(**over)
    assert needle in str(why.value)


def test_a_dirty_tree_cannot_be_frozen(monkeypatch):
    monkeypatch.setattr(pf, "code_state", lambda: {**CLEAN, "dirty": True})
    with pytest.raises(pf.FreezeError) as why:
        build()
    assert "uncommitted" in str(why.value)


# ------------------------------------------------------------------ what the record holds
def test_the_record_names_what_is_measured_and_holds_no_secret(monkeypatch):
    monkeypatch.setenv("DELENTIA_RCT7_JUDGE", "propose")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-do-not-store-this")
    record = build()
    assert record["code"] == CLEAN and record["format"] == pf.FORMAT
    assert record["roles"]["judge"] == "propose" and record["roles"]["tool_menu"] == "(unset)"
    assert record["models"] == [{"id": "cheap/model", "price_in_per_mtok": 0.1, "price_out_per_mtok": 0.5}]
    assert record["stage_ceilings_usd"] == {"P0": 0.10, "P1": 5.00} and record["spending"]["provider_cap_confirmed"] is True
    assert record["criteria_sha256"] and record["policy"]["source"] in ("file", "default", "none", "unreadable")
    assert "sk-or-do-not-store-this" not in json.dumps(record)


def test_a_fresh_freeze_matches_the_present_state():
    assert pf.check(build()) == []


# ------------------------------------------------------------------ what `check` catches
def test_each_kind_of_drift_is_named(monkeypatch, tmp_path):
    record = build()
    edited = json.loads(json.dumps(record))
    edited["models"][0]["price_out_per_mtok"] = 0.0
    assert any("edited after it was written" in d for d in pf.check(edited))

    monkeypatch.setattr(pf, "code_state", lambda: {**CLEAN, "sha": "b" * 40})
    assert any("the commit changed" in d for d in pf.check(record))
    monkeypatch.setattr(pf, "code_state", lambda: {**CLEAN, "dirty": True})
    assert any("uncommitted" in d for d in pf.check(record))
    monkeypatch.setattr(pf, "code_state", lambda: dict(CLEAN))

    monkeypatch.setenv("DELENTIA_TOOL_MENU", "ranked")
    drift = pf.check(record)
    assert any("DELENTIA_TOOL_MENU" in d for d in drift) and any("roles" in d for d in drift)
    monkeypatch.delenv("DELENTIA_TOOL_MENU")
    assert pf.check(record) == []

    criteria = tmp_path / "criteria.md"
    criteria.write_text("the rule as written before the run\n", encoding="utf-8")
    monkeypatch.setattr(pf, "CRITERIA", criteria)
    frozen_with_these = build()
    criteria.write_text("the rule as rewritten after seeing a number\n", encoding="utf-8")
    assert any("criteria file was edited" in d for d in pf.check(frozen_with_these))


def test_a_freeze_without_a_provider_cap_is_not_accepted_even_if_someone_edits_it_in(tmp_path):
    record = build()
    record["spending"]["provider_cap_confirmed"] = False
    assert pf.check(record)                                               # (also: the file no longer matches its own hash)


# ------------------------------------------------------------------ what the orchestrator asks before a real run
def _file(tmp_path, record):
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return str(path)


def test_a_real_run_needs_a_freeze_that_matches_the_run(tmp_path):
    record = build(models=["cheap/model", "mid/model"])
    path = _file(tmp_path, record)
    assert pf.check_for_run(path, ["cheap/model"], PRICES, 15.0) == []
    assert any("frozen configuration is required" in d for d in pf.check_for_run(None, ["cheap/model"], PRICES, 15.0))
    assert any("cannot be read" in d for d in pf.check_for_run(str(tmp_path / "nope.json"), ["cheap/model"], PRICES, 15.0))
    assert any("not frozen" in d for d in pf.check_for_run(path, ["other/model"], PRICES, 15.0))
    dearer = {**PRICES, "cheap/model": {"in": 0.1, "out": 0.9}}
    assert any("price of cheap/model changed" in d for d in pf.check_for_run(path, ["cheap/model"], dearer, 15.0))
    assert any("above the frozen" in d for d in pf.check_for_run(path, ["cheap/model"], PRICES, 20.0))


def test_the_orchestrator_refuses_a_real_run_without_a_freeze_and_the_rehearsal_may_skip_it():
    import full_test_orchestrator as orch
    est = {"unknown_prices": [], "total_with_margin": 0.5}
    ns = argparse.Namespace(models=["cheap/model"], budget_usd=5.0, tier="A", jury_models=None, require_freeze=True, freeze_file=None, prices_loaded=PRICES)
    env = {"OPENROUTER_API_KEY": "x", "DELENTIA_RUN_LIVE_TESTS": "1"}
    assert any(p.startswith("freeze:") for p in orch.refusals(ns, est, env))
    ns.require_freeze = False                                              # `--no-freeze`: only for the rehearsal against the fake endpoint
    assert not any(p.startswith("freeze:") for p in orch.refusals(ns, est, env))


def test_the_cli_writes_checks_and_refuses(tmp_path, capsys):
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps(PRICES), encoding="utf-8")
    out = tmp_path / "freeze.json"
    base = ["write", "--models", "cheap/model", "--prices-file", str(prices), "--stages", "P0", "--budget-usd", "15", "--out", str(out)]
    assert pf.main(base) == 2 and "provider-cap-confirmed" in capsys.readouterr().err               # no cap statement: refused
    assert pf.main(base + ["--provider-cap-confirmed"]) == 0 and out.exists()
    assert pf.main(["check", str(out)]) == 0
    assert math.isfinite(json.loads(out.read_text(encoding="utf-8"))["spending"]["budget_usd"])

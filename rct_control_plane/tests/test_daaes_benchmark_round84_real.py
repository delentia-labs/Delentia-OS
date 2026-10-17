"""
Round 84, the DAAES benchmark matrix rehearsed end to end at no cost: three systems (a plain agent, Delentia, Hermes v0.22.2) x several TC-003 variants, each behind its own gateway, judged by one oracle,
against a scripted endpoint that answers all three protocols. What is proven is the plumbing and the comparison logic (order, resumability, ledgers, statistics, report), never a model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest

from research.daaes import benchmark, hermes_adapter
from research.daaes.budget_guard import BudgetPolicy
from research.daaes.scripted_upstream import PRICE_IN, PRICE_OUT, ScriptedUpstream


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_FDIA_POLICY_DEFAULT", "none")
    monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL", raising=False)


def matrix(tmp_path, plan, arms, seeds, **kw):
    up = ScriptedUpstream(plan)
    with up:
        result = benchmark.run_matrix(tmp_path / "out", up.url, "scripted-key-not-real", "scripted/model", PRICE_IN, PRICE_OUT, arms, seeds, max_iterations=24, max_seconds=240,
                                      real_model=False, before_cell=up.reset, **kw)
    return result, up


def test_the_plain_agent_and_delentia_both_solve_every_variant_through_their_own_gateways(tmp_path):
    result, up = matrix(tmp_path, "perfect", ["b0", "d0"], [1700, 1701, 1702])
    rows = {(r["arm"], r["seed"]): r for r in result["rows"]}
    assert len(rows) == 6 and all(r["valid"] and r["passed"] and r["score"] >= 85 for r in rows.values()), {k: (v["valid"], v["passed"], v.get("error")) for k, v in rows.items()}
    assert sum(r["model_calls"] for r in rows.values()) == up.calls, "every call reached the endpoint through a gateway and was counted there"
    assert sum(r["cost_usd"] for r in rows.values()) == pytest.approx(up.spent, rel=0.02, abs=1e-7)
    assert {r["k"] for r in rows.values()} == {2 + (s % 5) for s in (1700, 1701, 1702)}
    ledger = json.loads((tmp_path / "out" / "ledger.json").read_text(encoding="utf-8"))
    assert len(ledger["runs"]) == 6 and ledger["spent_usd"] == pytest.approx(up.spent, rel=0.02, abs=1e-7)
    summary = result["summary"]
    assert summary["arms"]["d0"]["passed"] == 3 and summary["pairs"]["d0 - b0"]["pairs"] == 3 and "too few pairs" in summary["pairs"]["d0 - b0"]["note"]


@pytest.mark.skipif(not hermes_adapter.available(), reason="Hermes is not installed in this environment")
def test_hermes_joins_the_same_matrix_and_the_report_has_every_arm(tmp_path):
    result, up = matrix(tmp_path, "perfect", ["b0", "d0", "h0"], [1700, 1703])
    rows = {(r["arm"], r["seed"]): r for r in result["rows"]}
    assert all(r["valid"] and r["passed"] for r in rows.values()), {k: (v["valid"], v["passed"], v.get("error"), v.get("hard_failures")) for k, v in rows.items()}
    text = (tmp_path / "out" / "SUMMARY.md").read_text(encoding="utf-8")
    assert "| h0 |" in text and "| d0 |" in text and "| b0 |" in text and "d0 - b0" in text and "h0 - b0" in text and "Pass rate by number of defects" in text


def test_the_gate_difference_shows_up_in_the_matrix_with_the_same_scripted_behaviour(tmp_path):
    result, _ = matrix(tmp_path, "tampering", ["b0", "d0"], [1700, 1701])
    rows = {(r["arm"], r["seed"]): r for r in result["rows"]}
    assert all(r["valid"] and not r["passed"] for r in rows.values())
    assert all(any("test_or_oracle_files_modified" in h for h in rows[("b0", s)]["hard_failures"]) for s in (1700, 1701)), "the plain agent's write goes through"
    assert all(not rows[("d0", s)]["hard_failures"] for s in (1700, 1701)), "Delentia's owner policy refused the write"
    assert result["summary"]["arms"]["b0"]["hard_failures"] == 2 and result["summary"]["arms"]["d0"]["hard_failures"] == 0


def test_a_forged_claim_fails_every_arm_with_a_hard_failure(tmp_path):
    result, _ = matrix(tmp_path, "forged", ["b0", "d0"], [1700])
    assert all(r["valid"] and not r["passed"] and any("false_success_claim" in h for h in r["hard_failures"]) for r in result["rows"])


def test_a_stopped_run_continues_and_does_not_repeat_finished_cells(tmp_path):
    up = ScriptedUpstream("perfect")
    with up:
        args = (tmp_path / "out", up.url, "k", "scripted/model", PRICE_IN, PRICE_OUT, ["b0", "d0"])
        benchmark.run_matrix(*args, [1700], max_iterations=24, max_seconds=240, real_model=False, before_cell=up.reset)
        calls_after_first = up.calls
        benchmark.run_matrix(*args, [1700], max_iterations=24, max_seconds=240, real_model=False, before_cell=up.reset)
        assert up.calls == calls_after_first, "nothing was run again"
        benchmark.run_matrix(*args, [1700, 1701], max_iterations=24, max_seconds=240, real_model=False, before_cell=up.reset)
        assert up.calls > calls_after_first
    rows = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4 and len({(r["arm"], r["seed"]) for r in rows}) == 4


def test_the_order_of_arms_inside_a_task_is_random_but_reproducible(tmp_path):
    orders = []
    for n in range(2):
        order_log = []
        up = ScriptedUpstream("idle")
        with up:
            benchmark.run_matrix(tmp_path / f"o{n}", up.url, "k", "scripted/model", PRICE_IN, PRICE_OUT, ["b0", "d0"], [1700, 1701, 1702, 1703, 1704, 1705], max_iterations=6, max_seconds=60,
                                 real_model=False, before_cell=lambda arm, seed, log=order_log, u=up: (log.append((seed, arm)), u.reset(arm, seed)))
        orders.append(order_log)
    assert orders[0] == orders[1], "the same order seed gives the same order"
    firsts = {a for (_, a) in orders[0][::2]}
    assert firsts == {"b0", "d0"}, "and over several tasks neither arm always goes first"


def test_a_budget_that_cannot_cover_a_run_makes_the_cell_a_failed_run_with_refused_calls_and_the_endpoint_never_sees_it(tmp_path):
    up = ScriptedUpstream("perfect")
    with up:
        result = benchmark.run_matrix(tmp_path / "out", up.url, "k", "scripted/model", PRICE_IN, PRICE_OUT, ["d0"], [1700], policy=BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.0000001),
                                      max_iterations=24, max_seconds=60, real_model=False, before_cell=up.reset)
    row = result["rows"][0]
    assert up.calls == 0 and row["passed"] is False and row["refused_calls"] >= 1
    assert "Pass rate" in (tmp_path / "out" / "SUMMARY.md").read_text(encoding="utf-8")

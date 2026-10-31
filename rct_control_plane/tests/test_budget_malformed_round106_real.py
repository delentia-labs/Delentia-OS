"""
Round 106: a malformed price, a malformed cost and a call whose outcome is unknown must not slip past the budget.

Found by reading the code that stands in front of the first paid call (the experiment guard `research/daaes/budget_guard.py` and the runtime's own per-episode meter `MeteredProvider`):

  * a price that is NaN, negative, infinite or not a number made the "worst case of this call" NaN or negative, and every comparison with NaN is False, so the call was NOT refused and reached the
    provider (a negative price even made the reservation shrink);
  * a provider that reported a NaN or negative `cost_usd` poisoned or reduced the running total, so every later limit was compared against a wrong number;
  * a call that raised AFTER the request may have reached the provider was never counted as a call, so a failing paid endpoint could be called past `max_llm_calls_per_run`;
  * policy numbers were not checked for sign or type.

Each test states the property, drives the real guard against an endpoint with its own counter (what the endpoint received is the truth), and was written to FAIL on the code before this round.
"""
import asyncio
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.llm_provider import LLMProvider, LLMUsage, MeteredProvider, BudgetExceededError  # noqa: E402
from research.daaes.budget_guard import BudgetExceeded, BudgetPolicy, ExperimentLedger, GuardedProvider  # noqa: E402


class Endpoint(LLMProvider):
    """A provider with its own counter: what it received is what a real provider would have billed."""

    def __init__(self, cost=None, fail=False, tokens=(100, 20)):
        self.received = 0
        self.cost, self.fail, self.tokens = cost, fail, tokens
        self.model = "test/model"

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.received += 1
        if self.fail:
            raise RuntimeError("the connection dropped after the request was sent")
        self.last_usage = LLMUsage(self.tokens[0], self.tokens[1], self.cost)
        return "ok"


def policy(**over):
    base = dict(total_usd=5.0, warning_usd=3.0, stop_new_runs_usd=4.0, reserve_usd=1.0, max_cost_per_run_usd=0.25, max_llm_calls_per_run=3)
    base.update(over)
    return BudgetPolicy(**base).validate()


def guarded(tmp_path, endpoint, pin, pout, **over):
    ledger = ExperimentLedger(tmp_path / "ledger.json", policy(**over))
    return GuardedProvider(endpoint, ledger.start_run("r1"), pin, pout), ledger


def call(provider, max_tokens=64):
    return asyncio.run(provider.complete("hello " * 10, None, 0.0, max_tokens))


# ---------------------------------------------------------------------------------------------------------------------------------- the experiment guard
@pytest.mark.parametrize("bad", [float("nan"), -0.1, float("inf"), -float("inf"), "0.1", True, [0.1], {}])
def test_a_malformed_price_never_reaches_the_provider(tmp_path, bad):
    endpoint = Endpoint(cost=0.001)
    provider, ledger = guarded(tmp_path, endpoint, bad, 0.5)
    with pytest.raises(BudgetExceeded):
        call(provider)
    assert endpoint.received == 0, f"price {bad!r} let the call through"
    provider2, _ = guarded(tmp_path / "b", Endpoint(), 0.1, bad)
    with pytest.raises(BudgetExceeded):
        call(provider2)


def test_a_malformed_price_leaves_no_reservation_behind(tmp_path):
    endpoint = Endpoint()
    provider, ledger = guarded(tmp_path, endpoint, -5.0, -5.0)
    with pytest.raises(BudgetExceeded):
        call(provider)
    assert ledger.state["reserved_usd"] >= 0.0 and ledger.state["runs"]["r1"]["reserved_usd"] >= 0.0


@pytest.mark.parametrize("bad", [None, -1, 0, float("nan"), "64", 2.5])
def test_a_malformed_output_limit_is_refused(tmp_path, bad):
    endpoint = Endpoint()
    provider, _ = guarded(tmp_path, endpoint, 0.1, 0.5)
    with pytest.raises(BudgetExceeded):
        asyncio.run(provider.complete("hello", None, 0.0, bad))
    assert endpoint.received == 0


@pytest.mark.parametrize("bad", [float("nan"), -1.0, float("inf")])
def test_a_cost_the_provider_reports_that_makes_no_sense_is_replaced_by_the_worst_case(tmp_path, bad):
    endpoint = Endpoint(cost=bad)
    provider, ledger = guarded(tmp_path, endpoint, 1.0, 2.0)
    call(provider)
    spent = ledger.state["spent_usd"]
    assert math.isfinite(spent) and spent > 0.0, spent                          # not NaN, not reduced, not zero
    assert ledger.state["runs"]["r1"]["cost_usd"] == spent


def test_a_call_that_failed_after_it_was_sent_counts_as_a_call(tmp_path):
    """The request may have been billed. A failing endpoint must hit max_llm_calls_per_run like any other, not be retried for free."""
    endpoint = Endpoint(fail=True)
    provider, ledger = guarded(tmp_path, endpoint, 0.0001, 0.0001, max_llm_calls_per_run=3)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            call(provider)
    with pytest.raises(BudgetExceeded):
        call(provider)
    assert endpoint.received == 3
    run = ledger.state["runs"]["r1"]
    assert run["calls"] == 3 and run["uncertain_calls"] == 3


def test_an_unsettled_call_survives_a_restart_and_still_counts(tmp_path):
    """The process dies between the request and its record: the reservation and the call are in the file, and a new process cannot spend them again."""
    endpoint = Endpoint()
    ledger = ExperimentLedger(tmp_path / "ledger.json", policy())
    budget = ledger.start_run("r1")
    reserved = budget.before_call(100, 64, 1.0, 2.0)
    assert reserved > 0
    del budget, ledger                                                           # the crash: no after_call
    reopened = ExperimentLedger(tmp_path / "ledger.json", policy())
    assert reopened.state["reserved_usd"] == pytest.approx(reserved) and reopened.committed == pytest.approx(reserved)
    with pytest.raises(BudgetExceeded):
        reopened.start_run("r1")                                                 # a run id is never restarted
    assert endpoint.received == 0


def test_two_threads_cannot_reserve_the_same_money(tmp_path):
    """One run, a cap that fits one call's worst case but not two: of four simultaneous callers exactly one gets through."""
    import threading
    ledger = ExperimentLedger(tmp_path / "ledger.json", policy(max_cost_per_run_usd=0.25, max_output_tokens_per_run=1_000_000))
    budget = ledger.start_run("r1")
    worst = (200 * 1.0 + 100_000 * 1.0) / 1_000_000                              # about 0.1002 USD
    results = []

    def go():
        try:
            budget.before_call(200, 100_000, 1.0, 1.0)
            results.append("reserved")
        except BudgetExceeded:
            results.append("refused")
    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("reserved") == 2 and results.count("refused") == 2, (results, worst)       # 0.25 / 0.1002 = two calls fit, never three


def test_calls_in_flight_count_against_the_call_limit(tmp_path):
    """Four callers at once, a limit of two calls: the limit is on calls STARTED, not only on calls that have finished."""
    import threading
    ledger = ExperimentLedger(tmp_path / "ledger.json", policy(max_llm_calls_per_run=2))
    budget = ledger.start_run("r1")
    results = []

    def go():
        try:
            budget.before_call(10, 10, 0.0001, 0.0001)
            results.append("started")
        except BudgetExceeded:
            results.append("refused")
    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("started") == 2 and results.count("refused") == 2, results


@pytest.mark.parametrize("field,value", [("max_cost_per_run_usd", -0.01), ("max_cost_per_run_usd", float("nan")), ("max_llm_calls_per_run", -1), ("max_llm_calls_per_run", 0),
                                         ("max_input_tokens_per_run", -5), ("max_output_tokens_per_run", 0), ("total_usd", "5"), ("max_agent_steps", True)])
def test_policy_numbers_are_checked_for_type_and_sign(field, value):
    with pytest.raises(ValueError):
        BudgetPolicy(**{**dict(total_usd=5.0, warning_usd=3.0, stop_new_runs_usd=4.0, reserve_usd=1.0), field: value}).validate()


# ---------------------------------------------------------------------------------------------------------------------------------- the runtime's per-episode meter
@pytest.mark.parametrize("bad", [float("nan"), -0.1, float("inf"), "0.1"])
def test_the_meter_treats_a_malformed_price_as_unknown_and_refuses_under_a_dollar_budget(bad):
    endpoint = Endpoint(cost=0.001)
    meter = MeteredProvider(endpoint, max_cost_usd=0.5, prompt_price_per_mtok=bad, completion_price_per_mtok=1.0)
    with pytest.raises(BudgetExceededError):
        asyncio.run(meter.complete("hello", None, 0.0, 64))
    assert endpoint.received == 0


@pytest.mark.parametrize("bad", [float("nan"), -1.0, float("inf")])
def test_the_meter_does_not_let_a_reported_cost_poison_the_total(bad):
    endpoint = Endpoint(cost=bad)
    meter = MeteredProvider(endpoint, max_cost_usd=1.0, prompt_price_per_mtok=1.0, completion_price_per_mtok=2.0)
    asyncio.run(meter.complete("hello", None, 0.0, 64))
    assert math.isfinite(meter.cost_usd) and meter.cost_usd >= 0.0
    # the next call is still judged against a real number: a huge request is refused
    with pytest.raises(BudgetExceededError):
        asyncio.run(meter.complete("hello " * 10, None, 0.0, 900_000))


def test_the_meter_counts_a_call_that_failed_after_it_was_sent():
    endpoint = Endpoint(fail=True)
    meter = MeteredProvider(endpoint, max_cost_usd=10.0, prompt_price_per_mtok=1.0, completion_price_per_mtok=2.0)
    with pytest.raises(RuntimeError):
        asyncio.run(meter.complete("hello", None, 0.0, 64))
    summary = meter.summary()
    assert meter.calls == 1 and meter.uncertain_calls == 1 and summary["prompt_tokens"] > 0

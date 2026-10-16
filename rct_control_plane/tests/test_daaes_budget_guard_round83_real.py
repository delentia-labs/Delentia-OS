"""
Round 83, DAAES model gateway + hard budget guard: an experiment-wide limit enforced BEFORE each call, across runs, surviving a crash, with unknown prices failing closed and no automatic paid fallback.
The provider is a fake that counts the calls that really reached it, so "refused" means "never sent".
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

import pytest

from rct_control_plane.llm_provider import LLMProvider, LLMUsage, MeteredProvider
from research.daaes.budget_guard import BudgetExceeded, BudgetPolicy, ExperimentLedger, GuardedProvider


class FakeProvider(LLMProvider):
    model = "fake-model"

    def __init__(self, reply="ok", prompt_tokens=100, completion_tokens=50, fail=False):
        self.sent, self.reply, self.pt, self.ct, self.fail = 0, reply, prompt_tokens, completion_tokens, fail

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.sent += 1
        if self.fail:
            raise ConnectionError("provider reset the connection")
        self.last_usage = LLMUsage(self.pt, self.ct, None)
        return self.reply


def policy(**kw):
    return BudgetPolicy.from_dict({"total_usd": 5.0, "warning_usd": 3.0, "stop_new_runs_usd": 4.0, "reserve_usd": 1.0, "max_cost_per_run_usd": 0.25, "max_llm_calls_per_run": 3, **kw})


def run(coro):
    return asyncio.run(coro)


def test_the_policy_refuses_the_switches_that_would_invalidate_an_experiment():
    with pytest.raises(ValueError, match="fallback"):
        BudgetPolicy(automatic_fallback=True).validate()
    with pytest.raises(ValueError, match="stop"):
        BudgetPolicy(on_budget_exceeded="continue").validate()
    with pytest.raises(ValueError, match="warning"):
        BudgetPolicy(warning_usd=4.5, stop_new_runs_usd=4.0).validate()


def test_a_call_over_the_call_limit_is_refused_before_it_is_sent(tmp_path):
    ledger = ExperimentLedger(tmp_path / "l.json", policy())
    inner = FakeProvider()
    guarded = GuardedProvider(inner, ledger.start_run("r1"), 1.0, 2.0)
    for _ in range(3):
        run(guarded.complete("hello"))
    with pytest.raises(BudgetExceeded, match="call 4"):
        run(guarded.complete("hello"))
    assert inner.sent == 3


def test_a_call_whose_worst_case_would_break_the_run_cost_is_never_sent(tmp_path):
    ledger = ExperimentLedger(tmp_path / "l.json", policy())
    inner = FakeProvider()
    guarded = GuardedProvider(inner, ledger.start_run("r1"), 100.0, 200.0)               # dear model: 2,000 tokens of output at $200/M is $0.40 > $0.25
    with pytest.raises(BudgetExceeded, match="per run"):
        run(guarded.complete("hello", max_tokens=2000))
    assert inner.sent == 0


def test_an_unknown_price_fails_closed(tmp_path):
    ledger = ExperimentLedger(tmp_path / "l.json", policy())
    inner = FakeProvider()
    with pytest.raises(BudgetExceeded, match="unknown"):
        run(GuardedProvider(inner, ledger.start_run("r1"), None, None).complete("hello"))
    assert inner.sent == 0


def test_spending_is_recorded_from_what_the_provider_reported_and_survives_a_restart(tmp_path):
    path = tmp_path / "l.json"
    ledger = ExperimentLedger(path, policy())
    guarded = GuardedProvider(FakeProvider(prompt_tokens=1000, completion_tokens=500), ledger.start_run("r1"), 1.0, 2.0)
    run(guarded.complete("hello"))
    again = ExperimentLedger(path, policy())                                              # a new process reads the same file
    assert again.state["spent_usd"] == pytest.approx((1000 * 1.0 + 500 * 2.0) / 1_000_000) and again.state["runs"]["r1"]["calls"] == 1 and again.state["reserved_usd"] == 0.0


def test_new_runs_stop_at_the_line_and_a_run_that_could_cut_into_the_reserve_is_not_started(tmp_path):
    ledger = ExperimentLedger(tmp_path / "l.json", policy(max_cost_per_run_usd=2.0, max_llm_calls_per_run=50))
    ledger.state["spent_usd"] = 3.9
    with pytest.raises(BudgetExceeded, match="reserve"):                                      # 3.9 + 2.0 > 5.0 - 1.0 : this run could cut into the reserve
        ledger.start_run("could-cut-the-reserve")
    ledger2 = ExperimentLedger(tmp_path / "m.json", policy(max_cost_per_run_usd=0.05))
    ledger2.state["spent_usd"] = 4.0
    with pytest.raises(BudgetExceeded, match="stop-new-runs"):
        ledger2.start_run("too-late")


def test_the_reserve_is_never_spent_even_when_another_process_spent_in_the_meantime(tmp_path):
    ledger = ExperimentLedger(tmp_path / "l.json", policy(max_cost_per_run_usd=0.5))
    guarded = GuardedProvider(FakeProvider(), ledger.start_run("r"), 100.0, 100.0)
    ledger.state["spent_usd"] = 3.9                                                           # a parallel run spent after this one started
    with pytest.raises(BudgetExceeded, match="reserve"):
        run(guarded.complete("x" * 400, max_tokens=2000))                                     # worst case $0.2: 3.9 + 0.2 > 5.0 - 1.0


def test_a_provider_failure_keeps_the_reservation_counted_because_the_request_may_have_arrived(tmp_path):
    ledger = ExperimentLedger(tmp_path / "l.json", policy())
    guarded = GuardedProvider(FakeProvider(fail=True), ledger.start_run("r1"), 1.0, 2.0)
    with pytest.raises(ConnectionError):
        run(guarded.complete("hello"))
    assert ledger.state["reserved_usd"] > 0                                               # not released: the guard errs towards having spent it


def test_a_run_id_is_never_reused(tmp_path):
    ledger = ExperimentLedger(tmp_path / "l.json", policy())
    ledger.start_run("r1")
    with pytest.raises(BudgetExceeded, match="already started"):
        ledger.start_run("r1")


def test_the_warning_line_is_recorded_once(tmp_path):
    ledger = ExperimentLedger(tmp_path / "l.json", policy(max_cost_per_run_usd=4.0, warning_usd=0.00001, stop_new_runs_usd=0.5, max_llm_calls_per_run=10))
    guarded = GuardedProvider(FakeProvider(prompt_tokens=10_000, completion_tokens=5_000), ledger.start_run("r1"), 1.0, 2.0)
    run(guarded.complete("hello"))
    run(guarded.complete("hello"))
    assert [w["line"] for w in ledger.state["warnings"]] == ["warning"]


def test_delentias_own_episode_meter_gets_the_same_numbers_and_also_refuses():
    p = policy()
    env = p.delentia_env()
    assert env["DELENTIA_EPISODE_BUDGET_USD"] == "0.25" and int(env["DELENTIA_EPISODE_MAX_TOKENS"]) == 220_000
    inner = FakeProvider()
    metered = MeteredProvider(inner, max_cost_usd=0.000001, prompt_price_per_mtok=1.0, completion_price_per_mtok=2.0)
    from rct_control_plane.llm_provider import BudgetExceededError
    with pytest.raises(BudgetExceededError):
        run(metered.complete("hello world " * 50, max_tokens=500))
    assert inner.sent == 0

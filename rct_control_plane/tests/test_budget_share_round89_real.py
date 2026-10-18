"""
Round 89 (master workflow W12): a parent and the subagents it starts share ONE spending cap.

Before, each child inherited the parent's whole per-episode cap, so a $0.25 parent with three children could cause $1.00 of spending, and the parent's meter never saw the children's.
The end-to-end half (real subagent processes, a scripted model over HTTP) is harness case C26 in scripts/full_pipeline_cases.py, run by test_full_pipeline_scripted_round52_real.py.
"""
import pytest

from rct_control_plane import budget_share
from rct_control_plane.llm_provider import BudgetExceededError, LLMProvider, MeteredProvider


class _Free(LLMProvider):
    free_of_charge = True
    model = "scripted"

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        return "ok"

    async def stream_complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048):
        yield "ok"


def _meter(cost_cap=None, token_cap=None, spent_usd=0.0, spent_tokens=0):
    m = MeteredProvider(_Free(), max_cost_usd=cost_cap, max_tokens_total=token_cap)
    m.cost_usd = spent_usd
    m.prompt_tokens = spent_tokens
    return m


def test_no_running_episode_means_nothing_is_changed():
    plan = budget_share.plan_child_budgets(3, meter=None)
    assert plan.allowed and plan.env == {}


def test_no_cap_means_nothing_is_changed():
    plan = budget_share.plan_child_budgets(3, meter=_meter())
    assert plan.allowed and plan.env == {}


def test_children_split_what_is_left_minus_the_parents_reserve():
    plan = budget_share.plan_child_budgets(3, meter=_meter(cost_cap=0.20, token_cap=100_000, spent_usd=0.04, spent_tokens=20_000))
    assert plan.allowed
    assert plan.per_child_usd == pytest.approx((0.20 - 0.04) * 0.8 / 3)
    assert plan.per_child_tokens == int(80_000 * 0.8 / 3)
    assert float(plan.env["DELENTIA_EPISODE_BUDGET_USD"]) == pytest.approx(plan.per_child_usd, rel=1e-6)
    assert int(plan.env["DELENTIA_EPISODE_MAX_TOKENS"]) == plan.per_child_tokens
    # three children at their cap plus the reserve can never be more than what was left
    assert 3 * plan.per_child_usd <= (0.20 - 0.04)


def test_nothing_is_shared_when_too_little_is_left():
    plan = budget_share.plan_child_budgets(3, meter=_meter(cost_cap=0.20, spent_usd=0.1999))
    assert not plan.allowed and "not enough" in plan.reason
    plan = budget_share.plan_child_budgets(2, meter=_meter(token_cap=5_000, spent_tokens=4_000))
    assert not plan.allowed


def test_an_unknown_cost_under_a_dollar_cap_refuses_instead_of_guessing():
    meter = _meter(cost_cap=0.20)
    meter.cost_known = False
    plan = budget_share.plan_child_budgets(2, meter=meter)
    assert not plan.allowed and "unknown" in plan.reason


def test_charging_back_counts_verified_numbers_and_the_whole_share_otherwise():
    meter = _meter(cost_cap=1.0, token_cap=100_000)
    plan = budget_share.plan_child_budgets(3, meter=meter)
    outcomes = [
        {"jitna": {"response_verified": True}, "spent_usd": 0.01, "tokens_used": 1_000},
        {"jitna": {"response_verified": False}, "spent_usd": 0.0, "tokens_used": 0},        # a forged answer's numbers are not believed: it is charged its share
        {"jitna": {"response_verified": True}, "spent_usd": None, "tokens_used": None},      # a child that could not say what it spent is charged its share
    ]
    charged = budget_share.charge_children(outcomes, plan, meter=meter)
    assert charged["charged_usd"] == pytest.approx(0.01 + 2 * plan.per_child_usd, abs=1e-6)
    assert charged["charged_tokens"] == 1_000 + 2 * plan.per_child_tokens
    assert meter.children_cost_usd == pytest.approx(charged["charged_usd"], abs=1e-6)
    assert meter.summary()["children_tokens"] == charged["charged_tokens"]


@pytest.mark.asyncio
async def test_the_parents_own_next_call_is_refused_once_the_children_used_its_cap():
    meter = _meter(token_cap=10_000)
    meter.charge_children(0.0, 9_990)
    with pytest.raises(BudgetExceededError):
        await meter.complete("hello", max_tokens=100)
    ok_meter = _meter(token_cap=10_000)
    assert await ok_meter.complete("hello", max_tokens=100) == "ok"          # the same call is fine when the children spent nothing


@pytest.mark.asyncio
async def test_the_cost_cap_counts_children_too():
    meter = MeteredProvider(_Free(), max_cost_usd=0.10, prompt_price_per_mtok=1.0, completion_price_per_mtok=1.0)
    meter.charge_children(0.0999, 0)
    with pytest.raises(BudgetExceededError):
        await meter.complete("hello " * 2000, max_tokens=500)


def test_the_governed_loop_publishes_and_clears_its_meter():
    import inspect
    from rct_control_plane import governed_autonomous_loop as gal
    source = inspect.getsource(gal.GovernedAutonomousLoop)
    assert "budget_share.current_meter.set(self._meter)" in source
    assert source.count("budget_share.current_meter.set(None)") >= 2        # at the start of an episode and again when it ends


def test_the_subagent_tool_uses_the_plan_and_charges_back():
    import inspect
    from rct_control_plane import mcp_server
    source = inspect.getsource(mcp_server.delentia_spawn_subagents)
    assert "plan_child_budgets" in source and "charge_children" in source and "child_env" in source

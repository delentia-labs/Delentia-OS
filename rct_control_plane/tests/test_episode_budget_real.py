"""
Round 50 (Round 48 end-point criterion 7, "know the cost in advance"):
every governed episode runs its model calls through a MeteredProvider that
adds up tokens and cost, and refuses a call whose worst case would exceed
the episode budget BEFORE the call is made.

The model is a scripted LLMProvider; decide_next_action, the governed loop,
persistence and the budget logic are real.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

from rct_control_plane import llm_provider as lp
from rct_control_plane.governed_autonomous_loop import (
    EPISODE_BUDGET_USD_ENV, EPISODE_MAX_TOKENS_ENV, GovernedAutonomousLoop,
)
from test_governed_autonomous_loop_real import _loop


class _ScriptedLLM(lp.LLMProvider):
    """Returns the scripted JSON decisions in order and reports usage the way
    a real backend does."""

    model = "scripted-model"

    def __init__(self, decisions, prompt_tokens=100, completion_tokens=20, cost=None):
        self.decisions = list(decisions)
        self.calls = 0
        self.usage = (prompt_tokens, completion_tokens, cost)

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.calls += 1
        self.last_usage = lp.LLMUsage(*self.usage)
        if self.decisions:
            return self.decisions.pop(0)
        return json.dumps({"action": "finish", "reasoning": "done", "final_answer": "done"})


def _recall_call(n):
    return json.dumps({"action": "call_tool", "tool_name": "delentia_recall",
                       "tool_args": {"query": f"q{n}"}, "reasoning": "look it up"})


# ---------------------------------------------------------------- MeteredProvider

def test_usage_is_added_up_and_priced():
    inner = _ScriptedLLM([], prompt_tokens=1000, completion_tokens=500)
    meter = lp.MeteredProvider(inner, prompt_price_per_mtok=3.0, completion_price_per_mtok=15.0)
    asyncio.run(meter.complete("hi"))
    asyncio.run(meter.complete("hi again"))
    s = meter.summary()
    assert (s["calls"], s["prompt_tokens"], s["completion_tokens"]) == (2, 2000, 1000)
    assert s["cost_usd"] == pytest.approx(2 * (1000 * 3 + 500 * 15) / 1_000_000)
    assert s["cost_known"] is True


def test_a_backend_reported_cost_wins_over_the_price_table():
    inner = _ScriptedLLM([], cost=0.0421)
    meter = lp.MeteredProvider(inner, prompt_price_per_mtok=1.0, completion_price_per_mtok=1.0)
    asyncio.run(meter.complete("hi"))
    assert meter.summary()["cost_usd"] == pytest.approx(0.0421)


def test_token_budget_refuses_before_the_call_is_made():
    inner = _ScriptedLLM([])
    meter = lp.MeteredProvider(inner, max_tokens_total=500)
    with pytest.raises(lp.BudgetExceededError, match="token budget"):
        asyncio.run(meter.complete("x" * 40, max_tokens=2048))  # worst case 2048+ > 500
    assert inner.calls == 0


def test_cost_budget_refuses_the_call_that_could_overspend():
    inner = _ScriptedLLM([], prompt_tokens=1000, completion_tokens=1000)
    meter = lp.MeteredProvider(inner, max_cost_usd=0.05, prompt_price_per_mtok=10.0, completion_price_per_mtok=10.0)
    asyncio.run(meter.complete("hi", max_tokens=1000))   # worst ~$0.01, real $0.02
    asyncio.run(meter.complete("hi", max_tokens=1000))   # spent $0.04 after this one
    with pytest.raises(lp.BudgetExceededError, match="cost budget"):
        asyncio.run(meter.complete("hi", max_tokens=1000))  # $0.04 + up to $0.01 ... + prompt > $0.05
    assert inner.calls == 2


def test_a_cost_budget_with_an_unknown_price_fails_closed():
    inner = _ScriptedLLM([])
    meter = lp.MeteredProvider(inner, max_cost_usd=1.0)  # no prices
    with pytest.raises(lp.BudgetExceededError, match="price of scripted-model is unknown"):
        asyncio.run(meter.complete("hi"))
    assert inner.calls == 0


def test_a_local_ollama_model_costs_nothing():
    meter = lp.MeteredProvider(lp.OllamaProvider(model="qwen2.5:7b"), max_cost_usd=0.01)
    assert meter.prompt_price_per_mtok == 0.0 and meter.completion_price_per_mtok == 0.0


def test_without_reported_usage_tokens_are_estimated_and_cost_is_unknown():
    class _Silent(lp.LLMProvider):
        async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
            return "an answer of a few words"
    meter = lp.MeteredProvider(_Silent())
    asyncio.run(meter.complete("a prompt of a few words"))
    s = meter.summary()
    assert s["prompt_tokens"] > 0 and s["completion_tokens"] > 0
    assert s["cost_known"] is False and s["cost_usd"] is None


# ---------------------------------------------------------------- providers report usage

class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_ollama_reports_its_real_token_counts(monkeypatch):
    async def _post(self, url, json=None, **kw):
        return _FakeResponse({"response": "ok", "prompt_eval_count": 42, "eval_count": 7})
    monkeypatch.setattr(lp.httpx.AsyncClient, "post", _post)
    provider = lp.OllamaProvider()
    asyncio.run(provider.complete("hi"))
    assert provider.last_usage == lp.LLMUsage(42, 7, 0.0)


def test_openrouter_reports_usage_and_cost(monkeypatch):
    async def _post(self, url, headers=None, json=None, **kw):
        return _FakeResponse({"choices": [{"message": {"content": "ok"}}],
                              "usage": {"prompt_tokens": 120, "completion_tokens": 30, "cost": 0.00042}})
    monkeypatch.setattr(lp.httpx.AsyncClient, "post", _post)
    provider = lp.OpenRouterProvider(api_key="sk-or-v1-test-not-real", model="some/model")
    assert asyncio.run(provider.complete("hi")) == "ok"
    assert provider.last_usage == lp.LLMUsage(120, 30, 0.00042)


# ---------------------------------------------------------------- governed loop

def test_an_episode_stops_cleanly_when_the_token_budget_would_be_exceeded(tmp_path):
    inner = _ScriptedLLM([_recall_call(i) for i in range(10)], prompt_tokens=400, completion_tokens=50)
    loop = _loop(tmp_path, "budget", llm_provider=inner, route=False, max_episode_tokens=2048 + 1500)
    result = asyncio.run(loop.run("summarise the audit log"))

    assert result["stopped_reason"] == "budget_exceeded"
    assert result["cost"]["refused"].startswith("token budget")
    assert inner.calls == result["cost"]["calls"] < 5
    assert result["steps"][-1]["tool_result"]["budget_exceeded"]


def test_every_episode_reports_its_cost_even_without_a_budget(tmp_path):
    inner = _ScriptedLLM([_recall_call(1)], prompt_tokens=300, completion_tokens=40)
    loop = _loop(tmp_path, "report", llm_provider=inner)
    result = asyncio.run(loop.run("summarise the audit log"))

    assert result["stopped_reason"] == "llm_finished"
    assert result["cost"]["calls"] == 2
    assert result["cost"]["prompt_tokens"] == 600
    assert result["cost"]["max_cost_usd"] is None
    runs = loop._persistence.get_experiment_runs(result["experiment"]["experiment_id"])
    metrics = runs[0]["metrics"]
    metrics = json.loads(metrics) if isinstance(metrics, str) else metrics
    assert metrics["llm_calls"] == 2 and metrics["prompt_tokens"] == 600
    assert loop._model_label().endswith(":scripted-model")  # the model, not the meter


def test_each_episode_gets_a_fresh_meter(tmp_path):
    inner = _ScriptedLLM([], prompt_tokens=10, completion_tokens=1)
    loop = _loop(tmp_path, "fresh", llm_provider=inner)
    first = asyncio.run(loop.run("summarise the audit log"))
    second = asyncio.run(loop.run("summarise the audit log"))
    assert first["cost"]["calls"] == second["cost"]["calls"] == 1


def test_budgets_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(EPISODE_BUDGET_USD_ENV, "0.25")
    monkeypatch.setenv(EPISODE_MAX_TOKENS_ENV, "5000")
    loop = _loop(tmp_path, "env")
    assert loop._max_episode_cost_usd == 0.25 and loop._max_episode_tokens == 5000


@pytest.mark.parametrize("name,value", [(EPISODE_BUDGET_USD_ENV, "ten"), (EPISODE_BUDGET_USD_ENV, "0"),
                                        (EPISODE_MAX_TOKENS_ENV, "-5")])
def test_a_bad_budget_setting_is_an_error_not_silently_ignored(tmp_path, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        _loop(tmp_path, "bad_env")


def test_the_loop_class_is_importable_with_budget_parameters():
    assert "max_episode_cost_usd" in GovernedAutonomousLoop.__init__.__code__.co_varnames


def test_an_openrouter_model_is_priced_from_the_catalog_only_when_a_cost_budget_is_set(tmp_path, monkeypatch):
    from rct_control_plane import model_config
    looked_up = []
    monkeypatch.setattr(model_config, "lookup_openrouter_prices", lambda m: looked_up.append(m) or (1.5, 6.0))
    provider = lp.OpenRouterProvider(api_key="sk-or-v1-test-not-real", model="some/model")

    no_budget = _loop(tmp_path, "or_free", llm_provider=provider)
    assert no_budget._new_meter().prompt_price_per_mtok is None and looked_up == []

    budgeted = _loop(tmp_path, "or_budget", llm_provider=provider, max_episode_cost_usd=0.5)
    meter = budgeted._new_meter()
    assert (meter.prompt_price_per_mtok, meter.completion_price_per_mtok) == (1.5, 6.0)
    assert looked_up == ["some/model"]


def test_an_unpriced_openrouter_model_with_a_cost_budget_makes_no_call(tmp_path, monkeypatch):
    from rct_control_plane import model_config
    monkeypatch.setattr(model_config, "lookup_openrouter_prices", lambda m: None)
    calls = []

    async def _post(self, url, headers=None, json=None, **kw):
        calls.append(url)
        raise AssertionError("no network call may be made")
    monkeypatch.setattr(lp.httpx.AsyncClient, "post", _post)
    provider = lp.OpenRouterProvider(api_key="sk-or-v1-test-not-real", model="some/model")
    loop = _loop(tmp_path, "or_unpriced", llm_provider=provider, max_episode_cost_usd=0.5)
    result = asyncio.run(loop.run("summarise the audit log"))
    assert result["stopped_reason"] == "budget_exceeded"
    assert "unknown" in result["cost"]["refused"]
    assert calls == []

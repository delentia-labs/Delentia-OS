"""
Round 81: the model-free demo under a dollar budget.

Found by running `delentia demo run compare --scripted` inside the host kit, which sets DELENTIA_EPISODE_BUDGET_USD: the run stopped at step 1 with
`budget_exceeded`, because the meter refuses a call when a cost budget is set and the model's price is unknown (fail closed), and the scripted provider has no price.
It costs nothing, so it says so; a provider that really has no known price must still be refused.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json

import pytest

from rct_control_plane.demo_scripted import ScriptedDemoProvider
from rct_control_plane.llm_provider import BudgetExceededError, LLMProvider, MeteredProvider


class _UnknownPrice(LLMProvider):
    """A hosted-style provider that reports no price."""

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        return json.dumps({"action": "finish", "reasoning": "x", "final_answer": "y"})


def test_the_scripted_demo_is_not_refused_when_a_dollar_budget_is_set(tmp_path):
    metered = MeteredProvider(ScriptedDemoProvider("compare", tmp_path), max_cost_usd=0.20, max_tokens_total=60000)
    reply = asyncio.run(metered.complete("hello", "system"))
    assert json.loads(reply)["action"] == "call_tool"
    summary = metered.summary()
    assert summary["refused"] is None and summary["cost_known"] is True and summary["cost_usd"] == 0.0


def test_a_provider_with_no_known_price_is_still_refused_under_a_dollar_budget():
    metered = MeteredProvider(_UnknownPrice(), max_cost_usd=0.20)
    with pytest.raises(BudgetExceededError, match="price .* is unknown"):
        asyncio.run(metered.complete("hello"))


def test_the_token_cap_still_applies_to_the_scripted_demo(tmp_path):
    metered = MeteredProvider(ScriptedDemoProvider("compare", tmp_path), max_cost_usd=0.20, max_tokens_total=10)
    with pytest.raises(BudgetExceededError, match="token budget"):
        asyncio.run(metered.complete("a prompt that is longer than ten tokens, certainly, because it keeps going and going"))

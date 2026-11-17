"""Amendment 13 (research/ROUND_TWO_AMENDMENT_13_R115.md): raw replies and per-call usage are kept, the ceiling is metered per decision, a probe applies no pass rule. No model, no network, no money."""
import asyncio
import json
import os
import sys
from types import SimpleNamespace


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from research import tool_choice_r3_r115 as tc  # noqa: E402
from research import tool_menu_siblings_r114 as sib  # noqa: E402

SPEC = json.loads(sib.EXTERNAL.read_text(encoding="utf-8"))
TOOLS = [{"name": "delentia_read_repo_file", "description": "Read a text file", "input_schema": {}}] + sib.synthetic_tools(SPEC["servers"])


class FakeProvider:
    """Stands in for OpenRouterProvider: complete() sets last_usage and last_served_by the way the real one does."""

    def __init__(self, cost, text="not json at all"):
        self.cost, self.text, self.last_usage, self.last_served_by, self.n = cost, text, None, None, 0

    async def complete(self, prompt, **kwargs):
        self.n += 1
        self.last_usage = SimpleNamespace(prompt_tokens=1200, completion_tokens=40, cost_usd=self.cost, cached_tokens=0)
        self.last_served_by = "Fake Upstream"
        return self.text


def deciding(reply_ok=True):
    async def decide(goal, history, menu, llm_provider=None):
        text = await llm_provider.complete("p")
        return {"action": "call_tool", "tool_name": "mcp__notes__read_note"} if reply_ok else {"parse_error": True, "action": "finish", "raw_first": text}
    return decide


SETS = {"thai_89": [{"goal": f"t{i}", "needs": ["mcp__notes__read_note"], "id": i} for i in range(5)],
        "english_44": [{"goal": f"e{i}", "needs": ["mcp__notes__read_note"], "id": i} for i in range(5)],
        "negatives_20": [{"goal": f"n{i}", "needs": [], "id": i} for i in range(5)]}


def go(provider, decide, **kw):
    return asyncio.run(tc.run(tc.Recorder(provider), SETS, TOOLS, decide, **kw))


def test_a_row_keeps_the_usage_of_each_call_and_the_raw_reply_only_when_unreadable():
    out = go(FakeProvider(0.01), deciding(reply_ok=False), limit_per_set=1)
    assert len(out["rows"]) == 6
    for r in out["rows"]:
        assert r["verdict"] == "unparsed" and r["cost_usd"] == 0.01
        c = r["calls"][0]
        assert c["prompt_tokens"] == 1200 and c["completion_tokens"] == 40 and c["cost_usd"] == 0.01 and c["served_by"] == "Fake Upstream" and c["raw"] == "not json at all"


def test_a_readable_reply_drops_its_raw_text_unless_keep_raw_is_given():
    plain = go(FakeProvider(0.01), deciding(reply_ok=True), limit_per_set=1)
    assert all(r["calls"][0]["raw"] is None for r in plain["rows"])
    kept = go(FakeProvider(0.01), deciding(reply_ok=True), limit_per_set=1, keep_raw=True)
    assert all(r["calls"][0]["raw"] == "not json at all" for r in kept["rows"])


def test_a_decision_with_two_calls_records_both():
    async def decide(goal, history, menu, llm_provider=None):
        await llm_provider.complete("first")
        await llm_provider.complete("retry")
        return {"parse_error": True}
    out = go(FakeProvider(0.004), decide, limit_per_set=1)
    assert all(len(r["calls"]) == 2 and r["cost_usd"] == 0.008 for r in out["rows"])


def test_the_local_meter_stops_a_run_before_it_passes_the_ceiling():
    provider = FakeProvider(0.02)
    out = go(provider, deciding(), stop_at_usd=0.10)
    spent = sum(r["cost_usd"] for r in out["rows"])
    assert out["stopped"] and "local meter" in out["stopped"]
    assert spent <= 0.10 + 1e-9 and spent + 0.02 >= 0.10 - 1e-9
    assert len(out["rows"]) == 4 and provider.n == 4                       # 4 x 0.02 = 0.08; a fifth might reach 0.10, the ceiling, so it is not started


def test_a_probe_runs_the_first_goals_only_and_applies_no_pass_rule(monkeypatch, capsys, tmp_path):
    out = go(FakeProvider(0.001), deciding(), limit_per_set=1)
    assert [r["set"] for r in out["rows"]] == ["thai_89", "thai_89", "english_44", "english_44", "negatives_20", "negatives_20"]
    base = ["--model", "anthropic/claude-haiku-5.5", "--price-in", "0.1", "--price-out", "0.5", "--budget-usd", "0.30", "--limit-per-set", "1"]
    monkeypatch.setattr(sys, "argv", ["x", *base])
    assert tc.main() == 0
    shown = capsys.readouterr().out
    assert shown.startswith("6 decisions (thai_89 1, english_44 1, negatives_20 1 x 2 arms)") and "Dry run" in shown

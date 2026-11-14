"""
Round 113, batch 1 of the harness fixes (research/HARNESS_FIX_CRITERIA_R113.md, written before the code). Every test here fails on the code before the change:
H1 the judge runs keep the raw reply or the error text and the reply allowance is a setting; H2 a paid policy's token limits follow the money; H12 W10 gets enough calls; S1 is pinned in
test_tool_menu_local_default_round96_real.py. Real files, real hashing, the real budget guard; the model is a script.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import rct7_judge
from research import live_workflows
from research import rct7_holdout as holdout
from research.daaes import budget_guard


def make_sheet(tmp_path, n=24):
    lines = ["# sheet", "", "| # | request | A/B/? | note |", "|---|---|---|---|"]
    for i in range(1, n + 1):
        lines.append(f"| {i} | request {i} {'needs a thing' if i <= n // 2 else 'is plain'} | {'A' if i <= n // 2 else 'B'} | |")
    path = tmp_path / "request_sheet.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class Script:
    """Answers the judge's question properly, except for the items told to answer in prose (unparsed) or to fail (provider error)."""

    def __init__(self, prose=(), boom=()):
        self.prose, self.boom, self.max_tokens_seen = set(prose), set(boom), []

    async def complete(self, prompt, system_prompt=None, temperature=0.0, max_tokens=300, json_mode=False):
        self.max_tokens_seen.append(max_tokens)
        number = int(prompt.split("request ")[1].split()[0])
        if number in self.boom:
            raise TimeoutError("the provider did not answer in 90 s")
        if number in self.prose:
            return "Let me think about this request carefully before I answer. First, the wording"
        stop = "needs a thing" in prompt
        return json.dumps({"clear": False, "unknowns": [{"question": "which?", "about": f"request {number}"}]} if stop else {"clear": True, "unknowns": []})


@pytest.fixture(autouse=True)
def _no_allowance_setting(monkeypatch):
    monkeypatch.delenv(rct7_judge.JUDGE_MAX_TOKENS_ENV, raising=False)


# ------------------------------------------------------------------ H1
def test_the_default_allowance_is_what_was_always_sent_and_a_bad_setting_falls_back(monkeypatch):
    assert rct7_judge.judge_max_tokens() == 300
    for bad in ("0", "50", "99999", "many", ""):
        monkeypatch.setenv(rct7_judge.JUDGE_MAX_TOKENS_ENV, bad)
        assert rct7_judge.judge_max_tokens() == 300
    monkeypatch.setenv(rct7_judge.JUDGE_MAX_TOKENS_ENV, "1200")
    assert rct7_judge.judge_max_tokens() == 1200


def test_the_allowance_set_in_the_environment_is_what_the_provider_receives(tmp_path, monkeypatch):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    first = Script()
    asyncio.run(holdout.run_once(sheet, first, "m"))
    assert set(first.max_tokens_seen) == {300}
    monkeypatch.setenv(rct7_judge.JUDGE_MAX_TOKENS_ENV, "1200")
    second = Script()
    entry = asyncio.run(holdout.run_once(sheet, second, "m"))            # another allowance is another configuration: accepted without --again
    assert set(second.max_tokens_seen) == {1200} and entry["judge_max_tokens"] == 1200 and entry["repeat"] is False


def test_a_second_run_with_the_same_allowance_is_still_refused(tmp_path, monkeypatch):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    monkeypatch.setenv(rct7_judge.JUDGE_MAX_TOKENS_ENV, "1200")
    asyncio.run(holdout.run_once(sheet, Script(), "m"))
    with pytest.raises(ValueError, match="already ran"):
        asyncio.run(holdout.run_once(sheet, Script(), "m"))


def test_an_entry_written_before_the_allowance_was_recorded_counts_as_300(tmp_path):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    entry = asyncio.run(holdout.run_once(sheet, Script(), "m"))
    _, runs_path = holdout._paths(sheet)
    old = {k: v for k, v in entry.items() if k not in ("judge_max_tokens", "unusable", "replies")}       # the shape of an entry of 2026-11-13
    runs_path.write_text(json.dumps([old]), encoding="utf-8")
    with pytest.raises(ValueError, match="already ran"):
        asyncio.run(holdout.run_once(sheet, Script(), "m"))


def test_an_unusable_item_says_which_kind_it_was_and_keeps_the_evidence(tmp_path):
    sheet = make_sheet(tmp_path)
    holdout.seal(sheet, "", "x")
    entry = asyncio.run(holdout.run_once(sheet, Script(prose=(1, 2, 13), boom=(3, 14)), "m"))
    assert entry["result"]["malformed"] == 5                                   # the runner's own count is unchanged
    assert entry["unusable"] == {"provider_error": 2, "unparsed_reply": 3}
    assert entry["replies"]["1"]["unusable"] == "unparsed_reply" and entry["replies"]["1"]["reply"].startswith("Let me think")
    assert entry["replies"]["3"]["unusable"] == "provider_error" and "TimeoutError" in entry["replies"]["3"]["error"] and "90 s" in entry["replies"]["3"]["error"]
    assert "unusable" not in entry["replies"]["4"] and json.loads(entry["replies"]["4"]["reply"])["clear"] is False
    stored = holdout.runs_of(sheet)[-1]
    assert stored["replies"]["13"]["reply"].startswith("Let me think")        # it is in the file a later reader opens, not only in memory


def test_a_long_reply_is_cut_at_the_stated_length():
    rec = holdout.Recording(object())
    rec.last_reply = "x" * 20000
    assert len(holdout.reply_record(rec, True)["reply"]) == holdout.REPLY_KEEP_CHARS


def test_the_two_axis_runner_keeps_the_same_record(tmp_path):
    from research import rct7_holdout_twoaxis as two
    rec = holdout.Recording(Script(prose=(1,)))

    async def one():
        v = await rct7_judge.judge_request(rec, "request 1 needs a thing")
        return holdout.reply_record(rec, None if v.clear is None and not v.error.startswith("nothing") else (v.clear is False and bool(v.unknowns)))
    assert asyncio.run(one())["unusable"] == "unparsed_reply"
    source = open(two.__file__, encoding="utf-8").read()
    assert "base.Recording(provider)" in source and "base.same_allowance(r)" in source and "\"replies\": replies" in source


# ------------------------------------------------------------------ H2
def paid_policy(budget):
    """The policy `python -m research.daaes benchmark` builds for a paid run (research/daaes/__main__.py)."""
    return budget_guard.BudgetPolicy(total_usd=budget, warning_usd=budget * 0.6, stop_new_runs_usd=budget * 0.8, reserve_usd=budget * 0.2, max_cost_per_run_usd=budget * 0.1,
                                     max_llm_calls_per_run=84, max_input_tokens_per_run=budget_guard.PAID_MAX_INPUT_TOKENS_PER_RUN,
                                     max_output_tokens_per_run=budget_guard.PAID_MAX_OUTPUT_TOKENS_PER_RUN)


def long_call(run, prompt_tokens=2000, completion_tokens=9000):
    """One finished call of a model that writes a long reply, at $1 in and $2 out per million: $0.02."""
    reserved = run.before_call(prompt_tokens, 4096, 1.0, 2.0)
    run.after_call(reserved, prompt_tokens, completion_tokens, (prompt_tokens * 1.0 + completion_tokens * 2.0) / 1_000_000)


def test_a_run_that_wrote_long_replies_is_not_stopped_by_a_token_count(tmp_path):
    """2026-11-13: a model that writes 5,000 to 9,000 completion tokens per call was refused on its ninth call for 'token limits' at $0.05 of a $0.16 run budget."""
    ledger = budget_guard.ExperimentLedger(tmp_path / "ledger.json", paid_policy(1.6))
    run = ledger.start_run("b0-1700")
    for _ in range(3):                                                         # 27,000 completion tokens so far: over the old limit of 20,000
        long_call(run)
    run.before_call(2400, 4096, 1.0, 2.0)                                      # the old policy refused here


def test_the_old_default_policy_would_have_refused_that_call(tmp_path):
    """The negative control: the same run under the limits a paid policy had before."""
    old = budget_guard.BudgetPolicy(total_usd=1.6, warning_usd=0.96, stop_new_runs_usd=1.28, reserve_usd=0.32, max_cost_per_run_usd=0.16, max_llm_calls_per_run=84)
    ledger = budget_guard.ExperimentLedger(tmp_path / "ledger.json", old)
    run = ledger.start_run("b0-1700")
    for _ in range(2):
        long_call(run)
    with pytest.raises(budget_guard.BudgetExceeded, match="token limits"):
        run.before_call(2400, 4096, 1.0, 2.0)


def test_the_dollar_limit_of_a_run_still_stops_it(tmp_path):
    ledger = budget_guard.ExperimentLedger(tmp_path / "ledger.json", paid_policy(1.6))   # $0.16 per run
    run = ledger.start_run("b0-1700")
    for _ in range(6):
        long_call(run)                                                         # $0.02 each
    with pytest.raises(budget_guard.BudgetExceeded, match="per run"):
        for _ in range(4):
            long_call(run)


def test_every_paid_policy_in_the_code_uses_the_paid_token_limits():
    for rel in ("research/daaes/__main__.py", "research/daaes/runner.py", "research/live_workflows.py"):
        text = open(os.path.join(os.path.dirname(__file__), "..", "..", rel), encoding="utf-8").read()
        assert "PAID_MAX_INPUT_TOKENS_PER_RUN" in text and "PAID_MAX_OUTPUT_TOKENS_PER_RUN" in text, rel


# ------------------------------------------------------------------ H12
def test_w10_gets_enough_calls_for_twenty_scenarios_and_an_explicit_value_wins():
    assert live_workflows.resolved_max_calls("W10", None) == 120
    assert live_workflows.resolved_max_calls("W03", None) == 30 and live_workflows.resolved_max_calls("W09", None) == 30
    assert live_workflows.resolved_max_calls("W10", 30) == 30 and live_workflows.resolved_max_calls("W03", 7) == 7

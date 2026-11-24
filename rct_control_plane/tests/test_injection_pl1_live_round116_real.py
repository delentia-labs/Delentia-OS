"""S1 of Launch Proof Level 1, the paid path, tested for free against a fake OpenRouter on loopback that charges "money" in its own counter.

What the criteria ask before any key (research/LAUNCH_PL1_CRITERIA_R116.md, S1, test (c)): a refused provider call never reaches the endpoint. Also here: the
whole paid path (the factory the CLI uses, the budget guard, the governed loop, the raw-reply recorder) with a model that obeys the planted instruction executes
nothing; the guard's ledger agrees with what the endpoint charged; every reply is kept; the run stops at the first side effect that executed; a paid run
without the person's key, the opt-in, a price or the freeze is refused. The endpoint's counters are the independent witness. Nothing here measures a model.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import logging

import pytest

import scripted_model as sm
from fake_openrouter import FakeOpenRouter

from rct_control_plane import mcp_server  # noqa: F401  (imported first, as in the full suite: see test_injection_pl1_round116_real.py)
from research.injection_pl1 import live_provider_factory, measure_live
from research.pl1.injection_set_r116 import attack_set

MODEL = "rehearsal/model"
PRICES = {MODEL: {"in": 0.2, "out": 0.8}}


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in ("DELENTIA_FDIA_POLICY", "DELENTIA_APPROVER_PUBKEYS", "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS", "DELENTIA_FALLBACK_MODELS",
                 "DELENTIA_FREEZE_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "ambient"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "rehearsal-not-a-real-key")          # the fake endpoint's own placeholder, never a real credential
    monkeypatch.setenv("DELENTIA_RUN_LIVE_TESTS", "1")
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", "placeholder")             # registered with monkeypatch so the loopback address set below is put back
    monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL")
    logging.disable(logging.WARNING)
    yield
    logging.disable(logging.NOTSET)


def item(scenario_id: str):
    return next(a for a in attack_set() if a["id"] == scenario_id)


def obedient(target):
    """Calls the scenario's source, then whatever the planted text asks (the scenario's sink), then finishes: a model that does what the page says."""
    state = {"n": 0}

    def policy(req):
        if req.history_empty:
            state["n"] = 0
        state["n"] += 1
        if state["n"] == 1:
            return sm._call(target["source"], target["source_args"])
        if state["n"] == 2:
            return sm._call(target["sink"], target["sink_args"])
        return sm._finish("Done as the page asked.")
    return policy


def run(tmp_path, server, ids, *, per_episode_usd=0.05, protections="on", legitimate=False):
    os.environ["DELENTIA_OPENROUTER_BASE_URL"] = server.base_url
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    factory = live_provider_factory("openrouter", MODEL, out, 1.0, 0.2, 0.8, per_episode_usd=per_episode_usd, max_calls=10)
    report = asyncio.run(measure_live(tmp_path / "work", out, factory, only=ids, legitimate=legitimate, protections=protections))
    replies = [json.loads(line) for line in (out / "raw_replies.jsonl").read_text(encoding="utf-8").splitlines()] if (out / "raw_replies.jsonl").exists() else []
    ledger = json.loads((out / "live_ledger.json").read_text(encoding="utf-8")) if (out / "live_ledger.json").exists() else {}
    return report, replies, ledger, out


def test_a_refused_call_never_reaches_the_endpoint(tmp_path):
    target = item("A03-system_notice")
    with FakeOpenRouter(PRICES, policy=obedient(target)) as server:
        report, replies, _ledger, _ = run(tmp_path, server, [target["id"]], per_episode_usd=0.0000001)
        assert server.calls == 0, "the endpoint must never have seen a call the guard refused"
    assert report["executed_with_protections"] == 0 and report["rows_on"][0]["guard_refused"]
    assert replies and all(r["reply"] is None and r["refused_by_guard"] for r in replies), "a refused call is recorded as refused, never as a reply"
    assert report["verdict"] == "inconclusive", "one scenario of 115 is never a pass"


def test_an_obedient_model_through_the_paid_path_executes_nothing_and_every_reply_is_kept(tmp_path):
    target = item("A03-system_notice")
    with FakeOpenRouter(PRICES, policy=obedient(target)) as server:
        report, replies, ledger, out = run(tmp_path, server, [target["id"]])
        calls, spent = server.calls, server.spent
    row = report["rows_on"][0]
    assert row["read_planted_text"] and row["requested_harmful_tool"], "the fake did read the page and ask for the harmful tool"
    assert report["executed_with_protections"] == 0 and row["stopped_reason"] == "pending_approval"
    assert calls >= 2 and len([r for r in replies if r["reply"]]) == calls, "every reply the endpoint sent is kept"
    assert all(r["episode"] == f"attack:{target['id']}" for r in replies)
    assert ledger["spent_usd"] == pytest.approx(spent, rel=0.02, abs=1e-7), "the guard's ledger must agree with what the endpoint charged"
    assert [json.loads(line)["id"] for line in (out / "rows.jsonl").read_text(encoding="utf-8").splitlines()] == [target["id"]]


def test_the_run_stops_at_the_first_side_effect_that_executed(tmp_path):
    # The set runs in its own order (A03 before A04). Protections OFF exists for this test only: the built-in floor alone still holds every write for a
    # signature, but it lets A03's shell command run.
    first, second = item("A03-system_notice"), item("A04-system_notice")
    with FakeOpenRouter(PRICES, policy=obedient(first)) as server:
        report, _replies, _ledger, out = run(tmp_path, server, [second["id"], first["id"]], protections="off")
    assert report["verdict"] == "fail" and report["stopped"] == "hard failure"
    assert report["hard_failures"] and report["hard_failures"][0].startswith(first["id"])
    assert "delentia_run_sandboxed_command executed" in report["hard_failures"][0]
    assert len(report["rows_on"]) == 1, "no scenario runs after a hard failure"
    assert len((out / "rows.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_a_paid_run_is_refused_without_the_key_the_opt_in_a_price_or_the_freeze(tmp_path, monkeypatch):
    def build(**kw):
        args = dict(kind="openrouter", model=MODEL, out=tmp_path, budget_usd=1.0, price_in=0.2, price_out=0.8)
        args.update(kw)
        return live_provider_factory(args["kind"], args["model"], args["out"], args["budget_usd"], args["price_in"], args["price_out"],
                                     per_episode_usd=0.03, max_calls=10)
    with pytest.raises(SystemExit, match="freeze"):                    # the real endpoint (no loopback address) and no freeze file
        build()
    with pytest.raises(SystemExit, match="unknown price"):
        build(price_in=None)
    with pytest.raises(SystemExit, match="unknown price"):
        build(budget_usd=0.0)
    monkeypatch.delenv("DELENTIA_RUN_LIVE_TESTS")
    with pytest.raises(SystemExit, match="DELENTIA_RUN_LIVE_TESTS"):
        build()
    monkeypatch.setenv("DELENTIA_RUN_LIVE_TESTS", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(SystemExit, match="OPENROUTER_API_KEY"):
        build()

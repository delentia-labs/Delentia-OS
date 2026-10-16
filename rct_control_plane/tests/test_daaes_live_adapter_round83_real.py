"""
Round 83, DAAES G2: the experiment budget guard stands in front of Delentia's real provider code, tested against a fake OpenRouter on loopback that charges "money" in its own counter.

The endpoint's counters (calls, spent) are the independent witness: a refused call is proven by the endpoint never having seen it. Nothing here is a measurement of any model.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
from pathlib import Path

import pytest

import scripted_model as sm
from fake_openrouter import FakeOpenRouter

from research.daaes import delentia_session as ds
from research.daaes.budget_guard import BudgetExceeded, BudgetPolicy, ExperimentLedger
from research.daaes.live_adapter import guarded, openrouter_provider, run_live_episode

MODEL = "rehearsal/model"
PRICES = {MODEL: {"in": 0.2, "out": 0.8}}


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in ("DELENTIA_FDIA_POLICY", "DELENTIA_APPROVER_PUBKEYS", "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS", "DELENTIA_FALLBACK_MODELS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "ambient"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "rehearsal-not-a-real-key")           # the fake endpoint's own placeholder, never a real credential
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("DELENTIA_LLM_MODEL", MODEL)


def two_step_policy(req):
    """Reads one file, then answers: two model calls per episode."""
    if req.history_empty:
        return sm._call("delentia_read_repo_file", {"relative_path": "docs/a.md"}, "read the file")
    return sm._finish("The file says: " + "A")


def episode(tmp_path, server, policy, run_id="r1", ledger="ledger.json", price=(0.2, 0.8)):
    provider = openrouter_provider(MODEL, base_url=server.base_url)
    guard = guarded(provider, tmp_path / ledger, policy, run_id, *price)
    return guard, run_live_episode("Read docs/a.md and tell me what it says", tmp_path / f"home-{run_id}", guard, mcp_server=ds.ScriptedWorld(ds.FILES), max_iterations=4)


def test_every_model_call_passes_the_guard_and_the_ledger_matches_the_endpoint(tmp_path):
    with FakeOpenRouter(PRICES, policy=two_step_policy) as server:
        guard, result = episode(tmp_path, server, BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.25))
        led = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
        assert result["stopped_reason"] == "llm_finished" and "The file says" in (result["final_answer"] or "")
        assert server.calls == 2 and led["runs"]["r1"]["calls"] == 2
        assert led["spent_usd"] == pytest.approx(server.spent, rel=0.02, abs=1e-7), "the guard's ledger must agree with what the endpoint charged"
        assert led["reserved_usd"] == pytest.approx(0.0, abs=1e-9) and guard.refused is None


def test_a_call_over_the_run_limit_is_refused_before_it_is_sent(tmp_path):
    with FakeOpenRouter(PRICES, policy=two_step_policy) as server:
        guard, result = episode(tmp_path, server, BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.0000001))
        assert server.calls == 0, "the endpoint must never have seen a refused call"
        assert guard.refused and "per run" in guard.refused
        assert result["stopped_reason"] != "llm_finished" and result["guard_refused"]


def test_the_call_limit_stops_the_second_call_and_only_the_second(tmp_path):
    with FakeOpenRouter(PRICES, policy=two_step_policy) as server:
        guard, result = episode(tmp_path, server, BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.25, max_llm_calls_per_run=1))
        assert server.calls == 1 and guard.refused and "model calls" in guard.refused
        assert result["stopped_reason"] != "llm_finished"
        assert json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["runs"]["r1"]["calls"] == 1


def test_an_unknown_price_fails_closed(tmp_path):
    with FakeOpenRouter(PRICES, policy=two_step_policy) as server:
        guard, result = episode(tmp_path, server, BudgetPolicy(), price=(None, None))
        assert server.calls == 0 and guard.refused and "price" in guard.refused


def test_the_experiment_total_is_kept_across_runs_and_a_new_process_and_stops_the_next_run(tmp_path):
    policy = BudgetPolicy(total_usd=0.008, warning_usd=0.003, stop_new_runs_usd=0.006, reserve_usd=0.001, max_cost_per_run_usd=0.003)
    with FakeOpenRouter(PRICES, policy=two_step_policy) as server:
        episode(tmp_path, server, policy, run_id="r1")
        spent_after_first = ExperimentLedger(tmp_path / "ledger.json", policy).committed               # a fresh reader of the same file: what a restarted process sees
        assert spent_after_first == pytest.approx(server.spent, rel=0.05, abs=1e-7) and spent_after_first > 0
        calls_before = server.calls
        outcomes = []
        for n in range(2, 80):
            try:
                episode(tmp_path, server, policy, run_id=f"r{n}")
                outcomes.append("ran")
            except BudgetExceeded:
                outcomes.append("refused")
                break
        assert "refused" in outcomes, "the experiment total must stop new runs eventually"
        led = ExperimentLedger(tmp_path / "ledger.json", policy)
        assert led.committed <= policy.total_usd - policy.reserve_usd + 1e-9
        assert server.spent <= policy.total_usd, (server.spent, calls_before)


def test_a_call_that_died_in_flight_keeps_its_reservation(tmp_path):
    from research.daaes.budget_guard import GuardedProvider

    class Dies:
        model = MODEL
        last_usage = None

        async def complete(self, *a, **k):
            raise ConnectionResetError("the process was killed after the request was sent")
    policy = BudgetPolicy(total_usd=5.0, reserve_usd=1.0, max_cost_per_run_usd=0.25)
    guard = guarded(Dies(), tmp_path / "ledger.json", policy, "r1", 0.2, 0.8)
    assert isinstance(guard, GuardedProvider)
    with pytest.raises(ConnectionResetError):
        asyncio.run(guard.complete("hello", max_tokens=100))
    state = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert state["reserved_usd"] > 0, "the request may have been charged: the guard keeps counting it"
    assert ExperimentLedger(tmp_path / "ledger.json", policy).committed > 0


def test_a_provider_handed_to_build_governed_loop_is_the_one_the_loop_calls(tmp_path):
    """The seam added for the experiment: without it the loop would have resolved its own provider and the guard would have been bypassed."""
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence

    class Marker:
        model = "marker"
        last_usage = None

        async def complete(self, *a, **k):
            return sm._finish("from the handed-in provider")
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "agentic.db"))
    loop = build_governed_loop(ds.NullKernel(), namespace="x", persistence=persistence, mcp_server=ds.ScriptedWorld(ds.FILES), conversation_turns=0, llm_provider=Marker())
    result = asyncio.run(loop.run("say something"))
    assert "from the handed-in provider" in (result["final_answer"] or "")


# ---- D3 (research variant NI): what persists a person's intent is not shown to the model, and nothing that ENFORCES goes with it
def test_ni_hides_pinned_rules_and_keeps_the_gates(tmp_path):
    from rct_control_plane import research_switches as rs
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.agent_memory import AgentMemory
    from rct_control_plane.persistence import ControlPlanePersistence

    seen = {}
    for label in ("A111", "A111+NI"):
        home = tmp_path / label.replace("+", "-")
        with ds.data_home(home, extra_env={"DELENTIA_RESEARCH_MODE": "1"}), ds.scripted_model([]) as state:
            persistence = ControlPlanePersistence(db_path=str(home / "agentic.db"))
            from rct_control_plane.agent_memory import MemoryType
            mid = asyncio.run(AgentMemory("research-ni", persistence).store("Never touch the billing tables.", MemoryType.FACT, importance=0.9))
            persistence.pin_memory(mid, "research-ni", True, by="owner")
            kernel = ds.NullKernel()
            kernel._agent_memory = AgentMemory("shared_default", persistence)
            loop = build_governed_loop(kernel, namespace="research-ni", persistence=persistence, mcp_server=ds.ScriptedWorld(ds.FILES), conversation_turns=0)
            receipt = rs.apply(loop, rs.Treatment.parse(label))
            asyncio.run(loop.run("Read docs/a.md"))
            seen[label] = {"context": "\n".join(state["contexts"]), "receipt": receipt, "threshold": loop._fdia_threshold}
    assert "Never touch the billing tables." in seen["A111"]["context"] and seen["A111"]["receipt"]["persistent_intent_in_prompt"] is True
    assert "Never touch the billing tables." not in seen["A111+NI"]["context"] and seen["A111+NI"]["receipt"]["persistent_intent_in_prompt"] is False
    assert seen["A111+NI"]["threshold"] == seen["A111"]["threshold"] > 0, "the numeric gate stays on in NI"
    assert "A111+NI" not in [t.label for t in rs.SUB_ABLATIONS], "NI is not one of the four registered sub-ablations"
    assert rs.Treatment.parse("A111+NI").variant == "NI"

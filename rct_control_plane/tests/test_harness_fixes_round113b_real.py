"""
Round 113, batch 2 of the harness fixes (research/HARNESS_FIX_CRITERIA_R113B.md, written before the code). Each test here fails on the code before the change:
S5 a refusal by require_parameters names the setting; H2b a budget refusal is not a busy provider; H3 the TC-003 live arm records what happened after the signature.
Real httpx objects, a real loopback endpoint for the live arm; the model is a script.
"""

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "scripts")))

import httpx
import pytest

from rct_control_plane import autonomous_loop, llm_provider

NO_ENDPOINTS = {"error": {"message": "No endpoints found that can handle the requested parameters. To learn more about provider routing, visit: https://openrouter.ai/docs", "code": 404}}


def status_error(status, body):
    request = httpx.Request("POST", "http://127.0.0.1:1/chat/completions", headers={"Authorization": "Bearer secret-token-value"}, content=b'{"messages": "the prompt text"}')
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(status, json=body, request=request))


# ------------------------------------------------------------------ S5
def test_a_refusal_by_require_parameters_names_the_setting_and_what_to_do():
    text = autonomous_loop._describe_llm_error(status_error(404, NO_ENDPOINTS))
    assert "DELENTIA_OPENROUTER_REQUIRE_PARAMETERS" in text and "404" in text and "choose another model" in text


def test_that_sentence_never_carries_the_body_a_header_or_the_request():
    text = autonomous_loop._describe_llm_error(status_error(404, NO_ENDPOINTS))
    for leaked in ("secret-token-value", "the prompt text", "provider routing", "openrouter.ai/docs", "Bearer"):
        assert leaked not in text


def test_another_404_is_described_as_before():
    assert autonomous_loop._describe_llm_error(status_error(404, {"error": {"message": "model not found"}})) == "model endpoint answered HTTP 404"
    assert autonomous_loop._describe_llm_error(status_error(500, NO_ENDPOINTS)) == "model endpoint answered HTTP 500"


def test_the_default_request_does_not_ask_for_require_parameters(monkeypatch):
    monkeypatch.delenv(llm_provider.PROVIDER_REQUIRE_PARAMS_ENV, raising=False)
    assert "require_parameters" not in llm_provider.openrouter_provider_preferences()
    monkeypatch.setenv(llm_provider.PROVIDER_REQUIRE_PARAMS_ENV, "1")
    assert llm_provider.openrouter_provider_preferences().get("require_parameters") is True


# ------------------------------------------------------------------ H2b
def test_a_budget_refusal_is_not_a_transient_error_and_a_rate_limit_still_is():
    assert autonomous_loop._is_transient_llm_error(status_error(429, {})) is True
    assert autonomous_loop._is_transient_llm_error(status_error(402, {"error": {"type": "budget_exceeded"}})) is False


def test_the_experiment_gateway_answers_a_budget_refusal_with_402():
    source = (HERE.parent.parent / "research" / "daaes" / "model_gateway.py").read_text(encoding="utf-8")
    assert 'handler._json(402, {"error": {"message": f"budget guard: {exc}", "type": "budget_exceeded"}})' in source
    assert 'handler._json(429' not in source


# ------------------------------------------------------------------ H3
def _live_module():
    spec = importlib.util.spec_from_file_location("live_adapter_tests", HERE / "test_daaes_live_adapter_round83_real.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def live(tmp_path, monkeypatch):
    module = _live_module()
    for name in ("DELENTIA_FDIA_POLICY", "DELENTIA_APPROVER_PUBKEYS", "DELENTIA_EPISODE_BUDGET_USD", "DELENTIA_EPISODE_MAX_TOKENS", "DELENTIA_FALLBACK_MODELS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "ambient"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "rehearsal-not-a-real-key")
    monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("DELENTIA_LLM_MODEL", module.MODEL)
    monkeypatch.setenv("DELENTIA_RUN_LIVE_TESTS", "1")
    monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", "placeholder")
    monkeypatch.delenv("DELENTIA_OPENROUTER_BASE_URL")
    return module


def test_the_live_arm_records_the_stop_the_answer_and_the_steps_after_the_signature(tmp_path, monkeypatch, live):
    from fake_openrouter import FakeOpenRouter
    from research.daaes import runner
    with FakeOpenRouter(live.PRICES, policy=live._scripted_over_http("perfect")) as server:
        monkeypatch.setenv("DELENTIA_OPENROUTER_BASE_URL", server.base_url)
        row = runner.run_live("TC-003", "openrouter", live.MODEL, tmp_path / "out", budget_usd=1.0, price_in=0.2, price_out=0.8, max_iterations=24)
    agent = row["agent"]
    assert agent["first_stopped_reason"] == "pending_approval"                    # the part before the pause, as it was always recorded
    assert agent["stopped_reason"] != "pending_approval"                          # what the episode really ended with, after the signature
    assert agent["final_answer"]                                                  # the answer of the continued episode; before: empty (None) for every signed run
    tools = [name for name, _ in agent["tool_calls"]]
    assert "delentia_write_repo_file" in tools and tools.count("delentia_run_public_tests") >= 2      # the steps after the signature are in the record
    assert row["passed"] is True and not row["hard_failures"]


def test_a_session_without_a_continued_episode_has_none_of_the_new_keys(tmp_path):
    from research.daaes import delentia_session as ds
    summary = ds.run_session(tmp_path / "home", ds.GOAL, ds.DECISIONS, ds.ScriptedWorld(ds.FILES), None, approve=True)
    assert "final_stopped_reason" not in summary and "final_answer_after_approval" not in summary and "steps_after_approval" not in summary

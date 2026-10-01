"""
Round 53: a circuit breaker around the model provider. Real httpx errors from a failing fake provider and a
real HTTP server that goes down; the governed loop is the real one. Time is the real clock, with the recovery
window set to fractions of a second.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import time

import httpx
import pytest

from rct_control_plane import provider_breaker as pb
from rct_control_plane.llm_provider import LLMProvider, LLMUsage
from scripted_model import ScriptedModel, competent
from test_governed_autonomous_loop_real import _FakeMCP, _loop


class Flaky(LLMProvider):
    model = "flaky-1"
    base_url = "http://flaky.test"

    def __init__(self):
        self.calls = 0
        self.down = True
        self.last_usage = None

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.calls += 1
        if self.down:
            raise httpx.ConnectError("refused")
        self.last_usage = LLMUsage(3, 4, None)
        return '{"action": "finish", "reasoning": "ok", "final_answer": "fine", "tool_name": null, "tool_args": {}}'

    async def stream_complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048):
        self.calls += 1
        if self.down:
            raise httpx.ConnectError("refused")
        yield "a"
        yield "b"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv(pb.THRESHOLD_ENV, "3")
    monkeypatch.setenv(pb.RECOVERY_ENV, "0.3")
    monkeypatch.delenv(pb.BREAKER_ENV, raising=False)
    pb.reset_all()
    yield
    pb.reset_all()


def call(provider):
    return asyncio.run(provider.complete("hi"))


def test_a_failing_endpoint_opens_the_circuit_after_the_threshold_and_calls_stop():
    flaky = Flaky()
    guarded = pb.wrap(flaky)
    for _ in range(3):
        with pytest.raises(httpx.ConnectError):
            call(guarded)
    assert flaky.calls == 3
    with pytest.raises(pb.ProviderUnavailable) as err:
        call(guarded)
    assert "circuit open" in str(err.value) and "refused" not in str(err.value)
    assert flaky.calls == 3                                         # the fourth call never reached the endpoint


def test_after_the_recovery_window_one_probe_goes_through_and_success_closes_it():
    flaky = Flaky()
    guarded = pb.wrap(flaky)
    for _ in range(3):
        with pytest.raises(httpx.ConnectError):
            call(guarded)
    flaky.down = False
    time.sleep(0.4)
    assert "fine" in call(guarded)
    assert pb.breaker_for(flaky).state.value == "closed"
    assert "fine" in call(guarded)


def test_a_failing_probe_reopens_the_circuit():
    flaky = Flaky()
    guarded = pb.wrap(flaky)
    for _ in range(3):
        with pytest.raises(httpx.ConnectError):
            call(guarded)
    time.sleep(0.4)
    with pytest.raises(httpx.ConnectError):                         # the probe fails
        call(guarded)
    with pytest.raises(pb.ProviderUnavailable):
        call(guarded)


def test_the_breaker_is_shared_by_every_wrapper_of_the_same_endpoint_but_not_another_model():
    a, b = Flaky(), Flaky()
    for _ in range(3):
        with pytest.raises(httpx.ConnectError):
            call(pb.wrap(a))
    with pytest.raises(pb.ProviderUnavailable):
        call(pb.wrap(b))                                            # a second provider object for the same endpoint
    other = Flaky()
    other.model = "other-model"
    with pytest.raises(httpx.ConnectError):
        call(pb.wrap(other))


def test_wrapper_passes_model_usage_and_inner_through():
    flaky = Flaky()
    flaky.down = False
    guarded = pb.wrap(flaky)
    assert guarded.model == "flaky-1" and guarded.inner is flaky
    call(guarded)
    assert guarded.last_usage == LLMUsage(3, 4, None)
    guarded.last_usage = None
    assert flaky.last_usage is None


def test_streaming_counts_toward_the_breaker_too():
    flaky = Flaky()
    guarded = pb.wrap(flaky)

    async def drain():
        return [piece async for piece in guarded.stream_complete("hi")]

    for _ in range(3):
        with pytest.raises(httpx.ConnectError):
            asyncio.run(drain())
    with pytest.raises(pb.ProviderUnavailable):
        asyncio.run(drain())
    flaky.down = False
    time.sleep(0.4)
    assert asyncio.run(drain()) == ["a", "b"]


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv(pb.BREAKER_ENV, "0")
    flaky = Flaky()
    assert pb.wrap(flaky) is flaky


def test_wrapping_twice_does_not_stack_breakers():
    guarded = pb.wrap(Flaky())
    assert pb.wrap(guarded) is guarded


# ------------------------------------------------------------------ in the governed loop

def test_a_dead_model_endpoint_stops_costing_every_episode_a_full_retry_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_LLM_RETRY_BACKOFF", "0")
    monkeypatch.setattr("rct_control_plane.llm_provider.get_default_provider", lambda *a, **k: flaky)
    flaky = Flaky()
    first = asyncio.run(_loop(tmp_path, "b1", mcp=_FakeMCP()).run("say hello"))
    assert first["stopped_reason"] == "llm_error"
    seen = flaky.calls
    assert seen >= 3                                                # 1 + 2 retries, enough to open the circuit
    second = asyncio.run(_loop(tmp_path, "b2", mcp=_FakeMCP()).run("say hello"))
    assert second["stopped_reason"] == "llm_error" and flaky.calls == seen        # no new call reached the endpoint
    note = second["steps"][-1]["tool_result"]["llm_error"]
    assert "circuit open" in note


def test_a_real_http_model_that_comes_back_is_used_again(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_LLM_RETRY_BACKOFF", "0")
    with ScriptedModel(competent) as model:
        from rct_control_plane.model_config import save_model_selection
        cfg = tmp_path / "model.json"
        save_model_selection("openai-compat", "scripted-1", path=cfg, endpoint={
            "base_url": model.base_url, "kind": "local", "region": "", "operator": "test"})
        monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(cfg))
        monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openai-compat")
        monkeypatch.setenv("DELENTIA_LLM_MODEL", "scripted-1")
        model.fail_next = 100
        down = asyncio.run(_loop(tmp_path, "h1", mcp=_FakeMCP()).run("Remember that the sky is blue"))
        assert down["stopped_reason"] == "llm_error"
        model.fail_next = 0
        time.sleep(0.4)                                             # past the recovery window: one probe is allowed
        up = asyncio.run(_loop(tmp_path, "h2", mcp=_FakeMCP()).run("Remember that the sky is blue"))
        assert up["stopped_reason"] != "llm_error"

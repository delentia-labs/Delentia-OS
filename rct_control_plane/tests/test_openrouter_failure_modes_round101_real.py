"""
Round 101: the real model-calling code against an endpoint that misbehaves the way a paid one does.

The rehearsal server of Round 55 is polite. This test file drives the REAL OpenRouterProvider, the REAL retry policy and the REAL governed loop through a hostile loopback server
(research/openrouter_failure_modes_r101.py) and asserts what a safe runtime must do with each failure: retry what is transient, stop at once on what is not, never hang, never leak the key,
never switch JSON mode off for a model because of an unrelated 400.

Found by running them (before this round): a 200 whose body is an error object (documented OpenRouter behaviour for an upstream failure), a null or list-shaped message and an HTML page each ended
the whole episode on the first attempt with a TypeError/KeyError; a reasoning model whose <think> block contained braces gave a parse error; the retries ignored Retry-After; a 400 for a
too-long prompt switched JSON mode off for that model for the rest of the process.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import time

import pytest

from rct_control_plane import llm_provider
from rct_control_plane.autonomous_loop import _extract_json, _is_transient_llm_error, _retry_delay, _strip_reasoning
from research.openrouter_failure_modes_r101 import GOOD, KEY, Hostile, ok
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop

USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "cost": 0.0002}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setenv("DELENTIA_LLM_RETRY_BACKOFF", "0.02")
    monkeypatch.setenv("DELENTIA_LLM_RETRIES", "2")
    monkeypatch.delenv("DELENTIA_CREDENTIAL_POOL_OPENROUTER", raising=False)
    monkeypatch.setenv("DELENTIA_OPENROUTER_TIMEOUT_S", "20")
    llm_provider._NO_JSON_MODE.discard("vendor/model")


def episode(tmp_path, script, name="fm"):
    """One governed episode whose model is the real OpenRouterProvider talking to the hostile server."""
    with Hostile(script) as server:
        os.environ["DELENTIA_OPENROUTER_BASE_URL"] = server.base_url
        provider = llm_provider.OpenRouterProvider(api_key=KEY, model="vendor/model")
        loop = _loop(tmp_path, name, kernel=_FakeKernel(), mcp=_FakeMCP(), llm_provider=provider)
        started = time.perf_counter()
        result = asyncio.run(asyncio.wait_for(loop.run("Say hello"), timeout=120))
        return result, server, time.perf_counter() - started


def reasons(result):
    return json.dumps(result["steps"], default=str)


# ------------------------------------------------------------------ replies that are odd but usable
def test_a_normal_reply_is_one_request(tmp_path):
    result, server, _t = episode(tmp_path, lambda n, b: ok(GOOD, USAGE))
    assert result["stopped_reason"] == "llm_finished" and server.requests >= 1


def test_json_inside_a_markdown_fence_with_prose_before_it_is_read(tmp_path):
    result, _s, _t = episode(tmp_path, lambda n, b: ok("Sure, here is my decision:\n```json\n" + GOOD + "\n```", USAGE))
    assert result["stopped_reason"] == "llm_finished"


def test_braces_inside_a_think_block_do_not_break_the_json(tmp_path):
    result, server, _t = episode(tmp_path, lambda n, b: ok("<think>I should finish now. {not json} {\"action\": \"x\"}</think>\n" + GOOD, USAGE))
    assert result["stopped_reason"] == "llm_finished"
    assert server.requests == 1, "no second 'please give me valid JSON' call was needed"


def test_a_list_of_content_parts_is_joined(tmp_path):
    result, _s, _t = episode(tmp_path, lambda n, b: ok([{"type": "text", "text": GOOD}], USAGE))
    assert result["stopped_reason"] == "llm_finished"


def test_a_reply_without_usage_or_with_a_string_cost_still_works(tmp_path):
    assert episode(tmp_path, lambda n, b: ok(GOOD))[0]["stopped_reason"] == "llm_finished"
    assert episode(tmp_path, lambda n, b: ok(GOOD, {**USAGE, "cost": "0.0002"}), name="fm2")[0]["stopped_reason"] == "llm_finished"


# ------------------------------------------------------------------ a 200 that carries no reply is retried like a 503
@pytest.mark.parametrize("first", [
    lambda: ok(None, USAGE),
    lambda: (200, {}, {"error": {"code": 502, "message": "Provider returned error"}}),
    lambda: (200, {}, {"choices": [], "usage": USAGE}),
    lambda: (200, {}, b"<html><body>Bad gateway</body></html>"),
    lambda: ok("   ", USAGE),
])
def test_a_200_without_a_usable_reply_is_retried_and_the_second_answer_is_used(tmp_path, first):
    result, server, _t = episode(tmp_path, lambda n, b: first() if n == 1 else ok(GOOD, USAGE))
    assert result["stopped_reason"] == "llm_finished"
    assert server.requests == 2


def test_if_it_never_gets_better_the_episode_ends_with_the_reason_after_three_tries(tmp_path):
    result, server, _t = episode(tmp_path, lambda n, b: (200, {}, {"error": {"code": 502, "message": "Provider returned error"}}))
    assert result["stopped_reason"] == "llm_error" and server.requests == 3
    text = reasons(result)
    assert "502" in text and KEY not in text


# ------------------------------------------------------------------ HTTP errors
def test_503_once_is_retried(tmp_path):
    result, server, _t = episode(tmp_path, lambda n, b: (503, {}, {"error": {"message": "overloaded"}}) if n == 1 else ok(GOOD, USAGE))
    assert result["stopped_reason"] == "llm_finished" and server.requests == 2


def test_500_forever_ends_after_three_tries_and_says_so(tmp_path):
    result, server, _t = episode(tmp_path, lambda n, b: (500, {}, {"error": {"message": "boom"}}))
    assert result["stopped_reason"] == "llm_error" and server.requests == 3
    assert "HTTP 500" in reasons(result)


def test_a_429_with_retry_after_is_waited_for(tmp_path):
    result, server, took = episode(tmp_path, lambda n, b: (429, {"Retry-After": "1"}, {"error": {"message": "rate limited"}}) if n == 1 else ok(GOOD, USAGE))
    assert result["stopped_reason"] == "llm_finished" and server.requests == 2
    assert took >= 0.9, "the retry came before the Retry-After the endpoint asked for"


@pytest.mark.parametrize("status", [401, 402, 403])
def test_a_refusal_that_cannot_get_better_is_one_request_not_three(tmp_path, status):
    result, server, _t = episode(tmp_path, lambda n, b: (status, {}, {"error": {"code": status, "message": "no"}}))
    assert result["stopped_reason"] == "llm_error" and server.requests == 1
    assert f"HTTP {status}" in reasons(result) and KEY not in reasons(result)


def test_a_400_for_another_reason_does_not_switch_json_mode_off_for_the_model(tmp_path):
    result, server, _t = episode(tmp_path, lambda n, b: (400, {}, {"error": {"message": "context length exceeded"}}))
    assert result["stopped_reason"] == "llm_error"
    assert "vendor/model" not in llm_provider._NO_JSON_MODE


def test_a_real_json_mode_rejection_is_remembered_once_the_retry_works(tmp_path):
    def script(n, body):
        if "response_format" in body:
            return 400, {}, {"error": {"message": "response_format is not supported by this provider"}}
        return ok(GOOD, USAGE)
    result, _s, _t = episode(tmp_path, script)
    assert result["stopped_reason"] == "llm_finished" and "vendor/model" in llm_provider._NO_JSON_MODE


# ------------------------------------------------------------------ the small pieces
def test_only_a_reply_error_and_the_listed_statuses_are_transient():
    assert _is_transient_llm_error(llm_provider.LLMReplyError("x"))
    assert not _is_transient_llm_error(ValueError("x"))


def test_retry_delay_uses_the_larger_of_the_backoff_and_retry_after_and_caps_it():
    class R:
        def __init__(self, value):
            self.response = type("X", (), {"headers": {"retry-after": value}})()
    assert _retry_delay(R("5"), 1.0, 1) == 5.0
    assert _retry_delay(R("500"), 1.0, 1) == 30.0
    assert _retry_delay(R("0"), 2.0, 2) == 4.0
    assert _retry_delay(R("soon"), 1.0, 2) == 2.0
    assert _retry_delay(ValueError("x"), 1.0, 3) == 3.0


def test_stripping_the_reasoning_block():
    assert _strip_reasoning("<think>a {b}</think>{\"x\": 1}") == "{\"x\": 1}"
    assert _strip_reasoning("<THINK>one</THINK>A<think>two</think>B") == "AB"
    assert _strip_reasoning("answer <think>cut off while thinking {\"x\": 1}") == "answer "
    assert _extract_json("<think>{\"wrong\": true}</think> {\"right\": true}") == {"right": True}


def test_stripping_is_linear_on_hostile_input():
    for text in ("<think>" * 20000, "<think></think>" * 10000, "<think" * 20000, "<" * 20000):
        started = time.perf_counter()
        _strip_reasoning(text)
        assert time.perf_counter() - started < 1.5


# ------------------------------------------------------------------ the streamed final answer
def test_a_broken_stream_does_not_lose_the_answer_the_decision_call_already_gave(tmp_path):
    with Hostile(lambda n, b: ok(GOOD, USAGE)) as server:
        os.environ["DELENTIA_OPENROUTER_BASE_URL"] = server.base_url
        provider = llm_provider.OpenRouterProvider(api_key=KEY, model="vendor/model")
        loop = _loop(tmp_path, "fm_stream", kernel=_FakeKernel(), mcp=_FakeMCP(), llm_provider=provider)

        async def broken(goal, history, on_token):
            raise ValueError("the stream was cut")
        loop._stream_final_answer = broken
        tokens = []
        result = asyncio.run(loop.run("Say hello", on_answer_token=tokens.append))
    assert result["stopped_reason"] == "llm_finished" and result["final_answer"] == "ok"

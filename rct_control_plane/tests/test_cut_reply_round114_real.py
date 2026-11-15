"""
Round 114: a reply that is empty because it stopped at the allowance.

Found by window 3 of round two (register R0097): in two of the 14 runs of haiku with the runtime, the last three requests of an episode were identical, each stopped at the 2,048-token
allowance with an empty message, and the episode ended `llm_error`. The loop's own recovery for an unusable reply (one more request with a 4,096 allowance) never ran, because the provider raised
`LLMReplyError` for the empty message before the loop saw any text and the loop's transient retry then re-sent the identical request with the same allowance.

Criteria written first: research/ROUND_TWO_CRITERIA_R113.md, Amendment 4. These tests drive the REAL provider, the REAL retry policy and the REAL governed loop through a loopback server.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio

import pytest

from rct_control_plane import llm_provider
from research.openrouter_failure_modes_r101 import GOOD, KEY, Hostile, ok
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop

USAGE = {"prompt_tokens": 100, "completion_tokens": 2048, "total_tokens": 2148, "cost": 0.0002}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setenv("DELENTIA_LLM_RETRY_BACKOFF", "0.02")
    monkeypatch.setenv("DELENTIA_LLM_RETRIES", "2")
    monkeypatch.delenv("DELENTIA_CREDENTIAL_POOL_OPENROUTER", raising=False)
    monkeypatch.setenv("DELENTIA_OPENROUTER_TIMEOUT_S", "20")
    llm_provider._NO_JSON_MODE.discard("vendor/model")


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _body(content, finish):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}], "usage": USAGE}


def episode(tmp_path, script, name="cut"):
    seen = []

    def recording(n, body):
        seen.append(body.get("max_tokens"))
        return script(n, body)

    with Hostile(recording) as server:
        os.environ["DELENTIA_OPENROUTER_BASE_URL"] = server.base_url
        provider = llm_provider.OpenRouterProvider(api_key=KEY, model="vendor/model")
        loop = _loop(tmp_path, name, kernel=_FakeKernel(), mcp=_FakeMCP(), llm_provider=provider)
        result = asyncio.run(asyncio.wait_for(loop.run("Say hello"), timeout=120))
        return result, server, seen


# ---------------------------------------------------------------- the provider tells the two kinds of empty message apart
def test_an_empty_message_that_stopped_at_the_allowance_is_a_cut_not_a_transient_error():
    with pytest.raises(llm_provider.LLMReplyCut) as info:
        llm_provider.reply_text(_Resp(_body("", "length")))
    assert isinstance(info.value, llm_provider.LLMReplyError)
    assert info.value.transient is False, "an identical request must not be re-sent for a cut reply"


def test_an_empty_message_with_any_other_finish_reason_is_still_transient():
    for finish in ("stop", None, "content_filter"):
        with pytest.raises(llm_provider.LLMReplyError) as info:
            llm_provider.reply_text(_Resp(_body("", finish)))
        assert not isinstance(info.value, llm_provider.LLMReplyCut)
        assert info.value.transient is True


def test_a_cut_reply_that_still_carries_text_is_returned_as_before():
    data, text = llm_provider.reply_text(_Resp(_body('{"action": "fi', "length")))
    assert text == '{"action": "fi'


# ---------------------------------------------------------------- the loop asks once more with the larger allowance
def test_a_reply_cut_at_the_allowance_gets_one_more_request_with_4096(tmp_path):
    def script(n, body):
        if (body.get("max_tokens") or 0) >= 4096:
            return ok(GOOD, USAGE)
        return ok("", USAGE, finish="length")

    result, server, seen = episode(tmp_path, script)
    assert result["stopped_reason"] == "llm_finished", result["stopped_reason"]
    assert server.requests == 2, "one cut request and one request with the larger allowance, not three identical ones"
    assert seen[0] != 4096 and seen[1] == 4096


def test_a_reply_cut_at_both_allowances_ends_as_parse_error_after_exactly_two_requests(tmp_path):
    result, server, seen = episode(tmp_path, lambda n, b: ok("", USAGE, finish="length"))
    assert result["stopped_reason"] == "parse_error", result["stopped_reason"]
    assert server.requests == 2 and seen[1] == 4096


# ---------------------------------------------------------------- what must stay as it was
def test_an_empty_message_that_is_not_a_cut_is_still_retried_as_before(tmp_path):
    result, server, _seen = episode(tmp_path, lambda n, b: ok("", USAGE, finish="stop"))
    assert result["stopped_reason"] == "llm_error"
    assert server.requests == 3, "the loop's transient retry (1 + 2 retries) is unchanged for an empty message that was not cut"


def test_an_empty_message_that_is_not_a_cut_recovers_when_the_next_request_is_fine(tmp_path):
    result, server, _seen = episode(tmp_path, lambda n, b: ok("", USAGE, finish="stop") if n == 1 else ok(GOOD, USAGE))
    assert result["stopped_reason"] == "llm_finished" and server.requests == 2

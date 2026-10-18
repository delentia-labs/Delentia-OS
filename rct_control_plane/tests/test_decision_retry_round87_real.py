"""
Round 87: one unusable reply no longer ends an episode.

Found by the b0/d0 rerun on qwen3:8b: all four Delentia runs stopped `parse_error` after five calls, and the fifth reply had used exactly the 2048 completion tokens it was allowed. A reasoning model spent
its whole allowance thinking and its JSON was cut off; the loop treated that single reply as the end. Now an unusable reply is asked for once more with a larger allowance and a plain instruction to answer
with the JSON only. Bounded: exactly one retry, then the old stop. The model is a scripted provider that behaves like the failing one; the loop, the parser and the stop are real.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
from typing import List, Optional

import pytest

from rct_control_plane.autonomous_loop import decide_next_action
from rct_control_plane.llm_provider import LLMProvider

TOOLS = [{"name": "delentia_read_repo_file", "description": "read a file", "input_schema": {"type": "object", "properties": {"relative_path": {"type": "string"}}}}]
GOOD = json.dumps({"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "a.md"}, "reasoning": "read it"})
CUT = '{"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "a.m'          # a reply cut off by the token cap


def provider_with(replies: List[str]):
    class Scripted(LLMProvider):
        model = "scripted/thinker"

        def __init__(self) -> None:
            self.queue = list(replies)
            self.calls: List[dict] = []

        async def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048, json_mode: bool = False) -> str:
            self.calls.append({"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature})
            return self.queue.pop(0)
    return Scripted()


def decide(provider):
    return asyncio.run(decide_next_action("read a.md", [], TOOLS, llm_provider=provider))


def test_a_cut_off_reply_is_retried_once_with_a_larger_allowance_and_the_second_reply_is_used():
    p = provider_with([CUT, GOOD])
    decision = decide(p)
    assert decision["action"] == "call_tool" and decision["tool_args"]["relative_path"] == "a.md" and not decision.get("parse_error")
    assert len(p.calls) == 2 and p.calls[0]["max_tokens"] == 2048 and p.calls[1]["max_tokens"] == 4096
    assert "not a valid JSON object" in p.calls[1]["prompt"] and "not a valid JSON object" not in p.calls[0]["prompt"]


def test_two_unusable_replies_still_end_in_parse_error_after_exactly_two_calls():
    p = provider_with([CUT, "I think the answer is probably a file."])
    decision = decide(p)
    assert decision.get("parse_error") is True and decision["action"] == "finish"
    assert len(p.calls) == 2


def test_a_good_first_reply_costs_exactly_one_call():
    p = provider_with([GOOD])
    assert decide(p)["action"] == "call_tool" and len(p.calls) == 1


def test_a_reply_with_json_but_no_action_is_also_retried():
    p = provider_with(['{"thinking": "hmm"}', GOOD])
    assert decide(p)["action"] == "call_tool" and len(p.calls) == 2


def test_an_exception_on_the_retry_reaches_the_caller_like_one_on_the_first_call():
    class Refusing(LLMProvider):
        model = "scripted/refusing"

        def __init__(self) -> None:
            self.n = 0

        async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
            self.n += 1
            if self.n == 1:
                return CUT
            raise RuntimeError("the budget meter refused the second call")
    with pytest.raises(RuntimeError):
        decide(Refusing())

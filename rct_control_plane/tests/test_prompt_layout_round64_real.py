"""
Round 64: what a prompt costs, and the two changes the measurement (scripts/measure_prompt_cost.py) led to.

  * the history renderer no longer picks a JSON-Patch line that is bigger than the plain line it replaces (it compared the patch with a
    JSON copy of the state in which every Thai letter is six characters, then sent the plain, unescaped line: +22% prompt tokens on three real documents)
  * DELENTIA_PROMPT_LAYOUT=cache_friendly (opt-in): the unchanging part (the menu of tools, the guidance, the reply format) is the system message and comes first,
    so a provider that caches a prompt prefix can reuse it from call to call AND from episode to episode; explicit cache markers go only to the model families that need them
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json


import rct_control_plane.autonomous_loop as al
from rct_control_plane.llm_provider import CompatProfile, _build_openrouter_payload

TOOLS = [{"name": f"delentia_tool_{c}", "description": f"does thing {c} " * 12, "input_schema": {"properties": {"x": {}}}} for c in "zebra"] + \
        [{"name": "delentia_read_repo_file", "description": "read a file " * 30, "input_schema": {"properties": {"relative_path": {}}}}]


class Spy:
    def __init__(self):
        self.calls = []

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.calls.append({"prompt": prompt, "system": system_prompt})
        return json.dumps({"action": "finish", "reasoning": "r", "final_answer": "done"})


def decide(goal, spy, history=None):
    return asyncio.run(al.decide_next_action(goal, history or [], TOOLS, spy, ""))


class TestLayout:
    def test_the_default_layout_is_what_it_always_was(self, monkeypatch):
        monkeypatch.delenv("DELENTIA_PROMPT_LAYOUT", raising=False)
        spy = Spy()
        decide("read the file", spy)
        assert spy.calls[0]["system"] is None and spy.calls[0]["prompt"].startswith("You are an autonomous agent working toward this goal:\nread the file")
        assert "Available tools:" in spy.calls[0]["prompt"]

    def test_cache_friendly_puts_everything_that_never_changes_in_the_system_message(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_PROMPT_LAYOUT", "cache_friendly")
        spy = Spy()
        decide("read the file", spy)
        call = spy.calls[0]
        assert "Available tools:" in call["system"] and "delentia_read_repo_file" in call["system"] and '"action": "finish"' in call["system"]
        assert "read the file" in call["prompt"] and "Available tools:" not in call["prompt"] and "read the file" not in call["system"]

    def test_the_system_message_is_byte_identical_for_two_different_goals_and_two_histories(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_PROMPT_LAYOUT", "cache_friendly")
        spy = Spy()
        decide("read the file", spy)
        step = al.LoopStep(iteration=0, tool_name="delentia_read_repo_file", tool_args={"relative_path": "a.md"}, tool_result={"content_text": "x"}, llm_reasoning="")
        decide("summarise something else entirely", spy, history=[step])
        assert spy.calls[0]["system"] == spy.calls[1]["system"]
        assert spy.calls[0]["prompt"] != spy.calls[1]["prompt"]

    def test_the_menu_is_in_a_fixed_order_whatever_order_the_tools_arrive_in(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_PROMPT_LAYOUT", "cache_friendly")
        spy = Spy()
        asyncio.run(al.decide_next_action("g", [], list(reversed(TOOLS)), spy, ""))
        asyncio.run(al.decide_next_action("g", [], TOOLS, spy, ""))
        assert spy.calls[0]["system"] == spy.calls[1]["system"]

    def test_the_governed_loop_keeps_the_whole_menu_under_this_layout(self, tmp_path, monkeypatch):
        from test_governed_autonomous_loop_real import _loop
        loop = _loop(tmp_path, "layout")
        tools = [{"name": "delentia_read_repo_file", "description": "read a file"}, {"name": "delentia_speak", "description": "say text aloud"},
                 {"name": "delentia_remember", "description": "store a note"}]
        monkeypatch.delenv("DELENTIA_PROMPT_LAYOUT", raising=False)
        narrowed = loop._tool_filter("read a file", tools)
        monkeypatch.setenv("DELENTIA_PROMPT_LAYOUT", "cache_friendly")
        assert loop._tool_filter("read a file", tools) == tools and len(narrowed) <= len(tools)

    def test_a_reply_is_still_understood_under_the_new_layout(self, monkeypatch):
        monkeypatch.setenv("DELENTIA_PROMPT_LAYOUT", "cache_friendly")
        d = decide("read the file", Spy())
        assert d["action"] == "finish" and d["final_answer"] == "done"


class TestCacheMarkers:
    LONG = "tools " * 1500

    def payload(self, model, system, monkeypatch, layout="cache_friendly"):
        if layout:
            monkeypatch.setenv("DELENTIA_PROMPT_LAYOUT", layout)
        else:
            monkeypatch.delenv("DELENTIA_PROMPT_LAYOUT", raising=False)
        return _build_openrouter_payload(model, "the goal", system, 0.3, 512, True, CompatProfile())

    def test_anthropic_and_google_models_get_an_explicit_marker_on_the_long_system_message(self, monkeypatch):
        for model in ("anthropic/claude-haiku-5.5", "google/gemini-2.5-flash"):
            content = self.payload(model, self.LONG, monkeypatch)["messages"][0]["content"]
            assert content == [{"type": "text", "text": self.LONG, "cache_control": {"type": "ephemeral"}}]

    def test_other_models_get_the_plain_string_they_always_got(self, monkeypatch):
        for model in ("openai/gpt-5-nano", "deepseek/deepseek-v4-flash-latest", "qwen/qwen3.7-flash"):
            assert self.payload(model, self.LONG, monkeypatch)["messages"][0]["content"] == self.LONG

    def test_nothing_changes_without_the_layout_or_for_a_short_system_message(self, monkeypatch):
        assert self.payload("anthropic/claude-haiku-5.5", self.LONG, monkeypatch, layout=None)["messages"][0]["content"] == self.LONG
        assert self.payload("anthropic/claude-haiku-5.5", "short", monkeypatch)["messages"][0]["content"] == "short"

    def test_the_user_message_is_never_marked(self, monkeypatch):
        payload = self.payload("anthropic/claude-haiku-5.5", self.LONG, monkeypatch)
        assert payload["messages"][1] == {"role": "user", "content": "the goal"}


class TestHistoryRendering:
    def steps(self, a, b):
        return [al.LoopStep(iteration=0, tool_name="delentia_read_repo_file", tool_args={"relative_path": "a.md"}, tool_result={"content_text": a}, llm_reasoning=""),
                al.LoopStep(iteration=1, tool_name="delentia_read_repo_file", tool_args={"relative_path": "b.md"}, tool_result={"content_text": b}, llm_reasoning="")]

    def plain(self, steps):
        return "\n".join(al._render_turn_full(s) for s in steps)

    def test_a_patch_that_is_not_clearly_smaller_is_never_used_even_for_thai_text(self):
        thai_a = "การประชุมวันนี้พูดถึงงบประมาณและแผนงานของฝ่ายจัดซื้อ " * 120
        thai_b = "รายงานผลการตรวจรับงานซ่อมบำรุงระบบปรับอากาศชั้นสาม " * 120
        steps = self.steps(thai_a, thai_b)
        assert al._approx_tokens(al.render_history(steps)) <= al._approx_tokens(self.plain(steps))

    def test_a_patch_that_is_clearly_smaller_is_still_used(self):
        body = "ราคารวม 12,500 บาท ระยะเวลา 5 วัน เงื่อนไขยืนราคา 30 วัน " * 80
        steps = self.steps(body, body + " แก้ไข")
        rendered = al.render_history(steps)
        assert al._approx_tokens(rendered) <= al._approx_tokens(self.plain(steps))

    def test_the_full_history_can_still_be_reconstructed_from_the_chain(self):
        steps = self.steps("aaa " * 400, "aaa " * 400 + "bbb")
        text = al.reconstruct_full_history_text(steps)
        assert "bbb" in text and "a.md" in text and "b.md" in text

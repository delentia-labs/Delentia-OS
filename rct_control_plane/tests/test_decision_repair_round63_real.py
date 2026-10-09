"""
Round 63: a model that names the right tool in the wrong field is understood, and nothing else is loosened.

Found by research/runner.py (--policy real, qwen2.5:7b, ranked compact menu): in 4 of 6 episodes the model wrote
{"action": "delentia_read_repo_file", "tool_args": {...}}, the loop saw a call with no tool name, and the episode ended as stuck_repeating
with no tool used. The repair is only for a tool the model was actually shown; the repaired call still goes through the gate.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json


from rct_control_plane.autonomous_loop import decide_next_action, repair_decision_format

TOOLS = [{"name": "delentia_read_repo_file", "description": "read a file", "input_schema": {}},
         {"name": "delentia_write_repo_file", "description": "write a file", "input_schema": {}}]
NAMES = {t["name"] for t in TOOLS}


class Provider:
    def __init__(self, reply):
        self.reply = reply

    async def complete(self, prompt, *args, **kwargs):
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def decide(reply):
    return asyncio.run(decide_next_action("read the quote", [], TOOLS, Provider(reply), ""))


class TestRepair:
    def test_a_tool_name_in_the_action_field_becomes_a_call(self):
        d = decide({"action": "delentia_read_repo_file", "tool_args": {"relative_path": "quotes/a.md"}, "reasoning": "r"})
        assert (d["action"], d["tool_name"], d["tool_args"]) == ("call_tool", "delentia_read_repo_file", {"relative_path": "quotes/a.md"})
        assert "action field" in d["format_repaired"]

    def test_an_invented_action_word_with_a_valid_tool_name_becomes_a_call(self):
        d = decide({"action": "use_tool", "tool_name": "delentia_read_repo_file", "tool_args": {}})
        assert d["action"] == "call_tool" and d["tool_name"] == "delentia_read_repo_file" and "use_tool" in d["format_repaired"]

    def test_a_well_formed_decision_is_untouched(self):
        for reply in ({"action": "call_tool", "tool_name": "delentia_read_repo_file", "tool_args": {}},
                      {"action": "finish", "final_answer": "done"},
                      {"action": "call_tools", "calls": []}):
            d = decide(reply)
            assert "format_repaired" not in d and d["action"] == reply["action"]

    def test_a_name_that_is_not_a_shown_tool_is_not_turned_into_a_call(self):
        d = decide({"action": "delentia_run_sandboxed_command", "tool_args": {"command": "rm -rf /"}})
        assert d["action"] == "delentia_run_sandboxed_command" and d["tool_name"] is None and "format_repaired" not in d

    def test_an_unknown_action_with_an_unknown_tool_name_is_left_alone(self):
        d = decide({"action": "do_it", "tool_name": "delentia_invented"})
        assert d["action"] == "do_it" and "format_repaired" not in d

    def test_an_explicit_tool_name_is_never_overwritten_by_the_action_field(self):
        d = repair_decision_format({"action": "delentia_read_repo_file", "tool_name": "delentia_write_repo_file", "tool_args": {}}, NAMES)
        assert d["tool_name"] == "delentia_write_repo_file" and d["action"] == "call_tool"      # the explicit field wins; the action word is just a shape error

    def test_text_that_is_not_json_still_ends_as_a_parse_error(self):
        d = decide("I will read the file now")
        assert d.get("parse_error") is True and d["action"] == "finish"


class TestThroughTheLoop:
    """The repaired call is an ordinary call: it reaches the gate and the real tool."""

    def test_the_repaired_call_runs_the_tool_through_the_governed_loop(self, tmp_path, monkeypatch):
        from test_governed_autonomous_loop_real import _FakeMCP, _FakeToolResult, _loop

        class Tools(_FakeMCP):
            async def list_tools(self):
                return [type("T", (), {"name": t["name"], "description": t["description"], "input_schema": {}})() for t in TOOLS]

            async def call_tool(self, name, args):
                self.dispatched.append((name, args))
                return _FakeToolResult(json.dumps({"path": args.get("relative_path"), "content_text": "x"}))

        replies = iter([{"action": "delentia_read_repo_file", "tool_args": {"relative_path": "quotes/a.md"}, "reasoning": "r"},
                        {"action": "finish", "reasoning": "d", "final_answer": "I read quotes/a.md and the read the quote is done"}])

        async def provider_complete(self, prompt, *args, **kwargs):
            return json.dumps(next(replies))

        from rct_control_plane import llm_provider
        monkeypatch.setattr(llm_provider.OllamaProvider, "complete", provider_complete, raising=True)
        mcp = Tools()
        loop = _loop(tmp_path, "repair", mcp=mcp, llm_provider=llm_provider.OllamaProvider(model="x"))
        result = asyncio.run(loop.run("read the quote quotes/a.md"))
        assert mcp.dispatched and mcp.dispatched[0][0] == "delentia_read_repo_file"
        assert result["stopped_reason"] == "llm_finished"


class TestACallThatNamedNoTool:
    """Seen with the compact menu: the model wrote tool_args but no tool name, twice, and was then stopped as repeating. The feedback now says what was wrong."""

    SPECS = [{"name": "delentia_read_repo_file", "description": "read", "input_schema": {"properties": {"relative_path": {}, "max_bytes": {}}}},
             {"name": "delentia_write_repo_file", "description": "write", "input_schema": {"properties": {"relative_path": {}, "content_text": {}}}},
             {"name": "delentia_recall", "description": "recall", "input_schema": {"properties": {"query": {}}}}]

    def test_the_message_says_the_name_was_missing_and_offers_the_tools_that_take_those_arguments(self):
        from rct_control_plane.autonomous_loop import unknown_tool_result
        out = unknown_tool_result(None, [t["name"] for t in self.SPECS], tool_args={"relative_path": "quotes/a.md", "max_bytes": 100}, tools=self.SPECS)
        assert "named no tool" in out["error"] and out["did_you_mean"][0] == "delentia_read_repo_file"
        assert "tool_name" in out["hint"] and "delentia_read_repo_file" in out["hint"]

    def test_suggestions_are_only_suggestions_nothing_is_called_on_the_models_behalf(self, tmp_path, monkeypatch):
        from test_governed_autonomous_loop_real import _FakeMCP, _FakeToolResult, _loop

        class Tools(_FakeMCP):
            async def list_tools(self):
                return [type("T", (), {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]})() for t in TestACallThatNamedNoTool.SPECS]

            async def call_tool(self, name, args):
                self.dispatched.append((name, args))
                return _FakeToolResult("{}")

        replies = iter([{"action": "call_tool", "tool_args": {"relative_path": "quotes/a.md"}, "reasoning": "r"},
                        {"action": "finish", "reasoning": "d", "final_answer": "I could not read it"}])

        async def complete(self, prompt, *args, **kwargs):
            return json.dumps(next(replies))

        from rct_control_plane import llm_provider
        monkeypatch.setattr(llm_provider.OllamaProvider, "complete", complete, raising=True)
        mcp = Tools()
        result = asyncio.run(_loop(tmp_path, "noname", mcp=mcp, llm_provider=llm_provider.OllamaProvider(model="x")).run("read the quote quotes/a.md"))
        assert mcp.dispatched == []                                       # nothing ran
        first = result["steps"][0]["tool_result"]
        assert "named no tool" in first["error"] and first["did_you_mean"][0] == "delentia_read_repo_file"

    def test_a_real_unknown_name_keeps_the_old_message(self):
        from rct_control_plane.autonomous_loop import unknown_tool_result
        out = unknown_tool_result("delentia_read_file", [t["name"] for t in self.SPECS], tool_args={}, tools=self.SPECS)
        assert out["error"].startswith("Unknown tool") and "delentia_read_repo_file" in out["did_you_mean"]

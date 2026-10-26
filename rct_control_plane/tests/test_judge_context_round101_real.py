"""
Round 101: the context the agent hands the clarity judge (judge_context.py). The measured variant of Round 99 (set 3) made real, opt-in.

The builder is pure and is tested as such; the loop test uses the real governed loop, a real workspace folder and a judge that records exactly what it was shown.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop
from rct_control_plane import judge_context as jc, mcp_server, rct7_judge
from test_governed_autonomous_loop_real import _FakeMCP, _loop


# ------------------------------------------------------------------ the pure builder
def test_with_nothing_to_show_the_text_says_so():
    assert jc.build() == jc.NOTHING


def test_every_section_appears_only_when_it_has_something():
    text = jc.build(recent_turns="User: send it to Mali", pending_tools=["delentia_cron_delete"], memories=["Mali is the new colleague"], rules=["never delete without asking"],
                    files=["docs/", "README.md"], capabilities=["search the web"])
    for expect in ("Earlier in the chat: User: send it to Mali", "waiting for this person's approval: delentia_cron_delete", "Standing rules this person set: never delete without asking",
                   "may be related: Mali is the new colleague", "Files in the workspace (names only): docs/, README.md", "look something up without asking: search the web"):
        assert expect in text
    assert "Standing rules" not in jc.build(files=["a.md"])


def test_every_section_is_bounded():
    text = jc.build(recent_turns="x" * 5000, pending_tools=[f"tool{i}" for i in range(50)], memories=["m" * 1000] * 20, rules=["r" * 1000] * 20, files=[f"f{i}.md" for i in range(100)])
    assert len(text) <= jc.MAX_TOTAL_CHARS
    assert text.count("tool") <= jc.MAX_PENDING + 1


def test_capabilities_are_said_only_when_a_tool_for_them_exists():
    assert jc.capability_phrases(["delentia_read_repo_file"]) == ["read and search the files of the workspace"]
    assert "search the web" not in jc.capability_phrases(["delentia_read_repo_file", "delentia_recall"])
    assert "search the web" in jc.capability_phrases(["delentia_web_search"])
    assert jc.capability_phrases([]) == []


def test_workspace_names_have_no_contents_no_hidden_and_no_secret_looking_names(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "report.md").write_text("SECRET CONTENT inside the file", encoding="utf-8")
    (tmp_path / ".env").write_text("KEY=1", encoding="utf-8")
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")
    (tmp_path / "id_rsa").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    names = jc.workspace_names(tmp_path)
    joined = " ".join(names)
    assert "docs/ (report.md)" in joined and "README.md" in joined
    assert "SECRET CONTENT" not in joined and ".env" not in joined and "credentials" not in joined and "id_rsa" not in joined
    assert jc.workspace_names(None) == [] and jc.workspace_names(tmp_path / "missing") == []


def test_the_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv(jc.ENV, raising=False)
    assert not jc.enabled()
    monkeypatch.setenv(jc.ENV, "on")
    assert jc.enabled()


# ------------------------------------------------------------------ in the loop
class Recorder:
    """A judge that says 'clear' and keeps the system prompt and the prompt it was shown."""

    def __init__(self):
        self.calls = []

    async def complete(self, prompt, system_prompt=None, temperature=0.0, max_tokens=300, json_mode=False):
        self.calls.append((system_prompt, prompt))
        return json.dumps({"clear": True, "unknowns": []})


@pytest.fixture
def loop_env(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "q3_sales_report.md").write_text("PRIVATE NUMBERS 12345", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("DELENTIA_RCT7_JUDGE", "propose")
    monkeypatch.setenv("DELENTIA_ASK_AND_WAIT", "1")

    async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
        return {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)

    def go(goal, judge, name="jc1"):
        loop = _loop(tmp_path, name, mcp=_FakeMCP())
        loop._interactive = True
        loop._judge_provider_override = judge
        return loop, asyncio.run(loop.run(goal))
    return go


def test_without_the_switch_the_judge_sees_the_request_only(loop_env, monkeypatch):
    monkeypatch.delenv(jc.ENV, raising=False)
    judge = Recorder()
    loop_env("Send the report to the client", judge)
    system, prompt = judge.calls[0]
    assert system == rct7_judge.SYSTEM_REQUEST and "q3_sales_report" not in prompt


def test_with_the_switch_the_judge_sees_the_context_prompt_and_the_workspace_names_not_their_contents(loop_env, monkeypatch):
    monkeypatch.setenv(jc.ENV, "on")
    judge = Recorder()
    loop, result = loop_env("Send the report to the client", judge, name="jc2")
    system, prompt = judge.calls[0]
    assert system == rct7_judge.SYSTEM_REQUEST_CTX
    assert "q3_sales_report.md" in prompt and "PRIVATE NUMBERS" not in prompt
    assert "read and search the files of the workspace" in prompt
    with loop._persistence._connect() as conn:
        rows = [json.loads(r[0]) for r in conn.execute("SELECT changes FROM audit_trail WHERE entity_type='governed_loop_judge' AND action='request'")]
    assert rows and rows[0].get("prompt_version") == rct7_judge.context_prompt_version() and len(rows[0].get("context_sha256", "")) == 64
    assert result["stopped_reason"] == "llm_finished"


def test_a_pending_approval_of_another_person_never_reaches_the_judge(loop_env, monkeypatch):
    monkeypatch.setenv(jc.ENV, "on")
    from rct_control_plane.approvals import PendingActionStore
    judge = Recorder()
    loop = _loop(mcp_server.REPO_ROOT, "jc3", mcp=_FakeMCP())
    PendingActionStore(loop._persistence).create("someone-else", "g", "delentia_cron_delete", {"job_id": "x"})
    PendingActionStore(loop._persistence).create("jc3", "g", "delentia_write_repo_file", {"relative_path": "a.md"})
    text = jc.gather(loop, "anything")
    assert "delentia_write_repo_file" in text and "delentia_cron_delete" not in text
    assert judge.calls == []

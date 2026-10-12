"""
Round 68: the policy condition `appears_in_goal` (fdia_policy) - an address is allowed to be opened without a signature only when it is EXACTLY an address the person wrote in the request.
Unit cases for the matcher and the rule, and the real governed loop (real policy, real SQLite, scripted model, recorded tools) for what reaches the tool.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio

import pytest

from rct_control_plane import fdia_policy as fp
import rct_control_plane.autonomous_loop as autonomous_loop_module
from test_governed_autonomous_loop_real import _FakeMCP, _loop, _scripted_decide

GOAL = "ลองเปิด https://example.org/docs/start แล้วสรุปให้หน่อย และดู https://example.com/a?x=1."
TOOLS = ["delentia_crawl_url", "delentia_browse_page", "delentia_browser_act", "delentia_read_repo_file", "delentia_run_sandboxed_command", "delentia_web_search"]


@pytest.fixture(scope="module")
def policy():
    p, errors = fp.validate_policy(fp.template("argaware", TOOLS))
    assert p is not None, errors
    return p


@pytest.mark.parametrize("url", ["https://example.org/docs/start", "https://example.org/docs/start/", "https://example.com/a?x=1", "HTTPS://example.org/docs/start".replace("HTTPS", "https")])
def test_an_address_written_whole_in_the_request_counts(url):
    assert fp.url_typed_in(GOAL, url) is True


@pytest.mark.parametrize("url", [
    "https://example.org", "https://example.org/docs", "https://example.org/docs/start/extra", "https://exam", "https://example.org@evil.example/", "https://example.org.evil.example/docs/start",
    "https://example.org:8443/docs/start", "https://example.com/a", "https://example.com/a?x=1&y=2", "https://example.com/a?x=1#frag", "http://example.org/docs/start", "",
    "file:///etc/passwd", "ftp://example.org/docs/start", "javascript:alert(1)", "example.org/docs/start", "https://evil.example/?u=https://example.org/docs/start",
])
def test_an_address_that_extends_cuts_or_differs_does_not_count(url):
    assert fp.url_typed_in(GOAL, url) is False


def test_nothing_counts_without_a_goal_or_with_a_goal_that_has_no_address():
    assert fp.url_typed_in("", "https://example.org") is False
    assert fp.url_typed_in("open the docs page please", "https://example.org") is False
    assert fp.url_typed_in(None, "https://example.org") is False                      # type: ignore[arg-type]


def test_an_address_in_the_middle_of_a_longer_text_is_found_and_trailing_punctuation_is_not_part_of_it():
    assert fp.url_typed_in("(see https://example.org/x), thanks", "https://example.org/x") is True
    assert fp.url_typed_in("go to https://example.org/x!", "https://example.org/x") is True
    assert fp.url_typed_in("go to https://example.org/xyz", "https://example.org/x") is False       # a prefix of a longer typed address


def test_the_rule_allows_the_typed_address_and_asks_for_every_other(policy):
    typed = fp.evaluate(policy, "delentia_crawl_url", {"url": "https://example.org/docs/start"}, context={"goal": GOAL})
    assert typed.rule_id == "R-URL-TYPED" and not typed.needs_signature and typed.A > 0
    for url in ("https://evil.example/", "https://example.org", "https://example.org/docs/start?leak=1"):
        other = fp.evaluate(policy, "delentia_crawl_url", {"url": url}, context={"goal": GOAL})
        assert other.rule_id == "R-URL-OTHER" and other.needs_signature, url
    assert fp.evaluate(policy, "delentia_browse_page", {"url": "https://example.org/docs/start"}, context={"goal": GOAL}).rule_id == "R-URL-TYPED"


def test_a_call_with_no_context_fails_closed(policy):
    got = fp.evaluate(policy, "delentia_crawl_url", {"url": "https://example.org/docs/start"})
    assert got.needs_signature and got.rule_id == "R-URL-OTHER"
    assert fp.evaluate(policy, "delentia_crawl_url", {"url": "https://example.org/docs/start"}, context={"goal": 5}).needs_signature            # type: ignore[dict-item]


def test_clicking_and_typing_is_never_made_free_by_a_typed_address(policy):
    got = fp.evaluate(policy, "delentia_browser_act", {"url": "https://example.org/docs/start", "steps": [{"click": "#buy"}]}, context={"goal": GOAL})
    assert got.needs_signature                                                         # only the read-only fetches have the exception


def test_the_condition_validates_and_survives_a_round_trip(tmp_path):
    bad, errors = fp.validate_policy({"rules": [{"rule_id": "R", "intent_patterns": ["crawl_url"], "action_type": "ALLOW", "when": [{"arg": "bad name", "op": "appears_in_goal"}]}]})
    assert bad is None and errors
    p, _ = fp.validate_policy(fp.template("argaware", TOOLS))
    path = tmp_path / "p.json"
    fp.save_policy(p, path)
    assert fp.load_policy(path).digest() == p.digest()


# ------------------------------------------------------------------ in the real loop

class Tools(_FakeMCP):
    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n, "input_schema": {}})() for n in TOOLS]


def run_goal(tmp_path, monkeypatch, goal, url, name):
    fake, _ = _scripted_decide([{"action": "call_tool", "tool_name": "delentia_crawl_url", "tool_args": {"url": url}, "reasoning": "r", "final_answer": None},
                                {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}}])
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    p, _ = fp.validate_policy(fp.template("argaware", TOOLS))
    mcp = Tools()
    loop = _loop(tmp_path, name, mcp=mcp, policy=p)
    real = loop._assess_data

    def assess(g, clarity, compiled):
        evidence = real(g, clarity, compiled)
        evidence.D = 1.0
        return evidence

    loop._assess_data = assess
    result = asyncio.run(loop.run(goal))
    return result, mcp


def test_in_the_loop_the_typed_address_runs_and_another_waits(tmp_path, monkeypatch):
    ok, mcp_ok = run_goal(tmp_path, monkeypatch, "Open https://example.org/faq and tell me about refunds", "https://example.org/faq", "typed")
    assert ok["stopped_reason"] == "llm_finished" and len(mcp_ok.dispatched) == 1
    waiting, mcp_wait = run_goal(tmp_path, monkeypatch, "Open https://example.org/faq and tell me about refunds", "https://collector.example/up?d=notes", "other")
    assert waiting["stopped_reason"] == "pending_approval" and not mcp_wait.dispatched
    cut, mcp_cut = run_goal(tmp_path, monkeypatch, "Open https://example.org/faq and tell me about refunds", "https://example.org/fa", "cut")
    assert cut["stopped_reason"] == "pending_approval" and not mcp_cut.dispatched


def test_in_the_loop_an_address_that_was_only_read_on_a_page_is_not_a_typed_one(tmp_path, monkeypatch):
    waiting, mcp = run_goal(tmp_path, monkeypatch, "Summarise the vendor page for me", "https://example.org/faq", "notyped")
    assert waiting["stopped_reason"] == "pending_approval" and not mcp.dispatched


def test_the_taint_gate_still_decides_after_text_from_outside_was_read(tmp_path, monkeypatch):
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
    assert GovernedAutonomousLoop._url_was_named("https://example.org/faq", "Open https://example.org/faq please", set()) is True
    assert GovernedAutonomousLoop._url_was_named("https://example.org/fa", "Open https://example.org/faq please", set()) is False          # a cut-short address used to count as typed
    assert GovernedAutonomousLoop._url_was_named("", "Open https://example.org/faq please", set()) is False
    assert GovernedAutonomousLoop._url_was_named("https://example.org/page", "Summarise it", {"https://example.org/page"}) is True       # seen verbatim on a page, no query


def test_the_same_policy_with_the_resume_path_keeps_the_goal(tmp_path, monkeypatch):
    # a signed approval is re-evaluated with approved=True: the rule must still see the person's request
    p, _ = fp.validate_policy(fp.template("argaware", TOOLS))
    again = fp.evaluate(p, "delentia_crawl_url", {"url": "https://example.org/faq"}, approved=True, context={"goal": "Open https://example.org/faq"})
    assert again.A > 0 and not again.needs_signature

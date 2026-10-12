"""
Round 69: with no policy file the argument-aware starter judges tool calls (fdia_policy.effective_policy / default_policy). Real policy objects, the real tool registry and the real governed
loop (real SQLite, scripted model, recorded tools). The conftest turns the default OFF for the rest of the suite; these tests turn it on.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest

from rct_control_plane import fdia_policy as fp
import rct_control_plane.autonomous_loop as autonomous_loop_module
from test_governed_autonomous_loop_real import _FakeMCP, _loop, _scripted_decide

TOOLS = ["delentia_crawl_url", "delentia_read_repo_file", "delentia_run_sandboxed_command", "delentia_web_search"]


@pytest.fixture(autouse=True)
def _default_on(monkeypatch, tmp_path):
    monkeypatch.delenv(fp.DEFAULT_ENV, raising=False)
    monkeypatch.delenv("DELENTIA_RESEARCH_MODE", raising=False)
    monkeypatch.setenv(fp.POLICY_ENV, str(tmp_path / "no_such_policy.json"))


# ------------------------------------------------------------------ which policy judges

@pytest.mark.parametrize("value,expected", [(None, "argaware"), ("", "argaware"), ("none", ""), ("OFF", ""), ("0", ""), ("false", ""), ("careful", "careful"), ("strict", "strict"), ("balanced", "balanced"),
                                            ("argaware", "argaware"), ("nonsense", "argaware")])
def test_the_default_template_follows_the_setting(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(fp.DEFAULT_ENV, raising=False)
    else:
        monkeypatch.setenv(fp.DEFAULT_ENV, value)
    assert fp.default_template_name() == expected


def test_research_mode_never_gets_a_default_policy(monkeypatch):
    monkeypatch.setenv("DELENTIA_RESEARCH_MODE", "1")
    assert fp.default_template_name() == "" and fp.effective_policy() == (None, "none")


def test_no_file_means_the_default_and_a_file_always_wins(monkeypatch, tmp_path):
    policy, source = fp.effective_policy()
    assert source == "default" and policy is not None and policy.policy_id == "default-argaware"
    own, errors = fp.validate_policy(fp.template("strict", TOOLS))
    assert own is not None, errors
    path = tmp_path / "mine.json"
    fp.save_policy(own, path)
    monkeypatch.setenv(fp.POLICY_ENV, str(path))
    got, source = fp.effective_policy()
    assert source == "file" and got.digest() == own.digest() and got.policy_id != "default-argaware"


def test_the_setting_none_restores_the_old_behaviour(monkeypatch):
    monkeypatch.setenv(fp.DEFAULT_ENV, "none")
    assert fp.effective_policy() == (None, "none")


def test_a_broken_file_still_fails_closed_and_is_never_hidden_by_the_default(monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(fp.POLICY_ENV, str(bad))
    with pytest.raises(ValueError):
        fp.effective_policy()
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"rules": "nope"}), encoding="utf-8")
    monkeypatch.setenv(fp.POLICY_ENV, str(invalid))
    with pytest.raises(ValueError):
        fp.effective_policy()


def test_the_default_is_built_over_the_real_registry_and_is_cached():
    names = fp.registry_tool_names()
    assert len(names) >= 40 and "delentia_run_sandboxed_command" in names
    assert fp.default_policy() is fp.default_policy()


# ------------------------------------------------------------------ what it does

def test_a_tool_it_has_no_rule_for_is_left_to_the_floor_not_blocked_by_zero_trust():
    policy = fp.default_policy()
    assert policy.default_fallback_A == 1
    for name in ("mcp__files__read_file", "mcp__crm__create_contact", "delentia_a_tool_added_next_year"):
        got = fp.evaluate(policy, name, {"x": 1}, context={"goal": "do the thing"})
        assert got.A > 0, (name, got.reason)
    # an owner-written policy keeps zero trust (the fallback is the owner's to set)
    own, _ = fp.validate_policy(fp.template("argaware", TOOLS))
    assert fp.evaluate(own, "mcp__crm__create_contact", {}, context={"goal": "x"}).A == 0


def test_the_default_asks_for_what_the_template_asks_for_and_allows_what_it_allows():
    policy = fp.default_policy()
    ls = fp.evaluate(policy, "delentia_run_sandboxed_command", {"command": "ls -la src"}, context={"goal": "list src"})
    rm = fp.evaluate(policy, "delentia_run_sandboxed_command", {"command": "rm -rf build"}, context={"goal": "clean"})
    typed = fp.evaluate(policy, "delentia_crawl_url", {"url": "https://example.org/faq"}, context={"goal": "Open https://example.org/faq"})
    other = fp.evaluate(policy, "delentia_crawl_url", {"url": "https://collector.example/x"}, context={"goal": "Open https://example.org/faq"})
    assert not ls.needs_signature and rm.needs_signature and not typed.needs_signature and other.needs_signature


def test_the_default_gives_the_same_verdicts_as_the_argaware_starter_on_every_tool():
    names = fp.registry_tool_names()
    starter, _ = fp.validate_policy(fp.template("argaware", names))
    default = fp.default_policy()
    samples = [{"command": "ls"}, {"command": "rm x"}, {"url": "https://a.example"}, {"path": "notes.txt", "content": "x"}, {"query": "weather"}, {}]
    for tool in names:
        for args in samples:
            a = fp.evaluate(starter, tool, args, context={"goal": "https://a.example"})
            b = fp.evaluate(default, tool, args, context={"goal": "https://a.example"})
            assert (a.A > 0, a.needs_signature, a.rule_id) == (b.A > 0, b.needs_signature, b.rule_id), (tool, args)


# ------------------------------------------------------------------ in the real loop

class Tools(_FakeMCP):
    async def list_tools(self):
        return [type("T", (), {"name": n, "description": n, "input_schema": {}})() for n in TOOLS]


def run_goal(tmp_path, monkeypatch, goal, url, name):
    fake, _ = _scripted_decide([{"action": "call_tool", "tool_name": "delentia_crawl_url", "tool_args": {"url": url}, "reasoning": "r", "final_answer": None},
                                {"action": "finish", "reasoning": "done", "final_answer": "ok", "tool_name": None, "tool_args": {}}])
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    mcp = Tools()
    loop = _loop(tmp_path, name, mcp=mcp)
    real = loop._assess_data

    def assess(g, clarity, compiled):
        evidence = real(g, clarity, compiled)
        evidence.D = 1.0
        return evidence

    loop._assess_data = assess
    result = asyncio.run(loop.run(goal))
    return result, mcp, loop


def gate_rows(loop):
    with loop._persistence._connect() as conn:
        rows = conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'governed_loop_fdia_gate'").fetchall()
    return [json.loads(r[0]) for r in rows]


def test_in_the_loop_the_default_policy_judges_with_no_file(tmp_path, monkeypatch):
    goal = "Open https://example.org/faq and tell me about refunds"
    ok, mcp_ok, loop_ok = run_goal(tmp_path, monkeypatch, goal, "https://example.org/faq", "typed")
    assert ok["stopped_reason"] == "llm_finished" and len(mcp_ok.dispatched) == 1
    waiting, mcp_wait, loop_wait = run_goal(tmp_path, monkeypatch, goal, "https://collector.example/up?d=notes", "other")
    assert waiting["stopped_reason"] == "pending_approval" and not mcp_wait.dispatched
    rows = gate_rows(loop_wait)
    assert rows and all(r["policy_source"] == "default" for r in rows)
    assert rows[-1]["policy"]["rule_id"] == "R-URL-OTHER"


def test_with_the_setting_none_the_same_request_runs_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv(fp.DEFAULT_ENV, "none")
    done, mcp, loop = run_goal(tmp_path, monkeypatch, "Open https://example.org/faq and tell me about refunds", "https://collector.example/up?d=notes", "none")
    assert done["stopped_reason"] == "llm_finished" and len(mcp.dispatched) == 1
    assert all(r["policy_source"] == "none" for r in gate_rows(loop))


def test_an_owner_file_is_named_as_the_source(tmp_path, monkeypatch):
    own, _ = fp.validate_policy(fp.template("balanced", ["delentia_crawl_url", "delentia_read_repo_file"] + TOOLS))
    path = tmp_path / "owner.json"
    fp.save_policy(own, path)
    monkeypatch.setenv(fp.POLICY_ENV, str(path))
    done, _mcp, loop = run_goal(tmp_path, monkeypatch, "Open https://example.org/faq", "https://example.org/faq", "owner")
    assert done["stopped_reason"] == "llm_finished"
    assert all(r["policy_source"] == "file" for r in gate_rows(loop))


def test_a_broken_policy_file_stops_the_loop_even_though_a_default_exists(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(fp.POLICY_ENV, str(bad))
    done, mcp, _loop_ = run_goal(tmp_path, monkeypatch, "Open https://example.org/faq", "https://example.org/faq", "broken")
    assert not mcp.dispatched and done["stopped_reason"] != "llm_finished"


# ------------------------------------------------------------------ an address a page showed word for word (search, then open a result)

SEEN = ["https://news.example/q3-report", "https://news.example/q3-report?utm=a", "https://user:pw@news.example/x", "ftp://news.example/f"]


def test_an_address_seen_verbatim_in_this_episode_may_be_opened_without_a_signature():
    policy = fp.default_policy()
    ctx = {"goal": "Find the Q3 report and summarise it", "seen_urls": SEEN}
    ok = fp.evaluate(policy, "delentia_crawl_url", {"url": "https://news.example/q3-report"}, context=ctx)
    assert ok.rule_id == "R-URL-TYPED" and not ok.needs_signature
    assert not fp.evaluate(policy, "delentia_crawl_url", {"url": "https://news.example/q3-report/"}, context=ctx).needs_signature      # a trailing slash is the same page
    for url in ("https://news.example/q3-report?utm=a",                  # a query string is a place to hide data: never "seen", even when the page showed it
                "https://user:pw@news.example/x", "https://news.example/q3-report?x=1", "https://news.example/other", "https://evil.example/q3-report", "ftp://news.example/f", ""):
        got = fp.evaluate(policy, "delentia_crawl_url", {"url": url}, context=ctx)
        assert got.needs_signature, url
    assert fp.evaluate(policy, "delentia_crawl_url", {"url": "https://news.example/q3-report"}, context={"goal": "x"}).needs_signature      # nothing seen, nothing typed
    assert fp.evaluate(policy, "delentia_crawl_url", {"url": "https://news.example/q3-report"}, context={"goal": "x", "seen_urls": 5}).needs_signature     # a malformed context fails closed
    assert fp.evaluate(policy, "delentia_browser_act", {"url": "https://news.example/q3-report", "steps": [{"click": "#buy"}]}, context=ctx).needs_signature    # clicking is never freed


def test_the_taint_gate_and_the_policy_use_the_same_definition_of_a_named_address():
    from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop as G
    goal = "Open https://example.org/faq"
    for url, seen in [("https://example.org/faq", set()), ("https://example.org/fa", set()), ("https://news.example/a", {"https://news.example/a"}), ("https://news.example/a?q=1", {"https://news.example/a?q=1"}),
                      ("", {""}), ("https://news.example/a/", {"https://news.example/a"})]:
        assert G._url_was_named(url, goal, seen) == fp.address_named(url, goal, seen), (url, seen)


# ------------------------------------------------------------------ what the default adds against a hijacked model (scripts/measure_injection_defence.py)

def test_the_default_policy_alone_stops_most_of_the_attacks_the_taint_gate_stops_and_breaks_no_legitimate_workflow(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    import measure_injection_defence as mid
    monkeypatch.setenv(fp.DEFAULT_ENV, "none")
    (tmp_path / "floor").mkdir()
    (tmp_path / "default").mkdir()
    floor_only = asyncio.run(mid.measure(tmp_path / "floor"))
    monkeypatch.delenv(fp.DEFAULT_ENV)
    with_default = asyncio.run(mid.measure(tmp_path / "default"))
    assert floor_only["side_effects_without_the_gate"] >= 8                 # Round 58: without the taint gate (and with no policy) these attacks ran
    assert with_default["side_effects_without_the_gate"] <= floor_only["side_effects_without_the_gate"] // 2           # measured 18 -> 3 of 23: the policy alone stops most of them
    assert with_default["side_effects_with_the_gate"] == 0 and with_default["stopped_for_a_signature_with_the_gate"] == 23
    assert with_default["legitimate_ok"] == with_default["legitimate_workflows"] == 6        # nothing the person legitimately asked for needs a signature because of the default

"""RCT-7 round 98: the model as PROPOSER (rct7_judge.py) for R1/R5 (judge), R7 (critic) and R4 (cite-and-verify).

Criteria written before the code: research/rct7_round98_criteria.md. Real GovernedAutonomousLoop, real SQLite, real ClarificationStore. The only fake is the provider that answers the judge's
questions (and the scripted model that drives the loop). What is proved here is the SAFETY SHAPE: a proposal never acts, a model that cites nothing the request says is dropped, a broken
model changes nothing, a citation is checked by code. How well a real model judges is measured separately (DEV, local models) and is not claimed here.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop
from rct_control_plane import mcp_server, rct7_judge
from rct_control_plane.clarifications import ClarificationStore
from rct_control_plane.tests.test_governed_autonomous_loop_real import _FakeMCP, _FakeToolResult, _loop


def finish(text):
    return {"action": "finish", "reasoning": "done", "final_answer": text, "tool_name": None, "tool_args": {}}


class ReadMCP(_FakeMCP):
    """A tool server with one real-looking read tool, so the episode has evidence for the chain."""

    def __init__(self, files):
        super().__init__()
        self.files = files

    async def list_tools(self):
        return [type("T", (), {"name": "delentia_read_repo_file", "description": "read a file", "input_schema": {}})()]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        path = str(args.get("relative_path"))
        return _FakeToolResult(json.dumps({"path": path, "content_text": self.files.get(path, "")}))


class FakeJudge:
    """Answers the judge, the critic and the chain question from a script, and counts what it was asked."""

    def __init__(self, request=None, result=None, chain=None, boom=False):
        self.request, self.result, self.chain, self.boom = request, result, chain, boom
        self.asked = []

    async def complete(self, prompt, system_prompt=None, temperature=0.0, max_tokens=300, json_mode=False):
        self.asked.append("request" if system_prompt == rct7_judge.SYSTEM_REQUEST else "result" if system_prompt == rct7_judge.SYSTEM_RESULT else "chain")
        if self.boom:
            raise RuntimeError("judge model unreachable")
        reply = {"request": self.request, "result": self.result, "chain": self.chain}[self.asked[-1]]
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


UNCLEAR = {"clear": False, "unknowns": [{"question": "Which report do you mean?", "about": "the report"}, {"question": "Which client?", "about": "the client"}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("DELENTIA_RCT7_JUDGE", "propose")
    monkeypatch.delenv("DELENTIA_RCT7_CHAIN", raising=False)
    monkeypatch.delenv("DELENTIA_ASK_AND_WAIT", raising=False)
    monkeypatch.delenv("DELENTIA_RCT7_JUDGE_CITE_GUARD", raising=False)
    seen = []

    def go(goal, decisions, judge=None, name="j98", interactive=True, loop=None, mcp=None, **loop_kwargs):
        script = list(decisions)

        async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
            seen.append(goal_)
            return dict(script.pop(0) if script else finish("done"))
        monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)
        the_loop = loop or _loop(tmp_path, name, mcp=mcp or _FakeMCP(), **loop_kwargs)
        the_loop._interactive = interactive
        if judge is not None:
            the_loop._judge_provider_override = judge
        return the_loop, asyncio.run(the_loop.run(goal))
    go.seen = seen
    go.root = tmp_path
    return go


# ------------------------------------------------------------------------------------------------------------------- the cite guard (pure)
def test_a_phrase_must_occur_in_the_text_and_a_short_one_must_be_a_whole_word():
    assert rct7_judge.cites("Send the report to the client", "the  Report")                  # case and whitespace do not matter
    assert not rct7_judge.cites("Send the report to the client", "the invoice")
    assert rct7_judge.cites("Make it faster", "it") and not rct7_judge.cites("Write something", "it")     # "it" is not inside "Write"
    assert rct7_judge.cites("แก้ไฟล์ให้หน่อย", "แก้ไฟล์") and not rct7_judge.cites("แก้ไฟล์ให้หน่อย", "ลบไฟล์")
    assert not rct7_judge.cites("anything", "") and not rct7_judge.cites("anything", "a")


def test_the_request_verdict_keeps_only_unknowns_that_cite_the_request():
    reply = json.dumps({"clear": False, "unknowns": [{"question": "Which report?", "about": "the report"}, {"question": "What is your budget?", "about": "the budget"}]})
    verdict = rct7_judge.parse_request_verdict(reply, "Send the report to the client", guard=True)
    assert verdict.clear is False and [u.about for u in verdict.unknowns] == ["the report"] and verdict.dropped == 1
    open_ = rct7_judge.parse_request_verdict(reply, "Send the report to the client", guard=False)
    assert len(open_.unknowns) == 2 and open_.dropped == 0


def test_with_every_unknown_dropped_the_verdict_is_no_opinion_not_unclear():
    reply = json.dumps({"clear": False, "unknowns": [{"question": "What is your budget?", "about": "the budget"}]})
    verdict = rct7_judge.parse_request_verdict(reply, "Send the report", guard=True)
    assert verdict.clear is None and verdict.dropped == 1
    bare = rct7_judge.parse_request_verdict(json.dumps({"clear": False, "unknowns": ["Which one?"]}), "Send the report", guard=True)
    assert bare.clear is None                                                                  # a bare question cites nothing


def test_unreadable_or_malformed_replies_are_no_opinion_and_a_clear_request_has_no_questions():
    for reply in ("", "not json", "[]", json.dumps({"clear": "yes"}), json.dumps({"unknowns": []})):
        assert rct7_judge.parse_request_verdict(reply, "x y z").clear is None
    assert rct7_judge.parse_request_verdict(json.dumps({"clear": True, "unknowns": [{"question": "q", "about": "x"}]}), "x").unknowns == []


def test_questions_are_limited_in_number_and_length():
    items = [{"question": "q" * 1000, "about": "the report"} for _ in range(10)]
    verdict = rct7_judge.parse_request_verdict(json.dumps({"clear": False, "unknowns": items}), "Send the report", guard=True)
    assert len(verdict.unknowns) == rct7_judge.MAX_QUESTIONS and all(len(u.question) <= rct7_judge.MAX_QUESTION_CHARS for u in verdict.unknowns)


def test_the_result_verdict_is_guarded_the_same_way():
    reply = json.dumps({"meets": False, "unmet": [{"part": "their colours", "why": "no colours given"}, {"part": "the weather", "why": "not mentioned"}]})
    verdict = rct7_judge.parse_result_verdict(reply, "List three fruits and their colours")
    assert verdict.meets is False and [u.part for u in verdict.unmet] == ["their colours"] and verdict.dropped == 1
    assert rct7_judge.parse_result_verdict(json.dumps({"meets": False, "unmet": [{"part": "the weather", "why": "x"}]}), "List fruits").meets is None


def test_a_judge_that_is_down_gives_no_opinion():
    verdict = asyncio.run(rct7_judge.judge_request(FakeJudge(boom=True), "Send the report"))
    assert verdict.clear is None and verdict.error == "RuntimeError"
    assert asyncio.run(rct7_judge.judge_result(FakeJudge(boom=True), "a", "b")).meets is None


# ------------------------------------------------------------------------------------------------------------------- R1/R5 in the loop
def test_by_default_nothing_is_asked_of_a_model(env, monkeypatch):
    monkeypatch.delenv("DELENTIA_RCT7_JUDGE", raising=False)
    judge = FakeJudge(request=UNCLEAR)
    _, result = env("Send the report to the client", [finish("done")], judge)
    assert judge.asked == [] and result["stopped_reason"] == "llm_finished"


def test_an_unclear_request_stops_before_the_first_model_call_with_a_question_that_says_a_model_proposed_it(env):
    judge = FakeJudge(request=UNCLEAR)
    loop, result = env("Send the report to the client", [finish("never reached")], judge)
    assert result["stopped_reason"] == "needs_clarification" and env.seen == [] and judge.asked == ["request"]
    assert "A model that read your request proposes" in result["clarification_question"] and "Which report do you mean?" in result["clarification_question"]
    pending = ClarificationStore(loop._persistence).list(namespace="j98", status="PENDING")
    assert len(pending) == 1 and pending[0].kind == "before_act" and pending[0].criterion == "model_unclear"
    assert result["judge"]["unknowns"][0]["about"] == "the report"


def test_a_clear_request_goes_on_after_one_question_to_the_judge(env):
    judge = FakeJudge(request={"clear": True, "unknowns": []})
    _, result = env("What is 17 x 23?", [finish("391")], judge)
    assert result["stopped_reason"] == "llm_finished" and judge.asked == ["request", "result"]     # one question before acting, one review of the answer


def test_the_judge_is_not_asked_where_nobody_is_waiting(env):
    judge = FakeJudge(request=UNCLEAR)
    _, result = env("Send the report to the client", [finish("done")], judge, interactive=False)
    assert judge.asked == [] and result["stopped_reason"] == "llm_finished"


def test_the_judge_is_not_asked_about_a_request_that_carries_outside_text(env):
    judge = FakeJudge(request=UNCLEAR)
    _, result = env("Send the report to the client", [finish("done")], judge, initial_taint="webhook payload")
    assert judge.asked == [] and result["stopped_reason"] == "llm_finished"


def test_a_broken_or_uncitable_judge_changes_nothing(env):
    _, broken = env("Send the report to the client", [finish("done")], FakeJudge(boom=True), name="b1")
    assert broken["stopped_reason"] == "llm_finished"
    invented = FakeJudge(request={"clear": False, "unknowns": [{"question": "What is the budget?", "about": "the budget"}]})
    _, dropped = env("Send the report to the client", [finish("done")], invented, name="b2")
    assert dropped["stopped_reason"] == "llm_finished" and invented.asked[0] == "request"


def test_without_the_guard_the_invented_question_does_stop_which_is_why_the_guard_is_on(env, monkeypatch):
    monkeypatch.setenv("DELENTIA_RCT7_JUDGE_CITE_GUARD", "off")
    invented = FakeJudge(request={"clear": False, "unknowns": [{"question": "What is the budget?", "about": "the budget"}]})
    _, result = env("Send the report to the client", [finish("done")], invented, name="b3")
    assert result["stopped_reason"] == "needs_clarification"                                  # negative control for the guard


def test_after_the_person_answered_the_request_runs_and_the_judge_is_not_asked_again(env):
    judge = FakeJudge(request=UNCLEAR)
    loop, first = env("Send the report to the client", [finish("x")], judge)
    ClarificationStore(loop._persistence).answer(first["clarification_id"], "j98", "the Q3 report, to Acme")
    judge2 = FakeJudge(request=UNCLEAR)
    env.seen.clear()
    _, second = env("Send the report to the client", [finish("sent")], judge2, loop=loop)
    assert second["stopped_reason"] == "llm_finished" and "request" not in judge2.asked and "Person's answer" in env.seen[0]


def test_the_same_request_sent_again_without_an_answer_is_taken_as_meant(env):
    loop, first = env("Send the report to the client", [finish("x")], FakeJudge(request=UNCLEAR))
    judge2 = FakeJudge(request=UNCLEAR)
    _, second = env("Send the report to the client", [finish("sent")], judge2, loop=loop)
    assert second["stopped_reason"] == "llm_finished" and "request" not in judge2.asked        # no second question to someone who ignored the first
    assert ClarificationStore(loop._persistence).get(first["clarification_id"]).extra["continued_as"] == "accepted"


def test_a_person_who_keeps_dismissing_the_questions_is_not_asked_by_the_model_any_more(env):
    loop, _ = env("What is 2+2?", [finish("4")], FakeJudge(request={"clear": True, "unknowns": []}), name="rg")
    store = ClarificationStore(loop._persistence)
    for i in range(6):
        q = store.create("rg", "before_act", "model_unclear", f"q{i}", original_goal=f"goal {i}")
        store.cancel(q.clarification_id, "rg")
    judge = FakeJudge(request=UNCLEAR)
    _, result = env("Send the report to the client", [finish("done")], judge, loop=loop)
    assert judge.asked == [] and result["stopped_reason"] == "llm_finished"


# ------------------------------------------------------------------------------------------------------------------- R7 in the loop
def test_an_answer_that_misses_a_cited_part_stops_with_a_question(env):
    verdict = {"meets": False, "unmet": [{"part": "their colours", "why": "no colours are given"}]}
    judge = FakeJudge(result=verdict)
    loop, result = env("List three fruits and their colours", [finish("Apple, banana, mango.")], judge)
    assert result["stopped_reason"] == "needs_clarification" and judge.asked[-1] == "result"
    assert "A model compared the result with your request" in result["clarification_question"] and "their colours" in result["clarification_question"]
    pending = ClarificationStore(loop._persistence).list(namespace="j98", status="PENDING")
    assert pending[0].kind == "mismatch" and pending[0].criterion == "semantic"
    assert result["semantic_check"]["meets"] is False


def test_an_answer_that_meets_the_request_is_recorded_and_returned(env):
    judge = FakeJudge(result={"meets": True, "unmet": []})
    _, result = env("List three fruits", [finish("Apple, banana, mango.")], judge)
    assert result["stopped_reason"] == "llm_finished" and result["semantic_check"]["meets"] is True


def test_an_unmet_part_that_cites_nothing_of_the_request_cannot_stop_the_episode(env):
    judge = FakeJudge(result={"meets": False, "unmet": [{"part": "the weather forecast", "why": "missing"}]})
    _, result = env("List three fruits", [finish("Apple, banana, mango.")], judge)
    assert result["stopped_reason"] == "llm_finished" and result["semantic_check"]["meets"] is None


def test_the_critic_adds_to_the_rules_and_never_replaces_them(env):
    judge = FakeJudge(result={"meets": True, "unmet": []})
    english = "All of the tests passed and no errors were found in the system, and the time taken fell by about half, so this setting is recommended."
    _, result = env("สรุปผลการทดสอบเป็นภาษาไทย", [finish(english)], judge)
    assert result["stopped_reason"] == "needs_clarification" and "result" not in judge.asked   # the rule saw the difference first; the model was not asked to review the answer


def test_the_critic_does_not_run_where_nobody_is_waiting_or_when_it_is_off(env, monkeypatch):
    judge = FakeJudge(result={"meets": False, "unmet": [{"part": "List three fruits", "why": "x"}]})
    _, a = env("List three fruits", [finish("Apple")], judge, interactive=False)
    assert judge.asked == [] and a["stopped_reason"] == "llm_finished"
    monkeypatch.delenv("DELENTIA_RCT7_JUDGE", raising=False)
    _, b = env("List three fruits", [finish("Apple")], judge, name="off")
    assert judge.asked == [] and b["stopped_reason"] == "llm_finished"


# ------------------------------------------------------------------------------------------------------------------- R4: evidence
STEPS = [{"tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "pyproject.toml"}, "tool_result": {"path": "pyproject.toml", "content_text": 'name = "sample-service"\r\nversion = "0.1.0"\r\n'}},
         {"tool_name": "delentia_search_repo", "tool_args": {}, "tool_result": {"matches": "3 matches: app.py:12, app.py:40, utils.py:7"}}]


def test_the_baseline_chain_traces_tokens_to_steps_the_request_or_nowhere():
    chain = rct7_judge.baseline_chain("Read pyproject.toml and report", "pyproject.toml has version 0.1.0 and license MIT, 3 matches in app.py", STEPS)
    by = {(c["kind"], c["token"]): c for c in chain["claims"]}
    assert by[("path", "pyproject.toml")]["support"] == "request" or by[("path", "pyproject.toml")]["support"] == "step"
    assert by[("path", "app.py")]["support"] == "step" and by[("path", "app.py")]["step"] == 2
    assert by[("number", "0.1.0")]["support"] == "step" and by[("number", "0.1.0")]["step"] == 1
    assert chain["unsupported"] == 0 or all(c["support"] != "unsupported" for c in chain["claims"] if c["token"] != "MIT")
    invented = rct7_judge.baseline_chain("x", "It listens on port 9999 and reads main.py", STEPS)
    assert {c["token"] for c in invented["claims"] if c["support"] == "unsupported"} == {"9999", "main.py"}


def test_a_claim_is_verified_only_when_its_quote_occurs_verbatim_in_the_cited_step():
    claims = [
        {"claim": "The version is 0.1.0", "evidence": [{"step": 1, "quote": 'version = "0.1.0"'}]},
        {"claim": "The name is sample-service", "evidence": [{"step": 1, "quote": 'name = "sample-service"'}]},
        {"claim": "The licence is MIT", "evidence": [{"step": 1, "quote": 'license = "MIT"'}]},
        {"claim": "Three matches", "evidence": [{"step": 7, "quote": "3 matches"}]},
        {"claim": "Two in app.py", "evidence": [{"step": 1, "quote": "app.py:12"}]},
        {"claim": "It was written in Go", "evidence": []},
        {"claim": "Matches are 3", "evidence": [{"step": 2, "quote": "3 matches"}]},
    ]
    got = {c["claim"]: c["status"] for c in rct7_judge.verify_claims(claims, STEPS)}
    assert got["The version is 0.1.0"] == "verified" and got["The name is sample-service"] == "verified" and got["Matches are 3"] == "verified"
    assert got["The licence is MIT"] == "quote_not_found"              # the quote does not occur
    assert got["Three matches"] == "step_missing"                      # no step 7
    assert got["Two in app.py"] == "quote_not_found"                   # a real quote, but from step 2, not step 1
    assert got["It was written in Go"] == "no_evidence"


def test_a_real_quote_does_not_support_a_claim_about_something_else():
    steps = [{"tool_name": "t", "tool_result": {"text": "Billing Service. Handles invoices. Port 8080."}}]
    unrelated = rct7_judge.verify_claims([{"claim": "It listens on port 9090", "evidence": [{"step": 1, "quote": "Handles invoices"}]}], steps)
    assert unrelated[0]["status"] == "token_unsupported" and unrelated[0]["unsupported"] == ["9090"]
    weak = rct7_judge.verify_claims([{"claim": "The software was written in Rust", "evidence": [{"step": 1, "quote": "Handles invoices"}]}], steps)
    assert weak[0]["status"] == "weak_support"
    fine = rct7_judge.verify_claims([{"claim": "It handles invoices on port 8080", "evidence": [{"step": 1, "quote": "Handles invoices. Port 8080"}]}], steps)
    assert fine[0]["status"] == "verified"


def test_whitespace_and_case_differences_do_not_break_a_true_quote():
    steps = [{"tool_name": "t", "tool_result": {"text": "line one\r\nline   two"}}]
    got = rct7_judge.verify_claims([{"claim": "line two exists", "evidence": [{"step": 1, "quote": "LINE ONE line two"}]}], steps)
    assert got[0]["status"] == "verified"
    assert rct7_judge.verify_claims("not a list", steps) == [] and rct7_judge.verify_claims([{"claim": "", "evidence": []}, "x"], steps) == []


def test_the_result_carries_the_baseline_chain_without_asking_a_model(env):
    judge = FakeJudge()
    steps = [{"action": "call_tool", "reasoning": "r", "final_answer": None, "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "pyproject.toml"}}]
    (env.root / "pyproject.toml").write_text('name = "sample-service"', encoding="utf-8")           # the file exists, so the rules ask nothing
    _, result = env("Read pyproject.toml and tell me the name", steps + [finish("The name in pyproject.toml is sample-service.")], judge, mcp=ReadMCP({"pyproject.toml": 'name = "sample-service"'}))
    assert "rct7_chain" in result and "chain" not in judge.asked
    assert any(c["token"] == "pyproject.toml" for c in result["rct7_chain"]["claims"]) and "cited" not in result["rct7_chain"]


def test_with_the_chain_switched_on_the_model_cites_and_the_code_checks(env, monkeypatch):
    monkeypatch.setenv("DELENTIA_RCT7_CHAIN", "cite")
    chain = {"claims": [{"claim": "The name is sample-service", "evidence": [{"step": 1, "quote": 'name = "sample-service"'}]},
                        {"claim": "It is licensed under MIT", "evidence": [{"step": 1, "quote": 'license = "MIT"'}]}]}
    judge = FakeJudge(chain=chain)
    steps = [{"action": "call_tool", "reasoning": "r", "final_answer": None, "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "pyproject.toml"}}]
    (env.root / "pyproject.toml").write_text('name = "sample-service"', encoding="utf-8")
    _, result = env("Read pyproject.toml and tell me the name and licence", steps + [finish("The name is sample-service, licensed under MIT.")], judge, interactive=False,
                    mcp=ReadMCP({"pyproject.toml": 'name = "sample-service"'}))
    cited = result["rct7_chain"]["cited"]
    assert judge.asked == ["chain"] and cited["verified"] == 1 and cited["unverified"] == 1
    assert {c["claim"]: c["status"] for c in cited["claims"]} == {"The name is sample-service": "verified", "It is licensed under MIT": "quote_not_found"}
    assert result["stopped_reason"] == "llm_finished"                                         # evidence is information: it stops nothing


def test_a_chain_model_that_fails_leaves_the_baseline_and_the_outcome_alone(env, monkeypatch):
    monkeypatch.setenv("DELENTIA_RCT7_CHAIN", "cite")
    steps = [{"action": "call_tool", "reasoning": "r", "final_answer": None, "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "pyproject.toml"}}]
    (env.root / "pyproject.toml").write_text('name = "sample-service"', encoding="utf-8")
    _, result = env("Read pyproject.toml and tell me the name", steps + [finish("The name is sample-service.")], FakeJudge(boom=True), mcp=ReadMCP({"pyproject.toml": 'name = "sample-service"'}))
    assert result["stopped_reason"] == "llm_finished" and result["rct7_chain"]["cited"]["error"] == "RuntimeError" and "claims" in result["rct7_chain"]


# ------------------------------------------------------------------------------------------------------------------- hostile input
def test_no_pattern_of_the_module_is_slow_on_hostile_text():
    import re
    import time
    hostile = {"spaces": " " * 20000, "word": "ก" * 20000, "digits": "1," * 10000, "dots": "a." * 10000, "urls": "http://a " * 3000, "slashes": "a/" * 10000}
    for name in dir(rct7_judge):
        pattern = getattr(rct7_judge, name)
        if not isinstance(pattern, re.Pattern):
            continue
        for label, text in hostile.items():
            started = time.time()
            pattern.search(text)
            pattern.findall(text)
            assert time.time() - started < 1.0, (name, label)
    started = time.time()
    rct7_judge.cites("x " * 10000, "y " * 50)
    rct7_judge.baseline_chain("g", "5 " * 5000 + "a.py " * 5000, STEPS)
    assert time.time() - started < 5.0


# ------------------------------------------------------------------------------------------------------------------- the Desk gets the new evidence
def test_the_desk_summary_carries_the_judge_the_critic_and_the_chain(env, monkeypatch):
    from rct_control_plane.desk_agent_stream import agent_events
    monkeypatch.setenv("DELENTIA_RCT7_CHAIN", "cite")
    (env.root / "pyproject.toml").write_text('name = "sample-service"', encoding="utf-8")
    judge = FakeJudge(request={"clear": True, "unknowns": []}, result={"meets": True, "unmet": []},
                      chain={"claims": [{"claim": "name is sample-service", "evidence": [{"step": 1, "quote": 'name = "sample-service"'}]}]})
    script = [{"action": "call_tool", "reasoning": "r", "final_answer": None, "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "pyproject.toml"}},
              finish("The name in pyproject.toml is sample-service.")]

    async def decide(goal_, history, available_tools, llm_provider=None, **kwargs):
        return dict(script.pop(0))
    monkeypatch.setattr(autonomous_loop, "decide_next_action", decide)

    def factory(kernel, namespace, **kwargs):
        loop = _loop(env.root, "desk98", mcp=ReadMCP({"pyproject.toml": 'name = "sample-service"'}))
        loop._judge_provider_override = judge
        return loop

    async def run():
        return [e async for e in agent_events("Read pyproject.toml and tell me the name", kernel=None, namespace="desk-test", loop_factory=factory, structured=True)]
    summary = next(e["data"] for e in asyncio.run(run()) if e["type"] == "summary")
    assert summary["semantic_check"]["meets"] is True
    assert summary["rct7_chain"]["cited"]["verified"] == 1 and summary["rct7_chain"]["claims"]


# ------------------------------------------------------------------------------------------------------------------- the chain must cover the answer, not only what the model chose to list
def test_a_clause_of_the_answer_that_no_listed_claim_speaks_about_is_reported_as_a_gap():
    answer = "The project is named sample-service, version 0.1.0, licensed under MIT."
    listed = [{"claim": "The project is named sample-service", "evidence": []}, {"claim": "version 0.1.0", "evidence": []}]
    assert rct7_judge.coverage_gaps(answer, listed) == ["licensed under MIT"]            # the model left the invented fact out of its list; the code did not
    full = listed + [{"claim": "licensed under MIT", "evidence": []}]
    assert rct7_judge.coverage_gaps(answer, full) == []


def test_a_faithful_answer_has_no_gaps_and_an_empty_list_leaves_every_clause_a_gap():
    answer = "report.csv is 1,204 bytes and notes.txt is 88 bytes."
    assert rct7_judge.coverage_gaps(answer, [{"claim": "report.csv is 1,204 bytes and notes.txt is 88 bytes"}]) == []
    assert rct7_judge.coverage_gaps("The service listens on port 8080 behind a proxy.", []) == ["The service listens on port 8080 behind a proxy"]
    assert rct7_judge.coverage_gaps("ตอบเป็นภาษาไทยทั้งหมด", []) == []                      # no Latin words to count: nothing is claimed about it
    assert rct7_judge.coverage_gaps("", None) == [] and rct7_judge.coverage_gaps("x", "not a list") == []

"""
Round 54: tool calls as an Execution Graph, run in waves. The executor is tested with real timers (calls that
really wait), and through the real governed loop with the real tool registry. No timing assertion is tighter than
half of what a serial run would take, so a slow machine does not make them flaky.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json
import threading
import time

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import dag_executor as dag
from test_governed_autonomous_loop_real import _FakeKernel, _FakeMCP, _loop, _scripted_decide


def graph_of(spec):
    """spec: {id: [dependencies]}"""
    return dag.compile_batch([dag.BatchCall(cid, "t", {}, deps) for cid, deps in spec.items()])


# ------------------------------------------------------------------ the graph

def test_independent_calls_form_one_wave_and_a_diamond_forms_three():
    assert dag.waves_of(graph_of({"a": [], "b": [], "c": []})) == [["a", "b", "c"]]
    assert dag.waves_of(graph_of({"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]})) == [["a"], ["b", "c"], ["d"]]
    assert dag.waves_of(graph_of({"x": ["y"], "y": []})) == [["y"], ["x"]]


@pytest.mark.parametrize("raw,fragment", [
    (None, "non-empty list"), ([], "non-empty list"), ("a", "non-empty list"),
    ([{"tool_args": {}}], "tool_name is required"), ([{"tool_name": ""}], "tool_name is required"),
    ([{"tool_name": "t", "tool_args": [1]}], "tool_args must be an object"),
    ([{"tool_name": "t", "depends_on": "a"}], "depends_on must be a list"),
    ([{"tool_name": "t"}] * 9, "at most 8"),
])
def test_malformed_batches_are_refused_with_a_reason(raw, fragment):
    with pytest.raises(dag.BatchError, match=fragment):
        dag.parse_calls(raw)


def test_ids_default_to_c1_c2_and_duplicates_unknown_deps_self_deps_and_cycles_are_refused():
    calls = dag.parse_calls([{"tool_name": "t"}, {"tool_name": "t", "depends_on": ["c1"]}])
    assert [c.id for c in calls] == ["c1", "c2"]
    with pytest.raises(dag.BatchError, match="unique"):
        dag.compile_batch([dag.BatchCall("a", "t"), dag.BatchCall("a", "t")])
    with pytest.raises(dag.BatchError, match="not in this batch"):
        dag.compile_batch([dag.BatchCall("a", "t", {}, ["ghost"])])
    with pytest.raises(dag.BatchError, match="itself"):
        dag.compile_batch([dag.BatchCall("a", "t", {}, ["a"])])
    with pytest.raises(dag.BatchError, match="cycle"):
        dag.compile_batch([dag.BatchCall("a", "t", {}, ["b"]), dag.BatchCall("b", "t", {}, ["a"])])


# ------------------------------------------------------------------ running waves (real waiting)

def sleeper(seconds, log=None):
    async def run_one(call):
        started = time.perf_counter()
        if log is not None:
            log.append(("start", call.id, started))
        await asyncio.sleep(seconds[call.id] if isinstance(seconds, dict) else seconds)
        if log is not None:
            log.append(("end", call.id, time.perf_counter()))
        return {"id": call.id}
    return run_one


def test_four_independent_waits_overlap():
    report = asyncio.run(dag.run_waves(graph_of({k: [] for k in "abcd"}), sleeper(0.3)))
    assert report.wall_ms < 0.6 * report.sequential_ms, report.summary()
    assert report.speedup > 1.8 and report.waves == [["a", "b", "c", "d"]]
    assert all(o.status == "done" for o in report.outcomes.values())


def test_dependencies_are_honoured_and_the_critical_path_bounds_the_speedup():
    log = []
    report = asyncio.run(dag.run_waves(graph_of({"a": [], "b": [], "c": ["a", "b"]}), sleeper(0.2, log)))
    starts = {cid: t for kind, cid, t in log if kind == "start"}
    ends = {cid: t for kind, cid, t in log if kind == "end"}
    assert starts["c"] >= max(ends["a"], ends["b"]) - 1e-3
    assert 350 < report.critical_path_ms < 700                       # two waves of about 200 ms
    assert report.wall_ms >= report.critical_path_ms * 0.9


def test_a_chain_gains_nothing():
    report = asyncio.run(dag.run_waves(graph_of({"a": [], "b": ["a"], "c": ["b"]}), sleeper(0.15)))
    assert report.speedup < 1.25 and len(report.waves) == 3


def test_max_parallel_caps_the_overlap():
    running, peak, lock = 0, 0, threading.Lock()

    async def run_one(call):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        await asyncio.sleep(0.1)
        with lock:
            running -= 1
        return {}

    asyncio.run(dag.run_waves(graph_of({k: [] for k in "abcdef"}), run_one, max_parallel=2))
    assert peak == 2


def test_a_failure_skips_its_dependents_but_not_its_siblings():
    async def run_one(call):
        if call.id == "bad":
            raise RuntimeError("disk on fire")
        return {"ok": call.id}

    report = asyncio.run(dag.run_waves(graph_of({"bad": [], "good": [], "after_bad": ["bad"], "after_good": ["good"], "deep": ["after_bad"]}), run_one))
    status = {cid: o.status for cid, o in report.outcomes.items()}
    assert status == {"bad": "failed", "good": "done", "after_bad": "skipped", "after_good": "done", "deep": "skipped"}
    assert "disk on fire" in report.outcomes["bad"].result["error"]
    assert "bad did not finish" in report.outcomes["after_bad"].note


def test_a_result_that_reports_an_error_counts_as_a_failure_with_is_failure():
    async def run_one(call):
        return {"error": "nope"} if call.id == "a" else {"ok": True}

    report = asyncio.run(dag.run_waves(graph_of({"a": [], "b": ["a"]}), run_one, is_failure=lambda r: bool(r.get("error"))))
    assert report.outcomes["a"].status == "failed" and report.outcomes["b"].status == "skipped"


def test_summary_is_json_serialisable():
    report = asyncio.run(dag.run_waves(graph_of({"a": [], "b": ["a"]}), sleeper(0.01)))
    assert json.loads(json.dumps(report.summary()))["statuses"] == {"a": "done", "b": "done"}


# ------------------------------------------------------------------ through the governed loop

class SlowTools(_FakeMCP):
    """Tools that really wait. Records when each call started and ended, and which thread ran it."""

    def __init__(self, delay=0.3):
        super().__init__()
        self.delay = delay
        self.log = []
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0

    async def list_tools(self):
        names = ["delentia_read_repo_file", "delentia_search_repo_files", "delentia_recall", "delentia_write_repo_file", "delentia_crawl_url"]
        return [type("T", (), {"name": n, "description": n, "input_schema": {}})() for n in names]

    async def call_tool(self, name, args):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.log.append(("start", name, args.get("relative_path") or args.get("query") or "", time.perf_counter()))
        await asyncio.sleep(self.delay)
        with self.lock:
            self.active -= 1
            self.log.append(("end", name, args.get("relative_path") or args.get("query") or "", time.perf_counter()))
        self.dispatched.append((name, args))
        return type("R", (), {"content": [type("C", (), {"text": json.dumps({"ok": True, "name": name})})()]})()


def batch(*calls, why="independent"):
    return {"action": "call_tools", "calls": list(calls), "reasoning": why, "tool_name": None, "tool_args": {}, "final_answer": None}


def read(cid, path, deps=None):
    return {"id": cid, "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": path}, **({"depends_on": deps} if deps else {})}


FINISH = {"action": "finish", "reasoning": "done", "final_answer": "<answer that restates the goal>", "tool_name": None, "tool_args": {}}


@pytest.fixture
def decide(monkeypatch):
    def apply(sequence):
        fake, calls = _scripted_decide(sequence)
        monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
        return calls
    return apply


@pytest.fixture
def parallel_on(monkeypatch):
    monkeypatch.setenv(dag.PARALLEL_ENV, "1")


def make(tmp_path, name, mcp, **kwargs):
    loop = _loop(tmp_path, name, kernel=kwargs.pop("kernel", _FakeKernel()), mcp=mcp, **kwargs)
    real = loop._assess_data

    def assess(goal, clarity, compile_result):
        evidence = real(goal, clarity, compile_result)
        evidence.D = 1.0
        return evidence

    loop._assess_data = assess
    return loop


def test_a_batch_costs_one_decision_and_its_waits_overlap(tmp_path, decide, parallel_on):
    mcp = SlowTools(0.3)
    decisions = decide([batch(read("a", "a.md"), read("b", "b.md"), read("c", "c.md"), read("d", "d.md")), FINISH])
    loop = make(tmp_path, "overlap", mcp)
    result = asyncio.run(loop.run("Read four project notes"))
    assert result["stopped_reason"] == "llm_finished" and decisions["n"] == 2          # one batch decision + one finish
    assert mcp.peak >= 3, "the four waits must have overlapped"
    reads = [s for s in result["steps"] if s["tool_name"] == "delentia_read_repo_file"]
    assert [s["tool_args"]["relative_path"] for s in reads] == ["a.md", "b.md", "c.md", "d.md"]
    assert all("[batch" in s["llm_reasoning"] and "done" in s["llm_reasoning"] for s in reads)
    with loop._persistence._connect() as conn:
        (row,) = conn.execute("SELECT changes FROM audit_trail WHERE entity_type = 'autonomous_loop_batch'").fetchall()
    summary = json.loads(row[0])
    assert summary["calls"] == 4 and summary["waves"] == [["a", "b", "c", "d"]] and summary["speedup"] > 1.8
    assert summary["wall_ms"] < 0.6 * summary["sequential_ms"], summary         # the batch itself, without the episode's own start-up


def test_dependencies_order_the_calls_inside_the_loop(tmp_path, decide, parallel_on):
    mcp = SlowTools(0.2)
    decide([batch(read("a", "a.md"), read("b", "b.md"), read("c", "c.md", ["a", "b"])), FINISH])
    asyncio.run(make(tmp_path, "order", mcp).run("Read three project notes in order"))
    starts = {path: t for kind, _, path, t in mcp.log if kind == "start"}
    ends = {path: t for kind, _, path, t in mcp.log if kind == "end"}
    assert starts["c.md"] >= max(ends["a.md"], ends["b.md"]) - 1e-3


def test_off_by_default_the_model_is_told_to_call_one_tool_and_nothing_runs(tmp_path, decide, monkeypatch):
    monkeypatch.delenv(dag.PARALLEL_ENV, raising=False)
    mcp = SlowTools(0.05)
    decide([batch(read("a", "a.md"), read("b", "b.md")), FINISH])
    result = asyncio.run(make(tmp_path, "off", mcp).run("Read two project notes"))
    assert not mcp.dispatched
    assert "not enabled" in result["steps"][0]["tool_result"]["batch_error"] and result["stopped_reason"] == "llm_finished"


def test_the_prompt_mentions_batches_only_when_enabled(monkeypatch):
    from rct_control_plane.autonomous_loop import _batch_guidance
    monkeypatch.delenv(dag.PARALLEL_ENV, raising=False)
    assert _batch_guidance() == ""
    monkeypatch.setenv(dag.PARALLEL_ENV, "1")
    text = _batch_guidance()
    assert "call_tools" in text and "depends_on" in text and str(dag.MAX_CALLS) in text


@pytest.mark.parametrize("calls,fragment", [
    ([read("a", "a.md", ["b"]), read("b", "b.md", ["a"])], "cycle"),
    ([read("a", "a.md", ["ghost"])], "not in this batch"),
    ([read(str(i), f"{i}.md") for i in range(9)], "at most"),
    ([{"id": "a", "tool_args": {}}], "tool_name is required"),
])
def test_a_bad_batch_is_explained_to_the_model_and_the_episode_continues(tmp_path, decide, parallel_on, calls, fragment):
    mcp = SlowTools(0.01)
    decide([batch(*calls), FINISH])
    result = asyncio.run(make(tmp_path, "bad", mcp).run("Read some project notes"))
    assert fragment in result["steps"][0]["tool_result"]["batch_error"]
    assert not mcp.dispatched and result["stopped_reason"] == "llm_finished"


def test_one_refused_call_stops_the_whole_batch_before_anything_runs(tmp_path, decide, parallel_on):
    mcp = SlowTools(0.05)
    write = {"id": "w", "tool_name": "delentia_write_repo_file", "tool_args": {"relative_path": "notes.md", "content_text": "x"}}
    decide([batch(read("a", "a.md"), read("b", "b.md"), write), FINISH])
    loop = make(tmp_path, "refused", mcp)
    result = asyncio.run(loop.run("Read two notes and write a summary"))
    assert result["stopped_reason"] == "pending_approval" and not mcp.dispatched
    assert result["steps"][-1]["tool_name"] == "delentia_write_repo_file"
    pending = loop._pending_actions().get(result["approval_id"])
    assert pending.tool_name == "delentia_write_repo_file" and pending.tool_args["relative_path"] == "notes.md"


def test_the_owner_policy_judges_every_call_in_a_batch(tmp_path, decide, parallel_on):
    from rct_control_plane import fdia_policy as fp
    policy, errors = fp.validate_policy({"rules": [{"rule_id": "R-READ", "intent_patterns": ["read_*"], "action_type": "CONDITIONAL", "denied_paths": [".env"]}]})
    assert policy is not None, errors
    mcp = SlowTools(0.05)
    decide([batch(read("a", "a.md"), read("b", "config/.env")), FINISH])
    result = asyncio.run(make(tmp_path, "policy", mcp, policy=policy).run("Read two project notes"))
    assert result["stopped_reason"] == "fdia_blocked" and not mcp.dispatched
    assert "restricted path" in result["steps"][-1]["tool_result"]["reason"]


def test_a_failing_call_does_not_stop_its_siblings_and_skips_its_dependents(tmp_path, decide, parallel_on):
    class Flaky(SlowTools):
        async def call_tool(self, name, args):
            if args.get("relative_path") == "bad.md":
                raise OSError("unreadable")
            return await super().call_tool(name, args)

    mcp = Flaky(0.05)
    decide([batch(read("bad", "bad.md"), read("ok", "ok.md"), read("after", "after.md", ["bad"])), FINISH])
    result = asyncio.run(make(tmp_path, "flaky", mcp).run("Read three project notes"))
    by_path = {s["tool_args"]["relative_path"]: s for s in result["steps"] if s["tool_name"]}
    assert "unreadable" in by_path["bad.md"]["tool_result"]["error"] and "failed" in by_path["bad.md"]["llm_reasoning"]
    assert by_path["ok.md"]["tool_result"]["ok"] is True
    assert "skipped" in by_path["after.md"]["tool_result"] and result["stopped_reason"] == "llm_finished"


def test_a_tool_that_does_not_exist_fails_that_call_only(tmp_path, decide, parallel_on):
    mcp = SlowTools(0.02)
    ghost = {"id": "g", "tool_name": "delentia_read_file", "tool_args": {"relative_path": "x"}}
    decide([batch(read("a", "a.md"), ghost), FINISH])
    result = asyncio.run(make(tmp_path, "ghost", mcp).run("Read some project notes"))
    steps = {s["tool_name"]: s for s in result["steps"] if s["tool_name"]}
    assert steps["delentia_read_repo_file"]["tool_result"]["ok"] is True
    assert "delentia_read_repo_file" in json.dumps(steps["delentia_read_file"]["tool_result"])         # the closest real name is suggested


def test_tools_outside_the_safe_list_run_one_at_a_time_even_in_the_same_wave(tmp_path, decide, parallel_on):
    mcp = SlowTools(0.1)
    recall = lambda cid, q: {"id": cid, "tool_name": "delentia_recall", "tool_args": {"query": q}}      # noqa: E731
    decide([batch(recall("a", "one"), recall("b", "two"), recall("c", "three")), FINISH])
    asyncio.run(make(tmp_path, "serial", mcp).run("Recall three things"))
    assert mcp.peak == 1


def test_real_tools_in_a_batch_return_real_results(tmp_path, decide, parallel_on):
    from rct_control_plane.mcp_server import mcp as real_mcp
    batch_call = batch(
        {"id": "readme", "tool_name": "delentia_read_repo_file", "tool_args": {"relative_path": "pyproject.toml"}},
        {"id": "find", "tool_name": "delentia_search_repo_files", "tool_args": {"pattern": "FDIA_GATE_THRESHOLD", "glob": "rct_control_plane/*.py"}})
    decide([batch_call, FINISH])
    result = asyncio.run(make(tmp_path, "real", real_mcp).run("Read pyproject.toml and find the FDIA gate threshold"))
    steps = {s["tool_name"]: s["tool_result"] for s in result["steps"] if s["tool_name"]}
    assert "name" in json.dumps(steps["delentia_read_repo_file"]) and "governed_autonomous_loop" in json.dumps(steps["delentia_search_repo_files"])
    assert result["stopped_reason"] == "llm_finished"

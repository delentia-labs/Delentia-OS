"""
Round 82, plan item T02: the research runner must be trustworthy BEFORE any paid batch.

The Architect's research plan of 2026-10-15 listed eight defects of research/runner.py. Two were reproduced by running the code (the ranked menu was cleared right after being
set; a ranked label on a full menu), the others were read in the source. Each is pinned here by a test that failed before the fix:

  1  effective menu          the row says "ranked", the runtime must see the ranked menu, and a mismatch fails the manipulation check
  2  cumulative budget       a resumed run adds what the earlier invocations spent
  3  reservation             the remaining programme budget is handed to the runtime as the episode's cap BEFORE the call
  4  attempt ledger          every attempt of an episode is kept with its cost; a write is never retried automatically
  5  resume                  a half-finished trajectory is rerun whole, from a clean namespace, and gives the same outcomes as an uninterrupted run
  6  run identity            code, model route, grader, policy, menu and the FULL tool schema (descriptions included); a resume across a change is refused
  7  failure denominator     an agent crash counts in the primary analysis; only a predeclared external outage is excluded, and missingness is reported per arm
  8  unknown cost           UNKNOWN is not 0; side calls are switched off in a research run and checked

Real harness, real governed loop, real MCP tools and a real workspace; the model is the scripted policy (rehearsal), which is what makes the outcome comparison exact.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import argparse
import asyncio
import json
from pathlib import Path

import pytest

from research import analyze, runner

TRAJ = "quotes-dev"


def make_args(tmp_path: Path, name: str, **overrides):
    values = dict(split="dev", policy="diligent", arms="A111", domain="quotes", unit_token_budget=0, memory_policy="none", preload_noise=0, max_seconds=60.0, repeats=1,
                  seed=20261008, out=str(tmp_path / f"{name}.jsonl"), only=None, work=str(tmp_path / f"work-{name}"), model_config=None, budget_usd=None, tool_menu="default",
                  floor="default", keep_going=True, stop_on_critical=False, budget_scope="run", new_run=False)
    values.update(overrides)
    return argparse.Namespace(**values)


def run_main(args):
    return asyncio.run(runner.main_async(args))


def rows_of(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def a_trajectory_id():
    static, trajs = runner._load_units("dev", None, "quotes")
    long = [t for t in trajs if len(t["episodes"]) >= 3]
    return long[0]["trajectory_id"]


@pytest.fixture(scope="module")
def one_static_task():
    static, _ = runner._load_units("dev", None, "quotes")
    return static[0]


# ------------------------------------------------------------------ 1 effective menu

def test_a_ranked_run_really_gives_the_runtime_the_ranked_menu(tmp_path):
    from rct_control_plane import tool_menu
    harness = runner.Harness(tmp_path / "w1", "diligent", tool_menu="ranked")
    try:
        harness.start()
        assert tool_menu.ranked_enabled() is True and tool_menu.compact_enabled() is True
        assert harness.effective_menu() == "ranked"
    finally:
        harness.close()
    other = runner.Harness(tmp_path / "w2", "diligent", tool_menu="default")
    try:
        other.start()
        assert tool_menu.ranked_enabled() is False and other.effective_menu() == "default"
    finally:
        other.close()


def test_a_row_records_the_menu_the_runtime_used_and_a_mismatch_fails_the_manipulation_check(tmp_path, one_static_task, monkeypatch):
    harness = runner.Harness(tmp_path / "w", "diligent", tool_menu="ranked")
    try:
        harness.start()
        arm = runner._arms("A111")[0]
        ns = "research-menu-1"
        row = asyncio.run(harness.run_episode(arm, one_static_task, split="dev", rep=0, namespace=ns, skill_db=str(tmp_path / "s1.db"), seed=1))
        assert row["tool_menu"] == "ranked" and row["menu_effective"] == "ranked"
        assert all(c["ok"] for c in row["manipulation_checks"] if c["check"].startswith("tool menu"))
        # Undo this injected fault before close restores the caller's settings;
        # a test-level undo afterwards would reintroduce the run's ranked menu.
        with monkeypatch.context() as fault:
            fault.delenv("DELENTIA_TOOL_MENU", raising=False)
            row2 = asyncio.run(harness.run_episode(arm, one_static_task, split="dev", rep=1, namespace="research-menu-2", skill_db=str(tmp_path / "s2.db"), seed=1))
            assert row2["menu_effective"] == "default" and row2["manipulation_ok"] is False
    finally:
        harness.close()


# ------------------------------------------------------------------ 2 + 3 cumulative budget and reservation

def test_a_resumed_run_adds_what_the_earlier_invocations_spent():
    rows = [{"cost_all_attempts_usd": 0.4, "cost_known": True}, {"cost_all_attempts_usd": 0.1, "cost_known": True}, {"cost_all_attempts_usd": None, "cost_known": False}]
    assert runner.budget_state(rows, "run") == (pytest.approx(0.5), 1)
    assert runner.budget_state(rows, "invocation") == (0.0, 0)
    with pytest.raises(ValueError):
        runner.budget_state(rows, "forever")


def test_the_remaining_budget_is_handed_to_the_runtime_before_the_call(tmp_path, one_static_task, monkeypatch):
    harness = runner.Harness(tmp_path / "w", "diligent", budget_usd=1.0, prior_spend=0.75)
    assert harness.remaining_budget() == pytest.approx(0.25)
    built = []
    import rct_control_plane.agent_factory as factory
    real_build = factory.build_governed_loop

    def spy(*a, **k):
        loop = real_build(*a, **k)
        built.append(loop)
        return loop
    monkeypatch.setattr(factory, "build_governed_loop", spy)
    try:
        harness.start()
        arm = runner._arms("A111")[0]
        asyncio.run(harness.run_episode(arm, one_static_task, split="dev", rep=0, namespace="research-cap", skill_db=str(tmp_path / "s.db"), seed=1))
    finally:
        harness.close()
    assert built and built[0]._max_episode_cost_usd == pytest.approx(0.25)


def test_a_run_whose_budget_is_already_spent_does_not_start_an_episode(tmp_path):
    harness = runner.Harness(tmp_path / "w", "diligent", budget_usd=1.0, prior_spend=1.0)
    assert harness.remaining_budget() == 0.0 and harness.budget_exhausted() is True


# ------------------------------------------------------------------ 4 attempt ledger

def fake_row(**kw):
    base = {"exclusion_reason": None, "cost_all_attempts_usd": 0.0, "cost_known": True, "write_committed": False, "outbound_events": 0, "stopped_reason": "llm_finished",
            "runtime_seconds": 0.1, "tokens_used": 10, "attack_success": False, "violations": [], "status": "success", "manipulation_ok": True, "manipulation_checks": [],
            "tool_calls": [], "steps_brief": [], "gate_decisions": [], "refusal_task": 0, "constraint_violation": False, "false_success_claim": False, "truthful": True}
    base.update(kw)
    return base


def test_every_attempt_is_kept_with_its_cost_and_the_final_row_sums_them(tmp_path, monkeypatch):
    harness = runner.Harness(tmp_path / "w", "diligent")
    answers = iter([fake_row(exclusion_reason="infrastructure: ConnectError", cost_all_attempts_usd=0.03, tokens_used=100), fake_row(cost_all_attempts_usd=0.05, tokens_used=200)])

    async def fake_episode(*a, **k):
        return next(answers)
    monkeypatch.setattr(harness, "run_episode", fake_episode)
    row = asyncio.run(harness.run_with_retry(None, {}, split="dev", rep=0))
    assert [a["exclusion_reason"] for a in row["attempts"]] == ["infrastructure: ConnectError", None]
    assert row["cost_all_attempts_usd"] == pytest.approx(0.08) and row["tokens_all_attempts"] == 300 and row["attempt_count"] == 2


def test_an_attempt_that_changed_something_is_not_retried_automatically(tmp_path, monkeypatch):
    harness = runner.Harness(tmp_path / "w", "diligent")
    calls = []

    async def fake_episode(*a, **k):
        calls.append(1)
        return fake_row(exclusion_reason="infrastructure: ReadTimeout", write_committed=True)
    monkeypatch.setattr(harness, "run_episode", fake_episode)
    row = asyncio.run(harness.run_with_retry(None, {}, split="dev", rep=0))
    assert len(calls) == 1 and row["attempt_count"] == 1 and "not retried" in row["retry_skipped"]


# ------------------------------------------------------------------ 5 resume

def outcome_signature(rows):
    return [(r["episode_index"], r["status"], r["STS"], r["memory_items_in_prompt"], tuple(r["tool_calls"])) for r in sorted(rows, key=lambda r: r["episode_index"])]


def test_a_killed_trajectory_resumes_to_the_same_outcomes_as_an_uninterrupted_one(tmp_path, monkeypatch):
    tid = a_trajectory_id()
    continuous = make_args(tmp_path, "continuous", only=[tid])
    assert run_main(continuous) == 0
    expected = outcome_signature(rows_of(continuous.out))
    assert len(expected) >= 3

    interrupted = make_args(tmp_path, "interrupted", only=[tid])
    real = runner.Harness.run_with_retry
    state = {"n": 0}

    async def kill_after_first(self, *a, **k):
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("the process was killed")
        return await real(self, *a, **k)
    monkeypatch.setattr(runner.Harness, "run_with_retry", kill_after_first)
    with pytest.raises(RuntimeError, match="killed"):
        run_main(interrupted)
    monkeypatch.setattr(runner.Harness, "run_with_retry", real)
    assert len(rows_of(interrupted.out)) == 1                                                   # only episode 1 was written before the kill
    assert run_main(interrupted) == 0                                                           # resume, same work folder, same output file

    all_rows = rows_of(interrupted.out)
    assert any(r.get("trajectory_attempt", 1) == 1 for r in all_rows)                          # the original attempt is kept
    final = [r for r in analyze.load_rows(Path(interrupted.out))]
    assert outcome_signature(final) == expected                                                 # and the analysis sees the same outcomes as an uninterrupted run
    assert {r.get("trajectory_attempt", 1) for r in final} == {2}


def test_a_second_kill_does_not_mix_two_attempts_into_one_trajectory(tmp_path, monkeypatch):
    tid = a_trajectory_id()
    args = make_args(tmp_path, "twice", only=[tid])
    real = runner.Harness.run_with_retry
    for kill_at in (2, 3):
        state = {"n": 0}

        async def killer(self, *a, _kill_at=kill_at, _state=state, **k):
            _state["n"] += 1
            if _state["n"] == _kill_at:
                raise RuntimeError("killed")
            return await real(self, *a, **k)
        monkeypatch.setattr(runner.Harness, "run_with_retry", killer)
        with pytest.raises(RuntimeError):
            run_main(args)
    monkeypatch.setattr(runner.Harness, "run_with_retry", real)
    assert run_main(args) == 0
    final = analyze.load_rows(Path(args.out))
    assert len({r.get("trajectory_attempt", 1) for r in final}) == 1 and len(final) >= 3


# ------------------------------------------------------------------ 6 run identity

def test_the_tool_schema_hash_covers_descriptions_and_input_schemas_not_only_names():
    a = [{"name": "t", "description": "reads a file", "inputSchema": {"type": "object", "properties": {"p": {"type": "string"}}}}]
    b = [{"name": "t", "description": "reads a file AND sends it out", "inputSchema": a[0]["inputSchema"]}]
    c = [{"name": "t", "description": "reads a file", "inputSchema": {"type": "object", "properties": {"p": {"type": "integer"}}}}]
    assert len({runner.tool_schema_hash(x) for x in (a, b, c)}) == 3


def test_the_run_identity_changes_with_the_menu_and_a_resume_across_it_is_refused(tmp_path):
    tid = a_trajectory_id()
    first = make_args(tmp_path, "identity", only=[tid], tool_menu="default")
    assert run_main(first) == 0
    identity = json.loads(Path(first.out + ".identity.json").read_text(encoding="utf-8"))
    for key in ("code_sha", "model_route", "grader_version", "tool_schema_hash", "policy", "tool_menu", "embedding", "floor"):
        assert key in identity
    changed = make_args(tmp_path, "identity", only=[tid], tool_menu="ranked", work=str(tmp_path / "work-identity-2"))
    assert run_main(changed) == 4                                                               # refused: the earlier rows were produced under another configuration
    assert run_main(make_args(tmp_path, "identity", only=[tid], tool_menu="ranked", work=str(tmp_path / "work-identity-3"), new_run=True)) == 0


# ------------------------------------------------------------------ 7 failure denominator

def test_only_a_predeclared_external_outage_is_an_infrastructure_fault():
    assert runner.classify_error("ConnectError: all connection attempts failed") == "infrastructure"
    assert runner.classify_error("ReadTimeout: the model endpoint did not answer") == "infrastructure"
    assert runner.classify_error("KeyError: 'tool_name'") == "agent"
    assert runner.classify_error("ValueError: the loop could not parse the decision") == "agent"
    assert runner.classify_error("") == "agent"


def test_an_agent_crash_stays_in_the_primary_analysis_and_missingness_is_reported_per_arm():
    crash = fake_row(exclusion_reason=None, status="failed", arm="A111", task_id="t1", family_id="f1", run_id="dev:t1:A111:r0")
    outage = fake_row(exclusion_reason="infrastructure: ReadTimeout", arm="A011", task_id="t1", family_id="f1", run_id="dev:t1:A011:r0")
    fine = fake_row(arm="A011", task_id="t2", family_id="f2", run_id="dev:t2:A011:r0")
    kept, dropped = analyze.usable([crash, outage, fine])
    assert crash in kept and fine in kept and dropped == [outage]
    report = analyze.missingness_by_arm([crash, outage, fine])
    assert report["A011"] == {"rows": 2, "excluded": 1, "share": pytest.approx(0.5)} and report["A111"]["excluded"] == 0


# ------------------------------------------------------------------ 8 unknown cost and side calls

def test_an_unknown_cost_is_unknown_not_zero():
    assert runner.episode_cost({"cost_usd": None, "cost_known": False}) == (None, False)
    assert runner.episode_cost({"cost_usd": 0.0, "cost_known": True}) == (0.0, True)
    assert runner.episode_cost({}) == (None, False)
    assert runner.episode_cost(None) == (None, False)


def test_side_calls_are_switched_off_in_a_research_run(tmp_path, monkeypatch):
    for name in ("DELENTIA_CORD_SECOND_OPINION", "DELENTIA_MEMORY_EMBED", "DELENTIA_MEMORY_QUESTIONS", "DELENTIA_MEMORY_QUERY_EXPANSION", "DELENTIA_PIPELINE_ALLOW_LLM"):
        monkeypatch.setenv(name, "flag" if name == "DELENTIA_CORD_SECOND_OPINION" else "ollama" if "EMBED" in name else "1")
    harness = runner.Harness(tmp_path / "w", "diligent")
    try:
        harness.start()
        for name in ("DELENTIA_CORD_SECOND_OPINION", "DELENTIA_MEMORY_EMBED", "DELENTIA_MEMORY_QUESTIONS", "DELENTIA_MEMORY_QUERY_EXPANSION", "DELENTIA_PIPELINE_ALLOW_LLM"):
            assert not os.environ.get(name), name
    finally:
        harness.close()


# ------------------------------------------------------------------ 9 workspace binding (found while writing the ops-domain tests)

def test_a_second_harness_in_one_process_gets_its_own_workspace_for_the_tools_and_the_gate(tmp_path):
    """mcp_server.REPO_ROOT is read once at import, so a second harness used the first one's folder: the file tools read the wrong files and the FDIA gate's grounding term (does the file the
    goal names exist?) looked in the wrong place, which let the same action pass in one run order and be blocked in another."""
    from rct_control_plane import mcp_server
    static, _ = runner._load_units("dev", None, "quotes")
    first_task, second_task = static[0], static[1]
    arm = runner._arms("A111")[0]
    one = runner.Harness(tmp_path / "w1", "diligent")
    try:
        one.start()
        asyncio.run(one.run_episode(arm, first_task, split="dev", rep=0, namespace="research-ws-1", skill_db=str(tmp_path / "s1.db"), seed=1))
    finally:
        one.close()
    two = runner.Harness(tmp_path / "w2", "diligent")
    try:
        two.start()
        assert mcp_server.REPO_ROOT == (tmp_path / "w2" / "repo").resolve()
        row = asyncio.run(two.run_episode(arm, second_task, split="dev", rep=0, namespace="research-ws-2", skill_db=str(tmp_path / "s2.db"), seed=1))
        assert all(step["result"] != "error" for step in row["steps_brief"] if step["tool"]), row["steps_brief"]
        assert row["VTS"] == 1 and all(c["ok"] for c in row["manipulation_checks"] if c["check"].startswith("workspace"))
        mcp_server.REPO_ROOT = (tmp_path / "w1" / "repo").resolve()                              # the old bug, put back on purpose
        bad = asyncio.run(two.run_episode(arm, second_task, split="dev", rep=1, namespace="research-ws-3", skill_db=str(tmp_path / "s3.db"), seed=1))
        assert bad["manipulation_ok"] is False
    finally:
        two.close()

"""
Round 51: D measured from the user's own data, and MEE growth that can be
measured (graded signal, persisted per namespace, skills that earn or lose
trust when reused). Real kernel, real SQLite, real compiler and matcher; the
only scripted part is the LLM's decision, as in the other loop tests.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
from pathlib import Path

import pytest

import rct_control_plane.autonomous_loop as autonomous_loop_module
from rct_control_plane import data_evidence as de
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.growth import Baseline, GrowthLedger, efficiency_baseline, episode_delta
from rct_control_plane.mee_engine import MEESession
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import (
    ARCHIVE_AFTER_FAILURES, SkillLibrary,
)

REPO = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------- data_evidence
class TestDataEvidence:
    def test_paths_and_values_are_extracted_without_mistaking_versions_or_urls(self):
        goal = 'Compare docs/a.md with "release 3" at https://example.com/x.html for v2.1 and 42 users'
        assert de.extract_paths(goal) == ["docs/a.md"]
        values = de.extract_values(goal)
        assert "https://example.com/x.html" in values and "release 3" in values and "42" in values

    def test_a_file_that_exists_grounds_the_goal_and_a_missing_one_does_not(self):
        exists = de.grounding_score("read pyproject.toml", "QUERY", REPO)
        missing = de.grounding_score("read no_such_file_xyz.toml", "QUERY", REPO)
        assert exists["score"] == 1.0 and exists["paths"]["pyproject.toml"] == "exists"
        assert missing["score"] == 0.0 and missing["paths"]["no_such_file_xyz.toml"] == "missing"

    def test_a_path_outside_the_workspace_is_not_grounded(self):
        g = de.grounding_score("read ../../etc/passwd.txt", "QUERY", REPO)
        assert g["score"] == 0.0

    def test_creating_a_new_file_in_an_existing_folder_is_fine_but_not_in_a_missing_one(self):
        ok = de.grounding_score("create docs/brand_new_note.md", "BUILD_APP", REPO)
        bad = de.grounding_score("create nonexistent_dir_q/sub/note.md", "BUILD_APP", REPO)
        assert ok["score"] > bad["score"] and ok["score"] >= 0.9

    def test_an_action_that_names_no_target_is_weakly_grounded(self):
        assert de.grounding_score("deploy it", "DEPLOY", REPO)["score"] < de.grounding_score("what is the capital of France", "QUERY", REPO)["score"]

    def test_evidence_raises_D_and_each_part_is_reported(self):
        bare = de.assess("Deploy the new database schema to production", clarity=1.0, intent_type="DEPLOY", workspace_root=REPO)
        rich = de.assess("Deploy the new database schema to production", clarity=1.0, intent_type="DEPLOY", workspace_root=REPO,
                         memory_scores=[0.6], skill_scores=[0.9], same_goal_verified=2, overall_verified_rate=1.0)
        assert rich.D > bare.D + 0.3
        assert set(rich.parts) == {"clarity", "grounding", "memory", "skills", "record"}
        assert any("memory" in m for m in bare.missing) and not any("memory" in m for m in rich.missing)

    def test_irrelevant_memory_does_not_count(self):
        a = de.assess("x goal", clarity=1.0, workspace_root=REPO, memory_scores=[0.05])
        assert a.parts["memory"] == 0.0

    def test_missing_files_are_named_in_what_is_missing(self):
        a = de.assess("fix no_such_file_xyz.py", clarity=1.0, intent_type="DEBUG", workspace_root=REPO)
        assert any("no_such_file_xyz.py" in m for m in a.missing)


# ------------------------------------------------------------------------ growth
class TestEpisodeDelta:
    VERIFIED = {"applicable": True, "aligned_with_intent": True, "similarity_score": 0.6}

    def _delta(self, **kw):
        base = dict(stopped_reason="llm_finished", verification=self.VERIFIED, iterations=2, cost_usd=None,
                    duration_s=1.0, baseline=Baseline(0, None, None, None), threshold=0.15)
        base.update(kw)
        return episode_delta(**base)

    def test_a_first_verified_success_grows(self):
        d = self._delta()
        assert d["delta"] > 0.5 and not d["governance_violation"] and d["parts"]["verified"]

    def test_being_faster_than_the_earlier_verified_runs_grows_more(self):
        slow_before = Baseline(2, iterations=6.0, cost_usd=None, duration_s=10.0)
        faster = self._delta(iterations=2, duration_s=4.0, baseline=slow_before)
        same = self._delta(iterations=6, duration_s=10.0, baseline=slow_before)
        slower = self._delta(iterations=12, duration_s=30.0, baseline=slow_before)
        assert faster["delta"] > same["delta"] > slower["delta"] > 0.0
        assert faster["parts"]["gains"]["iterations"] > 0.6

    def test_cost_counts_when_both_runs_have_it(self):
        b = Baseline(1, 3.0, 0.02, 5.0)
        cheaper = self._delta(iterations=3, cost_usd=0.005, duration_s=5.0, baseline=b)
        assert cheaper["parts"]["gains"]["cost"] == pytest.approx(0.75)

    def test_unverified_outcomes_never_grow(self):
        assert self._delta(stopped_reason="max_iterations_reached")["delta"] < 0
        assert self._delta(verification={"applicable": True, "aligned_with_intent": False, "similarity_score": 0.0})["delta"] < 0
        blocked = self._delta(stopped_reason="fdia_blocked")
        assert blocked["delta"] == -1.0 and blocked["governance_violation"]
        assert self._delta(stopped_reason="pending_approval")["delta"] == 0.0

    def test_baseline_uses_only_verified_runs_and_the_median(self):
        runs = [{"metrics": {"finished": 1, "aligned_with_intent": 1, "iterations": i, "duration_s": float(i)}} for i in (2, 4, 9)]
        runs.append({"metrics": {"finished": 1, "aligned_with_intent": 0, "iterations": 99}})
        runs.append({"metrics": {"finished": 0, "aligned_with_intent": None, "iterations": 50}})
        b = efficiency_baseline(runs)
        assert b.runs == 3 and b.iterations == 4.0


class TestGrowthLedgerPersists:
    def test_g_belongs_to_the_namespace_and_survives_a_new_process(self, tmp_path):
        db = ControlPlanePersistence(db_path=str(tmp_path / "g.db"))
        a = GrowthLedger(db, "alice")
        for _ in range(3):
            a.record({"delta": 0.8, "governance_violation": False, "parts": {"verified": True}})
        g_alice = a.session.g
        assert g_alice > 1.2 and a.episodes == 3

        again = GrowthLedger(ControlPlanePersistence(db_path=str(tmp_path / "g.db")), "alice")
        assert again.session.g == pytest.approx(g_alice, rel=1e-4)
        assert again.episodes == 3 and again.verified_episodes == 3
        assert GrowthLedger(db, "bob").session.g == 1.0       # another user starts from scratch

    def test_a_violation_costs_resilience(self, tmp_path):
        ledger = GrowthLedger(ControlPlanePersistence(db_path=str(tmp_path / "v.db")), "u")
        ledger.record({"delta": -1.0, "governance_violation": True, "parts": {"verified": False}})
        assert ledger.session.resilience < 1.0 and ledger.session.g < 1.0


# ---------------------------------------------------------------- skill feedback
def _step(session, delta=0.6):
    return session.step(delta)


class TestSkillFeedback:
    def test_near_duplicate_problems_reinforce_one_skill_and_keep_the_shorter_solution(self, tmp_path):
        lib = SkillLibrary(db_path=str(tmp_path / "s.db"))
        session = MEESession("t")
        first = lib.maybe_extract_skill("Summarise the quarterly sales report", ["a", "b", "c", "d"], _step(session))
        second = lib.maybe_extract_skill("Summarise the quarterly sales report now", ["a", "b"], _step(session))
        assert lib.count() == 1
        assert second.id == first.id and second.reinforced == 2
        assert second.solution == ["a", "b"]
        lib.maybe_extract_skill("Summarise the quarterly sales report again", ["a", "b", "c"], _step(session))
        assert lib.get_skill(first.id).solution == ["a", "b"]      # never replaced by a longer one

    def test_distinct_problems_stay_distinct(self, tmp_path):
        lib = SkillLibrary(db_path=str(tmp_path / "s.db"))
        session = MEESession("t")
        lib.maybe_extract_skill("Summarise the quarterly sales report", ["a"], _step(session))
        lib.maybe_extract_skill("Deploy the billing service to staging", ["b"], _step(session))
        assert lib.count() == 2

    def test_reuse_outcomes_change_reliability_and_ranking(self, tmp_path):
        lib = SkillLibrary(db_path=str(tmp_path / "s.db"))
        session = MEESession("t")
        good = lib.maybe_extract_skill("Rotate the staging database credentials safely", ["g"], _step(session))
        bad = lib.maybe_extract_skill("Rotate the production database credentials quickly", ["b"], _step(session))
        lib.record_outcome([good.id], success=True)
        lib.record_outcome([good.id], success=True)
        lib.record_outcome([bad.id], success=False)
        assert lib.get_skill(good.id).reliability > 0.7 > 0.4 > lib.get_skill(bad.id).reliability
        ranked = lib.retrieve_similar_skills("Rotate the database credentials", top_k=2)
        assert ranked[0].id == good.id

    def test_a_skill_that_keeps_failing_is_archived_not_deleted(self, tmp_path):
        lib = SkillLibrary(db_path=str(tmp_path / "s.db"))
        skill = lib.maybe_extract_skill("Clear the build cache on the CI runner", ["x"], _step(MEESession("t")))
        for _ in range(ARCHIVE_AFTER_FAILURES):
            lib.record_outcome([skill.id], success=False)
        assert lib.get_skill(skill.id).archived is True
        assert lib.count() == 1                                   # still stored (Zero-Delete)
        assert lib.retrieve_similar_skills("Clear the build cache on the CI runner") == []

    def test_databases_from_before_round_51_are_migrated_in_place(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "old.db")
        with sqlite3.connect(db) as c:
            c.execute("""CREATE TABLE skills (id TEXT PRIMARY KEY, problem_statement TEXT NOT NULL, solution TEXT NOT NULL,
                keywords TEXT NOT NULL, delta REAL NOT NULL, resilience REAL NOT NULL, g_before REAL NOT NULL, g_after REAL NOT NULL,
                growth_ratio REAL NOT NULL, governance_violation INTEGER NOT NULL, session_id TEXT, created_at TEXT NOT NULL)""")
            c.execute("INSERT INTO skills VALUES ('s1','old problem text here','[]','[\"old\",\"problem\",\"text\"]',0.5,1,1,1.1,1.1,0,NULL,'2026-01-01')")
        lib = SkillLibrary(db_path=db)
        got = lib.get_skill("s1")
        assert got is not None and got.uses == 0 and got.archived is False and got.reliability == 0.5


# ------------------------------------------------------------------ in the loop
class _Tool:
    def __init__(self, name):
        self.name, self.description, self.input_schema = name, name, {}


class _Result:
    def __init__(self, text):
        self.content = [type("C", (), {"text": text})()]


class _MCP:
    def __init__(self):
        self.dispatched = []

    async def list_tools(self):
        return [_Tool("delentia_run_sandboxed_command"), _Tool("delentia_recall")]

    async def call_tool(self, name, args):
        self.dispatched.append((name, args))
        return _Result('{"ok": true}')


def _script(monkeypatch, per_episode):
    """per_episode: list of decision lists; each run() consumes the next."""
    state = {"episode": -1, "i": 0}

    async def fake(goal, history, available_tools, llm_provider=None, extra_context=""):
        if not history:
            state["episode"] += 1
            state["i"] = 0
        seq = per_episode[min(state["episode"], len(per_episode) - 1)]
        d = dict(seq[min(state["i"], len(seq) - 1)])
        state["i"] += 1
        if d.get("final_answer") == "ECHO":
            d["final_answer"] = f"Completed the goal: {goal}"
        state.setdefault("contexts", []).append(extra_context)
        return d
    monkeypatch.setattr(autonomous_loop_module, "decide_next_action", fake)
    return state


LS = {"action": "call_tool", "tool_name": "delentia_run_sandboxed_command", "tool_args": {"command": "ls -la"},
      "reasoning": "look", "final_answer": None}
FINISH = {"action": "finish", "reasoning": "done", "final_answer": "ECHO", "tool_name": None, "tool_args": {}}


@pytest.fixture(scope="module")
def kernel():
    return AlgorithmKernel41()


def _loop(tmp_path, kernel, namespace="r51", db="r51.db", mcp=None):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / db))
    kernel._agent_memory = AgentMemory(namespace, persistence)
    return GovernedAutonomousLoop(
        mcp_server=mcp or _MCP(), persistence=persistence, kernel=kernel,
        skill_library=SkillLibrary(db_path=str(tmp_path / f"{db}.skills")), max_iterations=6, namespace=namespace,
    )


RISKY_GOAL = "Deploy the new database schema to production"


class TestDInTheLoop:
    def test_a_high_stakes_goal_with_no_data_behind_it_is_blocked_and_says_what_is_missing(self, tmp_path, kernel, monkeypatch):
        _script(monkeypatch, [[LS, FINISH]])
        loop = _loop(tmp_path, kernel)
        result = asyncio.run(loop.run(RISKY_GOAL))
        assert result["stopped_reason"] == "fdia_blocked"
        blocked = result["steps"][-1]["tool_result"]
        assert blocked["F"] < 0.5 and blocked["D"] < 0.6
        assert any("memory" in m for m in blocked["missing_data"])
        assert blocked["data_parts"]["memory"] == 0.0

    def test_the_same_goal_passes_once_the_user_has_relevant_data(self, tmp_path, kernel, monkeypatch):
        _script(monkeypatch, [[LS, FINISH]])
        loop = _loop(tmp_path, kernel)
        persistence, namespace = loop._persistence, loop.namespace
        asyncio.run(AgentMemory(namespace, persistence).store(
            "Production database schema deploy runs through the blue green pipeline, migrations are reviewed first",
            MemoryType.FACT, importance=0.9))
        session = MEESession("seed")
        loop._skill_library.maybe_extract_skill(RISKY_GOAL, [{"tool_name": "delentia_recall"}], session.step(0.6))
        experiment_id = loop.experiment_id_for_goal(RISKY_GOAL)
        persistence.save_experiment(experiment_id, "deploy")
        for n in range(2):
            persistence.save_experiment_run(
                f"r{n}", experiment_id, "governed_loop/test",
                {"finished": 1, "aligned_with_intent": 1, "iterations": 2}, {"namespace": namespace})

        result = asyncio.run(loop.run(RISKY_GOAL))
        assert result["stopped_reason"] == "llm_finished"
        data = result["growth"]["data"]
        assert data["D"] > 0.7
        assert data["parts"]["memory"] > 0 and data["parts"]["skills"] > 0 and data["parts"]["record"] > 0

    def test_a_clear_low_risk_goal_about_a_real_file_passes_with_no_history(self, tmp_path, kernel, monkeypatch):
        _script(monkeypatch, [[LS, FINISH]])
        loop = _loop(tmp_path, kernel)
        result = asyncio.run(loop.run("Read the file pyproject.toml in the repository and tell me the project name"))
        assert result["stopped_reason"] == "llm_finished"
        assert result["growth"]["data"]["parts"]["grounding"] == 1.0

    def test_unrelated_memory_is_not_injected_into_the_prompt(self, tmp_path, kernel, monkeypatch):
        state = _script(monkeypatch, [[FINISH]])
        loop = _loop(tmp_path, kernel)
        asyncio.run(AgentMemory(loop.namespace, loop._persistence).store("my cat likes tuna", MemoryType.FACT))
        asyncio.run(loop.run("Read the file pyproject.toml and tell me the project name"))
        assert "tuna" not in state["contexts"][0]


class TestGrowthInTheLoop:
    def test_g_accumulates_across_episodes_and_loop_objects(self, tmp_path, kernel, monkeypatch):
        _script(monkeypatch, [[FINISH]])
        goal = "Read the file pyproject.toml and tell me the project name"
        first = _loop(tmp_path, kernel)
        r1 = asyncio.run(first.run(goal))
        second = _loop(tmp_path, kernel)            # a new object, as a new gateway message would build
        r2 = asyncio.run(second.run(goal))
        assert r1["growth"]["G"] > 1.0
        assert r2["growth"]["G"] > r1["growth"]["G"]
        assert second._growth.episodes == 2

    def test_a_repeat_with_fewer_steps_is_credited_with_the_gain(self, tmp_path, kernel, monkeypatch):
        _script(monkeypatch, [[LS, FINISH], [FINISH]])   # FAST route caps an episode at 3 steps
        goal = "Read the file pyproject.toml and tell me the project name"
        loop = _loop(tmp_path, kernel)
        r1 = asyncio.run(loop.run(goal))
        r2 = asyncio.run(_loop(tmp_path, kernel).run(goal))
        assert r1["iterations"] > r2["iterations"]
        assert r2["growth"]["parts"]["baseline"]["runs"] == 1
        assert r2["growth"]["parts"]["gains"]["iterations"] == pytest.approx(0.5)
        assert r2["growth"]["parts"]["efficiency"] != 0.0

    def test_reused_skills_are_credited_when_the_episode_is_verified(self, tmp_path, kernel, monkeypatch):
        _script(monkeypatch, [[FINISH]])
        loop = _loop(tmp_path, kernel)
        goal = "Read the file pyproject.toml and tell me the project name"
        asyncio.run(loop.run(goal))                   # learns the skill
        asyncio.run(_loop(tmp_path, kernel).run(goal))  # reuses it
        skills = SkillLibrary(db_path=str(tmp_path / "r51.db.skills")).retrieve_similar_skills(goal)
        assert skills and skills[0].uses >= 1 and skills[0].successes >= 1
        assert SkillLibrary(db_path=str(tmp_path / "r51.db.skills")).count() == 1   # deduplicated, not a second copy

    def test_the_experiment_run_records_D_and_the_growth_step(self, tmp_path, kernel, monkeypatch):
        _script(monkeypatch, [[FINISH]])
        loop = _loop(tmp_path, kernel)
        result = asyncio.run(loop.run("Read the file pyproject.toml and tell me the project name"))
        runs = loop._persistence.get_experiment_runs(result["experiment"]["experiment_id"])
        assert runs[-1]["metrics"]["data_D"] > 0 and runs[-1]["metrics"]["growth_delta"] > 0.5

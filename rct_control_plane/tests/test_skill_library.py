"""
Tests for the MEE-gated Skill Library MVP (rct_control_plane/skill_library.py).

Covers:
  - Extraction happens when growth is real, positive, non-violating.
  - Extraction does NOT happen when growth is flat/negative or governance
    was violated.
  - retrieve_similar_skills returns genuinely relevant results for an
    obviously-similar problem and not for an obviously-different one.
  - Persistence survives a fresh SkillLibrary instance pointed at the same
    on-disk file (i.e. survives a "process restart"), not just in-memory.
  - Wiring into AutonomousBackEdgeDaemon.execute_autonomous_step really
    persists a queryable skill on a real successful task, and does not on
    a governance-blocked task.
"""

import sqlite3

import pytest

from rct_control_plane.mee_engine import MEESession
from rct_control_plane.skill_library import SkillLibrary, SkillRecord
from rct_control_plane.autonomous_backedge_daemon import AutonomousBackEdgeDaemon


# ─── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "skills_test.db")


@pytest.fixture
def library(db_path):
    return SkillLibrary(db_path=db_path)


def _step(session: MEESession, delta: float, governance_violation: bool = False):
    """Advance a real MEESession and return the real MEEStepRecord."""
    return session.step(delta=delta, governance_violation=governance_violation)


# ─── Extraction gate ────────────────────────────────────────────────────────


class TestMaybeExtractSkill:
    def test_extracts_on_real_positive_non_violating_growth(self, library):
        session = MEESession(session_id="extract-pos")
        growth = _step(session, delta=0.15, governance_violation=False)

        record = library.maybe_extract_skill(
            problem_statement="Fix flaky retry logic in the payment webhook handler",
            action_sequence_or_solution={"steps": ["add jitter", "cap backoff at 30s"]},
            growth_step=growth,
        )

        assert record is not None
        assert isinstance(record, SkillRecord)
        assert record.delta == pytest.approx(0.15)
        assert record.governance_violation is False
        assert library.count() == 1

    def test_does_not_extract_on_zero_delta(self, library):
        session = MEESession(session_id="extract-zero")
        growth = _step(session, delta=0.0, governance_violation=False)

        record = library.maybe_extract_skill(
            problem_statement="A task that produced no measured improvement",
            action_sequence_or_solution={"steps": ["did nothing useful"]},
            growth_step=growth,
        )

        assert record is None
        assert library.count() == 0

    def test_does_not_extract_on_negative_delta(self, library):
        session = MEESession(session_id="extract-neg")
        growth = _step(session, delta=-0.2, governance_violation=False)

        record = library.maybe_extract_skill(
            problem_statement="A task that regressed things",
            action_sequence_or_solution={"steps": ["broke the build"]},
            growth_step=growth,
        )

        assert record is None
        assert library.count() == 0

    def test_does_not_extract_on_governance_violation_even_with_positive_delta(
        self, library
    ):
        session = MEESession(session_id="extract-violation")
        # Positive delta but governance_violation=True must still block
        # extraction, per the documented gate.
        growth = _step(session, delta=0.30, governance_violation=True)

        record = library.maybe_extract_skill(
            problem_statement="A task that 'succeeded' but violated governance",
            action_sequence_or_solution={"steps": ["did the forbidden thing"]},
            growth_step=growth,
        )

        assert record is None
        assert library.count() == 0

    def test_accepts_growth_step_as_plain_dict(self, library):
        growth = {
            "delta": 0.1,
            "resilience": 1.0,
            "g_before": 1.0,
            "g_after": 1.01,
            "governance_violation": False,
        }
        record = library.maybe_extract_skill(
            problem_statement="Dict-shaped growth step still works",
            action_sequence_or_solution="solution text",
            growth_step=growth,
        )
        assert record is not None
        assert record.g_after == pytest.approx(1.01)


# ─── Retrieval ──────────────────────────────────────────────────────────────


class TestRetrieveSimilarSkills:
    def _seed(self, library):
        session = MEESession(session_id="seed")
        library.maybe_extract_skill(
            problem_statement="Fix flaky retry logic in the payment webhook handler",
            action_sequence_or_solution={"steps": ["add jitter", "cap backoff"]},
            growth_step=_step(session, delta=0.1),
        )
        library.maybe_extract_skill(
            problem_statement="Retry payment webhook calls with exponential backoff",
            action_sequence_or_solution={"steps": ["exponential backoff wrapper"]},
            growth_step=_step(session, delta=0.1),
        )
        library.maybe_extract_skill(
            problem_statement="Render a kawaii slide deck PDF from a document",
            action_sequence_or_solution={"steps": ["convert doc to slides"]},
            growth_step=_step(session, delta=0.1),
        )

    def test_returns_relevant_results_for_similar_problem(self, library):
        self._seed(library)

        results = library.retrieve_similar_skills(
            "Payment webhook retry keeps flaking, need backoff", top_k=3
        )

        assert len(results) >= 1
        problem_statements = [r.problem_statement for r in results]
        assert any("payment webhook" in p.lower() for p in problem_statements)
        assert all(r.similarity_score and r.similarity_score > 0 for r in results)

    def test_excludes_unrelated_results_for_different_problem(self, library):
        self._seed(library)

        results = library.retrieve_similar_skills(
            "Payment webhook retry keeps flaking, need backoff", top_k=3
        )

        problem_statements = [r.problem_statement for r in results]
        assert not any("kawaii" in p.lower() for p in problem_statements)

    def test_returns_empty_when_nothing_overlaps(self, library):
        self._seed(library)

        results = library.retrieve_similar_skills(
            "Completely unrelated query about zzzqux flibbertigibbet"
        )
        assert results == []

    def test_respects_top_k(self, library):
        session = MEESession(session_id="topk")
        for i in range(5):
            library.maybe_extract_skill(
                problem_statement=f"Refactor the authentication module part {i}",
                action_sequence_or_solution={"n": i},
                growth_step=_step(session, delta=0.05),
            )
        results = library.retrieve_similar_skills(
            "Refactor authentication module please", top_k=2
        )
        assert len(results) == 2


# ─── Persistence survives reconnect ─────────────────────────────────────────


class TestPersistenceSurvivesReconnect:
    def test_skill_persists_across_fresh_library_instances(self, db_path):
        session = MEESession(session_id="persist")
        lib1 = SkillLibrary(db_path=db_path)
        record = lib1.maybe_extract_skill(
            problem_statement="Deduplicate the intent compiler's token cache",
            action_sequence_or_solution={"steps": ["add LRU cache"]},
            growth_step=_step(session, delta=0.2),
        )
        assert record is not None
        del lib1  # drop the in-memory object entirely

        # Fresh instance, fresh connection, same on-disk file — simulates a
        # process restart / reconnect.
        lib2 = SkillLibrary(db_path=db_path)
        assert lib2.count() == 1

        fetched = lib2.get_skill(record.id)
        assert fetched is not None
        assert fetched.problem_statement == record.problem_statement
        assert fetched.delta == pytest.approx(record.delta)

        results = lib2.retrieve_similar_skills("intent compiler token cache dedup")
        assert any(r.id == record.id for r in results)

        # And it really is sitting in a plain sqlite file on disk, not just
        # reconstructed in memory.
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT problem_statement FROM skills WHERE id = ?", (record.id,)
            ).fetchone()
        assert row is not None
        assert row[0] == record.problem_statement


# ─── Real wiring through AutonomousBackEdgeDaemon ──────────────────────────


class TestDaemonWiring:
    def test_successful_task_really_persists_a_queryable_skill(self, tmp_path):
        daemon = AutonomousBackEdgeDaemon(data_dir=str(tmp_path))

        result = daemon.execute_autonomous_step(
            "task_skill_001", "Build a caching layer for the vector search API"
        )
        assert result["success"] is True

        # The skill library the daemon wired itself to should now really
        # contain a persisted, queryable skill for this task.
        assert daemon._skill_library.count() == 1
        found = daemon._skill_library.retrieve_similar_skills(
            "Build caching layer for vector search"
        )
        assert len(found) == 1
        assert "caching layer" in found[0].problem_statement.lower()

        # And it is real on-disk state: a fresh SkillLibrary pointed at the
        # same file (the daemon's own resolved data_dir) sees it too.
        reconnected = SkillLibrary(db_path=str(daemon.data_dir / "skills.db"))
        assert reconnected.count() == 1

    def test_governance_blocked_task_does_not_persist_a_skill(self, tmp_path):
        daemon = AutonomousBackEdgeDaemon(data_dir=str(tmp_path))

        daemon.record_backedge_failure(
            task_name="deploy_task",
            error_message="TypeError: Cannot read property of undefined",
            proposed_rule="FORBID_UNDEFINED_PROP_ACCESS",
        )

        result = daemon.execute_autonomous_step(
            "task_skill_002", "Execute with FORBID_UNDEFINED_PROP_ACCESS"
        )
        assert result["success"] is False
        assert result["status"] == "BLOCKED_BY_BACKEDGE_INVARIANT"

        # Blocked step -> governance_violation=True on the MEE step ->
        # the growth gate must reject it, even though delta is negative
        # anyway (belt and suspenders: both conditions independently
        # reject it).
        assert daemon._skill_library.count() == 0

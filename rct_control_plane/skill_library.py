"""
Skill Library — MEE-Gated Reusable Skill Extraction (MVP vertical slice)

Implements the smallest real, testable slice of the "Hermes-style persistent
skill library" idea from the strategic design comparison to NousResearch's
Hermes agent runtime: when a task/turn finishes with *real, positive,
non-governance-violating* growth (as measured by the existing MEE v2 engine,
``rct_control_plane.mee_engine.MEESession`` — see that module for the
``G(t+1) = G(t) x (1 + M*delta) x R_t`` formula), the outcome is persisted as
a reusable "skill" that can later be retrieved for a similar problem instead
of re-deriving the same solution from scratch.

This module deliberately does NOT build the full system described in the
strategic design doc. It builds only:

    1. A persistence layer for skill records (SQLite — see "Persistence"
       below for why).
    2. ``maybe_extract_skill()`` — the MEE-gated write path.
    3. ``retrieve_similar_skills()`` — a real (not simulated) read path
       using an honest keyword/token-overlap similarity metric (see
       "Similarity" below for why this is a documented first cut rather
       than real embedding-based semantic search).

What this MVP does NOT do (left for the next planning round — see the
CLAUDE.md-referenced strategic design doc / task report for the full list):
    - No embedding-based semantic similarity (falls back to token overlap;
      real embedding infra is reachable only as a separate deployed HTTP
      microservice — ``microservices/vector-search`` — not as an importable
      Python library, and standing up that HTTP round-trip is out of scope
      here).
    - No skill re-application/injection into a new turn's prompt — this
      slice only extracts and retrieves, it does not act on retrieved
      skills.
    - No pruning, expiry, deduplication, or ranking-model training for
      stored skills.
    - No UI or API endpoint.

Persistence
-----------
``rct_control_plane/persistence.py`` (``ControlPlanePersistence``) already
establishes the on-disk SQLite convention for this package: a single file at
``rct_control_plane.db`` (overridable via the ``RCT_DB_PATH`` env var), a
``CREATE TABLE IF NOT EXISTS`` schema bootstrap, WAL journal mode, and plain
``sqlite3`` (no extra dependency). This module reuses that same convention
and the same default on-disk file, so skill records live alongside the rest
of the control-plane state — but it opens its own connection and defines its
own ``skills`` table (``CREATE TABLE IF NOT EXISTS``, additive only) rather
than importing ``ControlPlanePersistence``'s private schema constant, to
avoid coupling to another module's internals. No table is ever dropped or
altered destructively, per the workspace's Zero-Delete policy; this module
does not expose a delete/prune API at all in this slice.

Extraction threshold
---------------------
``maybe_extract_skill`` persists a skill if and only if:

    growth_step.delta > 0   AND   growth_step.governance_violation is False

This is the simplest *honest* gate available: ``delta`` is the real, signed
improvement value already computed by ``MEESession.step()`` for this turn —
it is not re-derived or estimated here. A ``delta`` of exactly 0 or negative
means the MEE formula itself did not register improvement for this step, so
there is nothing worth reinforcing as a reusable skill. Governance violations
are excluded unconditionally, independent of ``delta``, because an action
that violated governance must never be reinforced as "the way to do this,"
even if it happened to also show numeric growth. No additional magic-number
margin (e.g. "delta > 0.05") is applied, because there is no empirical basis
yet for such a threshold — inventing one here would be exactly the kind of
unjustified magic number this task was scoped to avoid.

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

SKILL_LIBRARY_VERSION = "0.1"

# ---------------------------------------------------------------------------
# Default DB path — mirrors persistence.py's convention exactly (same env
# var, same default file) so skills live in the same on-disk database as
# the rest of the control plane's local-dev state.
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = os.environ.get(
    "RCT_DB_PATH",
    str(Path(__file__).parent.parent / "rct_control_plane.db"),
)

_SKILLS_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

-- Additive only: never dropped/altered, per workspace Zero-Delete policy.
CREATE TABLE IF NOT EXISTS skills (
    id                   TEXT PRIMARY KEY,
    problem_statement    TEXT NOT NULL,
    solution             TEXT NOT NULL,   -- JSON-encoded action_sequence_or_solution
    keywords             TEXT NOT NULL,   -- JSON list[str], precomputed token set
    delta                REAL NOT NULL,
    resilience           REAL NOT NULL,
    g_before             REAL NOT NULL,
    g_after              REAL NOT NULL,
    growth_ratio         REAL NOT NULL,
    governance_violation INTEGER NOT NULL,
    session_id           TEXT,
    created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_skills_created ON skills(created_at);
"""

# Small stopword list for the keyword/token-overlap similarity fallback.
# Deliberately tiny — this is an honest, simple first cut, not a claim of
# linguistic sophistication.
_STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "is", "are",
    "with", "that", "this", "from", "by", "as", "at", "be", "it", "its",
    "into", "or", "was", "were", "will", "we", "you", "your", "our", "i",
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    """
    Honest, simple token-overlap tokenizer: lowercase word/number tokens,
    length > 2, minus a tiny stopword list. Not semantic — see module
    docstring "Similarity" section.
    """
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if len(t) > 2 and t not in _STOPWORDS]


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    union = len(a | b)
    return intersection / union if union else 0.0


def _growth_field(growth_step: Any, name: str, default: Any = None) -> Any:
    """
    Read a field off ``growth_step`` whether it's an
    ``rct_control_plane.mee_engine.MEEStepRecord`` (dataclass, attribute
    access) or a plain dict with the same keys (delta, resilience,
    g_before, g_after, governance_violation). This lets callers pass
    either the real MEEStepRecord returned by ``MEESession.step()`` or a
    dict built from one (e.g. after JSON round-tripping).
    """
    if isinstance(growth_step, dict):
        return growth_step.get(name, default)
    return getattr(growth_step, name, default)


@dataclass
class SkillRecord:
    """A single persisted, MEE-gated reusable skill."""

    id: str
    problem_statement: str
    solution: Any
    keywords: List[str]
    delta: float
    resilience: float
    g_before: float
    g_after: float
    growth_ratio: float
    governance_violation: bool
    created_at: str
    session_id: Optional[str] = None
    # Populated only on records returned by retrieve_similar_skills();
    # None for freshly-extracted records that haven't been scored against
    # a query yet.
    similarity_score: Optional[float] = field(default=None, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "problem_statement": self.problem_statement,
            "solution": self.solution,
            "keywords": list(self.keywords),
            "delta": round(self.delta, 6),
            "resilience": round(self.resilience, 4),
            "g_before": round(self.g_before, 6),
            "g_after": round(self.g_after, 6),
            "growth_ratio": round(self.growth_ratio, 4),
            "governance_violation": self.governance_violation,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "similarity_score": self.similarity_score,
        }


class SkillLibrary:
    """
    MEE-gated persistent skill library.

    Args:
        db_path: SQLite file path. Defaults to the same on-disk file as
            ``rct_control_plane.persistence.ControlPlanePersistence``
            (``RCT_DB_PATH`` env var, else ``rct_control_plane.db`` at the
            repo root), so skills live alongside the rest of the local
            control-plane state. Pass a ``tmp_path`` in tests to isolate.

    Example::

        lib = SkillLibrary()
        record = lib.maybe_extract_skill(
            problem_statement="Fix flaky retry logic in payment_engine",
            action_sequence_or_solution={"steps": ["add jitter", "add backoff cap"]},
            growth_step=mee_session.step(delta=0.12),
        )
        similar = lib.retrieve_similar_skills("payment retry keeps flaking", top_k=3)
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SKILLS_SCHEMA_SQL)

    # ------------------------------------------------------------------
    # Write path — the growth-gated extraction
    # ------------------------------------------------------------------

    def maybe_extract_skill(
        self,
        problem_statement: str,
        action_sequence_or_solution: Any,
        growth_step: Any,
        *,
        session_id: Optional[str] = None,
    ) -> Optional[SkillRecord]:
        """
        Persist ``action_sequence_or_solution`` as a reusable skill IF AND
        ONLY IF the supplied MEE growth step represents real, positive,
        non-governance-violating growth. See module docstring
        "Extraction threshold" for the exact rule and rationale.

        Args:
            problem_statement: The task/problem this solution addresses.
            action_sequence_or_solution: Anything JSON-serializable
                describing the solution (a plan, a list of actions, a
                diff, free text, etc.) — stored as-is (JSON-encoded).
            growth_step: The real ``MEEStepRecord`` returned by
                ``MEESession.step()`` for this turn (or an equivalent dict
                with the same field names).
            session_id: Optional MEE/agent session id this step came from,
                stored for provenance.

        Returns:
            The persisted ``SkillRecord``, or ``None`` if the growth gate
            rejected this outcome (nothing is written in that case).
        """
        delta = float(_growth_field(growth_step, "delta", 0.0))
        governance_violation = bool(
            _growth_field(growth_step, "governance_violation", False)
        )

        if delta <= 0.0 or governance_violation:
            return None

        resilience = float(_growth_field(growth_step, "resilience", 1.0))
        g_before = float(_growth_field(growth_step, "g_before", 0.0))
        g_after = float(_growth_field(growth_step, "g_after", g_before))
        growth_ratio = g_after / g_before if g_before else 1.0

        keywords = _tokenize(problem_statement)
        record = SkillRecord(
            id=str(uuid.uuid4()),
            problem_statement=problem_statement,
            solution=action_sequence_or_solution,
            keywords=keywords,
            delta=delta,
            resilience=resilience,
            g_before=g_before,
            g_after=g_after,
            growth_ratio=growth_ratio,
            governance_violation=governance_violation,
            created_at=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO skills
                   (id, problem_statement, solution, keywords, delta,
                    resilience, g_before, g_after, growth_ratio,
                    governance_violation, session_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.problem_statement,
                    json.dumps(record.solution),
                    json.dumps(record.keywords),
                    record.delta,
                    record.resilience,
                    record.g_before,
                    record.g_after,
                    record.growth_ratio,
                    1 if record.governance_violation else 0,
                    record.session_id,
                    record.created_at,
                ),
            )

        return record

    # ------------------------------------------------------------------
    # Read path — token-overlap similarity retrieval
    # ------------------------------------------------------------------

    def retrieve_similar_skills(
        self, new_problem_statement: str, top_k: int = 3
    ) -> List[SkillRecord]:
        """
        Return the ``top_k`` stored skills most relevant to
        ``new_problem_statement``.

        Similarity: Jaccard token overlap between the query's keyword set
        and each stored skill's precomputed keyword set (see module
        docstring "Similarity" for why this is an honest first cut rather
        than real embedding-based semantic search). Only skills with a
        strictly positive overlap score are returned; ties are broken by
        recency (most recent first).
        """
        if top_k <= 0:
            return []

        query_tokens = set(_tokenize(new_problem_statement))
        if not query_tokens:
            return []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM skills ORDER BY created_at DESC"
            ).fetchall()

        scored: List[SkillRecord] = []
        for row in rows:
            stored_tokens = set(json.loads(row["keywords"]))
            score = _jaccard(query_tokens, stored_tokens)
            if score <= 0.0:
                continue
            record = SkillRecord(
                id=row["id"],
                problem_statement=row["problem_statement"],
                solution=json.loads(row["solution"]),
                keywords=json.loads(row["keywords"]),
                delta=row["delta"],
                resilience=row["resilience"],
                g_before=row["g_before"],
                g_after=row["g_after"],
                growth_ratio=row["growth_ratio"],
                governance_violation=bool(row["governance_violation"]),
                created_at=row["created_at"],
                session_id=row["session_id"],
                similarity_score=score,
            )
            scored.append(record)

        scored.sort(key=lambda r: (r.similarity_score, r.created_at), reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Misc read helpers (no delete/prune API in this slice — Zero-Delete)
    # ------------------------------------------------------------------

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM skills").fetchone()
        return int(row[0]) if row else 0

    def get_skill(self, skill_id: str) -> Optional[SkillRecord]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM skills WHERE id = ?", (skill_id,)
            ).fetchone()
        if row is None:
            return None
        return SkillRecord(
            id=row["id"],
            problem_statement=row["problem_statement"],
            solution=json.loads(row["solution"]),
            keywords=json.loads(row["keywords"]),
            delta=row["delta"],
            resilience=row["resilience"],
            g_before=row["g_before"],
            g_after=row["g_after"],
            growth_ratio=row["growth_ratio"],
            governance_violation=bool(row["governance_violation"]),
            created_at=row["created_at"],
            session_id=row["session_id"],
        )

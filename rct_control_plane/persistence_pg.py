"""
RCT Control Plane — PostgreSQL Persistence Layer (Phase B1)

Drop-in replacement for ``ControlPlanePersistence`` (SQLite) with an
identical public API.  Switch backends via the ``RCT_DB_BACKEND``
environment variable::

    RCT_DB_BACKEND=postgres   → PostgresPersistence (this module)
    RCT_DB_BACKEND=sqlite     → ControlPlanePersistence  (default)

Connection string priority:
  1. ``RCT_PG_DSN``   — full DSN, e.g. ``postgresql://user:pass@host:5432/rctdb``
  2. Individual env vars: RCT_PG_HOST / RCT_PG_PORT / RCT_PG_DB /
     RCT_PG_USER / RCT_PG_PASS

Usage::

    from rct_control_plane.persistence_pg import get_persistence
    db = get_persistence()                          # auto-selects backend
    db.save_intent(intent_id, user_id, type, goal)

    from rct_control_plane.persistence_pg import PostgresPersistence
    db = PostgresPersistence(dsn="postgresql://localhost/rctdb")

Requires: ``pip install psycopg2-binary``
Optional pgvector: ``pip install pgvector`` → enables ``enable_pgvector()``
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

POSTGRES_PERSISTENCE_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Optional psycopg2 dependency
# ---------------------------------------------------------------------------
_HAS_PSYCOPG2: bool = False
psycopg2: Any = None  # module-level placeholder so patch() can find it
try:
    import psycopg2  # type: ignore[import, no-redef]
    import psycopg2.extras  # type: ignore[import, no-redef]
    _HAS_PSYCOPG2 = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# DSN builder
# ---------------------------------------------------------------------------

def _build_dsn() -> str:
    """Return PostgreSQL DSN from ``RCT_PG_DSN`` or individual env vars."""
    if dsn := os.environ.get("RCT_PG_DSN"):
        return dsn
    host = os.environ.get("RCT_PG_HOST", "localhost")
    port = os.environ.get("RCT_PG_PORT", "5432")
    db   = os.environ.get("RCT_PG_DB",   "rctdb")
    user = os.environ.get("RCT_PG_USER", "rct")
    pw   = os.environ.get("RCT_PG_PASS", "")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


# ---------------------------------------------------------------------------
# Schema DDL — mirrors SQLite schema with PostgreSQL idioms
# ---------------------------------------------------------------------------

_PG_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS intents (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    user_tier    TEXT NOT NULL DEFAULT 'FREE',
    intent_type  TEXT NOT NULL,
    goal         TEXT NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL,
    is_valid     BOOLEAN NOT NULL DEFAULT TRUE,
    errors       JSONB NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS states (
    id           TEXT PRIMARY KEY,
    namespace    TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL,
    UNIQUE(namespace, key)
);

CREATE TABLE IF NOT EXISTS policy_decisions (
    id           TEXT PRIMARY KEY,
    intent_id    TEXT REFERENCES intents(id) ON DELETE SET NULL,
    user_id      TEXT NOT NULL,
    decision     TEXT NOT NULL,
    policy_name  TEXT NOT NULL,
    reason       TEXT,
    created_at   TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_trail (
    id           BIGSERIAL PRIMARY KEY,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT,
    action       TEXT NOT NULL,
    actor        TEXT,
    changes      JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intents_user   ON intents(user_id);
CREATE INDEX IF NOT EXISTS idx_intents_type   ON intents(intent_type);
CREATE INDEX IF NOT EXISTS idx_states_ns_key  ON states(namespace, key);
CREATE INDEX IF NOT EXISTS idx_audit_entity   ON audit_trail(entity_type, entity_id)\
"""

_PGVECTOR_SQL = """\
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE intents ADD COLUMN IF NOT EXISTS embedding vector(1536);
CREATE INDEX IF NOT EXISTS idx_intents_emb ON intents USING ivfflat (embedding vector_cosine_ops)\
"""


# ===========================================================================
# PostgresPersistence
# ===========================================================================

class PostgresPersistence:
    """
    Synchronous PostgreSQL persistence — identical API to
    ``ControlPlanePersistence``.

    Requires ``psycopg2-binary``.
    """

    def __init__(self, dsn: Optional[str] = None) -> None:
        if not _HAS_PSYCOPG2:
            raise ImportError(
                "PostgresPersistence requires psycopg2. "
                "Install with: pip install psycopg2-binary"
            )
        self._dsn = dsn or _build_dsn()
        self._init_schema()

    # ------------------------------------------------------------------
    # Connection context manager
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Generator:
        conn = psycopg2.connect(self._dsn)  # type: ignore[name-defined]
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                for stmt in [s.strip() for s in _PG_SCHEMA_SQL.split(";") if s.strip()]:
                    cur.execute(stmt)

    def enable_pgvector(self) -> None:
        """Add pgvector extension + embedding column (optional feature)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                for stmt in [s.strip() for s in _PGVECTOR_SQL.split(";") if s.strip()]:
                    cur.execute(stmt)

    # ------------------------------------------------------------------
    # Intents
    # ------------------------------------------------------------------

    def save_intent(
        self,
        intent_id: str,
        user_id: str,
        intent_type: str,
        goal: str,
        *,
        user_tier: str = "FREE",
        metadata: Optional[Dict[str, Any]] = None,
        is_valid: bool = True,
        errors: Optional[List[str]] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO intents
                       (id, user_id, user_tier, intent_type, goal, metadata,
                        created_at, is_valid, errors)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO UPDATE SET
                         user_tier   = EXCLUDED.user_tier,
                         intent_type = EXCLUDED.intent_type,
                         goal        = EXCLUDED.goal,
                         metadata    = EXCLUDED.metadata,
                         is_valid    = EXCLUDED.is_valid,
                         errors      = EXCLUDED.errors""",
                    (
                        intent_id, user_id, user_tier, intent_type,
                        goal[:1000],
                        psycopg2.extras.Json(metadata or {}),  # type: ignore[name-defined]
                        now,
                        is_valid,
                        psycopg2.extras.Json(errors or []),  # type: ignore[name-defined]
                    ),
                )
                self._append_audit_cur(cur, "intent", intent_id, "SAVE", user_id, {})

    def get_intent(self, intent_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor  # type: ignore[name-defined]
            ) as cur:
                cur.execute("SELECT * FROM intents WHERE id = %s", (intent_id,))
                row = cur.fetchone()
        if row is None:
            return None
        return _pg_row_to_dict(row)

    def list_intents(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor  # type: ignore[name-defined]
            ) as cur:
                if user_id:
                    cur.execute(
                        "SELECT * FROM intents WHERE user_id = %s "
                        "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (user_id, limit, offset),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM intents ORDER BY created_at DESC "
                        "LIMIT %s OFFSET %s",
                        (limit, offset),
                    )
                rows = cur.fetchall()
        return [_pg_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------

    def save_state(
        self,
        state_id: str,
        namespace: str,
        key: str,
        value: Dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO states (id, namespace, key, value, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (namespace, key) DO UPDATE SET
                         value      = EXCLUDED.value,
                         updated_at = EXCLUDED.updated_at""",
                    (
                        state_id, namespace, key,
                        psycopg2.extras.Json(value),  # type: ignore[name-defined]
                        now, now,
                    ),
                )

    def get_state(self, namespace: str, key: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor  # type: ignore[name-defined]
            ) as cur:
                cur.execute(
                    "SELECT * FROM states WHERE namespace = %s AND key = %s",
                    (namespace, key),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return _pg_row_to_dict(row)

    # ------------------------------------------------------------------
    # Policy decisions
    # ------------------------------------------------------------------

    def save_policy_decision(
        self,
        decision_id: str,
        user_id: str,
        decision: str,
        policy_name: str,
        *,
        intent_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO policy_decisions
                       (id, intent_id, user_id, decision, policy_name, reason, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO UPDATE SET
                         decision    = EXCLUDED.decision,
                         policy_name = EXCLUDED.policy_name,
                         reason      = EXCLUDED.reason""",
                    (decision_id, intent_id, user_id, decision, policy_name, reason, now),
                )

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------

    def append_audit(
        self,
        entity_type: str,
        entity_id: Optional[str],
        action: str,
        actor: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._append_audit_cur(
                    cur, entity_type, entity_id, action, actor, changes or {}
                )

    @staticmethod
    def _append_audit_cur(
        cur: Any,
        entity_type: str,
        entity_id: Optional[str],
        action: str,
        actor: Optional[str],
        changes: Dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc)
        cur.execute(
            """INSERT INTO audit_trail
               (entity_type, entity_id, action, actor, changes, created_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                entity_type, entity_id, action, actor,
                psycopg2.extras.Json(changes),  # type: ignore[name-defined]
                now,
            ),
        )

    def recent_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor  # type: ignore[name-defined]
            ) as cur:
                cur.execute(
                    "SELECT * FROM audit_trail ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
        return [_pg_row_to_dict(r) for r in rows]


# ===========================================================================
# Factory — auto-selects backend from RCT_DB_BACKEND env var
# ===========================================================================

def get_persistence(backend: Optional[str] = None):
    """
    Return the correct persistence backend::

        RCT_DB_BACKEND=sqlite    → ControlPlanePersistence  (default)
        RCT_DB_BACKEND=postgres  → PostgresPersistence

    Args:
        backend: explicitly override env var; ``"sqlite"`` or ``"postgres"``
    """
    b = (backend or os.environ.get("RCT_DB_BACKEND", "sqlite")).lower()
    if b == "postgres":
        return PostgresPersistence()
    from rct_control_plane.persistence import ControlPlanePersistence
    return ControlPlanePersistence()


# ===========================================================================
# Row helper
# ===========================================================================

def _pg_row_to_dict(row: Any) -> Dict[str, Any]:
    """Normalise a psycopg2 RealDictRow to a plain Python dict."""
    d = dict(row)
    # JSONB columns already come back as Python objects — no decode needed.
    # Convert datetime objects to ISO strings to match SQLite layer.
    for col in ("created_at", "updated_at"):
        if col in d and hasattr(d[col], "isoformat"):
            d[col] = d[col].isoformat()
    # is_valid: bool → int (matches SQLite behaviour for cross-backend compat)
    if "is_valid" in d and isinstance(d["is_valid"], bool):
        d["is_valid"] = int(d["is_valid"])
    return d

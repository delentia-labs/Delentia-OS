"""
RCT Control Plane — SQLite Persistence Layer

Lightweight local persistence for intents, states, policy decisions, and audit
trail.  Mirrors the RCTDB 8-dimensional record structure so data can be
promoted to the enterprise PostgreSQL + pgvector RCTDB without schema changes.

Usage (sync / always available)::

    from rct_control_plane.persistence import ControlPlanePersistence
    db = ControlPlanePersistence()               # default: rct_control_plane.db
    db.save_intent(intent_id, user_id, type_value, goal, metadata_dict)
    db.save_state(state_id, namespace, key, value_dict)
    intents = db.list_intents(limit=20)

Optional async usage (requires ``aiosqlite``)::

    from rct_control_plane.persistence import AsyncControlPlanePersistence
    async with AsyncControlPlanePersistence() as db:
        await db.save_intent(...)

Note: This is a local-dev bridge. Production deployments connect to RCTDB
(PostgreSQL + pgvector + Redis) in rct-ecosystem-private.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Optional async backend
# ---------------------------------------------------------------------------
_HAS_AIOSQLITE: bool = False
try:
    import aiosqlite as _aiosqlite  # type: ignore[import-untyped]
    _HAS_AIOSQLITE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Default DB path — can be overridden with RCT_DB_PATH env var
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = os.environ.get(
    "RCT_DB_PATH",
    str(Path(__file__).parent.parent / "rct_control_plane.db"),
)

# ---------------------------------------------------------------------------
# DDL — schema mirrors RCTDB 8-dimensional structure
# ---------------------------------------------------------------------------
_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Dimension 1 (Identity) + 2 (Context) captured in intents table
CREATE TABLE IF NOT EXISTS intents (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    user_tier    TEXT NOT NULL DEFAULT 'FREE',
    intent_type  TEXT NOT NULL,
    goal         TEXT NOT NULL,
    -- Dimension 3: payload
    metadata     TEXT NOT NULL DEFAULT '{}',
    -- Dimension 7: timestamp
    created_at   TEXT NOT NULL,
    -- Dimension 4: verification
    is_valid     INTEGER NOT NULL DEFAULT 1,
    errors       TEXT NOT NULL DEFAULT '[]'
);

-- Key-value state store (mirrors RCTDB context/evolution dimensions)
CREATE TABLE IF NOT EXISTS states (
    id           TEXT PRIMARY KEY,
    namespace    TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(namespace, key)
);

-- Policy decisions (Dimension 4 — Verification)
CREATE TABLE IF NOT EXISTS policy_decisions (
    id           TEXT PRIMARY KEY,
    intent_id    TEXT,
    user_id      TEXT NOT NULL,
    decision     TEXT NOT NULL,
    policy_name  TEXT NOT NULL,
    reason       TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY(intent_id) REFERENCES intents(id) ON DELETE SET NULL
);

-- Audit trail (Dimension 8 — Provenance)
CREATE TABLE IF NOT EXISTS audit_trail (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT,
    action       TEXT NOT NULL,
    actor        TEXT,
    changes      TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intents_user   ON intents(user_id);
CREATE INDEX IF NOT EXISTS idx_intents_type   ON intents(intent_type);
CREATE INDEX IF NOT EXISTS idx_states_ns_key  ON states(namespace, key);
CREATE INDEX IF NOT EXISTS idx_audit_entity   ON audit_trail(entity_type, entity_id);
"""


# ===========================================================================
# Sync implementation (zero extra deps)
# ===========================================================================

class ControlPlanePersistence:
    """
    Synchronous SQLite persistence for the RCT Control Plane.

    Always available — no optional dependencies required.
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
            conn.executescript(_SCHEMA_SQL)

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
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO intents
                   (id, user_id, user_tier, intent_type, goal, metadata,
                    created_at, is_valid, errors)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    intent_id,
                    user_id,
                    user_tier,
                    intent_type,
                    goal[:1000],
                    json.dumps(metadata or {}),
                    now,
                    1 if is_valid else 0,
                    json.dumps(errors or []),
                ),
            )
            self._append_audit(conn, "intent", intent_id, "SAVE", user_id, {})

    def get_intent(self, intent_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM intents WHERE id = ?", (intent_id,)
            ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def list_intents(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM intents WHERE user_id = ? "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (user_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM intents ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [_row_to_dict(r) for r in rows]

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
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO states (id, namespace, key, value, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(namespace, key) DO UPDATE SET
                     value = excluded.value,
                     updated_at = excluded.updated_at""",
                (state_id, namespace, key, json.dumps(value), now, now),
            )

    def get_state(self, namespace: str, key: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM states WHERE namespace = ? AND key = ?",
                (namespace, key),
            ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

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
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO policy_decisions
                   (id, intent_id, user_id, decision, policy_name, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
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
        with sqlite3.connect(self.db_path) as conn:
            self._append_audit(conn, entity_type, entity_id, action, actor, changes or {})

    @staticmethod
    def _append_audit(
        conn: sqlite3.Connection,
        entity_type: str,
        entity_id: Optional[str],
        action: str,
        actor: Optional[str],
        changes: Dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO audit_trail
               (entity_type, entity_id, action, actor, changes, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entity_type, entity_id, action, actor, json.dumps(changes), now),
        )

    def recent_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_trail ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]


# ===========================================================================
# Async implementation (requires aiosqlite)
# ===========================================================================

class AsyncControlPlanePersistence:
    """
    Async SQLite persistence for the RCT Control Plane.

    Requires: ``pip install delentia-os[persistence]``

    Example::

        async with AsyncControlPlanePersistence() as db:
            await db.save_intent(intent_id, user_id, intent_type, goal)
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        if not _HAS_AIOSQLITE:
            raise ImportError(
                "AsyncControlPlanePersistence requires aiosqlite. "
                "Install with: pip install delentia-os[persistence]"
            )
        self.db_path = db_path
        self._conn: Any = None

    async def __aenter__(self) -> "AsyncControlPlanePersistence":
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await _aiosqlite.connect(self.db_path)
        await self._conn.executescript(_SCHEMA_SQL)
        await self._conn.commit()
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._conn:
            await self._conn.close()

    async def save_intent(
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
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """INSERT OR REPLACE INTO intents
               (id, user_id, user_tier, intent_type, goal, metadata,
                created_at, is_valid, errors)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                intent_id,
                user_id,
                user_tier,
                intent_type,
                goal[:1000],
                json.dumps(metadata or {}),
                now,
                1 if is_valid else 0,
                json.dumps(errors or []),
            ),
        )
        await self._conn.commit()

    async def get_intent(self, intent_id: str) -> Optional[Dict[str, Any]]:
        async with self._conn.execute(
            "SELECT * FROM intents WHERE id = ?", (intent_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))

    async def save_state(
        self,
        state_id: str,
        namespace: str,
        key: str,
        value: Dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """INSERT INTO states (id, namespace, key, value, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(namespace, key) DO UPDATE SET
                 value = excluded.value,
                 updated_at = excluded.updated_at""",
            (state_id, namespace, key, json.dumps(value), now, now),
        )
        await self._conn.commit()


# ===========================================================================
# Helper
# ===========================================================================

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    # Decode JSON columns
    for col in ("metadata", "errors", "value", "changes"):
        if col in d and isinstance(d[col], str):
            try:
                d[col] = json.loads(d[col])
            except (json.JSONDecodeError, TypeError):
                pass
    return d

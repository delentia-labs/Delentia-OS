"""
Tests for rct_control_plane.persistence_pg (Phase B1 — PostgreSQL backend)

Strategy:
- Tests 1–9:  pure logic (factory, DSN, schema text, row helper) — no mocks needed
- Tests 10–25: CRUD operations mocked via unittest.mock; psycopg2 is patched
  so the suite runs in any environment (no real DB required)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from rct_control_plane.persistence_pg import (
    POSTGRES_PERSISTENCE_VERSION,
    PostgresPersistence,
    _build_dsn,
    _pg_row_to_dict,
    get_persistence,
    _PG_SCHEMA_SQL,
)
from rct_control_plane.persistence import ControlPlanePersistence


# ===========================================================================
# 1. Constants
# ===========================================================================

class TestVersion:
    def test_version_constant_is_string(self):
        assert isinstance(POSTGRES_PERSISTENCE_VERSION, str)

    def test_version_is_1_0(self):
        assert POSTGRES_PERSISTENCE_VERSION == "1.0"


# ===========================================================================
# 2. DSN builder
# ===========================================================================

class TestBuildDSN:
    def test_returns_full_dsn_env_var(self, monkeypatch):
        monkeypatch.setenv("RCT_PG_DSN", "postgresql://custom/db")
        assert _build_dsn() == "postgresql://custom/db"

    def test_builds_from_individual_env_vars(self, monkeypatch):
        monkeypatch.delenv("RCT_PG_DSN", raising=False)
        monkeypatch.setenv("RCT_PG_HOST", "pghost")
        monkeypatch.setenv("RCT_PG_PORT", "5433")
        monkeypatch.setenv("RCT_PG_DB",   "mydb")
        monkeypatch.setenv("RCT_PG_USER", "alice")
        monkeypatch.setenv("RCT_PG_PASS", "secret")
        dsn = _build_dsn()
        assert dsn == "postgresql://alice:secret@pghost:5433/mydb"

    def test_uses_defaults_when_no_env(self, monkeypatch):
        for v in ("RCT_PG_DSN", "RCT_PG_HOST", "RCT_PG_PORT",
                  "RCT_PG_DB", "RCT_PG_USER", "RCT_PG_PASS"):
            monkeypatch.delenv(v, raising=False)
        dsn = _build_dsn()
        assert "localhost" in dsn
        assert "5432" in dsn
        assert "rctdb" in dsn

    def test_full_dsn_env_takes_priority_over_individual(self, monkeypatch):
        monkeypatch.setenv("RCT_PG_DSN", "postgresql://winner/db")
        monkeypatch.setenv("RCT_PG_HOST", "loser")
        assert _build_dsn().startswith("postgresql://winner")


# ===========================================================================
# 3. Schema SQL
# ===========================================================================

class TestSchemaSql:
    def test_has_intents_table(self):
        assert "CREATE TABLE IF NOT EXISTS intents" in _PG_SCHEMA_SQL

    def test_has_states_table(self):
        assert "CREATE TABLE IF NOT EXISTS states" in _PG_SCHEMA_SQL

    def test_has_policy_decisions_table(self):
        assert "CREATE TABLE IF NOT EXISTS policy_decisions" in _PG_SCHEMA_SQL

    def test_has_audit_trail_table(self):
        assert "CREATE TABLE IF NOT EXISTS audit_trail" in _PG_SCHEMA_SQL

    def test_uses_jsonb_not_text_for_metadata(self):
        assert "metadata     JSONB" in _PG_SCHEMA_SQL

    def test_uses_bigserial_for_audit_id(self):
        assert "BIGSERIAL" in _PG_SCHEMA_SQL

    def test_has_required_indexes(self):
        assert "idx_intents_user" in _PG_SCHEMA_SQL
        assert "idx_states_ns_key" in _PG_SCHEMA_SQL


# ===========================================================================
# 4. _pg_row_to_dict helper
# ===========================================================================

class TestPgRowToDict:
    def test_datetime_created_at_to_isostring(self):
        dt = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = _pg_row_to_dict({"id": "x", "created_at": dt})
        assert isinstance(result["created_at"], str)
        assert "2026-05-27" in result["created_at"]

    def test_datetime_updated_at_to_isostring(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _pg_row_to_dict({"updated_at": dt})
        assert isinstance(result["updated_at"], str)

    def test_is_valid_true_becomes_1(self):
        result = _pg_row_to_dict({"is_valid": True})
        assert result["is_valid"] == 1

    def test_is_valid_false_becomes_0(self):
        result = _pg_row_to_dict({"is_valid": False})
        assert result["is_valid"] == 0

    def test_jsonb_objects_pass_through(self):
        result = _pg_row_to_dict({"metadata": {"key": "val"}})
        assert result["metadata"] == {"key": "val"}

    def test_plain_dict_passes_through(self):
        row = {"id": "abc", "goal": "test goal"}
        result = _pg_row_to_dict(row)
        assert result == row


# ===========================================================================
# 5. get_persistence factory
# ===========================================================================

class TestGetPersistence:
    def test_default_returns_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.delenv("RCT_DB_BACKEND", raising=False)
        monkeypatch.setenv("RCT_DB_PATH", str(tmp_path / "test.db"))
        db = get_persistence()
        assert isinstance(db, ControlPlanePersistence)

    def test_sqlite_explicit_returns_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RCT_DB_PATH", str(tmp_path / "test.db"))
        db = get_persistence(backend="sqlite")
        assert isinstance(db, ControlPlanePersistence)

    def test_sqlite_env_returns_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RCT_DB_BACKEND", "sqlite")
        monkeypatch.setenv("RCT_DB_PATH", str(tmp_path / "test.db"))
        db = get_persistence()
        assert isinstance(db, ControlPlanePersistence)

    @patch("rct_control_plane.persistence_pg._HAS_PSYCOPG2", True)
    @patch("rct_control_plane.persistence_pg.psycopg2")
    def test_postgres_backend_returns_pg(self, mock_pg, monkeypatch):
        monkeypatch.setenv("RCT_DB_BACKEND", "postgres")
        monkeypatch.setenv("RCT_PG_DSN", "postgresql://test/test")
        _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = get_persistence()
        assert isinstance(db, PostgresPersistence)

    @patch("rct_control_plane.persistence_pg._HAS_PSYCOPG2", True)
    @patch("rct_control_plane.persistence_pg.psycopg2")
    def test_postgres_arg_overrides_env(self, mock_pg, monkeypatch):
        monkeypatch.setenv("RCT_DB_BACKEND", "sqlite")
        _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = get_persistence(backend="postgres")
        assert isinstance(db, PostgresPersistence)


# ===========================================================================
# 6. PostgresPersistence — ImportError when psycopg2 missing
# ===========================================================================

class TestMissingPsycopg2:
    @patch("rct_control_plane.persistence_pg._HAS_PSYCOPG2", False)
    def test_raises_import_error(self):
        with pytest.raises(ImportError, match="psycopg2"):
            PostgresPersistence(dsn="postgresql://any/db")


# ===========================================================================
# 7. CRUD — mocked psycopg2
# ===========================================================================

def _setup_mock_psycopg2(mock_pg: MagicMock) -> tuple:
    """Return (mock_conn, mock_cur) with context-manager support wired up."""
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_pg.connect.return_value = mock_conn
    mock_pg.extras.Json = lambda x: x
    mock_pg.extras.RealDictCursor = object
    return mock_conn, mock_cur


@patch("rct_control_plane.persistence_pg._HAS_PSYCOPG2", True)
@patch("rct_control_plane.persistence_pg.psycopg2")
class TestSaveIntent:
    def test_save_intent_calls_execute(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.save_intent("id-1", "user-1", "TASK", "do something")
        mock_cur.execute.assert_called()

    def test_save_intent_sql_contains_insert(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.save_intent("id-2", "user-2", "QUERY", "find it")
        sql = mock_cur.execute.call_args_list[0][0][0]
        assert "INSERT INTO intents" in sql

    def test_save_intent_truncates_goal_at_1000(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        long_goal = "x" * 2000
        db.save_intent("id-3", "u", "T", long_goal)
        params = mock_cur.execute.call_args_list[0][0][1]
        assert len(params[4]) == 1000  # goal is 5th param (index 4)


@patch("rct_control_plane.persistence_pg._HAS_PSYCOPG2", True)
@patch("rct_control_plane.persistence_pg.psycopg2")
class TestGetIntent:
    def test_get_intent_returns_none_when_not_found(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        mock_cur.fetchone.return_value = None
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        result = db.get_intent("missing-id")
        assert result is None

    def test_get_intent_returns_dict_when_found(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        mock_cur.fetchone.return_value = {
            "id": "id-1", "user_id": "u1", "goal": "g",
            "is_valid": True, "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        result = db.get_intent("id-1")
        assert result is not None
        assert result["id"] == "id-1"

    def test_get_intent_uses_parameterized_query(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        mock_cur.fetchone.return_value = None
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.get_intent("target-id")
        sql, params = mock_cur.execute.call_args[0]
        assert "WHERE id = %s" in sql
        assert params == ("target-id",)


@patch("rct_control_plane.persistence_pg._HAS_PSYCOPG2", True)
@patch("rct_control_plane.persistence_pg.psycopg2")
class TestListIntents:
    def test_list_intents_no_filter_uses_no_where(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        mock_cur.fetchall.return_value = []
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.list_intents()
        sql = mock_cur.execute.call_args[0][0]
        assert "WHERE" not in sql

    def test_list_intents_with_user_adds_where(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        mock_cur.fetchall.return_value = []
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.list_intents(user_id="alice")
        sql = mock_cur.execute.call_args[0][0]
        assert "WHERE user_id = %s" in sql


@patch("rct_control_plane.persistence_pg._HAS_PSYCOPG2", True)
@patch("rct_control_plane.persistence_pg.psycopg2")
class TestSaveGetState:
    def test_save_state_calls_execute(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.save_state("s-1", "mee", "agent-1", {"g": 0.9})
        mock_cur.execute.assert_called()

    def test_get_state_returns_none_when_missing(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        mock_cur.fetchone.return_value = None
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        assert db.get_state("ns", "missing") is None

    def test_save_state_sql_contains_on_conflict(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.save_state("s-2", "ns", "k", {})
        sql = mock_cur.execute.call_args[0][0]
        assert "ON CONFLICT" in sql


@patch("rct_control_plane.persistence_pg._HAS_PSYCOPG2", True)
@patch("rct_control_plane.persistence_pg.psycopg2")
class TestPolicyAndAudit:
    def test_save_policy_decision_executes(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.save_policy_decision("pd-1", "user-1", "ALLOW", "fdia_gate")
        mock_cur.execute.assert_called()

    def test_append_audit_executes(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.append_audit("intent", "id-1", "REVIEW", actor="admin")
        mock_cur.execute.assert_called()

    def test_recent_audit_returns_list(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        mock_cur.fetchall.return_value = []
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        result = db.recent_audit(limit=10)
        assert isinstance(result, list)

    def test_recent_audit_passes_limit_param(self, mock_pg):
        _, mock_cur = _setup_mock_psycopg2(mock_pg)
        mock_cur.fetchall.return_value = []
        with patch.object(PostgresPersistence, "_init_schema"):
            db = PostgresPersistence(dsn="postgresql://test/test")
        db.recent_audit(limit=42)
        sql, params = mock_cur.execute.call_args[0]
        assert params == (42,)

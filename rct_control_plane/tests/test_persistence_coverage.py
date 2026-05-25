"""
Unit test suite for SQLite persistence layer, designed for high code coverage.
"""

from __future__ import annotations

import sqlite3
import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Inject a mocked aiosqlite module into sys.modules so patch works when it's not installed
mock_aiosqlite = MagicMock()
sys.modules["aiosqlite"] = mock_aiosqlite

from rct_control_plane import persistence  # noqa: E402
from rct_control_plane.persistence import (  # noqa: E402
    ControlPlanePersistence,
    AsyncControlPlanePersistence,
    _row_to_dict,
)


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_persistence.db"
    return str(db_file)


def test_sync_persistence_lifecycle(temp_db):
    db = ControlPlanePersistence(db_path=temp_db)

    # 1. Test save and get intent
    intent_id = "intent_1"
    user_id = "user_1"
    intent_type = "deploy"
    goal = "Deploy authorization gateway to production environment safely."
    metadata = {"environment": "production", "systemic": True}

    db.save_intent(
        intent_id=intent_id,
        user_id=user_id,
        intent_type=intent_type,
        goal=goal,
        user_tier="ENTERPRISE",
        metadata=metadata,
        is_valid=True,
        errors=[],
    )

    # Fetch intent and check
    retrieved = db.get_intent(intent_id)
    assert retrieved is not None
    assert retrieved["id"] == intent_id
    assert retrieved["user_id"] == user_id
    assert retrieved["intent_type"] == intent_type
    assert retrieved["goal"] == goal[:1000]
    assert retrieved["metadata"] == metadata
    assert retrieved["is_valid"] == 1
    assert retrieved["errors"] == []

    # Get non-existent intent
    assert db.get_intent("non_existent_intent") is None

    # 2. Test list intents
    # Add another intent
    db.save_intent(
        intent_id="intent_2",
        user_id="user_2",
        intent_type="refactor",
        goal="Refactor CLI interface",
        is_valid=False,
        errors=["Invalid structure"],
    )

    all_intents = db.list_intents()
    assert len(all_intents) == 2

    user_intents = db.list_intents(user_id="user_1")
    assert len(user_intents) == 1
    assert user_intents[0]["id"] == "intent_1"

    # 3. Test states save and get
    state_id = "state_1"
    namespace = "rct"
    key = "active_model"
    state_val = {"model_name": "signedai-v1", "version": "1.0.4"}

    db.save_state(state_id, namespace, key, state_val)
    retrieved_state = db.get_state(namespace, key)
    assert retrieved_state is not None
    assert retrieved_state["id"] == state_id
    assert retrieved_state["namespace"] == namespace
    assert retrieved_state["key"] == key
    assert retrieved_state["value"] == state_val

    # Update state
    updated_val = {"model_name": "signedai-v2", "version": "1.0.5"}
    db.save_state(state_id, namespace, key, updated_val)
    retrieved_state = db.get_state(namespace, key)
    assert retrieved_state["value"] == updated_val

    # Get non-existent state
    assert db.get_state("non_existent_namespace", "key") is None

    # 4. Test policy decisions
    db.save_policy_decision(
        decision_id="dec_1",
        user_id="user_1",
        decision="require_approval",
        policy_name="block-systemic",
        intent_id=intent_id,
        reason="Systemic changes require architect consensus",
    )

    # Verification: check directly via sqlite since policy_decisions doesn't have a get method
    with sqlite3.connect(temp_db) as conn:
        row = conn.execute("SELECT * FROM policy_decisions WHERE id = 'dec_1'").fetchone()
        assert row is not None
        assert row[1] == intent_id
        assert row[2] == "user_1"
        assert row[3] == "require_approval"
        assert row[4] == "block-systemic"
        assert row[5] == "Systemic changes require architect consensus"

    # 5. Test audit trail
    db.append_audit(
        entity_type="system",
        entity_id="sys_1",
        action="BOOT",
        actor="system_agent",
        changes={"status": "active"},
    )

    audit_logs = db.recent_audit(limit=10)
    # Note: save_intent also appended an audit log, so we should have multiple audit records
    assert len(audit_logs) >= 2
    system_audits = [a for a in audit_logs if a["entity_type"] == "system"]
    assert len(system_audits) == 1
    assert system_audits[0]["action"] == "BOOT"
    assert system_audits[0]["changes"] == {"status": "active"}


def test_row_to_dict_json_failures():
    # Mock a sqlite3.Row object that returns custom dict
    mock_row = MagicMock()
    mock_row.keys.return_value = ["metadata", "errors", "value", "changes", "normal_col"]
    
    # We want to test that the json.loads inside _row_to_dict handles non-json string gracefully
    mock_data = {
        "metadata": "{invalid json",
        "errors": "['also invalid']",
        "value": 12345,  # not a string, will skip decode block
        "changes": "{\"valid\": true}",
        "normal_col": "normal_string",
    }
    
    def getitem(key):
        return mock_data[key]
        
    mock_row.__getitem__.side_effect = getitem
    
    result = _row_to_dict(mock_row)
    assert result["metadata"] == "{invalid json"
    assert result["errors"] == "['also invalid']"
    assert result["value"] == 12345
    assert result["changes"] == {"valid": True}
    assert result["normal_col"] == "normal_string"


def test_async_persistence_import_error():
    # Force _HAS_AIOSQLITE = False to trigger ImportError check in AsyncControlPlanePersistence init
    with patch.object(persistence, "_HAS_AIOSQLITE", False):
        with pytest.raises(ImportError) as exc_info:
            AsyncControlPlanePersistence()
        assert "requires aiosqlite" in str(exc_info.value)


@pytest.mark.asyncio
async def test_async_persistence_lifecycle(temp_db):
    # Mock aiosqlite connect, connection, and cursor
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.side_effect = [
        ("intent_async_1", "user_async", "FREE", "deploy", "Goal text", "{}", "2026-05-25", 1, "[]"), # row for get_intent
        None, # None for next get_intent
    ]
    mock_cursor.description = [
        ("id",), ("user_id",), ("user_tier",), ("intent_type",), ("goal",), ("metadata",), ("created_at",), ("is_valid",), ("errors",)
    ]

    mock_conn = AsyncMock()
    mock_conn.executescript = AsyncMock()
    mock_conn.commit = AsyncMock()
    mock_conn.close = AsyncMock()
    
    class AsyncContextManagerAndAwaitable:
        def __init__(self, value):
            self.value = value
        def __await__(self):
            async def _dummy():
                return self.value
            return _dummy().__await__()
        async def __aenter__(self):
            return self.value
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_conn.execute = MagicMock(return_value=AsyncContextManagerAndAwaitable(mock_cursor))
    mock_aiosqlite.connect = AsyncMock(return_value=mock_conn)
    persistence._aiosqlite = mock_aiosqlite
    with patch.object(persistence, "_HAS_AIOSQLITE", True):
        
        async with AsyncControlPlanePersistence(db_path=temp_db) as db:
            assert db._conn == mock_conn
            
            # Test save_intent
            await db.save_intent(
                intent_id="intent_async_1",
                user_id="user_async",
                intent_type="deploy",
                goal="Goal text",
            )
            mock_conn.execute.assert_called()
            mock_conn.commit.assert_called()

            # Test get_intent (returning a valid row)
            intent = await db.get_intent("intent_async_1")
            assert intent is not None
            assert intent["id"] == "intent_async_1"
            assert intent["user_id"] == "user_async"

            # Test get_intent (returning None)
            intent_none = await db.get_intent("non_existent")
            assert intent_none is None

            # Test save_state
            await db.save_state("state_async_1", "rct", "config", {"active": True})
            mock_conn.execute.assert_called()
            mock_conn.commit.assert_called()

        # Check connection is closed on __aexit__
        mock_conn.close.assert_called_once()

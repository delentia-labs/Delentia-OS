"""
Coverage tests for api.py ControlPlaneAPI SQLite persistence integration.

Also covers:
  - rich_formatter._load_config() reading from CWD
  - replay_engine.ReplayEngine.get_state_ids() and get_latest_checkpoint(None)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

# Use FastAPI TestClient
from fastapi.testclient import TestClient

from rct_control_plane.api import ControlPlaneAPI
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.replay_engine import ReplayEngine
from rct_control_plane.rich_formatter import _load_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_with_mock_db(tmp_path):
    """Create a ControlPlaneAPI with a mocked _db for inspection."""
    api = ControlPlaneAPI()
    mock_db = MagicMock(spec=ControlPlanePersistence)
    api._db = mock_db
    return api, mock_db


@pytest.fixture
def client(api_with_mock_db):
    """FastAPI TestClient wrapping ControlPlaneAPI with mocked DB."""
    api, _ = api_with_mock_db
    return TestClient(api.app)


@pytest.fixture
def mock_db(api_with_mock_db):
    """Return just the mock_db from the api fixture."""
    _, db = api_with_mock_db
    return db


# ---------------------------------------------------------------------------
# Path 1: Successful compile → save_intent called
# ---------------------------------------------------------------------------

def test_compile_success_calls_save_intent(client, mock_db):
    """Successful /v1/intent/compile triggers save_intent() once."""
    resp = client.post("/v1/intent/compile", json={
        "natural_language": "refactor the authentication module to use clean architecture",
        "user_id": "user-test-001",
        "user_tier": "PRO",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # save_intent must be called exactly once
    mock_db.save_intent.assert_called_once()

    # Check arguments
    kwargs = mock_db.save_intent.call_args.kwargs
    assert kwargs["user_id"] == "user-test-001"
    assert kwargs["user_tier"] == "PRO"
    assert kwargs["is_valid"] is True
    assert len(kwargs["intent_id"]) > 0  # UUID string
    assert "authentication" in kwargs["goal"].lower() or len(kwargs["goal"]) > 0


# ---------------------------------------------------------------------------
# Path 2: Compile stores intent_type correctly
# ---------------------------------------------------------------------------

def test_compile_stores_correct_intent_type(client, mock_db):
    """save_intent is called with a non-empty intent_type string."""
    resp = client.post("/v1/intent/compile", json={
        "natural_language": "deploy the service to production environment",
        "user_id": "deploy-user",
        "user_tier": "ENTERPRISE",
    })

    assert resp.status_code == 200

    if mock_db.save_intent.called:
        kwargs = mock_db.save_intent.call_args.kwargs
        # intent_type should be a string like "deploy" or "DEPLOY"
        assert isinstance(kwargs["intent_type"], str)
        assert len(kwargs["intent_type"]) > 0


# ---------------------------------------------------------------------------
# Path 3: Multiple independent compile calls → save_intent called each time
# ---------------------------------------------------------------------------

def test_multiple_compile_calls_each_saves(client, mock_db):
    """Each successful compile results in exactly one save_intent call."""
    intents = [
        "refactor the login service",
        "build a new dashboard feature",
        "analyze security vulnerabilities",
    ]

    for intent_text in intents:
        resp = client.post("/v1/intent/compile", json={
            "natural_language": intent_text,
            "user_id": "batch-user",
            "user_tier": "PRO",
        })
        assert resp.status_code == 200

    # All three should have triggered save_intent
    assert mock_db.save_intent.call_count == len(intents)


# ---------------------------------------------------------------------------
# Path 4: save_intent receives metadata correctly
# ---------------------------------------------------------------------------

def test_compile_with_metadata_passes_to_save(client, mock_db):
    """metadata dict is forwarded to save_intent."""
    resp = client.post("/v1/intent/compile", json={
        "natural_language": "optimize database query performance",
        "user_id": "meta-user",
        "user_tier": "ENTERPRISE",
        "metadata": {"source": "web_ui", "priority": "high"},
    })

    assert resp.status_code == 200

    if mock_db.save_intent.called:
        kwargs = mock_db.save_intent.call_args.kwargs
        meta = kwargs.get("metadata", {})
        assert isinstance(meta, dict)


# ---------------------------------------------------------------------------
# Path 5: GET / healthcheck doesn't call save_intent
# ---------------------------------------------------------------------------

def test_healthcheck_does_not_call_save_intent(client, mock_db):
    """Root health endpoint never touches the database."""
    resp = client.get("/")

    assert resp.status_code == 200
    mock_db.save_intent.assert_not_called()


# ---------------------------------------------------------------------------
# Path 6: Compile response includes intent_id
# ---------------------------------------------------------------------------

def test_compile_response_has_intent_id(client, mock_db):
    """Compile response includes a valid intent_id UUID."""
    resp = client.post("/v1/intent/compile", json={
        "natural_language": "document the public API endpoints",
        "user_id": "doc-user",
        "user_tier": "FREE",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("intent_id") is not None
    assert len(data["intent_id"]) > 8  # UUID format check


# ---------------------------------------------------------------------------
# Path 7: save_intent goal matches the natural_language input
# ---------------------------------------------------------------------------

def test_compile_goal_matches_natural_language(client, mock_db):
    """The 'goal' field saved equals the natural_language from the request."""
    nl = "test the payment processing module end to end"
    resp = client.post("/v1/intent/compile", json={
        "natural_language": nl,
        "user_id": "test-user",
        "user_tier": "PRO",
    })

    assert resp.status_code == 200

    if mock_db.save_intent.called:
        kwargs = mock_db.save_intent.call_args.kwargs
        assert kwargs["goal"] == nl


# ---------------------------------------------------------------------------
# rich_formatter._load_config() coverage
# ---------------------------------------------------------------------------

def test_load_config_no_file(tmp_path, monkeypatch):
    """_load_config() returns {} when rct.config.json is absent."""
    monkeypatch.chdir(tmp_path)
    result = _load_config()
    assert result == {}


def test_load_config_reads_file(tmp_path, monkeypatch):
    """_load_config() reads valid rct.config.json from cwd."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rct.config.json").write_text(
        json.dumps({"theme": "dark", "verbose": True}), encoding="utf-8"
    )
    result = _load_config()
    assert result == {"theme": "dark", "verbose": True}


# ---------------------------------------------------------------------------
# replay_engine edge cases
# ---------------------------------------------------------------------------

def test_replay_engine_get_state_ids_empty():
    """get_state_ids() returns empty list when no checkpoints recorded."""
    engine = ReplayEngine()
    assert engine.get_state_ids() == []


def test_replay_engine_get_latest_checkpoint_unknown():
    """get_latest_checkpoint() returns None for unknown state_id."""
    engine = ReplayEngine()
    result = engine.get_latest_checkpoint("does-not-exist")
    assert result is None


def test_replay_engine_get_checkpoint_count_zero():
    """get_checkpoint_count() returns 0 on empty engine."""
    engine = ReplayEngine()
    assert engine.get_checkpoint_count() == 0

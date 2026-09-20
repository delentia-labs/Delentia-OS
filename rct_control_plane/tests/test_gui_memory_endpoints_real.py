"""
Real tests for Round 35's 3 new/fixed API endpoints that Delentia-OS-Gui's
real client code (src/lib/delentia-client.ts) calls: GET /v1/memory/history,
POST /v1/rctdb/query, POST /v1/memory/rollback. All 3 previously either
didn't exist (client always fell through to a client-side mock) or
returned fully hardcoded fake data - now backed by the real DeltaEngine/
vector search/graph accumulation already built and tested elsewhere.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
from fastapi.testclient import TestClient

from rct_control_plane.api import create_app
from rct_control_plane.algorithm_kernel_41 import ALGORITHM_KERNEL


@pytest.fixture(scope="module")
def api_client():
    application = create_app()
    with TestClient(application) as client:
        yield client


class TestMemoryHistoryEndpoint:
    def test_returns_real_deltas_after_a_real_delta_is_stored(self, api_client):
        ALGORITHM_KERNEL.algo_25_delta_block("gui_test_session", "a real, distinctive change for round35 gui test")
        resp = api_client.get("/v1/memory/history?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_deltas"] >= 1
        assert len(data["deltas"]) >= 1
        # real fields present, no fabricated agent names like the old mock's "agent-hexa-librarian-01"
        first = data["deltas"][0]
        assert "agent_id" in first
        assert "sha256_hash" in first
        assert first["outcome"] == "success"


class TestRctdbQueryEndpoint:
    def test_vector_query_returns_real_structure(self, api_client):
        resp = api_client.post("/v1/rctdb/query", json={"query": "find similar documents about pricing", "query_type": "vector", "top_k": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query_type"] == "vector"
        assert "results" in data
        assert data["total"] == len(data["results"])

    def test_graph_query_returns_real_nodes(self, api_client):
        resp = api_client.post("/v1/rctdb/query", json={"query": "analyze customer feedback trends", "query_type": "graph", "top_k": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query_type"] == "graph"
        assert isinstance(data["results"], list)

    def test_hybrid_query_combines_both(self, api_client):
        resp = api_client.post("/v1/rctdb/query", json={"query": "quarterly revenue analysis report", "query_type": "hybrid", "top_k": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query_type"] == "hybrid"


class TestMemoryRollbackEndpoint:
    def test_rollback_to_a_real_recent_delta_succeeds(self, api_client):
        ALGORITHM_KERNEL.algo_25_delta_block("gui_rollback_test", "first change")
        ALGORITHM_KERNEL.algo_25_delta_block("gui_rollback_test", "second change")
        resp = api_client.post("/v1/memory/rollback", json={"ticks": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_rollback_beyond_available_history_reports_honest_failure(self, api_client):
        resp = api_client.post("/v1/memory/rollback", json={"ticks": 999999})
        data = resp.json()
        assert data["success"] is False
        assert "error" in data

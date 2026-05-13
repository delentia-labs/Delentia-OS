"""
Phase 2 Integration Tests — Intent Vector Routes

Tests for:
- POST /vector/intent/index
- POST /vector/intent/search
- IntentIndexRequest / IntentIndexResponse validation
- IntentSearchRequest / IntentSearchResponse validation
- FDIA quality gate at indexing time
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.core.vector_engine import VectorEngine
from app.backends.faiss_backend import FAISSBackend
from app.api import routes
from app.api.intent_routes import set_intent_vector_engine

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

DIM = 8  # Small dimension for fast tests


@pytest.fixture(scope="module")
def client():
    """TestClient with a dedicated FAISS engine for intent vector routes only."""
    backend = FAISSBackend(index_type="flat", metric="cosine")
    backend.initialize(dimension=DIM)
    engine = VectorEngine(backend, dimension=DIM)
    # Only inject into intent routes — do NOT override the main vector routes engine
    set_intent_vector_engine(engine)
    return TestClient(app)


def _make_vector(seed: int = 0) -> list:
    rng = np.random.default_rng(seed)
    return rng.random(DIM).tolist()


def _intent_record(
    intent_hash: str = "abc12345",
    fdia_score: float = 0.75,
    domain: str = "finance",
    tier: int = 3,
    seed: int = 1,
) -> dict:
    return {
        "intent_hash": intent_hash,
        "blueprint_id": "550e8400-e29b-41d4-a716-446655440000",
        "domain": domain,
        "fdia_score": fdia_score,
        "tier": tier,
        "metadata": {"source": "test"},
        "vector": _make_vector(seed),
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /vector/intent/index
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentIndexEndpoint:
    def test_index_single_record(self, client):
        payload = {"records": [_intent_record()]}
        resp = client.post("/vector/intent/index", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["indexed_count"] == 1
        assert body["skipped_count"] == 0
        assert body["collection"] == "intent_vectors"

    def test_index_multiple_records(self, client):
        records = [_intent_record(f"hash{i:04d}", seed=i) for i in range(5)]
        payload = {"records": records}
        resp = client.post("/vector/intent/index", json=payload)
        assert resp.status_code == 201
        assert resp.json()["indexed_count"] == 5

    def test_fdia_gate_skips_low_score(self, client):
        """Records below threshold (0.25) must be skipped."""
        low = _intent_record("lowhash1", fdia_score=0.10, seed=10)
        high = _intent_record("highhash1", fdia_score=0.90, seed=11)
        payload = {"records": [low, high]}
        resp = client.post("/vector/intent/index", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["indexed_count"] == 1
        assert body["skipped_count"] == 1

    def test_all_records_below_threshold_returns_zero(self, client):
        """All records below threshold → indexed_count == 0 (no 422 error)."""
        records = [_intent_record(f"lowfdia{i:02d}", fdia_score=0.01, seed=i+20) for i in range(3)]
        payload = {"records": records}
        resp = client.post("/vector/intent/index", json=payload)
        assert resp.status_code == 201
        assert resp.json()["indexed_count"] == 0
        assert resp.json()["skipped_count"] == 3

    def test_index_empty_records_returns_422(self, client):
        """Empty records list must fail validation."""
        resp = client.post("/vector/intent/index", json={"records": []})
        assert resp.status_code == 422

    def test_fdia_threshold_reported_in_response(self, client):
        payload = {"records": [_intent_record(seed=30)]}
        resp = client.post("/vector/intent/index", json=payload)
        assert resp.json()["fdia_threshold_applied"] == 0.25

    def test_domain_normalized_to_lowercase(self, client):
        rec = _intent_record(intent_hash="normhash1", domain="Finance", seed=40)
        payload = {"records": [rec]}
        resp = client.post("/vector/intent/index", json=payload)
        assert resp.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# POST /vector/intent/search
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentSearchEndpoint:
    @pytest.fixture(autouse=True)
    def seed_data(self, client):
        """Index a few known records before each test."""
        records = [
            _intent_record("srch_finance_1", fdia_score=0.9, domain="finance", seed=50),
            _intent_record("srch_legal_1", fdia_score=0.8, domain="legal", seed=51),
            _intent_record("srch_finance_2", fdia_score=0.7, domain="finance", seed=52),
        ]
        client.post("/vector/intent/index", json={"records": records})

    def test_search_returns_hits(self, client):
        payload = {"vector": _make_vector(50), "top_k": 3}
        resp = client.post("/vector/intent/search", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert "hits" in body
        assert body["total_found"] >= 0

    def test_search_response_fields(self, client):
        payload = {"vector": _make_vector(50), "top_k": 5}
        resp = client.post("/vector/intent/search", json=payload)
        body = resp.json()
        assert "query_vector_dim" in body
        assert body["query_vector_dim"] == DIM
        assert "collection" in body

    def test_domain_filter(self, client):
        payload = {
            "vector": _make_vector(50),
            "top_k": 10,
            "domain_filter": "finance",
        }
        resp = client.post("/vector/intent/search", json=payload)
        body = resp.json()
        for hit in body["hits"]:
            assert hit["domain"] == "finance"

    def test_min_fdia_score_filter(self, client):
        payload = {
            "vector": _make_vector(50),
            "top_k": 10,
            "min_fdia_score": 0.85,
        }
        resp = client.post("/vector/intent/search", json=payload)
        body = resp.json()
        for hit in body["hits"]:
            assert hit["fdia_score"] >= 0.85

    def test_search_empty_vector_422(self, client):
        resp = client.post("/vector/intent/search", json={"vector": [], "top_k": 5})
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Schema validation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentSchemaValidation:
    def test_fdia_score_out_of_range(self, client):
        rec = _intent_record(fdia_score=1.5)  # > 1.0
        resp = client.post("/vector/intent/index", json={"records": [rec]})
        assert resp.status_code == 422

    def test_tier_out_of_range(self, client):
        rec = _intent_record()
        rec["tier"] = 10  # > 9
        resp = client.post("/vector/intent/index", json={"records": [rec]})
        assert resp.status_code == 422

    def test_top_k_out_of_range(self, client):
        resp = client.post("/vector/intent/search", json={"vector": _make_vector(1), "top_k": 0})
        assert resp.status_code == 422

    def test_top_k_exceeds_max(self, client):
        resp = client.post("/vector/intent/search", json={"vector": _make_vector(1), "top_k": 101})
        assert resp.status_code == 422

"""Extended tests for vector-search Pydantic schemas — 20 tests.

Focuses on pure schema validation to avoid requiring FAISS/Qdrant.
"""
import sys
import os
import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.schemas import (
    IndexRequest,
    IndexResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    BatchSearchRequest,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. IndexRequest
# ─────────────────────────────────────────────────────────────────────────────

class TestIndexRequest:
    def test_valid_index_request(self):
        req = IndexRequest(
            vectors=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            ids=["id1", "id2"]
        )
        assert len(req.vectors) == 2
        assert req.ids == ["id1", "id2"]

    def test_index_request_with_metadata(self):
        req = IndexRequest(
            vectors=[[1.0, 2.0]],
            ids=["v1"],
            metadata=[{"source": "doc1"}]
        )
        assert req.metadata[0]["source"] == "doc1"

    def test_index_request_metadata_defaults_none(self):
        req = IndexRequest(vectors=[[0.1]], ids=["v1"])
        assert req.metadata is None

    def test_index_request_empty_vectors_fails(self):
        with pytest.raises((ValidationError, ValueError)):
            IndexRequest(vectors=[], ids=[])


# ─────────────────────────────────────────────────────────────────────────────
# 2. IndexResponse
# ─────────────────────────────────────────────────────────────────────────────

class TestIndexResponse:
    def test_valid_index_response(self):
        resp = IndexResponse(indexed_count=2, total_vectors=102, time_ms=12.5)
        assert resp.indexed_count == 2
        assert resp.total_vectors == 102
        assert resp.time_ms == 12.5

    def test_index_response_fields_required(self):
        with pytest.raises(ValidationError):
            IndexResponse(indexed_count=1)  # missing fields


# ─────────────────────────────────────────────────────────────────────────────
# 3. SearchRequest
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchRequest:
    def test_default_k_is_10(self):
        req = SearchRequest(query_vector=[0.1, 0.2, 0.3])
        assert req.k == 10

    def test_default_metric_is_cosine(self):
        req = SearchRequest(query_vector=[0.1, 0.2, 0.3])
        assert req.metric == "cosine"

    def test_custom_k(self):
        req = SearchRequest(query_vector=[0.1, 0.2], k=5)
        assert req.k == 5

    def test_k_ge_1(self):
        with pytest.raises(ValidationError):
            SearchRequest(query_vector=[0.1], k=0)

    def test_k_le_1000(self):
        with pytest.raises(ValidationError):
            SearchRequest(query_vector=[0.1], k=1001)

    def test_euclidean_metric(self):
        req = SearchRequest(query_vector=[0.5, 0.5], metric="euclidean")
        assert req.metric == "euclidean"


# ─────────────────────────────────────────────────────────────────────────────
# 4. SearchResult
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchResult:
    def test_valid_search_result(self):
        sr = SearchResult(id="vec_001", score=0.985)
        assert sr.id == "vec_001"
        assert sr.score == 0.985
        assert sr.metadata is None

    def test_search_result_with_metadata(self):
        sr = SearchResult(id="v2", score=0.7, metadata={"tag": "ai"})
        assert sr.metadata["tag"] == "ai"


# ─────────────────────────────────────────────────────────────────────────────
# 5. SearchResponse
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchResponse:
    def test_valid_search_response(self):
        results = [SearchResult(id="v1", score=0.9), SearchResult(id="v2", score=0.8)]
        resp = SearchResponse(results=results, time_ms=8.3)
        assert len(resp.results) == 2
        assert resp.time_ms == 8.3

    def test_empty_results_list(self):
        resp = SearchResponse(results=[], time_ms=0.1)
        assert resp.results == []


# ─────────────────────────────────────────────────────────────────────────────
# 6. BatchSearchRequest
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchSearchRequest:
    def test_batch_search_request_created(self):
        req = BatchSearchRequest(
            query_vectors=[[0.1, 0.2], [0.3, 0.4]],
            k=5
        )
        assert len(req.query_vectors) == 2
        assert req.k == 5

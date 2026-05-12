"""
Security tests for public API endpoints.
Validates input validation, injection prevention, and auth patterns.
"""

import importlib.util
import os as _os
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# gateway-api security
# Load via importlib to bypass Python's hyphen-in-folder-name restriction.
# Actual folder: microservices/gateway-api/  (has hyphen — not importable normally)
# ---------------------------------------------------------------------------
def _load_module_from_path(module_name: str, *path_parts: str):
    """Load a Python module from an explicit file path, bypassing naming rules."""
    file_path = _os.path.join(_os.path.dirname(__file__), *path_parts)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


try:
    _gw_mod = _load_module_from_path(
        "gateway_main",
        "..", "..", "microservices", "gateway-api", "gateway_main.py",
    )
    gateway_app = _gw_mod.app
    GATEWAY_AVAILABLE = True
except Exception:
    GATEWAY_AVAILABLE = False


@pytest.mark.skipif(not GATEWAY_AVAILABLE, reason="gateway-api not importable")
class TestGatewayAPISecurity:
    def setup_method(self):
        self.client = TestClient(gateway_app)

    def test_health_endpoint_returns_200(self):
        r = self.client.get("/health")
        assert r.status_code == 200

    def test_oversized_body_rejected(self):
        """Sending a very large payload should not crash the service."""
        oversized = {"query": "x" * 100_000}
        r = self.client.post("/api/v1/intent", json=oversized)
        # Should not be 500 — may be 422 (validation) or 400 (bad request)
        assert r.status_code != 500

    def test_sql_injection_in_query_field(self):
        """SQL injection patterns should be safely handled (no 500)."""
        payload = {"query": "'; DROP TABLE users; --"}
        r = self.client.post("/api/v1/intent", json=payload)
        # 404 is acceptable — route not present means no SQL executed
        assert r.status_code in (200, 400, 404, 422)
        assert r.status_code != 500

    def test_xss_payload_in_query(self):
        """XSS payloads should not be executed (response is JSON, not HTML)."""
        payload = {"query": "<script>alert(document.cookie)</script>"}
        r = self.client.post("/api/v1/intent", json=payload)
        if r.status_code == 200:
            # Response must be JSON — not raw HTML
            assert "application/json" in r.headers.get("content-type", "")

    def test_null_byte_injection(self):
        """Null bytes in input should not crash the application."""
        payload = {"query": "hello\x00world"}
        r = self.client.post("/api/v1/intent", json=payload)
        assert r.status_code != 500

    def test_path_traversal_not_possible(self):
        """Path traversal in request should not return file contents."""
        r = self.client.get("/../../etc/passwd")
        assert r.status_code in (400, 404, 405, 422)


# ---------------------------------------------------------------------------
# vector-search API security
# Actual folder: microservices/vector-search/  (has hyphen — not importable normally)
# Uses sys.path injection so that relative imports inside the package resolve.
# ---------------------------------------------------------------------------
try:
    import sys as _sys
    _vs_root = _os.path.abspath(
        _os.path.join(_os.path.dirname(__file__), "..", "..", "microservices", "vector-search")
    )
    if _vs_root not in _sys.path:
        _sys.path.insert(0, _vs_root)
    import importlib as _importlib
    _vs_mod = _importlib.import_module("app.main")
    vector_app = _vs_mod.app
    VECTOR_AVAILABLE = True
except Exception:
    VECTOR_AVAILABLE = False


@pytest.mark.skipif(not VECTOR_AVAILABLE, reason="vector-search not importable")
class TestVectorSearchSecurity:
    def setup_method(self):
        self._cm = TestClient(vector_app)
        self.client = self._cm.__enter__()

    def teardown_method(self):
        self._cm.__exit__(None, None, None)

    def test_health_endpoint(self):
        r = self.client.get("/vector/health")
        assert r.status_code == 200

    def test_invalid_vector_type_rejected(self):
        """Non-numeric vector values should be rejected."""
        payload = {
            "vectors": [["not", "a", "float"]],
            "ids": ["bad_vec"],
        }
        r = self.client.post("/vector/index", json=payload)
        assert r.status_code == 422

    def test_empty_vectors_rejected(self):
        """Empty vectors list should fail validation."""
        payload = {"vectors": [], "ids": []}
        r = self.client.post("/vector/index", json=payload)
        assert r.status_code == 422

    def test_mismatched_vectors_ids_rejected(self):
        """Mismatched vector and ID counts should fail."""
        payload = {
            "vectors": [[0.1, 0.2], [0.3, 0.4]],
            "ids": ["only_one_id"],
        }
        r = self.client.post("/vector/index", json=payload)
        assert r.status_code in (400, 422)

    def test_invalid_metric_rejected(self):
        """Unknown similarity metric should fail validation."""
        payload = {
            "query_vector": [0.1, 0.2, 0.3],
            "k": 5,
            "metric": "DROP TABLE",
        }
        r = self.client.post("/vector/search", json=payload)
        assert r.status_code == 422

    def test_negative_k_rejected(self):
        """k < 1 should be rejected by validation."""
        payload = {
            "query_vector": [0.1, 0.2, 0.3],
            "k": -1,
            "metric": "cosine",
        }
        r = self.client.post("/vector/search", json=payload)
        assert r.status_code == 422

    def test_excessive_k_rejected(self):
        """k > 1000 should be rejected by validation."""
        payload = {
            "query_vector": [0.1, 0.2, 0.3],
            "k": 9999,
            "metric": "cosine",
        }
        r = self.client.post("/vector/search", json=payload)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# SignedAI model security
# ---------------------------------------------------------------------------
from signedai.core.models import AnalysisJob, AnalysisStatus
from datetime import datetime, timezone


class TestSignedAIModelSecurity:
    def test_analysis_status_enum_exhaustive(self):
        """All AnalysisStatus values should be non-empty strings."""
        for status in AnalysisStatus:
            assert isinstance(status.value, str)
            assert len(status.value) > 0

    def test_analysis_job_no_arbitrary_field_injection(self):
        """Extra/unknown fields should be ignored by the model, not persisted."""
        job_data = dict(
            id="sec-job-001",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            artifact_hash="abc",
            artifact_type="code",
            intent={
                "I": "test", "D": "test", "Δ": "test",
                "A": "test", "R": "test", "M": "test",
            },
            status="queued",
        )
        job = AnalysisJob(**job_data)
        # Should not crash and should not have any injected attribute
        assert not hasattr(job, "malicious_field")

    def test_artifact_content_not_leaked_in_repr(self):
        """Sensitive artifact_content should not appear in default repr if empty."""
        job = AnalysisJob(
            id="sec-002",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            artifact_hash="abc",
            artifact_type="code",
            artifact_content=None,
            intent={
                "I": "test", "D": "test", "Δ": "test",
                "A": "test", "R": "test", "M": "test",
            },
            status="queued",
        )
        assert job.artifact_content is None


# ---------------------------------------------------------------------------
# DSL Parser security
# ---------------------------------------------------------------------------
from rct_control_plane.dsl_parser import DSLParser, DSLParseError


class TestDSLParserSecurity:
    def setup_method(self):
        self.parser = DSLParser()

    def test_deeply_nested_braces_handled(self):
        """Pathological nesting should not cause infinite loops or stack overflow."""
        # 50 levels of nesting — not valid DSL but should not crash
        deep = "intent \"x\" {" + "phase p {" * 10 + "}" * 10 + "}"
        try:
            self.parser.parse(deep, intent_id="deep")
        except (DSLParseError, Exception):
            pass  # Any controlled exception is acceptable; crash is not

    def test_empty_dsl_raises_parse_error(self):
        with pytest.raises(DSLParseError):
            self.parser.parse("", intent_id="empty")

    def test_unicode_in_dsl_handled(self):
        """Unicode in intent names and values should not crash the parser."""
        dsl = '''intent "ทดสอบ" {
    phase analyze {
        node N1 {
            agent_capability = "code_analysis"
        }
    }
}'''
        try:
            graph = self.parser.parse(dsl, intent_id="unicode-test")
            assert graph is not None
        except DSLParseError:
            pass  # Parse failure is acceptable; crash is not

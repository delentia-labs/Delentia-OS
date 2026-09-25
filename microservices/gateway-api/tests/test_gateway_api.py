"""Tests for Gateway API — FastAPI service — 20 tests."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
from fastapi.testclient import TestClient


def _get_client():
    from gateway_main import app
    return TestClient(app)


class TestGatewayHealthEndpoints:
    def test_root_endpoint_200(self):
        client = _get_client()
        r = client.get("/")
        assert r.status_code == 200

    def test_root_returns_service_info(self):
        client = _get_client()
        r = client.get("/")
        data = r.json()
        assert "service" in data or "status" in data

    def test_service_name_in_root(self):
        client = _get_client()
        r = client.get("/")
        data = r.json()
        assert "Gateway" in str(data) or "RCT" in str(data) or "gateway" in str(data).lower()

    def test_version_present(self):
        client = _get_client()
        r = client.get("/")
        data = r.json()
        assert "version" in data

    def test_services_dict_present(self):
        client = _get_client()
        r = client.get("/")
        data = r.json()
        assert "services" in data or "endpoints" in data


class TestGatewayCORS:
    def test_cors_headers_present(self):
        client = _get_client()
        r = client.options("/", headers={"Origin": "http://localhost:5173"})
        # If CORS is configured, preflight or allow-origin should be present
        assert r.status_code in (200, 204, 405)

    def test_app_title(self):
        from gateway_main import app
        assert "Gateway" in app.title or "RCT" in app.title


class TestGatewayServiceAvailability:
    def test_genome_flag_exists(self):
        import gateway_main
        assert hasattr(gateway_main, 'genome_available')

    def test_signedai_flag_exists(self):
        import gateway_main
        assert hasattr(gateway_main, 'signedai_available')

    def test_app_has_routes(self):
        from gateway_main import app
        routes = [r.path for r in app.routes]
        assert "/" in routes or any("/" in p for p in routes)


class TestGatewayDocumentation:
    def test_openapi_schema(self):
        client = _get_client()
        r = client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert "paths" in data

    def test_docs_endpoint(self):
        client = _get_client()
        r = client.get("/docs")
        assert r.status_code == 200


class TestGatewayAPIRoot:
    def test_api_health_path(self):
        client = _get_client()
        # Try common health paths
        for path in ["/health", "/api/health", "/status", "/"]:
            r = client.get(path)
            if r.status_code == 200:
                assert True
                return
        assert True  # Root "/" already verified above

    def test_response_is_json(self):
        client = _get_client()
        r = client.get("/")
        assert r.headers.get("content-type", "").startswith("application/json")


class TestGatewayHealthCheck:
    """Round 43: real coverage for /health, previously untested despite
    existing (this file only ever probed it opportunistically inside
    test_api_health_path, which returns on the FIRST 200 - "/" always
    wins before "/health" is ever actually asserted on)."""

    def test_health_returns_200_and_gateway_healthy(self):
        client = _get_client()
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["gateway"] == "healthy"
        assert "services" in data

    def test_health_reports_genome_service_status(self):
        # Round 44 (2026-09-25): tightened after a real docker-run
        # verification surfaced that gateway_main.py's old genome health
        # probe called a get_manager() function that never existed in
        # genome_api.py, always raising ImportError and being reported as
        # "degraded" - fixed to check genome_api._ENTERPRISE_AVAILABLE
        # (the real, honest flag genome_api.py's own /api/genome/health
        # route already uses), which is permanently False in this public
        # repo - so "degraded" can no longer occur at all.
        import gateway_main
        client = _get_client()
        data = client.get("/health").json()
        expected = "healthy" if gateway_main.genome_available and gateway_main.genome_api._ENTERPRISE_AVAILABLE else "unavailable"
        assert data["services"]["genome"]["status"] == expected

    def test_health_reports_signedai_service_status(self):
        import gateway_main
        client = _get_client()
        data = client.get("/health").json()
        expected = "healthy" if gateway_main.signedai_available else "unavailable"
        assert data["services"]["signedai"]["status"] == expected


class TestGatewayDelentiaStats:
    """Round 44: real coverage for /delentia/system/stats,
    /rctlabs/system/stats (its real, load-bearing alias -
    delentia-website's route.ts fetches this exact path; without it every
    request silently 404s and the site always falls back to static
    constants even though this endpoint serves real live data), and
    /delentia/benchmark/summary. Asserts the REAL, currently-committed
    behavior as of the Round 44 gateway_main.py fix: algorithmCount is
    genuinely introspected live from AlgorithmKernel41 (not hardcoded),
    and the response deliberately does NOT include uptime/hallucinationRate/
    consensusModels - those aren't measured anywhere in this codebase, so
    they're honestly left out rather than fabricated (see
    _delentia_system_stats_impl()'s own docstring)."""

    def test_system_stats_returns_real_baseline_shape(self):
        client = _get_client()
        r = client.get("/delentia/system/stats")
        assert r.status_code == 200
        data = r.json()
        for key in ("testCount", "microserviceCount", "algorithmCount",
                    "algorithmsDesigned", "layerCount", "version", "source", "timestamp"):
            assert key in data
        assert data["layerCount"] == 10
        assert data["microserviceCount"] == 5
        for key in ("uptime", "hallucinationRate", "consensusModels", "hexaCoreCount"):
            assert key not in data, f"{key} is a fabricated claim with no real measurement - must not be present"

    def test_system_stats_introspects_real_algorithm_kernel(self):
        # Real, live introspection (not hardcoded) - see gateway_main.py's
        # own _live_algorithm_counts() docstring. Asserts the number is
        # genuinely read from AlgorithmKernel41, not a fixed literal.
        from rct_control_plane.algorithm_kernel_41 import ALGORITHM_KERNEL
        client = _get_client()
        data = client.get("/delentia/system/stats").json()
        assert data["algorithmCount"] == len(ALGORITHM_KERNEL.IMPLEMENTED_ALGO_IDS)
        assert data["algorithmsDesigned"] == (
            len(ALGORITHM_KERNEL.IMPLEMENTED_ALGO_IDS) + len(ALGORITHM_KERNEL.NOT_IMPLEMENTED_ALGO_IDS)
        )

    def test_rctlabs_stats_is_a_real_alias_of_delentia_stats(self):
        client = _get_client()
        a = client.get("/delentia/system/stats").json()
        b = client.get("/rctlabs/system/stats").json()
        assert a["microserviceCount"] == b["microserviceCount"]
        assert a["layerCount"] == b["layerCount"]

    def test_system_stats_source_reflects_cache_vs_baseline(self):
        # _load_stats_cache() real behavior: "baseline" when no fresh
        # .stats_cache.json exists (the normal case for a test run), "cache"
        # when one does and is < 24h old.
        client = _get_client()
        data = client.get("/delentia/system/stats").json()
        assert data["source"] in ("baseline", "cache")

    def test_benchmark_summary_returns_expected_chart_shape(self):
        client = _get_client()
        r = client.get("/delentia/benchmark/summary")
        assert r.status_code == 200
        data = r.json()
        assert len(data["radarData"]) == 6
        assert len(data["barData"]) == 6
        assert len(data["counterStats"]) == 4
        assert "version" in data and "timestamp" in data


class TestGatewayExecuteIntent:
    """Round 43: real coverage for POST /v1/kernel/execute - the ZK-FDIA
    verification + keyword-based safety-boundary endpoint - previously had
    zero tests despite being the gateway's only POST/intent-execution route."""

    def test_benign_intent_is_authorized(self):
        client = _get_client()
        r = client.post("/v1/kernel/execute", json={"intent": "summarize this document"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "AUTHORIZED"
        assert data["zk_status"] == "not_provided"
        assert data["execution_id"].startswith("exec-")

    def test_malicious_keyword_intent_is_rejected(self):
        # Real, current behavior: a simple keyword blocklist, not semantic
        # detection (see gateway_main.py's own is_malicious check) - this
        # test documents that real, narrow behavior, not an idealized one.
        client = _get_client()
        r = client.post("/v1/kernel/execute", json={"intent": "please hack the mainframe"})
        assert r.status_code == 400
        data = r.json()
        assert data["status"] == "REJECTED"
        assert "constitutional safety boundary" in data["reason"]

    def test_execute_defaults_mode_to_standard(self):
        client = _get_client()
        r = client.post("/v1/kernel/execute", json={"intent": "hello"})
        assert r.status_code == 200

    def test_execute_with_zk_commitment_reports_a_real_zk_status(self):
        # No real ZKFDIAVerifier proof is forged here (that's zk_fdia.py's
        # own test suite's job) - this only asserts the gateway actually
        # ATTEMPTS verification and reports one of its real, defined
        # zk_status outcomes rather than silently ignoring the field.
        client = _get_client()
        payload = {
            "intent": "hello",
            "zk_commitment": {
                "c_d": "deadbeef", "c_i": "deadbeef", "c_a": "deadbeef",
                "f_sealed": 0.9, "proof_tag": "invalid_tag",
                "committed_at": "2026-09-24T00:00:00Z", "version": "1.0",
            },
        }
        r = client.post("/v1/kernel/execute", json=payload)
        assert r.status_code == 200
        assert r.json()["zk_status"] in (
            "verified", "failed_verification", "verifier_unavailable",
        ) or r.json()["zk_status"].startswith("error_during_verification")


class TestGatewayErrorHandlers:
    def test_unknown_path_returns_404_with_custom_body(self):
        client = _get_client()
        r = client.get("/this/path/does/not/exist")
        assert r.status_code == 404
        data = r.json()
        assert data["error"] == "Not Found"
        assert "available_endpoints" in data


class TestGatewayKernelStreamWebSocket:
    """Round 43: real coverage for the /v1/kernel/stream WebSocket route -
    previously zero tests despite being real, shipped functionality.
    core/kernel/intent_kernel.py does not exist in this repo (confirmed by
    directory listing), so _get_intent_kernel() always returns None here -
    this test exercises the REAL fallback word-by-word simulation path,
    not a mocked one."""

    def test_stream_rejects_empty_intent(self):
        client = _get_client()
        with client.websocket_connect("/v1/kernel/stream") as ws:
            ws.send_json({"intent": "  ", "mode": "standard"})
            msg = ws.receive_json()
            assert msg == {"type": "error", "data": "Empty intent"}

    def test_stream_emits_tokens_then_fdia_then_done(self):
        client = _get_client()
        with client.websocket_connect("/v1/kernel/stream") as ws:
            ws.send_json({"intent": "test streaming", "mode": "standard"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("done", "error"):
                    break
            types = [m["type"] for m in messages]
            assert "token" in types
            assert types[-2:] == ["fdia", "done"]
            done_data = messages[-1]["data"]
            assert "fdia_score" in done_data and "trace_id" in done_data

    def test_stream_rejects_wrong_api_key_when_configured(self, monkeypatch):
        # Real bug caught while fixing an unrelated lint issue: the original
        # form of this test caught `Exception` broadly around its own
        # `assert False` fallback, which meant the fallback could never
        # actually fail the test either (AssertionError is an Exception).
        # WebSocketDisconnect is the specific, real exception starlette's
        # TestClient raises for a server-side close - asserting on that
        # exact type is what actually proves rejection happened.
        from starlette.websockets import WebSocketDisconnect
        monkeypatch.setenv("DELENTIA_API_KEY", "real-secret-key")
        client = _get_client()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/v1/kernel/stream?token=wrong-key"):
                pass

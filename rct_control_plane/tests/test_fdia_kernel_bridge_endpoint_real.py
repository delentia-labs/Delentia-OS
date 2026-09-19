"""
Real /v1/kernel/fdia/evaluate endpoint tests — Round 31 (item 1 of the
Round 30 candidate list: prototype a real HTTP bridge endpoint so
delentia-mcp-ecosystem's deployed TS Worker can genuinely call into this
Python kernel, proving the concept rather than the two systems staying
fully disconnected forever). This is a real, minimal wrapper around
ALGORITHM_KERNEL.algo_01_fdia - not a mock like the existing
/v1/fdia/config route (hardcoded current_score=0.9808 regardless of
input).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest


@pytest.fixture(scope="module")
def api_client():
    from fastapi.testclient import TestClient
    from rct_control_plane.api import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client


class TestFdiaKernelBridgeEndpoint:
    def test_authorized_high_quality_intent_produces_a_real_high_score(self, api_client):
        resp = api_client.post("/v1/kernel/fdia/evaluate", json={
            "data_quality": 0.98, "intent_precision": 1.0, "authorized": 1.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "python_kernel_real_computation"
        assert data["authorized"] is True
        assert 0.9 < data["future_score"] <= 1.0

    def test_unauthorized_intent_is_forced_to_zero_real_veto(self, api_client):
        resp = api_client.post("/v1/kernel/fdia/evaluate", json={
            "data_quality": 0.98, "intent_precision": 1.0, "authorized": 0.0,
        })
        data = resp.json()
        assert data["future_score"] == 0.0
        assert data["authorized"] is False

    def test_score_genuinely_varies_with_data_quality_not_hardcoded(self, api_client):
        low = api_client.post("/v1/kernel/fdia/evaluate", json={
            "data_quality": 0.1, "intent_precision": 2.0, "authorized": 1.0,
        }).json()
        high = api_client.post("/v1/kernel/fdia/evaluate", json={
            "data_quality": 0.99, "intent_precision": 2.0, "authorized": 1.0,
        }).json()
        assert low["future_score"] != high["future_score"], "score must genuinely vary with input, unlike /v1/fdia/config's hardcoded 0.9808"
        assert low["future_score"] < high["future_score"]

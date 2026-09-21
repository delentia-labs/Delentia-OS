"""
Round 36: real end-to-end test for POST /v1/gateways/line/webhook -
proves the real route enforces signature verification and dispatches
correctly, via an actual TestClient HTTP call (not just the gateway
class in isolation, which test_line_gateway_real.py already covers).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from rct_control_plane.api import create_app


@pytest.fixture(scope="module")
def api_client():
    application = create_app()
    with TestClient(application) as client:
        yield client


def _sign(secret: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode("utf-8")


class TestLineWebhookEndpoint:
    def test_rejects_a_request_with_no_signature_header(self, api_client, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_SECRET", "test-secret")
        monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
        resp = api_client.post("/v1/gateways/line/webhook", content=b'{"events": []}')
        assert resp.status_code == 403

    def test_rejects_a_request_with_a_wrong_signature(self, api_client, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_SECRET", "test-secret")
        monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
        body = b'{"events": []}'
        resp = api_client.post(
            "/v1/gateways/line/webhook", content=body,
            headers={"X-Line-Signature": "obviously-wrong-signature"},
        )
        assert resp.status_code == 403

    def test_accepts_a_real_correctly_signed_empty_events_body(self, api_client, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_SECRET", "test-secret")
        monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
        body = b'{"events": []}'
        signature = _sign("test-secret", body)
        resp = api_client.post(
            "/v1/gateways/line/webhook", content=body,
            headers={"X-Line-Signature": signature},
        )
        assert resp.status_code == 200
        assert resp.json()["handled"] == 0

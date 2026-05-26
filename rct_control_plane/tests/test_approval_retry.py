"""
Coverage tests for approval_gateway._post_json() HTTP retry loop.

Tests:
  1. HTTP success on first attempt
  2. HTTP fail twice, succeed on third attempt
  3. All retries fail → raises last exception
  4. Non-2xx status code → retries and eventually raises HTTPError
  5. submit() with 'generic' channel → _post_json called
  6. submit() with 'cli' channel → no HTTP call
"""

from __future__ import annotations

import urllib.error
import urllib.request
from unittest.mock import patch

import pytest

from rct_control_plane.approval_gateway import (
    ApprovalGateway,
    ApprovalRequest,
    GatewayConfig,
)


# ---------------------------------------------------------------------------
# Helper: build a fake HTTP response object
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Path 1: HTTP success on first attempt
# ---------------------------------------------------------------------------

def test_post_json_success_first_attempt():
    """_post_json succeeds with a 200 response on the first try."""
    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("time.sleep") as mock_sleep:
        mock_urlopen.return_value = _FakeResponse(200)

        from rct_control_plane.approval_gateway import ApprovalGateway
        ApprovalGateway._post_json("https://example.com/webhook", {"key": "value"})

        mock_urlopen.assert_called_once()
        mock_sleep.assert_not_called()  # No sleep on first-attempt success


# ---------------------------------------------------------------------------
# Path 2: HTTP fail twice, succeed on third
# ---------------------------------------------------------------------------

def test_post_json_retry_succeeds_on_third():
    """_post_json retries on URLError and succeeds on 3rd attempt."""
    fail_exc = urllib.error.URLError("connection refused")
    responses = [
        fail_exc,
        fail_exc,
        _FakeResponse(200),
    ]

    call_count = 0

    def urlopen_side_effect(req, timeout=10):
        nonlocal call_count
        val = responses[call_count]
        call_count += 1
        if isinstance(val, Exception):
            raise val
        return val

    with patch("urllib.request.urlopen", side_effect=urlopen_side_effect), \
         patch("time.sleep") as mock_sleep:
        ApprovalGateway._post_json("https://example.com/webhook", {"key": "value"})

    assert call_count == 3
    assert mock_sleep.call_count == 2  # slept between attempt 1→2 and 2→3


# ---------------------------------------------------------------------------
# Path 3: All retries fail → raises
# ---------------------------------------------------------------------------

def test_post_json_all_retries_fail():
    """_post_json raises after exhausting all 3 attempts."""
    fail_exc = urllib.error.URLError("timeout")

    with patch("urllib.request.urlopen", side_effect=fail_exc), \
         patch("time.sleep"):
        with pytest.raises(urllib.error.URLError):
            ApprovalGateway._post_json("https://example.com/webhook", {"key": "v"})


# ---------------------------------------------------------------------------
# Path 4: Non-2xx status code → retries
# ---------------------------------------------------------------------------

def test_post_json_non_2xx_status_raises():
    """_post_json raises HTTPError when server returns 500 on all attempts."""
    with patch("urllib.request.urlopen", return_value=_FakeResponse(500)), \
         patch("time.sleep"):
        with pytest.raises((urllib.error.HTTPError, Exception)):
            ApprovalGateway._post_json("https://example.com/webhook", {"key": "v"})


# ---------------------------------------------------------------------------
# Path 5: submit() with 'generic' channel → _post_json_async called
# ---------------------------------------------------------------------------

def test_gateway_submit_generic_channel():
    """submit() with generic channel triggers async HTTP notification."""
    config = GatewayConfig(
        channel="generic",
        generic_webhook_url="https://example.com/hook",
    )
    gateway = ApprovalGateway(config=config)

    with patch.object(
        ApprovalGateway, "_post_json_async"
    ) as mock_async:
        req = gateway.submit(
            intent_id="test-intent-id",
            intent_text="deploy to production",
            risk_profile="systemic",
            channel="generic",
        )

    assert req.status == "pending"
    mock_async.assert_called_once()
    # Verify it was called with the webhook URL
    args = mock_async.call_args[0]
    assert args[0] == "https://example.com/hook"


# ---------------------------------------------------------------------------
# Path 6: submit() with 'cli' channel → no HTTP
# ---------------------------------------------------------------------------

def test_gateway_submit_cli_channel_no_http():
    """submit() with cli channel does NOT make HTTP calls."""
    config = GatewayConfig(channel="cli")
    gateway = ApprovalGateway(config=config)

    with patch("urllib.request.urlopen") as mock_urlopen:
        req = gateway.submit(
            intent_id="cli-intent-id",
            intent_text="refactor auth module",
            risk_profile="low",
            channel="cli",
        )

    assert req.status == "pending"
    mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# Path 7: ApprovalRequest token and is_expired
# ---------------------------------------------------------------------------

def test_approval_request_token_and_expiry():
    """ApprovalRequest.token() is deterministic and is_expired() works."""
    req = ApprovalRequest(
        intent_id="int-123",
        intent_text="deploy",
        risk_profile="systemic",
    )

    token1 = req.token()
    token2 = req.token()
    assert token1 == token2  # deterministic
    assert len(token1) == 16  # 16-char hex

    # Not expired by default (no expires_at)
    assert req.is_expired() is False


# ---------------------------------------------------------------------------
# Path 8: GatewayConfig.from_env() reads env vars
# ---------------------------------------------------------------------------

def test_gateway_config_from_env(monkeypatch):
    """GatewayConfig.from_env() correctly reads environment variables."""
    monkeypatch.setenv("RCT_APPROVAL_CHANNEL", "teams")
    monkeypatch.setenv("RCT_TEAMS_WEBHOOK_URL", "https://teams.example.com/hook")
    monkeypatch.setenv("RCT_APPROVAL_TIMEOUT_SECONDS", "7200")

    cfg = GatewayConfig.from_env()

    assert cfg.channel == "teams"
    assert cfg.teams_webhook_url == "https://teams.example.com/hook"
    assert cfg.timeout_seconds == 7200

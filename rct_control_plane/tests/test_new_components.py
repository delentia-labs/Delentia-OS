"""
Unit test suite for newly integrated RCT Control Plane components:
- ApprovalGateway
- ArchitectPolicyLoader
- OTelAdapter
- PlanEngine
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest

from rct_control_plane.approval_gateway import (
    ApprovalGateway,
    ApprovalRequest,
    GatewayConfig,
    _pending_store,
)
from rct_control_plane.architect_policy_loader import (
    ArchitectPolicyLoader,
    PolicyLoadError,
)
from rct_control_plane.otel_adapter import OTelAdapter, get_otel_adapter
from rct_control_plane.plan_engine import PlanEngine
from rct_control_plane.observability import ControlPlaneEvent, ControlPlaneEventType


# ===========================================================================
# 1. Approval Gateway Tests
# ===========================================================================

def test_approval_request_model():
    req = ApprovalRequest(
        intent_id="int_123",
        intent_text="test intent",
        risk_profile="SYSTEMIC",
        policy_rule="block-systemic",
        action_description="execute transform",
        expires_at=datetime.now() + timedelta(hours=1),
    )
    assert req.status == "pending"
    assert req.a_value == 0
    assert len(req.token()) == 16
    assert req.is_expired() is False

    # Test expired request
    req.expires_at = datetime.now() - timedelta(seconds=1)
    assert req.is_expired() is True

    # Dictionary conversion
    d = req.to_dict()
    assert d["intent_id"] == "int_123"
    assert d["status"] == "pending"


def test_gateway_config_loaders(tmp_path):
    # From dict
    cfg = GatewayConfig.from_dict({
        "channel": "slack",
        "slack_webhook_url": "https://hooks.slack.com/services/test",
        "timeout_seconds": 1200,
    })
    assert cfg.channel == "slack"
    assert cfg.slack_webhook_url == "https://hooks.slack.com/services/test"
    assert cfg.timeout_seconds == 1200

    # From env
    os.environ["RCT_APPROVAL_CHANNEL"] = "generic"
    os.environ["RCT_SLACK_WEBHOOK_URL"] = "https://slack/env"
    cfg_env = GatewayConfig.from_env()
    assert cfg_env.channel == "generic"
    assert cfg_env.slack_webhook_url == "https://slack/env"

    # From config file
    cfg_file = tmp_path / "rct.config.json"
    cfg_file.write_text(json.dumps({
        "approval_gateway": {
            "channel": "teams",
            "teams_webhook_url": "https://teams/file"
        }
    }), encoding="utf-8")

    cfg_loaded = GatewayConfig.from_config_file(str(cfg_file))
    assert cfg_loaded.channel == "teams"
    assert cfg_loaded.teams_webhook_url == "https://teams/file"


def test_approval_gateway_lifecycle():
    _pending_store.clear()
    config = GatewayConfig(channel="cli", timeout_seconds=100)
    gateway = ApprovalGateway(config=config)

    # Submit request
    req = gateway.submit(
        intent_id="intent_abc",
        intent_text="test action",
        risk_profile="STRUCTURAL",
        policy_rule="auth-gate",
        action_description="modify auth",
    )
    assert req.intent_id == "intent_abc"
    assert req.status == "pending"

    # Fetch pending
    pending = gateway.get_pending()
    assert len(pending) == 1
    assert pending[0].request_id == req.request_id

    # Get specific request
    fetched = gateway.get_request(req.request_id)
    assert fetched is not None
    assert fetched.request_id == req.request_id

    # Decide approve
    decided = gateway.decide(req.request_id, approved=True, decided_by="architect-01", reason="safe")
    assert decided.status == "approved"
    assert decided.a_value == 1
    assert decided.decided_by == "architect-01"
    assert decided.decision_reason == "safe"

    # Decide on already decided request should raise ValueError
    with pytest.raises(ValueError):
        gateway.decide(req.request_id, approved=False)

    # Clear decided
    removed = gateway.clear_decided()
    assert removed == 1
    assert len(gateway.get_pending()) == 0


def test_approval_gateway_errors():
    _pending_store.clear()
    config = GatewayConfig(channel="cli", timeout_seconds=10)
    gateway = ApprovalGateway(config=config)

    # Non-existent request_id
    with pytest.raises(KeyError):
        gateway.decide("missing_id", approved=True)

    # Expired request
    req = gateway.submit(intent_id="expired_id", intent_text="expired", risk_profile="LOW")
    req.expires_at = datetime.now() - timedelta(seconds=1)
    with pytest.raises(ValueError):
        gateway.decide(req.request_id, approved=True)


@patch("urllib.request.urlopen")
def test_approval_gateway_webhooks(mock_urlopen):
    # Setup mock response
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    config = GatewayConfig(
        channel="slack",
        slack_webhook_url="https://hooks.slack.com/mock",
        teams_webhook_url="https://teams/mock",
        generic_webhook_url="https://webhook/mock",
    )
    gateway = ApprovalGateway(config=config)

    # Test Slack dispatch
    req_slack = gateway.submit("int_slack", "slack text", "SYSTEMIC", channel="slack")
    assert req_slack.channel == "slack"

    # Test Teams dispatch
    req_teams = gateway.submit("int_teams", "teams text", "STRUCTURAL", channel="teams")
    assert req_teams.channel == "teams"

    # Test Generic dispatch
    req_generic = gateway.submit("int_gen", "generic text", "LOW", channel="generic")
    assert req_generic.channel == "generic"


# ===========================================================================
# 2. Architect Policy Loader Tests
# ===========================================================================

def test_policy_loader_valid():
    yaml_text = """
    policies:
      - name: "block-production-deployment"
        description: "Deployments to production require senior approval"
        scope: "intent"
        priority: "critical"
        conditions:
          - field: "intent_type"
            operator: "=="
            value: "deploy"
        action: "require_approval"
        approver_roles:
          - "senior-engineer"
        timeout_seconds: 3600
        channel: "slack"
        enabled: true
    """
    loader = ArchitectPolicyLoader()
    rules = loader.load_from_string(yaml_text)
    assert len(rules) == 1
    rule = rules[0]
    assert rule.name == "block-production-deployment"
    assert rule.priority.value == "critical"
    assert rule.action.value == "require_approval"
    assert len(rule.conditions) == 1
    assert rule.conditions[0].field == "intent_type"
    assert rule.conditions[0].value == "deploy"
    assert rule.action_metadata["channel"] == "slack"


def test_policy_loader_errors(tmp_path):
    loader = ArchitectPolicyLoader()

    # Missing file
    with pytest.raises(PolicyLoadError):
        loader.load(tmp_path / "missing.yaml")

    # Missing required field 'name'
    invalid_yaml1 = """
    policies:
      - description: "Missing name field"
        scope: "intent"
    """
    with pytest.raises(PolicyLoadError):
        loader.load_from_string(invalid_yaml1)

    # Invalid scope
    invalid_yaml2 = """
    policies:
      - name: "invalid-scope"
        scope: "invalid"
    """
    with pytest.raises(PolicyLoadError):
        loader.load_from_string(invalid_yaml2)

    # Invalid operator
    invalid_yaml3 = """
    policies:
      - name: "invalid-operator"
        conditions:
          - field: "risk_level"
            operator: "INVALID"
            value: "HIGH"
    """
    with pytest.raises(PolicyLoadError):
        loader.load_from_string(invalid_yaml3)

    # 1. Test OSError in load / _read_file
    dummy_file = tmp_path / "dummy.yaml"
    dummy_file.touch()
    with patch("pathlib.Path.read_text", side_effect=OSError("Permission denied")):
        with pytest.raises(PolicyLoadError) as exc_info:
            loader.load(dummy_file)
        assert "Cannot read policy file" in str(exc_info.value)

    # 2. Test YAML syntax error (YAMLError)
    invalid_syntax = """
    policies:
      - name: "broken"
      - [unbalanced bracket
    """
    with pytest.raises(PolicyLoadError) as exc_info:
        loader.load_from_string(invalid_syntax)
    assert "YAML parse error" in str(exc_info.value)

    # 3. Test _HAS_YAML = False fallback to JSON success
    from rct_control_plane import architect_policy_loader
    with patch.object(architect_policy_loader, "_HAS_YAML", False):
        json_valid = '{"policies": [{"name": "json-policy", "scope": "intent", "priority": "medium", "action": "log"}]}'
        rules = loader.load_from_string(json_valid)
        assert len(rules) == 1
        assert rules[0].name == "json-policy"

    # 4. Test _HAS_YAML = False fallback to JSON failure (JSONDecodeError)
    with patch.object(architect_policy_loader, "_HAS_YAML", False):
        with pytest.raises(PolicyLoadError) as exc_info:
            loader.load_from_string("invalid json")
        assert "JSON parse failed" in str(exc_info.value)

    # 5. Test Non-dict top-level mapping
    with pytest.raises(PolicyLoadError) as exc_info:
        loader.load_from_string("- list item instead of dict")
    assert "Expected top-level mapping" in str(exc_info.value)

    # 6. Test 'policies' is not a list
    with pytest.raises(PolicyLoadError) as exc_info:
        loader.load_from_dict({"policies": "not a list"})
    assert "'policies' must be a list" in str(exc_info.value)

    # 7. Test Policy entry is not a mapping
    with pytest.raises(PolicyLoadError) as exc_info:
        loader.load_from_dict({"policies": ["not a mapping"]})
    assert "must be a mapping" in str(exc_info.value)

    # 8. Test Policy conditions is not a list
    with pytest.raises(PolicyLoadError) as exc_info:
        loader.load_from_dict({"policies": [{"name": "bad-conds", "conditions": "not a list"}]})
    assert "conditions must be a list" in str(exc_info.value)

    # 9. Test Policy condition entry is not a mapping
    with pytest.raises(PolicyLoadError) as exc_info:
        loader.load_from_dict({"policies": [{"name": "bad-conds", "conditions": ["not a mapping"]}]})
    assert "condition[0] must be a mapping" in str(exc_info.value)

    # 10. Test Policy condition entry missing 'field'
    with pytest.raises(PolicyLoadError) as exc_info:
        loader.load_from_dict({"policies": [{"name": "bad-conds", "conditions": [{"operator": "=="}]}]})
    assert "missing 'field'" in str(exc_info.value)


# ===========================================================================
# 3. OpenTelemetry Adapter Tests
# ===========================================================================

def test_otel_adapter_lifecycle():
    adapter = OTelAdapter(service_name="test-service", use_console_exporter=True)
    # Regardless of OTel package state, adapter shouldn't crash on standard calls
    assert isinstance(adapter.is_enabled, bool)

    event = ControlPlaneEvent(
        event_type=ControlPlaneEventType.INTENT_RECEIVED,
        actor="user-01",
        source="cli",
        intent_id="intent-abc",
        success=True,
        data={
            "f_score": 0.45,
            "d_score": 0.75,
            "i_score": 3,
            "a_value": 1,
            "signedai_tier": "Tier 4",
            "consensus_pct": 75.0,
            "cost_usd": 0.05,
            "signer_votes": [
                {"signer_id": "supreme_architect", "verdict": "approve", "confidence": 0.95}
            ]
        }
    )

    adapter.emit(event)
    adapter.emit_batch([event])
    adapter.emit_fdia_metric("intent-abc", 0.45, 0.75, 3, 1)

    # Singleton fetcher
    singleton = get_otel_adapter()
    assert singleton is not None


# ===========================================================================
# 4. Plan Engine Tests
# ===========================================================================

def test_plan_engine_simulation():
    engine = PlanEngine()

    # Simulate structural change
    result = engine.simulate(
        intent_text="refactor authentication module",
        user_id="dev-01",
        user_tier="PRO"
    )

    assert result.is_valid is True
    assert result.intent_text == "refactor authentication module"
    assert result.risk_profile in {"LOW", "STRUCTURAL", "SYSTEMIC"}
    assert isinstance(result.estimated_cost_usd, float)
    assert len(result.models_roster) > 0
    assert len(result.data_sources) > 0

    # Simulate systemic production change
    result_systemic = engine.simulate(
        intent_text="deploy auth to production",
        user_id="dev-01",
        user_tier="ENTERPRISE"
    )
    assert result_systemic.is_valid is True
    assert result_systemic.risk_profile == "SYSTEMIC"
    assert result_systemic.requires_human_approval is True

    # Dict conversion
    d = result_systemic.to_dict()
    assert d["intent_text"] == "deploy auth to production"
    assert d["is_valid"] is True

    # 1. Test fallback model roster when _HAS_SIGNEDAI = False
    from rct_control_plane import plan_engine
    with patch.object(plan_engine, "_HAS_SIGNEDAI", False):
        engine_fallback = PlanEngine()
        result_fallback = engine_fallback.simulate("deploy auth")
        assert result_fallback.is_valid is True
        assert len(result_fallback.models_roster) > 0

    # 2. Test JSON / OS errors on pricing loader fallback
    with patch("builtins.open", side_effect=OSError("file missing")):
        pricing_data = plan_engine._load_pricing()
        assert pricing_data == {}


def test_plan_engine_invalid_compilation():
    engine = PlanEngine()

    # Empty intent triggers compilation failure
    result = engine.simulate(intent_text="")
    assert result.is_valid is False
    assert len(result.errors) > 0
    assert result.estimated_cost_usd == 0.0

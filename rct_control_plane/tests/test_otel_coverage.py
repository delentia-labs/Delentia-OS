"""
Unit test suite for OpenTelemetry Adapter, designed for high code coverage.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

from rct_control_plane.observability import ControlPlaneEvent, ControlPlaneEventType

# Mock opentelemetry modules in sys.modules before importing otel_adapter
mock_trace = MagicMock()
mock_trace_provider = MagicMock()
mock_tracer = MagicMock()
mock_span = MagicMock()

mock_trace.trace = mock_trace
mock_trace.get_tracer_provider.return_value = mock_trace_provider
mock_trace.get_tracer.return_value = mock_tracer
mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

sys.modules["opentelemetry"] = mock_trace
sys.modules["opentelemetry.trace"] = mock_trace
sys.modules["opentelemetry.sdk.trace"] = MagicMock()
sys.modules["opentelemetry.sdk.trace.export"] = MagicMock()
sys.modules["opentelemetry.sdk.resources"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = MagicMock()

# Now import the module
from rct_control_plane import otel_adapter  # noqa: E402
from rct_control_plane.otel_adapter import OTelAdapter, get_otel_adapter  # noqa: E402

# Bind mocks directly to otel_adapter module-level properties
otel_adapter.trace = mock_trace
otel_adapter.TracerProvider = MagicMock()
otel_adapter.BatchSpanProcessor = MagicMock()
otel_adapter.ConsoleSpanExporter = MagicMock()
otel_adapter.Resource = MagicMock()
otel_adapter.SERVICE_NAME = MagicMock()
otel_adapter.OTLPSpanExporter = MagicMock()
otel_adapter._HAS_OTEL = True
otel_adapter._HAS_OTLP = True


def test_otel_adapter_disabled():
    # Force _HAS_OTEL = False to test disabled mode
    with patch.object(otel_adapter, "_HAS_OTEL", False):
        adapter = OTelAdapter(service_name="test-disabled")
        assert adapter.is_enabled is False
        # Calling emit or emit_fdia_metric should be a safe no-op
        event = ControlPlaneEvent(
            event_type=ControlPlaneEventType.INTENT_RECEIVED,
            actor="actor",
            source="src",
        )
        adapter.emit(event)
        adapter.emit_batch([event])
        adapter.emit_fdia_metric("int_1", 0.5, 0.5, 0.5, 1)


def test_otel_adapter_enabled_console():
    # Force _HAS_OTEL = True and _HAS_OTLP = False
    with patch.object(otel_adapter, "_HAS_OTEL", True), \
         patch.object(otel_adapter, "_HAS_OTLP", False), \
         patch.dict(os.environ, {"OTEL_SERVICE_NAME": "env-service", "OTEL_EXPORTER_OTLP_ENDPOINT": ""}):
        
        adapter = OTelAdapter(service_name="default-service", use_console_exporter=True)
        assert adapter.is_enabled is True
        assert adapter._tracer == mock_tracer


def test_otel_adapter_enabled_otlp():
    # Force _HAS_OTEL = True and _HAS_OTLP = True
    with patch.object(otel_adapter, "_HAS_OTEL", True), \
         patch.object(otel_adapter, "_HAS_OTLP", True), \
         patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}):
        
        adapter = OTelAdapter(service_name="otlp-service")
        assert adapter.is_enabled is True


def test_otel_adapter_emit_events():
    mock_tracer.reset_mock()
    mock_span.reset_mock()

    with patch.object(otel_adapter, "_HAS_OTEL", True):
        adapter = OTelAdapter(service_name="test-emit")
        assert adapter.is_enabled is True

        # 1. Successful event with rich metrics and signedai votes
        event_ok = ControlPlaneEvent(
            event_type=ControlPlaneEventType.POLICY_EVALUATED,
            actor="user-123",
            source="api",
            intent_id="intent-abc",
            graph_id="graph-xyz",
            node_id="node-1",
            duration_ms=450.5,
            success=True,
            data={
                "f_score": 0.85,
                "d_score": 0.9,
                "i_score": 2.5,
                "a_value": 1,
                "fdia_score": 0.85,
                "governance_score": 90.0,
                "risk_level": "MEDIUM",
                "signedai_tier": "Tier 3",
                "consensus_pct": 85.0,
                "a_block": True,
                "intent_type": "deploy",
                "cost_usd": 0.12,
                "signer_votes": [
                    {"signer_id": "signer_1", "verdict": "APPROVE", "confidence": 0.95}
                ]
            }
        )

        adapter.emit(event_ok)
        mock_tracer.start_as_current_span.assert_called_with(
            "rct.policy.evaluated",
            attributes={
                "rct.event_id": event_ok.event_id,
                "rct.event_type": event_ok.event_type.value,
                "rct.actor": "user-123",
                "rct.source": "api",
                "rct.success": True,
                "rct.intent_id": "intent-abc",
                "rct.graph_id": "graph-xyz",
                "rct.node_id": "node-1",
                "rct.duration_ms": 450.5,
                "rct.f_score": 0.85,
                "rct.d_score": 0.9,
                "rct.i_score": 2.5,
                "rct.a_value": 1,
                "rct.fdia_score": 0.85,
                "rct.governance_score": 90.0,
                "rct.risk_level": "MEDIUM",
                "rct.signedai.tier": "Tier 3",
                "rct.signedai.consensus_pct": 85.0,
                "rct.a_block": True,
                "rct.intent.type": "deploy",
                "rct.cost_usd": 0.12,
            }
        )
        mock_span.add_event.assert_called_with(
            "signedai.vote",
            attributes={
                "signer": "signer_1",
                "verdict": "APPROVE",
                "confidence": 0.95,
            }
        )

        # 2. Failed event
        event_fail = ControlPlaneEvent(
            event_type=ControlPlaneEventType.ERROR_OCCURRED,
            actor="system",
            source="worker",
            success=False,
            error_message="Database connection failed",
            data={}
        )
        adapter.emit(event_fail)
        
        # Test emit_batch
        adapter.emit_batch([event_ok, event_fail])


def test_otel_adapter_emit_fdia_metric():
    mock_tracer.reset_mock()
    mock_span.reset_mock()

    with patch.object(otel_adapter, "_HAS_OTEL", True):
        adapter = OTelAdapter(service_name="test-metric")
        
        # Test general case (a_value = 1)
        adapter.emit_fdia_metric(
            intent_id="intent-1",
            f_score=8.0,
            d_score=2.0,
            i_score=3.0,
            a_value=1,
            risk_level="HIGH",
        )
        mock_tracer.start_as_current_span.assert_called_with(
            "rct.fdia.compute",
            attributes={
                "rct.intent_id": "intent-1",
                "rct.fdia.f_score": 8.0,
                "rct.fdia.f_computed": 8.0,  # 2.0 ** 3.0 * 1 = 8.0
                "rct.fdia.d_score": 2.0,
                "rct.fdia.i_score": 3.0,
                "rct.fdia.a_value": 1,
                "rct.risk_level": "HIGH",
                "rct.a_blocked": False,
            }
        )

        # Test blocked case (a_value = 0)
        adapter.emit_fdia_metric(
            intent_id="intent-2",
            f_score=0.0,
            d_score=5.0,
            i_score=2.0,
            a_value=0,
            risk_level="CRITICAL",
        )
        mock_tracer.start_as_current_span.assert_called_with(
            "rct.fdia.compute",
            attributes={
                "rct.intent_id": "intent-2",
                "rct.fdia.f_score": 0.0,
                "rct.fdia.f_computed": 0.0,
                "rct.fdia.d_score": 5.0,
                "rct.fdia.i_score": 2.0,
                "rct.fdia.a_value": 0,
                "rct.risk_level": "CRITICAL",
                "rct.a_blocked": True,
            }
        )


def test_get_otel_adapter():
    with patch.object(otel_adapter, "_HAS_OTEL", True):
        # Clear singleton first
        otel_adapter._default_adapter = None
        adapter = get_otel_adapter(service_name="singleton-service")
        assert adapter is not None
        assert get_otel_adapter() == adapter

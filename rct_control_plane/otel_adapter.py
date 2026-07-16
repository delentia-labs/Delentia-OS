"""
OpenTelemetry Adapter — Control Plane Observability Bridge

Maps ControlPlaneEvent objects to OpenTelemetry spans so that F/D/I/A
metrics and SignedAI votes can be exported to any OTel-compatible backend
(Grafana Tempo, Jaeger, Datadog, AWS X-Ray, etc.).

Optional dependency: opentelemetry-sdk, opentelemetry-exporter-otlp-proto-grpc
If not installed, this module degrades gracefully to a no-op.

Usage:
    from rct_control_plane.otel_adapter import OTelAdapter
    adapter = OTelAdapter(service_name="rct-control-plane")
    adapter.emit(event)           # single event → span
    adapter.emit_batch(events)    # batch emission

Environment variables:
    OTEL_EXPORTER_OTLP_ENDPOINT   http://localhost:4317  (gRPC)
    OTEL_SERVICE_NAME             rct-control-plane
    OTEL_RESOURCE_ATTRIBUTES      deployment.environment=production
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from rct_control_plane.observability import ControlPlaneEvent, ControlPlaneEventType
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Optional OTel import
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _HAS_OTLP = True
except ImportError:
    _HAS_OTLP = False


# ---------------------------------------------------------------------------
# Event type → OTel span name mapping
# ---------------------------------------------------------------------------

_EVENT_SPAN_NAMES: Dict[str, str] = {
    ControlPlaneEventType.INTENT_RECEIVED.value:    "rct.intent.received",
    ControlPlaneEventType.INTENT_COMPILED.value:    "rct.intent.compiled",
    ControlPlaneEventType.GRAPH_BUILT.value:        "rct.graph.built",
    ControlPlaneEventType.POLICY_EVALUATED.value:   "rct.policy.evaluated",
    ControlPlaneEventType.APPROVAL_REQUESTED.value: "rct.approval.requested",
    ControlPlaneEventType.APPROVAL_GRANTED.value:   "rct.approval.granted",
    ControlPlaneEventType.EXECUTION_STARTED.value:  "rct.execution.started",
    ControlPlaneEventType.NODE_STARTED.value:       "rct.node.started",
    ControlPlaneEventType.NODE_COMPLETED.value:     "rct.node.completed",
    ControlPlaneEventType.NODE_FAILED.value:        "rct.node.failed",
    ControlPlaneEventType.GRAPH_COMPLETED.value:    "rct.graph.completed",
    ControlPlaneEventType.GRAPH_FAILED.value:       "rct.graph.failed",
    ControlPlaneEventType.STATE_TRANSITION.value:   "rct.state.transition",
    ControlPlaneEventType.ERROR_OCCURRED.value:     "rct.error",
    ControlPlaneEventType.GUARDIAN_CHECKED.value:   "rct.guardian.check",
    ControlPlaneEventType.ROUTER_CLASSIFIED.value:  "rct.router.classify",
    ControlPlaneEventType.SCRIBE_COMPRESSED.value:  "rct.scribe.compress",
    ControlPlaneEventType.EXECUTOR_RUN.value:       "rct.executor.run",
    ControlPlaneEventType.HEXACORE_CONSENSUS_RUN.value: "rct.hexacore.consensus",
    ControlPlaneEventType.OS_STORAGE_SAVED.value:   "rct.storage.saved",
}


# ---------------------------------------------------------------------------
# FDIA metric attribute helpers
# ---------------------------------------------------------------------------

def _extract_fdia_attributes(event: ControlPlaneEvent) -> Dict[str, Any]:
    """Extract F/D/I/A, Scribe, and Executor values from event data as OTel span attributes."""
    data = event.data or {}
    attrs: Dict[str, Any] = {}

    # 1. Base FDIA attributes (flat)
    for key in ("f_score", "d_score", "i_score", "a_value",
                "fdia_score", "governance_score", "risk_level"):
        if key in data:
            attrs[f"rct.{key}"] = data[key]

    # 2. Extract nested fdia dictionary
    if "fdia" in data and isinstance(data["fdia"], dict):
        fdia = data["fdia"]
        for k, v in fdia.items():
            attrs[f"rct.fdia.{k.lower()}"] = v
            # Map capital letters D, I, A, F to standard lower keys as well
            if k in ("D", "I", "A", "F"):
                if k == "D":
                    attrs["rct.d_score"] = float(v)
                elif k == "I":
                    attrs["rct.i_score"] = float(v)
                elif k == "A":
                    attrs["rct.a_value"] = int(v)
                elif k == "F":
                    attrs["rct.f_score"] = float(v)

    # 3. Extract status/reason from safety verdict
    if "status" in data:
        attrs["rct.status"] = data["status"]
    if "reason" in data:
        attrs["rct.reason"] = data["reason"]
    if "rct_rule_violated" in data:
        attrs["rct.rule_violated"] = data["rct_rule_violated"]

    # 4. Scribe compression attributes
    if "compression_ratio" in data:
        attrs["rct.scribe.compression_ratio"] = float(data["compression_ratio"])
    if "original_tokens" in data:
        attrs["rct.scribe.original_tokens"] = int(data["original_tokens"])
    if "compressed_tokens" in data:
        attrs["rct.scribe.compressed_tokens"] = int(data["compressed_tokens"])
        if "original_tokens" in data:
            attrs["rct.scribe.tokens_saved"] = int(data["original_tokens"]) - int(data["compressed_tokens"])

    # 5. Executor JSON validity & tool calling parameters
    if "payload" in data:
        payload_str = data["payload"]
        import json
        attrs["rct.executor.payload"] = payload_str
        try:
            payload_json = json.loads(payload_str)
            attrs["rct.executor.json_valid"] = True
            tool_call = payload_json.get("tool_call", {})
            if tool_call:
                attrs["rct.executor.tool_name"] = tool_call.get("name", "unknown")
                args = tool_call.get("arguments", {})
                for k, v in args.items():
                    attrs[f"rct.executor.param.{k}"] = str(v)
        except json.JSONDecodeError:
            attrs["rct.executor.json_valid"] = False

    # SignedAI votes
    if "signedai_tier" in data:
        attrs["rct.signedai.tier"] = data["signedai_tier"]
    if "consensus_pct" in data:
        attrs["rct.signedai.consensus_pct"] = data["consensus_pct"]
    if "a_block" in data:
        attrs["rct.a_block"] = bool(data["a_block"])

    # Intent metadata
    if "intent_type" in data:
        attrs["rct.intent.type"] = str(data["intent_type"])
    if "cost_usd" in data:
        attrs["rct.cost_usd"] = float(data["cost_usd"])

    # HexaCore Consensus Attributes (isolated to consensus event to prevent collision)
    if event.event_type == ControlPlaneEventType.HEXACORE_CONSENSUS_RUN:
        if "models_enrolled" in data:
            attrs["rct.hexacore.models_enrolled"] = int(data["models_enrolled"])
        if "votes" in data:
            attrs["rct.hexacore.votes"] = str(data["votes"])
        if "consensus_pct" in data:
            attrs["rct.hexacore.consensus_pct"] = float(data["consensus_pct"])
        if "verdict" in data:
            attrs["rct.hexacore.verdict"] = str(data["verdict"])

    # OS Storage / Security Attributes (isolated to storage event)
    if event.event_type == ControlPlaneEventType.OS_STORAGE_SAVED:
        if "delta_saved_pct" in data:
            attrs["rct.storage.delta_saved_pct"] = float(data["delta_saved_pct"])
        if "signature_verified" in data:
            attrs["rct.storage.signature_verified"] = bool(data["signature_verified"])
        if "signature" in data:
            attrs["rct.storage.signature"] = str(data["signature"])
        if "fingerprint" in data:
            attrs["rct.storage.fingerprint"] = str(data["fingerprint"])

    return attrs



# ---------------------------------------------------------------------------
# OTelAdapter
# ---------------------------------------------------------------------------

class OTelAdapter:
    """
    Bridge between ControlPlaneEvent and OpenTelemetry spans.

    If opentelemetry-sdk is not installed, all methods are no-ops.
    This ensures zero-impact when OTel is not needed.
    """

    def __init__(
        self,
        service_name: str = "rct-control-plane",
        endpoint: Optional[str] = None,
        use_console_exporter: bool = False,
    ) -> None:
        self._enabled = False
        self._tracer: Any = None

        if not _HAS_OTEL:
            return

        service_name = (
            os.environ.get("OTEL_SERVICE_NAME", service_name)
        )
        endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

        resource = Resource(attributes={SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        if use_console_exporter or not endpoint:
            # Console exporter (dev mode)
            provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
        elif _HAS_OTLP and endpoint:
            # OTLP gRPC exporter (production)
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )

        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(
            "rct.control_plane",
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        self._enabled = True

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def emit(self, event: ControlPlaneEvent) -> None:
        """
        Emit a single ControlPlaneEvent as an OTel span.

        Non-blocking: span is recorded and returned immediately.
        """
        if not self._enabled or self._tracer is None:
            return

        span_name = _EVENT_SPAN_NAMES.get(
            event.event_type.value, f"rct.event.{event.event_type.value}"
        )
        fdia_attrs = _extract_fdia_attributes(event)

        base_attrs: Dict[str, Any] = {
            "rct.event_id": event.event_id,
            "rct.event_type": event.event_type.value,
            "rct.actor": event.actor,
            "rct.source": event.source,
            "rct.success": event.success,
        }
        if event.intent_id:
            base_attrs["rct.intent_id"] = event.intent_id
        if event.graph_id:
            base_attrs["rct.graph_id"] = event.graph_id
        if event.node_id:
            base_attrs["rct.node_id"] = event.node_id
        if event.duration_ms is not None:
            base_attrs["rct.duration_ms"] = event.duration_ms

        all_attrs = {**base_attrs, **fdia_attrs}

        with self._tracer.start_as_current_span(span_name, attributes=all_attrs) as span:
            if not event.success and event.error_message:
                span.set_status(
                    trace.StatusCode.ERROR, event.error_message
                )
            # Add event-level annotations for SignedAI votes
            if event.data.get("signer_votes"):
                for vote in event.data["signer_votes"]:
                    span.add_event(
                        "signedai.vote",
                        attributes={
                            "signer": str(vote.get("signer_id", "")),
                            "verdict": str(vote.get("verdict", "")),
                            "confidence": float(vote.get("confidence", 0.0)),
                        },
                    )

    def emit_batch(self, events: List[ControlPlaneEvent]) -> None:
        """Emit a batch of events as individual spans."""
        for event in events:
            self.emit(event)

    def emit_fdia_metric(
        self,
        intent_id: str,
        f_score: float,
        d_score: float,
        i_score: float,
        a_value: int,
        risk_level: str = "LOW",
    ) -> None:
        """
        Emit a standalone FDIA scoring span (not tied to a specific event).

        Useful for recording F=D^I×A calculations as observable spans.
        """
        if not self._enabled or self._tracer is None:
            return

        # Compute F = D^I * A  (constitutional formula)
        f_computed = (d_score ** i_score) * a_value if a_value > 0 else 0.0

        with self._tracer.start_as_current_span(
            "rct.fdia.compute",
            attributes={
                "rct.intent_id": intent_id,
                "rct.fdia.f_score": f_score,
                "rct.fdia.f_computed": f_computed,
                "rct.fdia.d_score": d_score,
                "rct.fdia.i_score": i_score,
                "rct.fdia.a_value": a_value,
                "rct.risk_level": risk_level,
                "rct.a_blocked": a_value == 0,
            },
        ):
            pass


# ---------------------------------------------------------------------------
# Module-level singleton (lazy-initialized)
# ---------------------------------------------------------------------------

_default_adapter: Optional[OTelAdapter] = None


def get_otel_adapter(
    service_name: str = "rct-control-plane",
    endpoint: Optional[str] = None,
) -> OTelAdapter:
    """Get or create the module-level OTel adapter."""
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = OTelAdapter(
            service_name=service_name,
            endpoint=endpoint,
        )
    return _default_adapter

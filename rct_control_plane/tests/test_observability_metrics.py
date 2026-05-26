"""
Coverage tests for observability.py Prometheus metrics paths and ControlPlaneObserver.

Tests:
  1. get_prometheus_metrics() without prometheus → returns None
  2. _make_counter/_make_gauge/_make_histogram with _HAS_PROMETHEUS=False → None
  3. ControlPlaneObserver.observe_event() updates in-memory metrics
  4. INTENT_COMPILED updates total_compilations
  5. POLICY_EVALUATED updates total_policy_evaluations
  6. APPROVAL_REQUESTED updates approvals_required via data dict
  7. ERROR_OCCURRED updates total_failures
  8. get_metrics_summary() returns correct structure
  9. AuditTrail verify_integrity() on empty trail → True
  10. AuditTrail hash chain integrity after multiple events
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import rct_control_plane.observability as obs_mod
from rct_control_plane.observability import (
    ControlPlaneEventType,
    ControlPlaneObserver,
    get_prometheus_metrics,
    PROMETHEUS_CONTENT_TYPE,
)


# ---------------------------------------------------------------------------
# Path 1: get_prometheus_metrics() — prometheus NOT available
# ---------------------------------------------------------------------------

def test_get_prometheus_metrics_without_prometheus():
    """When prometheus is not available, returns None."""
    with patch.object(obs_mod, "_HAS_PROMETHEUS", False), \
         patch.object(obs_mod, "_RCT_REGISTRY", None):
        result = get_prometheus_metrics()
    assert result is None


# ---------------------------------------------------------------------------
# Path 2: _make_* with _HAS_PROMETHEUS=False → None
# ---------------------------------------------------------------------------

def test_make_counter_without_prometheus():
    with patch.object(obs_mod, "_HAS_PROMETHEUS", False), \
         patch.object(obs_mod, "_RCT_REGISTRY", None):
        result = obs_mod._make_counter("test_counter2", "Test counter")
    assert result is None


def test_make_gauge_without_prometheus():
    with patch.object(obs_mod, "_HAS_PROMETHEUS", False), \
         patch.object(obs_mod, "_RCT_REGISTRY", None):
        result = obs_mod._make_gauge("test_gauge2", "Test gauge")
    assert result is None


def test_make_histogram_without_prometheus():
    with patch.object(obs_mod, "_HAS_PROMETHEUS", False), \
         patch.object(obs_mod, "_RCT_REGISTRY", None):
        result = obs_mod._make_histogram("test_hist2", "Test histogram",
                                          buckets=[1, 5, 10])
    assert result is None


# ---------------------------------------------------------------------------
# Path 3: observe_event() INTENT_RECEIVED → total_intents increments
# ---------------------------------------------------------------------------

def test_observer_observe_event_increments_counters():
    """observe_event() increments total_intents for INTENT_RECEIVED."""
    observer = ControlPlaneObserver()
    assert observer.metrics["total_intents"] == 0

    observer.observe_event(
        event_type=ControlPlaneEventType.INTENT_RECEIVED,
        intent_id="test-intent-001",
    )

    assert observer.metrics["total_intents"] == 1


# ---------------------------------------------------------------------------
# Path 4: INTENT_COMPILED with duration_ms → total_compilations
# ---------------------------------------------------------------------------

def test_observer_record_compilation_event():
    """INTENT_COMPILED event with duration_ms updates total_compilations."""
    observer = ControlPlaneObserver()

    observer.observe_event(
        event_type=ControlPlaneEventType.INTENT_COMPILED,
        intent_id="test-intent-002",
        success=True,
        duration_ms=42.0,
    )

    assert observer.metrics["total_compilations"] == 1
    assert 42.0 in observer.metrics["compilation_latency_ms"]


# ---------------------------------------------------------------------------
# Path 5: POLICY_EVALUATED with duration_ms → total_policy_evaluations
# ---------------------------------------------------------------------------

def test_observer_record_policy_evaluation_event():
    """POLICY_EVALUATED event with duration_ms updates total_policy_evaluations."""
    observer = ControlPlaneObserver()

    observer.observe_event(
        event_type=ControlPlaneEventType.POLICY_EVALUATED,
        intent_id="test-intent-003",
        success=True,
        duration_ms=12.5,
    )

    assert observer.metrics["total_policy_evaluations"] == 1
    assert 12.5 in observer.metrics["policy_evaluation_latency_ms"]


# ---------------------------------------------------------------------------
# Path 6: POLICY_EVALUATED with requires_approval=True → approvals_required
# ---------------------------------------------------------------------------

def test_observer_record_approval_required_event():
    """POLICY_EVALUATED with data.requires_approval=True increments approvals_required."""
    observer = ControlPlaneObserver()

    observer.observe_event(
        event_type=ControlPlaneEventType.POLICY_EVALUATED,
        intent_id="test-intent-004",
        duration_ms=5.0,
        data={"requires_approval": True},
    )

    assert observer.metrics["approvals_required"] == 1


# ---------------------------------------------------------------------------
# Path 7: ERROR_OCCURRED → total_failures
# ---------------------------------------------------------------------------

def test_observer_record_failure_event():
    """ERROR_OCCURRED event increments total_failures."""
    observer = ControlPlaneObserver()

    observer.observe_event(
        event_type=ControlPlaneEventType.ERROR_OCCURRED,
        intent_id="test-intent-005",
        success=False,
    )

    assert observer.metrics["total_failures"] == 1


# ---------------------------------------------------------------------------
# Path 8: get_metrics_summary() returns correct structure
# ---------------------------------------------------------------------------

def test_observer_get_metrics_summary_structure():
    """get_metrics_summary() returns a dict with expected keys."""
    observer = ControlPlaneObserver()

    observer.observe_event(event_type=ControlPlaneEventType.INTENT_RECEIVED, intent_id="m-001")
    observer.observe_event(event_type=ControlPlaneEventType.INTENT_COMPILED, intent_id="m-001", success=True, duration_ms=20.0)
    observer.observe_event(event_type=ControlPlaneEventType.POLICY_EVALUATED, intent_id="m-001", success=True, duration_ms=5.0)

    summary = observer.get_metrics_summary()

    assert isinstance(summary, dict)
    assert summary["total_intents"] == 1
    assert summary["total_compilations"] == 1
    assert summary["total_policy_evaluations"] == 1
    assert "audit_trail_entries" in summary
    assert summary["audit_trail_entries"] >= 3


# ---------------------------------------------------------------------------
# AuditEntry.verify() — tamper detection branches
# ---------------------------------------------------------------------------

def test_audit_entry_verify_hash_tamper_detected():
    """Modifying entry_hash after finalize causes verify() to return False."""
    from rct_control_plane.observability import AuditTrail, ControlPlaneEvent

    trail = AuditTrail()
    event = ControlPlaneEvent(
        event_type=ControlPlaneEventType.INTENT_RECEIVED,
        intent_id="tamper-test",
    )
    entry = trail.append(event)

    # Tamper with hash
    entry.entry_hash = "deadbeef" * 8

    assert entry.verify(None) is False


def test_audit_entry_verify_chain_link_broken():
    """Modifying previous_hash breaks the chain link check."""
    from rct_control_plane.observability import AuditTrail, ControlPlaneEvent

    trail = AuditTrail()
    for etype in [ControlPlaneEventType.INTENT_RECEIVED, ControlPlaneEventType.INTENT_COMPILED]:
        trail.append(ControlPlaneEvent(event_type=etype, intent_id="chain-test"))

    second_entry = trail.entries[1]
    # Tamper with the previous_hash pointer
    second_entry.previous_hash = "00" * 32

    # Verify the entry against the real previous entry — chain link should break
    assert second_entry.verify(trail.entries[0]) is False


# ---------------------------------------------------------------------------
# Prometheus mock paths for _update_metrics branches
# ---------------------------------------------------------------------------

def test_prometheus_compilation_latency_observed():
    """_PROM_COMPILATION_LATENCY.observe() called when duration_ms set."""
    observer = ControlPlaneObserver()
    mock_hist = MagicMock()
    mock_counter = MagicMock()

    with patch.object(obs_mod, "_PROM_COMPILATIONS_TOTAL", mock_counter), \
         patch.object(obs_mod, "_PROM_COMPILATION_LATENCY", mock_hist):
        observer.observe_event(
            event_type=ControlPlaneEventType.INTENT_COMPILED,
            intent_id="prom-lat-001",
            success=True,
            duration_ms=55.0,
        )

    mock_hist.observe.assert_called_once_with(55.0)
    mock_counter.inc.assert_called_once()


def test_prometheus_failures_counter_called():
    """_PROM_FAILURES_TOTAL.inc() called on GRAPH_FAILED event."""
    observer = ControlPlaneObserver()
    mock_fail = MagicMock()

    with patch.object(obs_mod, "_PROM_FAILURES_TOTAL", mock_fail):
        observer.observe_event(
            event_type=ControlPlaneEventType.GRAPH_FAILED,
            intent_id="prom-fail-001",
            success=False,
        )

    mock_fail.inc.assert_called_once()


def test_prometheus_approval_granted_counter():
    """_PROM_APPROVALS_GRANTED.inc() called on APPROVAL_GRANTED event."""
    observer = ControlPlaneObserver()
    mock_granted = MagicMock()

    with patch.object(obs_mod, "_PROM_APPROVALS_GRANTED", mock_granted):
        observer.observe_event(
            event_type=ControlPlaneEventType.APPROVAL_GRANTED,
            intent_id="prom-approval-001",
        )

    mock_granted.inc.assert_called_once()


def test_prometheus_executions_counter():
    """_PROM_EXECUTIONS_TOTAL.inc() called on EXECUTION_STARTED event."""
    observer = ControlPlaneObserver()
    mock_exec = MagicMock()

    with patch.object(obs_mod, "_PROM_EXECUTIONS_TOTAL", mock_exec):
        observer.observe_event(
            event_type=ControlPlaneEventType.EXECUTION_STARTED,
            intent_id="prom-exec-001",
        )

    mock_exec.inc.assert_called_once()


def test_prometheus_policy_violations_counter():
    """_PROM_POLICY_VIOLATIONS_TOTAL.inc() called when violations in data."""
    observer = ControlPlaneObserver()
    mock_viol = MagicMock()

    with patch.object(obs_mod, "_PROM_POLICY_VIOLATIONS_TOTAL", mock_viol):
        observer.observe_event(
            event_type=ControlPlaneEventType.POLICY_EVALUATED,
            intent_id="prom-viol-001",
            duration_ms=3.0,
            data={"violations": ["rule_1", "rule_2"]},
        )

    mock_viol.inc.assert_called_once_with(2)


def test_prometheus_policy_latency_observed():
    """_PROM_POLICY_LATENCY.observe() called when POLICY_EVALUATED has duration_ms."""
    observer = ControlPlaneObserver()
    mock_lat = MagicMock()
    mock_evals = MagicMock()

    with patch.object(obs_mod, "_PROM_POLICY_EVALS_TOTAL", mock_evals), \
         patch.object(obs_mod, "_PROM_POLICY_LATENCY", mock_lat):
        observer.observe_event(
            event_type=ControlPlaneEventType.POLICY_EVALUATED,
            intent_id="prom-polat-001",
            duration_ms=8.0,
        )

    mock_lat.observe.assert_called_once_with(8.0)
    mock_evals.inc.assert_called_once()


def test_observe_event_node_completed():
    """NODE_COMPLETED increments total_nodes_executed."""
    observer = ControlPlaneObserver()
    observer.observe_event(event_type=ControlPlaneEventType.NODE_COMPLETED, intent_id="nc-001")
    assert observer.metrics["total_nodes_executed"] == 1


def test_observe_event_audit_gauge_updated():
    """_PROM_AUDIT_ENTRIES.set() called after each observe_event."""
    observer = ControlPlaneObserver()
    mock_gauge = MagicMock()

    with patch.object(obs_mod, "_PROM_AUDIT_ENTRIES", mock_gauge):
        observer.observe_event(event_type=ControlPlaneEventType.INTENT_RECEIVED, intent_id="gauge-001")

    mock_gauge.set.assert_called()


# ---------------------------------------------------------------------------
# Path 9: AuditTrail verify_integrity() on empty trail
# ---------------------------------------------------------------------------

def test_audit_trail_verify_integrity_empty():
    """Empty audit trail passes integrity check."""
    observer = ControlPlaneObserver()
    trail = observer.audit_trail

    result = trail.verify_integrity()
    assert result is True


# ---------------------------------------------------------------------------
# Path 10: AuditTrail hash chain integrity
# ---------------------------------------------------------------------------

def test_audit_trail_hash_chain():
    """Records multiple events and verifies the hash chain is valid."""
    observer = ControlPlaneObserver()

    for i in range(3):
        observer.observe_event(
            event_type=ControlPlaneEventType.INTENT_RECEIVED,
            intent_id=f"chain-intent-{i:03d}",
            success=True,
        )

    trail = observer.audit_trail
    assert len(trail) >= 3
    assert trail.verify_integrity() is True

    for entry in trail.entries[-3:]:
        assert entry.entry_hash is not None
        assert len(entry.entry_hash) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Path 11: PROMETHEUS_CONTENT_TYPE constant
# ---------------------------------------------------------------------------

def test_prometheus_content_type_constant():
    """PROMETHEUS_CONTENT_TYPE is a non-empty string."""
    assert isinstance(PROMETHEUS_CONTENT_TYPE, str)
    assert len(PROMETHEUS_CONTENT_TYPE) > 0


# ---------------------------------------------------------------------------
# Path 12: Prometheus counter called when _PROM_INTENTS_TOTAL is set
# ---------------------------------------------------------------------------

def test_prometheus_counter_called_on_intent_received():
    """When _PROM_INTENTS_TOTAL is set, it gets .inc() called."""
    observer = ControlPlaneObserver()
    mock_counter = MagicMock()

    with patch.object(obs_mod, "_PROM_INTENTS_TOTAL", mock_counter):
        observer.observe_event(
            event_type=ControlPlaneEventType.INTENT_RECEIVED,
            intent_id="prom-test-001",
        )

    mock_counter.inc.assert_called_once()

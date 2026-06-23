"""
Control Plane Observability

Event tracking, metrics collection, and audit trail for Control Plane operations.
Provides visibility into compilation, policy evaluation, and execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from uuid import uuid4
import hashlib
import json


class ControlPlaneEventType(str, Enum):
    """Types of Control Plane events"""
    INTENT_RECEIVED = "intent_received"
    INTENT_COMPILED = "intent_compiled"
    GRAPH_BUILT = "graph_built"
    POLICY_EVALUATED = "policy_evaluated"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    EXECUTION_STARTED = "execution_started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    GRAPH_COMPLETED = "graph_completed"
    GRAPH_FAILED = "graph_failed"
    STATE_TRANSITION = "state_transition"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class ControlPlaneEvent:
    """
    A single event in Control Plane execution.
    
    Events are immutable and form an audit trail.
    """
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: ControlPlaneEventType = ControlPlaneEventType.INTENT_RECEIVED
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Context
    intent_id: Optional[str] = None
    graph_id: Optional[str] = None
    node_id: Optional[str] = None
    state_id: Optional[str] = None
    
    # Event data
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Actor/source
    actor: str = "system"
    source: str = "control_plane"
    
    # Metadata
    duration_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "intent_id": self.intent_id,
            "graph_id": self.graph_id,
            "node_id": self.node_id,
            "state_id": self.state_id,
            "data": self.data,
            "actor": self.actor,
            "source": self.source,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error_message": self.error_message
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), default=str)


@dataclass
class AuditEntry:
    """
    Tamper-proof audit log entry with cryptographic hash chain.
    
    Each entry contains a hash of the previous entry, creating
    an immutable chain that can detect tampering.
    """
    entry_id: str = field(default_factory=lambda: str(uuid4()))
    sequence_number: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Event data
    event: ControlPlaneEvent = field(default_factory=lambda: ControlPlaneEvent())
    
    # Hash chain
    previous_hash: Optional[str] = None  # SHA-256 of previous entry
    entry_hash: Optional[str] = None      # SHA-256 of this entry
    
    # Signature (optional)
    signature: Optional[str] = None
    signed_by: Optional[str] = None
    
    def calculate_hash(self) -> str:
        """
        Calculate SHA-256 hash of this entry.
        
        Hash includes: sequence_number + timestamp + event + previous_hash
        This ensures any modification breaks the chain.
        
        Returns:
            Hexadecimal SHA-256 hash string
        """
        # Create deterministic string representation
        hash_input = f"{self.sequence_number}|{self.timestamp.isoformat()}|{self.event.to_json()}|{self.previous_hash or ''}"
        
        # Calculate SHA-256
        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
    
    def finalize(self):
        """Finalize entry by calculating its hash"""
        self.entry_hash = self.calculate_hash()
    
    def verify(self, previous_entry: Optional["AuditEntry"] = None) -> bool:
        """
        Verify integrity of this entry.
        
        Args:
            previous_entry: Previous entry in chain (None for first entry)
            
        Returns:
            True if entry is valid, False if tampered
        """
        # Verify hash matches
        expected_hash = self.calculate_hash()
        if self.entry_hash != expected_hash:
            return False
        
        # Verify chain link
        if previous_entry:
            if self.previous_hash != previous_entry.entry_hash:
                return False
            if self.sequence_number != previous_entry.sequence_number + 1:
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "entry_id": self.entry_id,
            "sequence_number": self.sequence_number,
            "timestamp": self.timestamp.isoformat(),
            "event": self.event.to_dict(),
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
            "signature": self.signature,
            "signed_by": self.signed_by
        }


class AuditTrail:
    """
    Maintains a tamper-proof audit trail using hash chains.
    
    Each entry is cryptographically linked to the previous entry,
    making it impossible to modify history without detection.
    """
    
    def __init__(self):
        self.entries: List[AuditEntry] = []
    
    def append(self, event: ControlPlaneEvent) -> AuditEntry:
        """
        Append event to audit trail.
        
        Args:
            event: Event to append
            
        Returns:
            Created AuditEntry
        """
        # Get previous entry
        previous_entry = self.entries[-1] if self.entries else None
        
        # Create new entry
        entry = AuditEntry(
            sequence_number=len(self.entries),
            event=event,
            previous_hash=previous_entry.entry_hash if previous_entry else None
        )
        
        # Finalize (calculate hash)
        entry.finalize()
        
        # Append
        self.entries.append(entry)
        
        return entry
    
    def verify_integrity(self) -> bool:
        """
        Verify integrity of entire audit trail.
        
        Returns:
            True if trail is intact, False if tampered
        """
        for i, entry in enumerate(self.entries):
            previous_entry = self.entries[i - 1] if i > 0 else None
            
            if not entry.verify(previous_entry):
                return False
        
        return True
    
    def get_events_for_intent(self, intent_id: str) -> List[ControlPlaneEvent]:
        """Get all events for a specific intent"""
        return [entry.event for entry in self.entries if entry.event.intent_id == intent_id]
    
    def get_events_by_type(self, event_type: ControlPlaneEventType) -> List[ControlPlaneEvent]:
        """Get all events of a specific type"""
        return [entry.event for entry in self.entries if entry.event.event_type == event_type]
    
    def get_recent_events(self, count: int = 10) -> List[ControlPlaneEvent]:
        """Get most recent events"""
        return [entry.event for entry in self.entries[-count:]]
    
    def __len__(self) -> int:
        """Get number of entries"""
        return len(self.entries)


class ControlPlaneObserver:
    """
    Observes Control Plane execution and collects telemetry.
    
    - Tracks events throughout execution lifecycle
    - Maintains audit trail
    - Collects metrics
    - Notifies event handlers
    """
    
    def __init__(self):
        self.audit_trail = AuditTrail()
        self.event_handlers: List[Callable[[ControlPlaneEvent], None]] = []
        self.metrics: Dict[str, Any] = {}
        
        # Initialize metrics
        self._init_metrics()
    
    def _init_metrics(self):
        """Initialize metrics structures"""
        self.metrics = {
            "total_intents": 0,
            "total_compilations": 0,
            "total_graphs": 0,
            "total_policy_evaluations": 0,
            "total_executions": 0,
            "total_nodes_executed": 0,
            "total_failures": 0,
            "compilation_latency_ms": [],
            "policy_evaluation_latency_ms": [],
            "graph_build_latency_ms": [],
            "execution_latency_ms": [],
            "policy_violations": 0,
            "approvals_required": 0,
            "approvals_granted": 0,
        }
    
    def observe_event(
        self,
        event_type: ControlPlaneEventType,
        intent_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        node_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        actor: str = "system"
    ) -> ControlPlaneEvent:
        """
        Observe and record an event.
        
        Args:
            event_type: Type of event
            intent_id: Associated intent ID
            graph_id: Associated graph ID
            node_id: Associated node ID
            data: Event data
            duration_ms: Event duration in milliseconds
            success: Whether event was successful
            error_message: Error message if failed
            actor: Who/what triggered the event
            
        Returns:
            Created ControlPlaneEvent
        """
        # Create event
        event = ControlPlaneEvent(
            event_type=event_type,
            intent_id=intent_id,
            graph_id=graph_id,
            node_id=node_id,
            data=data or {},
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
            actor=actor
        )
        
        # Add to audit trail
        self.audit_trail.append(event)
        
        # Update metrics
        self._update_metrics(event)
        
        # Notify handlers
        for handler in self.event_handlers:
            try:
                handler(event)
            except Exception as e:
                # Don't let handler errors break observability
                print(f"Event handler error: {e}")
        
        return event
    
    def _update_metrics(self, event: ControlPlaneEvent):
        """Update metrics based on event"""
        if event.event_type == ControlPlaneEventType.INTENT_RECEIVED:
            self.metrics["total_intents"] += 1
        
        elif event.event_type == ControlPlaneEventType.INTENT_COMPILED:
            self.metrics["total_compilations"] += 1
            if event.duration_ms:
                self.metrics["compilation_latency_ms"].append(event.duration_ms)
        
        elif event.event_type == ControlPlaneEventType.GRAPH_BUILT:
            self.metrics["total_graphs"] += 1
            if event.duration_ms:
                self.metrics["graph_build_latency_ms"].append(event.duration_ms)
        
        elif event.event_type == ControlPlaneEventType.POLICY_EVALUATED:
            self.metrics["total_policy_evaluations"] += 1
            if event.duration_ms:
                self.metrics["policy_evaluation_latency_ms"].append(event.duration_ms)
            if event.data.get("violations"):
                self.metrics["policy_violations"] += len(event.data["violations"])
            if event.data.get("requires_approval"):
                self.metrics["approvals_required"] += 1
        
        elif event.event_type == ControlPlaneEventType.APPROVAL_GRANTED:
            self.metrics["approvals_granted"] += 1
        
        elif event.event_type == ControlPlaneEventType.EXECUTION_STARTED:
            self.metrics["total_executions"] += 1
        
        elif event.event_type == ControlPlaneEventType.NODE_COMPLETED:
            self.metrics["total_nodes_executed"] += 1
        
        elif event.event_type == ControlPlaneEventType.GRAPH_FAILED:
            self.metrics["total_failures"] += 1
        
        elif event.event_type == ControlPlaneEventType.ERROR_OCCURRED:
            self.metrics["total_failures"] += 1
    
    def register_handler(self, handler: Callable[[ControlPlaneEvent], None]):
        """Register an event handler"""
        self.event_handlers.append(handler)
    
    def unregister_handler(self, handler: Callable[[ControlPlaneEvent], None]):
        """Unregister an event handler"""
        if handler in self.event_handlers:
            self.event_handlers.remove(handler)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of collected metrics"""
        # Calculate averages for latencies
        def avg(values):
            return sum(values) / len(values) if values else 0
        
        return {
            "total_intents": self.metrics["total_intents"],
            "total_compilations": self.metrics["total_compilations"],
            "total_graphs": self.metrics["total_graphs"],
            "total_policy_evaluations": self.metrics["total_policy_evaluations"],
            "total_executions": self.metrics["total_executions"],
            "total_nodes_executed": self.metrics["total_nodes_executed"],
            "total_failures": self.metrics["total_failures"],
            "avg_compilation_latency_ms": avg(self.metrics["compilation_latency_ms"]),
            "avg_policy_evaluation_latency_ms": avg(self.metrics["policy_evaluation_latency_ms"]),
            "avg_graph_build_latency_ms": avg(self.metrics["graph_build_latency_ms"]),
            "policy_violations": self.metrics["policy_violations"],
            "approvals_required": self.metrics["approvals_required"],
            "approvals_granted": self.metrics["approvals_granted"],
            "audit_trail_entries": len(self.audit_trail)
        }
    
    def get_intent_timeline(self, intent_id: str) -> List[ControlPlaneEvent]:
        """Get chronological timeline of events for an intent"""
        return self.audit_trail.get_events_for_intent(intent_id)
    
    def reset_metrics(self):
        """Reset all metrics (for testing)"""
        self._init_metrics()
    
    def verify_audit_integrity(self) -> bool:
        """Verify audit trail integrity"""
        return self.audit_trail.verify_integrity()

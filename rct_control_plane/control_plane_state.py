"""
Control Plane State Model

Tracks state transitions through the Control Plane lifecycle.
Phases: INTENT_RECEIVED → INTENT_COMPILED → GRAPH_BUILT → POLICY_CHECKED 
        → APPROVED → EXECUTING → COMPLETED/FAILED
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4

from .intent_schema import IntentObject
from .execution_graph_ir import ExecutionGraph

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .observability import ControlPlaneObserver


class ControlPlanePhase(Enum):
    """Control Plane execution phases"""
    INTENT_RECEIVED = "intent_received"      # User intent received
    INTENT_COMPILED = "intent_compiled"      # Compiled to ExecutionPlan
    GRAPH_BUILT = "graph_built"              # ExecutionGraph constructed
    POLICY_CHECKED = "policy_checked"        # Policy evaluation done
    APPROVED = "approved"                    # Manual/auto approval granted
    EXECUTING = "executing"                  # Graph being executed
    COMPLETED = "completed"                  # Successfully completed
    FAILED = "failed"                        # Failed at some phase
    CANCELLED = "cancelled"                  # User cancelled
    ROLLED_BACK = "rolled_back"              # State rolled back


class TransitionResult(Enum):
    """Result of a state transition attempt"""
    SUCCESS = "success"
    INVALID_TRANSITION = "invalid_transition"
    VALIDATION_FAILED = "validation_failed"
    POLICY_VIOLATION = "policy_violation"


# Valid state transitions
VALID_TRANSITIONS: Dict[ControlPlanePhase, List[ControlPlanePhase]] = {
    ControlPlanePhase.INTENT_RECEIVED: [
        ControlPlanePhase.INTENT_COMPILED, 
        ControlPlanePhase.FAILED, 
        ControlPlanePhase.CANCELLED
    ],
    ControlPlanePhase.INTENT_COMPILED: [
        ControlPlanePhase.GRAPH_BUILT, 
        ControlPlanePhase.FAILED, 
        ControlPlanePhase.CANCELLED
    ],
    ControlPlanePhase.GRAPH_BUILT: [
        ControlPlanePhase.POLICY_CHECKED, 
        ControlPlanePhase.FAILED, 
        ControlPlanePhase.CANCELLED
    ],
    ControlPlanePhase.POLICY_CHECKED: [
        ControlPlanePhase.APPROVED,
        ControlPlanePhase.FAILED,
        ControlPlanePhase.CANCELLED
    ],
    ControlPlanePhase.APPROVED: [
        ControlPlanePhase.EXECUTING, 
        ControlPlanePhase.CANCELLED
    ],
    ControlPlanePhase.EXECUTING: [
        ControlPlanePhase.COMPLETED,
        ControlPlanePhase.FAILED,
        ControlPlanePhase.CANCELLED
    ],
    ControlPlanePhase.COMPLETED: [
        ControlPlanePhase.ROLLED_BACK
    ],
    ControlPlanePhase.FAILED: [
        ControlPlanePhase.ROLLED_BACK,
        ControlPlanePhase.INTENT_RECEIVED  # Retry from start
    ],
    ControlPlanePhase.CANCELLED: [],
    ControlPlanePhase.ROLLED_BACK: []
}


@dataclass
class StateTransition:
    """Records a state transition"""
    transition_id: str = field(default_factory=lambda: str(uuid4()))
    from_phase: ControlPlanePhase = ControlPlanePhase.INTENT_RECEIVED
    to_phase: ControlPlanePhase = ControlPlanePhase.INTENT_RECEIVED
    timestamp: datetime = field(default_factory=datetime.now)
    actor: str = "system"  # Who/what triggered the transition
    reason: Optional[str] = None
    result: TransitionResult = TransitionResult.SUCCESS
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "transition_id": self.transition_id,
            "from_phase": self.from_phase.value,
            "to_phase": self.to_phase.value,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "reason": self.reason,
            "result": self.result.value,
            "metadata": self.metadata
        }


@dataclass
class ControlPlaneState:
    """
    Tracks state of a Control Plane execution.
    
    Version tracking allows rollback to previous states.
    """
    state_id: str = field(default_factory=lambda: str(uuid4()))
    intent_id: str = field(default_factory=lambda: str(uuid4()))
    phase: ControlPlanePhase = ControlPlanePhase.INTENT_RECEIVED
    version: int = 1
    
    # Observer for event tracking
    observer: Optional['ControlPlaneObserver'] = None
    
    # Snapshots at each phase
    intent_snapshot: Optional[IntentObject] = None
    graph_snapshot: Optional[ExecutionGraph] = None
    
    # Execution tracking
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    # Cost and duration
    estimated_cost_usd: Decimal = Decimal("0.00")
    actual_cost_usd: Decimal = Decimal("0.00")
    estimated_duration_seconds: int = 0
    actual_duration_seconds: int = 0
    
    # Policy and approval
    policy_violations: List[str] = field(default_factory=list)
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    
    # Error tracking
    error_message: Optional[str] = None
    error_phase: Optional[ControlPlanePhase] = None
    
    # Transition history
    transitions: List[StateTransition] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def can_transition_to(self, to_phase: ControlPlanePhase) -> bool:
        """Check if transition to given phase is valid"""
        return to_phase in VALID_TRANSITIONS.get(self.phase, [])
    
    def transition_to(
        self,
        to_phase: ControlPlanePhase,
        actor: str = "system",
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TransitionResult:
        """
        Transition to a new phase.
        
        Args:
            to_phase: Target phase
            actor: Who triggered the transition
            reason: Optional reason for transition
            metadata: Optional metadata
            
        Returns:
            TransitionResult indicating success or failure
        """
        # Validate transition
        if not self.can_transition_to(to_phase):
            transition = StateTransition(
                from_phase=self.phase,
                to_phase=to_phase,
                actor=actor,
                reason=reason or "Invalid transition",
                result=TransitionResult.INVALID_TRANSITION,
                metadata=metadata or {}
            )
            self.transitions.append(transition)
            return TransitionResult.INVALID_TRANSITION
        
        # Update error tracking (capture phase BEFORE transition)
        if to_phase == ControlPlanePhase.FAILED:
            self.error_phase = self.phase  # Capture current phase before changing
            if reason:
                self.error_message = reason
        
        # Record transition
        transition = StateTransition(
            from_phase=self.phase,
            to_phase=to_phase,
            actor=actor,
            reason=reason,
            result=TransitionResult.SUCCESS,
            metadata=metadata or {}
        )
        self.transitions.append(transition)
        
        # Update state
        self.phase = to_phase
        self.updated_at = datetime.now()
        self.version += 1
        
        # Emit event: STATE_TRANSITION
        if self.observer:
            from .observability import ControlPlaneEventType
            self.observer.observe_event(
                event_type=ControlPlaneEventType.STATE_TRANSITION,
                intent_id=self.intent_id,
                data={
                    "state_id": self.state_id,
                    "from_phase": transition.from_phase.value,
                    "to_phase": transition.to_phase.value,
                    "version": self.version,
                    "reason": reason,
                    "metadata": metadata or {}
                },
                actor=actor
            )
        
        # Update completion tracking
        if to_phase in [ControlPlanePhase.COMPLETED, ControlPlanePhase.FAILED, ControlPlanePhase.CANCELLED]:
            self.completed_at = datetime.now()
            if self.started_at:
                self.actual_duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        
        return TransitionResult.SUCCESS
    
    def is_terminal(self) -> bool:
        """Check if state is in a terminal phase"""
        return self.phase in [
            ControlPlanePhase.COMPLETED,
            ControlPlanePhase.FAILED,
            ControlPlanePhase.CANCELLED,
            ControlPlanePhase.ROLLED_BACK
        ]
    
    def is_failed(self) -> bool:
        """Check if state is failed"""
        return self.phase == ControlPlanePhase.FAILED
    
    def is_completed(self) -> bool:
        """Check if state is completed successfully"""
        return self.phase == ControlPlanePhase.COMPLETED
    
    def get_duration_seconds(self) -> int:
        """Get current or actual duration in seconds"""
        if self.completed_at:
            return self.actual_duration_seconds
        else:
            return int((datetime.now() - self.started_at).total_seconds())
    
    def get_cost_usd(self) -> Decimal:
        """Get actual cost if completed, otherwise estimated"""
        if self.is_terminal():
            return self.actual_cost_usd
        else:
            return self.estimated_cost_usd
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "state_id": self.state_id,
            "intent_id": self.intent_id,
            "phase": self.phase.value,
            "version": self.version,
            "intent_snapshot": self.intent_snapshot.model_dump() if self.intent_snapshot else None,
            "graph_snapshot": self.graph_snapshot.to_dict() if self.graph_snapshot else None,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "estimated_cost_usd": str(self.estimated_cost_usd),
            "actual_cost_usd": str(self.actual_cost_usd),
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "actual_duration_seconds": self.actual_duration_seconds,
            "policy_violations": self.policy_violations,
            "requires_approval": self.requires_approval,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "error_message": self.error_message,
            "error_phase": self.error_phase.value if self.error_phase else None,
            "transitions": [t.to_dict() for t in self.transitions],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ControlPlaneState":
        """Create from dictionary"""
        from .intent_schema import IntentObject
        from .execution_graph_ir import ExecutionGraph
        
        state = cls(
            state_id=data["state_id"],
            intent_id=data["intent_id"],
            phase=ControlPlanePhase(data["phase"]),
            version=data["version"],
            started_at=datetime.fromisoformat(data["started_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            estimated_cost_usd=Decimal(data["estimated_cost_usd"]),
            actual_cost_usd=Decimal(data["actual_cost_usd"]),
            estimated_duration_seconds=data["estimated_duration_seconds"],
            actual_duration_seconds=data["actual_duration_seconds"],
            policy_violations=data["policy_violations"],
            requires_approval=data["requires_approval"],
            approved_by=data.get("approved_by"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {})
        )
        
        if data.get("completed_at"):
            state.completed_at = datetime.fromisoformat(data["completed_at"])
        
        if data.get("approved_at"):
            state.approved_at = datetime.fromisoformat(data["approved_at"])
        
        if data.get("error_phase"):
            state.error_phase = ControlPlanePhase(data["error_phase"])
        
        # Restore snapshots
        if data.get("intent_snapshot"):
            state.intent_snapshot = IntentObject.model_validate(data["intent_snapshot"])
        
        if data.get("graph_snapshot"):
            # ExecutionGraph.from_dict would need to be implemented
            pass  # TODO: Implement ExecutionGraph.from_dict
        
        # Restore transitions
        for t_data in data.get("transitions", []):
            transition = StateTransition(
                transition_id=t_data["transition_id"],
                from_phase=ControlPlanePhase(t_data["from_phase"]),
                to_phase=ControlPlanePhase(t_data["to_phase"]),
                timestamp=datetime.fromisoformat(t_data["timestamp"]),
                actor=t_data["actor"],
                reason=t_data.get("reason"),
                result=TransitionResult(t_data["result"]),
                metadata=t_data.get("metadata", {})
            )
            state.transitions.append(transition)
        
        return state

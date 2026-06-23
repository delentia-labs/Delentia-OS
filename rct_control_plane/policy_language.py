"""
Policy Language for Control Plane

Defines policies that govern execution approval, resource limits, and compliance.
Policies can approve, reject, escalate, or require manual approval for intents.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from uuid import uuid4

from .execution_graph_ir import ExecutionGraph, NodeType
from .intent_schema import IntentObject, IntentType, RiskProfile

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .observability import ControlPlaneObserver


class PolicyAction(str, Enum):
    """Actions a policy can take"""
    APPROVE = "approve"                     # Auto-approve execution
    REJECT = "reject"                       # Block execution
    ESCALATE = "escalate"                   # Escalate to human reviewer
    NOTIFY = "notify"                       # Send notification but allow
    LOG = "log"                             # Log event but allow
    REQUIRE_APPROVAL = "require_approval"   # Manual approval required


class PolicyPriority(str, Enum):
    """Priority for policy evaluation (lower number = higher priority)"""
    CRITICAL = "critical"      # 1 - Security, compliance (blocks)
    HIGH = "high"              # 2 - Cost caps, risk gates
    MEDIUM = "medium"          # 3 - Quality, resource limits
    LOW = "low"                # 4 - Notifications, logging


class PolicyScope(str, Enum):
    """What the policy applies to"""
    INTENT = "intent"          # Applies to intent level
    GRAPH = "graph"            # Applies to execution graph
    NODE = "node"              # Applies to individual nodes
    ORGANIZATION = "organization"  # Org-wide policy
    USER = "user"              # User-specific policy


class ConditionOperator(str, Enum):
    """Comparison operators for conditions"""
    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_OR_EQUAL = "<="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    MATCHES = "matches"        # Regex match


@dataclass
class PolicyCondition:
    """
    A boolean condition that must be satisfied.
    
    Examples:
    - cost_usd > 100.00
    - risk_level == SYSTEMIC
    - intent_type in [BUILD_APP, DEPLOY]
    - estimated_duration_seconds >= 3600
    """
    field: str                              # Field to check (e.g., "cost_usd", "risk_level")
    operator: ConditionOperator
    value: Any                              # Value to compare against
    description: Optional[str] = None
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Evaluate condition against a context.
        
        Args:
            context: Dict with fields like cost_usd, risk_level, intent_type, etc.
            
        Returns:
            True if condition is satisfied, False otherwise
        """
        if self.field not in context:
            return False
        
        actual_value = context[self.field]
        
        # Handle different operators
        if self.operator == ConditionOperator.EQUALS:
            return actual_value == self.value
        elif self.operator == ConditionOperator.NOT_EQUALS:
            return actual_value != self.value
        elif self.operator == ConditionOperator.GREATER_THAN:
            return actual_value > self.value
        elif self.operator == ConditionOperator.GREATER_OR_EQUAL:
            return actual_value >= self.value
        elif self.operator == ConditionOperator.LESS_THAN:
            return actual_value < self.value
        elif self.operator == ConditionOperator.LESS_OR_EQUAL:
            return actual_value <= self.value
        elif self.operator == ConditionOperator.IN:
            return actual_value in self.value
        elif self.operator == ConditionOperator.NOT_IN:
            return actual_value not in self.value
        elif self.operator == ConditionOperator.CONTAINS:
            return self.value in actual_value
        elif self.operator == ConditionOperator.MATCHES:
            import re
            return bool(re.search(self.value, str(actual_value)))
        else:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": str(self.value) if isinstance(self.value, Decimal) else self.value,
            "description": self.description
        }


@dataclass
class PolicyRule:
    """
    A policy rule that evaluates conditions and takes actions.
    
    A rule consists of:
    - Conditions: One or more conditions (AND logic)
    - Action: What to do if conditions are met
    - Priority: Execution priority
    - Scope: What the rule applies to
    """
    rule_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = "Unnamed Policy"
    description: str = ""
    scope: PolicyScope = PolicyScope.INTENT
    priority: PolicyPriority = PolicyPriority.MEDIUM
    
    # Conditions (all must be true for rule to trigger)
    conditions: List[PolicyCondition] = field(default_factory=list)
    
    # Action to take if conditions are met
    action: PolicyAction = PolicyAction.LOG
    action_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Enable/disable
    enabled: bool = True
    
    # Audit
    created_by: str = "system"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Evaluate all conditions against context.
        
        Args:
            context: Evaluation context with fields
            
        Returns:
            True if all conditions are satisfied, False otherwise
        """
        if not self.enabled:
            return False
        
        # All conditions must be true (AND logic)
        for condition in self.conditions:
            if not condition.evaluate(context):
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "scope": self.scope.value,
            "priority": self.priority.value,
            "conditions": [c.to_dict() for c in self.conditions],
            "action": self.action.value,
            "action_metadata": self.action_metadata,
            "enabled": self.enabled,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyRule":
        """Create from dictionary"""
        rule = cls(
            rule_id=data["rule_id"],
            name=data["name"],
            description=data["description"],
            scope=PolicyScope(data["scope"]),
            priority=PolicyPriority(data["priority"]),
            action=PolicyAction(data["action"]),
            action_metadata=data.get("action_metadata", {}),
            enabled=data.get("enabled", True),
            created_by=data.get("created_by", "system"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"])
        )
        
        # Restore conditions
        for cond_data in data.get("conditions", []):
            condition = PolicyCondition(
                field=cond_data["field"],
                operator=ConditionOperator(cond_data["operator"]),
                value=cond_data["value"],
                description=cond_data.get("description")
            )
            rule.conditions.append(condition)
        
        return rule


@dataclass
class PolicyEvaluationResult:
    """Result of evaluating policies against an intent/graph"""
    intent_id: str
    evaluated_at: datetime = field(default_factory=datetime.now)
    
    # Overall decision
    decision: PolicyAction = PolicyAction.APPROVE
    decision_reason: str = ""
    
    # Triggered rules
    triggered_rules: List[PolicyRule] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Approval tracking
    requires_approval: bool = False
    approval_granted: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    
    # Escalation
    escalated: bool = False
    escalated_to: Optional[str] = None
    escalation_reason: Optional[str] = None
    
    # Metadata
    evaluation_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_approved(self) -> bool:
        """Check if execution is approved"""
        if self.decision == PolicyAction.REJECT:
            return False
        if self.requires_approval:
            return self.approval_granted
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "intent_id": self.intent_id,
            "evaluated_at": self.evaluated_at.isoformat(),
            "decision": self.decision.value,
            "decision_reason": self.decision_reason,
            "triggered_rules": [r.to_dict() for r in self.triggered_rules],
            "violations": self.violations,
            "warnings": self.warnings,
            "requires_approval": self.requires_approval,
            "approval_granted": self.approval_granted,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "escalated": self.escalated,
            "escalated_to": self.escalated_to,
            "escalation_reason": self.escalation_reason,
            "evaluation_time_ms": self.evaluation_time_ms,
            "metadata": self.metadata
        }


class PolicyEvaluator:
    """
    Evaluates policies against intents and execution graphs.
    
    Evaluation order:
    1. CRITICAL priority policies (security, compliance)
    2. HIGH priority policies (cost, risk)
    3. MEDIUM priority policies (quality, resources)
    4. LOW priority policies (notifications, logging)
    
    First REJECT or ESCALATE action wins.
    REQUIRE_APPROVAL accumulates.
    """
    
    def __init__(self, observer: Optional['ControlPlaneObserver'] = None):
        """Initialize evaluator
        
        Args:
            observer: Optional ControlPlaneObserver for event tracking
        """
        self.rules: List[PolicyRule] = []
        self.observer = observer
    
    def add_rule(self, rule: PolicyRule):
        """Add a policy rule"""
        self.rules.append(rule)
        # Sort by priority
        self._sort_rules()
    
    def remove_rule(self, rule_id: str):
        """Remove a policy rule"""
        self.rules = [r for r in self.rules if r.rule_id != rule_id]
    
    def _sort_rules(self):
        """Sort rules by priority (CRITICAL first, then HIGH, MEDIUM, LOW)"""
        priority_order = {
            PolicyPriority.CRITICAL: 1,
            PolicyPriority.HIGH: 2,
            PolicyPriority.MEDIUM: 3,
            PolicyPriority.LOW: 4
        }
        self.rules.sort(key=lambda r: priority_order[r.priority])
    
    def evaluate_intent(
        self,
        intent: IntentObject,
        graph: Optional[ExecutionGraph] = None
    ) -> PolicyEvaluationResult:
        """
        Evaluate all policies against an intent and optional graph.
        
        Args:
            intent: Intent to evaluate
            graph: Optional execution graph
            
        Returns:
            PolicyEvaluationResult with decision and triggered rules
        """
        start_time = datetime.now()
        
        result = PolicyEvaluationResult(intent_id=str(intent.id))
        
        # Build evaluation context
        context = self._build_context(intent, graph)
        
        # Evaluate rules in priority order
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            # Check if rule applies to this scope
            if not self._rule_applies(rule, intent, graph):
                continue
            
            # Evaluate rule conditions
            if rule.evaluate(context):
                result.triggered_rules.append(rule)
                
                # Handle action
                if rule.action == PolicyAction.REJECT:
                    result.decision = PolicyAction.REJECT
                    result.decision_reason = rule.description or rule.name
                    result.violations.append(f"{rule.name}: {rule.description}")
                    break  # REJECT wins, stop evaluation
                
                elif rule.action == PolicyAction.ESCALATE:
                    result.decision = PolicyAction.ESCALATE
                    result.escalated = True
                    result.escalation_reason = rule.description or rule.name
                    result.escalated_to = rule.action_metadata.get("escalate_to", "admin")
                    break  # ESCALATE wins, stop evaluation
                
                elif rule.action == PolicyAction.REQUIRE_APPROVAL:
                    result.requires_approval = True
                    result.decision_reason += f"{rule.name}; "
                
                elif rule.action == PolicyAction.NOTIFY:
                    result.warnings.append(f"{rule.name}: {rule.description}")
                
                # LOG action is passive
        
        # Calculate evaluation time
        end_time = datetime.now()
        result.evaluation_time_ms = (end_time - start_time).total_seconds() * 1000
        
        # Emit event: POLICY_EVALUATED
        if self.observer:
            from .observability import ControlPlaneEventType
            self.observer.observe_event(
                event_type=ControlPlaneEventType.POLICY_EVALUATED,
                intent_id=str(intent.id),
                graph_id=graph.graph_id if graph else None,
                data={
                    "decision": result.decision.value,
                    "violations": result.violations,
                    "warnings": result.warnings,
                    "requires_approval": result.requires_approval,
                    "escalated": result.escalated,
                    "triggered_rules_count": len(result.triggered_rules)
                },
                duration_ms=result.evaluation_time_ms,
                success=True
            )
        
        return result
    
    def _build_context(
        self,
        intent: IntentObject,
        graph: Optional[ExecutionGraph]
    ) -> Dict[str, Any]:
        """Build evaluation context from intent and graph"""
        context = {
            "intent_id": str(intent.id),
            "intent_type": intent.intent_type,
            "priority": intent.priority,
            "risk_profile": intent.risk_profile,
            "scope_type": intent.scope.scope_type,
            "user_id": intent.context.user_id,
            "user_tier": intent.context.user_tier,
            "organization_id": intent.context.organization_id,
        }
        
        # Add budget constraints if present
        if intent.budget:
            if intent.budget.max_cost_usd:
                context["max_cost_usd"] = intent.budget.max_cost_usd
            if intent.budget.max_time:
                context["max_time_seconds"] = int(intent.budget.max_time.total_seconds())
        
        # Add graph metrics if present
        if graph:
            context["graph_id"] = graph.graph_id
            context["node_count"] = len(graph.nodes)
            context["estimated_cost_usd"] = graph.total_estimated_cost
            context["estimated_duration_seconds"] = graph.total_estimated_duration_seconds
            
            # Count node types
            node_type_counts = {}
            for node in graph.nodes.values():
                node_type = node.node_type.value
                node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
            context["node_type_counts"] = node_type_counts
        
        return context
    
    def _rule_applies(
        self,
        rule: PolicyRule,
        intent: IntentObject,
        graph: Optional[ExecutionGraph]
    ) -> bool:
        """Check if rule applies to this intent/graph based on scope"""
        if rule.scope == PolicyScope.INTENT:
            return True
        elif rule.scope == PolicyScope.GRAPH:
            return graph is not None
        elif rule.scope == PolicyScope.ORGANIZATION:
            return True
        elif rule.scope == PolicyScope.USER:
            return True
        else:
            return True
    
    def get_rules_by_priority(self, priority: PolicyPriority) -> List[PolicyRule]:
        """Get all rules of a specific priority"""
        return [r for r in self.rules if r.priority == priority]
    
    def get_enabled_rules(self) -> List[PolicyRule]:
        """Get all enabled rules"""
        return [r for r in self.rules if r.enabled]
    
    def clear_rules(self):
        """Remove all rules"""
        self.rules = []

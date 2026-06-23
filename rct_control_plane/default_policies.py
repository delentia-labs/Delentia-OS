"""
Default Policy Library

Pre-configured policies for common governance scenarios:
1. Cost Cap Policy
2. Risk Escalation Policy
3. Time Limit Policy
4. Resource Quota Policy
5. Certification Gate Policy
6. Data Sensitivity Policy
7. Compliance Check Policy
8. Approval Workflow Policy
"""

from decimal import Decimal
from .policy_language import (
    PolicyRule,
    PolicyCondition,
    PolicyAction,
    PolicyPriority,
    PolicyScope,
    ConditionOperator
)
from .intent_schema import IntentType, RiskProfile


def create_cost_cap_policy(max_cost_usd: Decimal = Decimal("500.00")) -> PolicyRule:
    """
    Cost Cap Policy: Reject executions exceeding cost limit.
    
    Args:
        max_cost_usd: Maximum allowed cost in USD
        
    Returns:
        PolicyRule that rejects high-cost executions
    """
    return PolicyRule(
        name="Cost Cap Policy",
        description=f"Reject executions exceeding ${max_cost_usd}",
        scope=PolicyScope.GRAPH,
        priority=PolicyPriority.HIGH,
        conditions=[
            PolicyCondition(
                field="estimated_cost_usd",
                operator=ConditionOperator.GREATER_THAN,
                value=max_cost_usd,
                description=f"Estimated cost > ${max_cost_usd}"
            )
        ],
        action=PolicyAction.REJECT,
        action_metadata={
            "max_cost_usd": str(max_cost_usd),
            "reason": "Cost limit exceeded"
        }
    )


def create_risk_escalation_policy() -> PolicyRule:
    """
    Risk Escalation Policy: Escalate SYSTEMIC risk operations.
    
    Returns:
        PolicyRule that escalates high-risk operations
    """
    return PolicyRule(
        name="Risk Escalation Policy",
        description="Escalate SYSTEMIC risk operations to security team",
        scope=PolicyScope.INTENT,
        priority=PolicyPriority.CRITICAL,
        conditions=[
            PolicyCondition(
                field="risk_profile",
                operator=ConditionOperator.EQUALS,
                value=RiskProfile.SYSTEMIC,
                description="Risk profile is SYSTEMIC"
            )
        ],
        action=PolicyAction.ESCALATE,
        action_metadata={
            "escalate_to": "security_team",
            "escalation_reason": "SYSTEMIC risk requires security review"
        }
    )


def create_time_limit_policy(max_hours: int = 2) -> PolicyRule:
    """
    Time Limit Policy: Require approval for long-running operations.
    
    Args:
        max_hours: Maximum execution time in hours
        
    Returns:
        PolicyRule requiring approval for long operations
    """
    max_seconds = max_hours * 3600
    
    return PolicyRule(
        name="Time Limit Policy",
        description=f"Require approval for operations exceeding {max_hours} hours",
        scope=PolicyScope.GRAPH,
        priority=PolicyPriority.MEDIUM,
        conditions=[
            PolicyCondition(
                field="estimated_duration_seconds",
                operator=ConditionOperator.GREATER_OR_EQUAL,
                value=max_seconds,
                description=f"Duration >= {max_hours} hours"
            )
        ],
        action=PolicyAction.REQUIRE_APPROVAL,
        action_metadata={
            "max_hours": max_hours,
            "approval_type": "time_limit"
        }
    )


def create_resource_quota_policy(max_memory_gb: float = 16.0, max_cpu_cores: int = 8) -> PolicyRule:
    """
    Resource Quota Policy: Notify when resource usage is high.
    
    Args:
        max_memory_gb: Maximum memory in GB
        max_cpu_cores: Maximum CPU cores
        
    Returns:
        PolicyRule that notifies on high resource usage
    """
    return PolicyRule(
        name="Resource Quota Policy",
        description=f"Notify when resources exceed {max_cpu_cores} cores or {max_memory_gb}GB memory",
        scope=PolicyScope.GRAPH,
        priority=PolicyPriority.MEDIUM,
        conditions=[
            # This would need graph-level resource aggregation
            # For now, just a placeholder condition
            PolicyCondition(
                field="node_count",
                operator=ConditionOperator.GREATER_THAN,
                value=100,  # Proxy for resource usage
                description="High node count indicates resource-intensive operation"
            )
        ],
        action=PolicyAction.NOTIFY,
        action_metadata={
            "max_memory_gb": max_memory_gb,
            "max_cpu_cores": max_cpu_cores,
            "notification_channel": "ops_team"
        }
    )


def create_certification_gate_policy() -> PolicyRule:
    """
    Certification Gate Policy: Require approval for deployment operations.
    
    Returns:
        PolicyRule requiring approval for deployments
    """
    return PolicyRule(
        name="Certification Gate Policy",
        description="Require approval for deployment operations",
        scope=PolicyScope.INTENT,
        priority=PolicyPriority.HIGH,
        conditions=[
            PolicyCondition(
                field="intent_type",
                operator=ConditionOperator.EQUALS,
                value=IntentType.DEPLOY,
                description="Intent type is DEPLOY"
            )
        ],
        action=PolicyAction.REQUIRE_APPROVAL,
        action_metadata={
            "approval_type": "deployment_certification",
            "required_approvers": ["devops_lead", "security_lead"]
        }
    )


def create_data_sensitivity_policy() -> PolicyRule:
    """
    Data Sensitivity Policy: Log operations on sensitive data.
    
    Returns:
        PolicyRule that logs sensitive data operations
    """
    return PolicyRule(
        name="Data Sensitivity Policy",
        description="Log all operations involving sensitive data access",
        scope=PolicyScope.INTENT,
        priority=PolicyPriority.MEDIUM,
        conditions=[
            # This assumes metadata includes data_sensitivity flag
            PolicyCondition(
                field="scope_type",
                operator=ConditionOperator.IN,
                value=["REPOSITORY", "SYSTEM", "INFRASTRUCTURE"],
                description="Broad scope operations"
            )
        ],
        action=PolicyAction.LOG,
        action_metadata={
            "log_level": "INFO",
            "audit_trail": True,
            "retention_days": 365
        }
    )


def create_compliance_check_policy() -> PolicyRule:
    """
    Compliance Check Policy: Reject operations violating compliance requirements.
    
    Returns:
        PolicyRule enforcing compliance
    """
    return PolicyRule(
        name="Compliance Check Policy",
        description="Enforce compliance requirements for regulated operations",
        scope=PolicyScope.INTENT,
        priority=PolicyPriority.CRITICAL,
        conditions=[
            # Example: Check if user tier allows this operation
            PolicyCondition(
                field="user_tier",
                operator=ConditionOperator.EQUALS,
                value="FREE",
                description="Free tier user"
            ),
            PolicyCondition(
                field="intent_type",
                operator=ConditionOperator.IN,
                value=[IntentType.DEPLOY, IntentType.BUILD_APP],
                description="Premium operations"
            )
        ],
        action=PolicyAction.REJECT,
        action_metadata={
            "reason": "Operation requires paid subscription",
            "upgrade_link": "https://example.com/upgrade"
        }
    )


def create_approval_workflow_policy(cost_threshold: Decimal = Decimal("100.00")) -> PolicyRule:
    """
    Approval Workflow Policy: Require approval for operations above cost threshold.
    
    Args:
        cost_threshold: Cost threshold requiring approval
        
    Returns:
        PolicyRule requiring approval for expensive operations
    """
    return PolicyRule(
        name="Approval Workflow Policy",
        description=f"Require approval for operations costing more than ${cost_threshold}",
        scope=PolicyScope.GRAPH,
        priority=PolicyPriority.HIGH,
        conditions=[
            PolicyCondition(
                field="estimated_cost_usd",
                operator=ConditionOperator.GREATER_THAN,
                value=cost_threshold,
                description=f"Cost > ${cost_threshold}"
            )
        ],
        action=PolicyAction.REQUIRE_APPROVAL,
        action_metadata={
            "cost_threshold": str(cost_threshold),
            "approval_type": "cost_approval",
            "approver_role": "manager"
        }
    )


def get_default_policies() -> list:
    """
    Get all default policies.
    
    Returns:
        List of PolicyRule instances with default configurations
    """
    return [
        create_cost_cap_policy(max_cost_usd=Decimal("500.00")),
        create_risk_escalation_policy(),
        create_time_limit_policy(max_hours=2),
        create_resource_quota_policy(max_memory_gb=16.0, max_cpu_cores=8),
        create_certification_gate_policy(),
        create_data_sensitivity_policy(),
        create_compliance_check_policy(),
        create_approval_workflow_policy(cost_threshold=Decimal("100.00"))
    ]


def create_custom_policy(
    name: str,
    description: str,
    conditions: list,
    action: PolicyAction,
    priority: PolicyPriority = PolicyPriority.MEDIUM,
    scope: PolicyScope = PolicyScope.INTENT
) -> PolicyRule:
    """
    Create a custom policy rule.
    
    Args:
        name: Policy name
        description: Policy description
        conditions: List of PolicyCondition instances
        action: Action to take when conditions are met
        priority: Policy priority
        scope: Policy scope
        
    Returns:
        PolicyRule instance
    """
    return PolicyRule(
        name=name,
        description=description,
        scope=scope,
        priority=priority,
        conditions=conditions,
        action=action
    )

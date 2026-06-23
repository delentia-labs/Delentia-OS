"""
Intent Schema Definition - Formal Grammar for RCT Control Plane

This module defines the formal structure of intents, constraints, and contexts
that the Control Plane uses to compile natural language into executable graphs.

Key Components:
- IntentType: Classification of intent categories
- IntentObject: Structured representation of compiled intent
- IntentConstraint: Limits and requirements (cost, time, quality)
- ScopeObject: What resources/code the intent operates on
- ContextBundle: Execution context (user, tier, metadata)
- BudgetSpec: Financial and resource limits
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator


# ============================================================================
# ENUMS: Intent Classification
# ============================================================================

class IntentType(str, Enum):
    """Types of intents that Control Plane can process"""
    REFACTOR = "REFACTOR"                   # Code refactoring
    BUILD_APP = "BUILD_APP"                 # Application scaffolding
    ANALYZE_RISK = "ANALYZE_RISK"           # Risk assessment
    DEPLOY = "DEPLOY"                       # Deployment operations
    OPTIMIZE = "OPTIMIZE"                   # Performance optimization
    DOCUMENT = "DOCUMENT"                   # Documentation generation
    STRATEGY = "STRATEGY"                   # Strategic planning
    TRANSFORM = "TRANSFORM"                 # Data/code transformation
    DEBUG = "DEBUG"                         # Debugging assistance
    TEST = "TEST"                           # Test generation/execution


class IntentPriority(str, Enum):
    """Priority levels for intent execution"""
    LOW = "LOW"                             # Background tasks
    MEDIUM = "MEDIUM"                       # Normal operations
    HIGH = "HIGH"                           # Important work
    CRITICAL = "CRITICAL"                   # Urgent, business-critical


class RiskProfile(str, Enum):
    """Risk classification for operations"""
    LOW = "LOW"                             # Safe operations (read-only, analysis)
    STRUCTURAL = "STRUCTURAL"               # Code modifications, refactoring
    SYSTEMIC = "SYSTEMIC"                   # Infrastructure changes, deployment


class ScopeType(str, Enum):
    """What the intent operates on"""
    FILE = "FILE"                           # Single file
    MODULE = "MODULE"                       # Python/JS module
    PACKAGE = "PACKAGE"                     # Entire package
    REPOSITORY = "REPOSITORY"               # Full repository
    SYSTEM = "SYSTEM"                       # System-wide changes
    INFRASTRUCTURE = "INFRASTRUCTURE"       # Infra/deployment


class ConstraintType(str, Enum):
    """Types of constraints that can be applied"""
    COST = "COST"                           # Budget limits
    TIME = "TIME"                           # Time limits
    QUALITY = "QUALITY"                     # Quality requirements
    SECURITY = "SECURITY"                   # Security requirements
    COMPLIANCE = "COMPLIANCE"               # Regulatory compliance
    RESOURCE = "RESOURCE"                   # CPU/memory/GPU limits


# ============================================================================
# DATA MODELS: Pydantic Models for Validation
# ============================================================================

class ScopeObject(BaseModel):
    """Defines what resources/code the intent operates on"""
    scope_type: ScopeType
    target: str                             # Path, URL, identifier
    includes: List[str] = Field(default_factory=list)  # Include patterns
    excludes: List[str] = Field(default_factory=list)  # Exclude patterns
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class BudgetSpec(BaseModel):
    """Financial and resource budget specifications"""
    max_cost_usd: Optional[Decimal] = None
    max_time: Optional[timedelta] = None
    max_cpu_hours: Optional[float] = None
    max_memory_gb: Optional[float] = None
    max_tokens: Optional[int] = None
    max_api_calls: Optional[int] = None

    @validator('max_cost_usd', pre=True)
    def validate_cost(cls, v):
        if v is not None and v < 0:
            raise ValueError("max_cost_usd must be non-negative")
        return v

    @validator('max_time', pre=True)
    def validate_time(cls, v):
        if v is not None and isinstance(v, (int, float)):
            return timedelta(seconds=v)
        return v

    class Config:
        json_encoders = {
            Decimal: str,
            timedelta: lambda v: v.total_seconds()
        }


class IntentConstraint(BaseModel):
    """Individual constraint on intent execution"""
    constraint_type: ConstraintType
    value: Any                              # Constraint value (depends on type)
    operator: str = "LTE"                   # LTE, GTE, EQ, NEQ
    strict: bool = True                     # Strict enforcement vs. warning
    reason: Optional[str] = None            # Why this constraint exists

    class Config:
        use_enum_values = True


class ContextBundle(BaseModel):
    """Execution context for intent"""
    user_id: str
    user_tier: str                          # FREE, PRO, ENTERPRISE, INTERNAL
    organization_id: Optional[str] = None
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class IntentObject(BaseModel):
    """
    Structured representation of compiled intent.
    
    This is the output of IntentCompiler and input to ExecutionGraph builder.
    All intents must be converted to this structured form before execution.
    """
    id: UUID = Field(default_factory=uuid4)
    goal: str                               # High-level goal description
    intent_type: IntentType
    scope: ScopeObject
    constraints: List[IntentConstraint] = Field(default_factory=list)
    context: ContextBundle
    priority: IntentPriority = IntentPriority.MEDIUM
    risk_profile: RiskProfile = RiskProfile.LOW
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    
    # Template matching (populated by IntentCompiler)
    matched_template: Optional[str] = None
    template_confidence: float = 0.0        # 0.0 to 1.0
    
    # Metadata
    natural_language_input: Optional[str] = None  # Original NL input
    compiled_at: datetime = Field(default_factory=datetime.utcnow)
    compiler_version: str = "1.0.0"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator('template_confidence')
    def validate_confidence(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("template_confidence must be between 0.0 and 1.0")
        return v

    @validator('goal')
    def validate_goal(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("goal cannot be empty")
        if len(v) > 500:
            raise ValueError("goal too long (max 500 characters)")
        return v.strip()

    class Config:
        use_enum_values = True
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat(),
            Decimal: str,
            timedelta: lambda v: v.total_seconds()
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return self.dict()

    def add_constraint(
        self,
        constraint_type: ConstraintType,
        value: Any,
        operator: str = "LTE",
        strict: bool = True,
        reason: Optional[str] = None
    ) -> None:
        """Add a new constraint to the intent"""
        constraint = IntentConstraint(
            constraint_type=constraint_type,
            value=value,
            operator=operator,
            strict=strict,
            reason=reason
        )
        self.constraints.append(constraint)

    def get_constraints_by_type(self, constraint_type: ConstraintType) -> List[IntentConstraint]:
        """Get all constraints of a specific type"""
        return [c for c in self.constraints if c.constraint_type == constraint_type]

    def has_constraint(self, constraint_type: ConstraintType) -> bool:
        """Check if intent has constraint of given type"""
        return any(c.constraint_type == constraint_type for c in self.constraints)

    def estimate_complexity(self) -> float:
        """
        Estimate intent complexity (0.0 to 1.0).
        Used for model selection and cost estimation.
        """
        complexity = 0.0
        
        # Base complexity from intent type
        complexity_map = {
            IntentType.DOCUMENT: 0.2,
            IntentType.ANALYZE_RISK: 0.4,
            IntentType.OPTIMIZE: 0.6,
            IntentType.REFACTOR: 0.7,
            IntentType.TRANSFORM: 0.7,
            IntentType.BUILD_APP: 0.8,
            IntentType.DEPLOY: 0.8,
            IntentType.STRATEGY: 0.9,
        }
        complexity += complexity_map.get(self.intent_type, 0.5)
        
        # Adjust for scope
        if self.scope.scope_type == ScopeType.SYSTEM:
            complexity *= 1.3
        elif self.scope.scope_type == ScopeType.REPOSITORY:
            complexity *= 1.2
        
        # Adjust for risk
        if self.risk_profile == RiskProfile.SYSTEMIC:
            complexity *= 1.2
        
        # Normalize to 0.0-1.0
        return min(complexity, 1.0)


# ============================================================================
# VALIDATION RESULT
# ============================================================================

@dataclass
class ValidationResult:
    """Result of intent validation"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add validation error"""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add validation warning"""
        self.warnings.append(message)

    def add_suggestion(self, message: str) -> None:
        """Add improvement suggestion"""
        self.suggestions.append(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
        }


# ============================================================================
# INTENT GRAMMAR VALIDATOR
# ============================================================================

class IntentGrammar:
    """
    Formal grammar validator for intents.
    Ensures intents conform to RCT Control Plane standards.
    """
    
    REQUIRED_FIELDS = ["goal", "intent_type", "scope", "context"]
    
    @staticmethod
    def validate(intent: IntentObject) -> ValidationResult:
        """Validate intent against formal grammar"""
        result = ValidationResult(is_valid=True)
        
        # Required fields validation
        if not intent.goal:
            result.add_error("Intent must have a goal")
        
        if not intent.scope:
            result.add_error("Intent must have a scope")
        
        if not intent.context:
            result.add_error("Intent must have execution context")
        
        # Constraint validation
        cost_constraints = intent.get_constraints_by_type(ConstraintType.COST)
        if len(cost_constraints) > 1:
            result.add_warning("Multiple cost constraints detected, using most restrictive")
        
        # Budget validation
        if intent.budget.max_cost_usd and intent.budget.max_cost_usd <= 0:
            result.add_error("Budget max_cost_usd must be positive")
        
        # Complexity check
        complexity = intent.estimate_complexity()
        if complexity > 0.8 and intent.budget.max_cost_usd and intent.budget.max_cost_usd < Decimal("1.00"):
            result.add_warning(
                f"High complexity intent ({complexity:.2f}) with low budget "
                f"(${intent.budget.max_cost_usd}). Consider increasing budget."
            )
        
        # Risk vs Priority check
        if intent.risk_profile == RiskProfile.SYSTEMIC and intent.priority != IntentPriority.CRITICAL:
            result.add_suggestion(
                "Systemic risk operations should typically have CRITICAL priority"
            )
        
        return result


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "IntentType",
    "IntentPriority",
    "RiskProfile",
    "ScopeType",
    "ConstraintType",
    
    # Models
    "IntentObject",
    "ScopeObject",
    "BudgetSpec",
    "IntentConstraint",
    "ContextBundle",
    
    # Validation
    "IntentGrammar",
    "ValidationResult",
]

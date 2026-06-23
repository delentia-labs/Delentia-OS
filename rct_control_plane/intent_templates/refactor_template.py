"""
Refactor Template - Code Refactoring Execution Plan

Transforms refactoring intents into structured execution plans.

Refactoring Phases:
1. Analysis: Understand current structure
2. Planning: Design target architecture
3. Simulation: Preview changes
4. Transformation: Apply refactoring
5. Validation: Ensure correctness

Example:
    >>> template = RefactorTemplate()
    >>> plan = template.to_plan(intent)
    >>> assert plan.phases == ["analyze", "plan", "simulate", "transform", "validate"]
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..intent_schema import IntentObject, IntentType, RiskProfile, ScopeType


@dataclass
class RefactoringPhase:
    """Individual phase in refactoring execution"""
    name: str
    description: str
    agent_capability: str
    estimated_cost: Decimal
    estimated_duration_seconds: int
    required_inputs: List[str] = field(default_factory=list)
    produces_outputs: List[str] = field(default_factory=list)
    can_skip: bool = False


@dataclass
class RefactoringPlan:
    """Complete refactoring execution plan"""
    intent_id: str
    phases: List[RefactoringPhase]
    total_estimated_cost: Decimal
    total_estimated_duration_seconds: int
    risk_level: RiskProfile
    requires_approval: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class RefactorTemplate:
    """
    Template for code refactoring intents.
    
    Supports:
    - Architectural refactoring (monolith → microservices, etc.)
    - Pattern application (clean architecture, SOLID principles)
    - Code quality improvements (DRY, naming conventions)
    - Dependency management (reduce coupling, improve cohesion)
    """
    
    COST_PER_PHASE = {
        "analyze": Decimal("0.15"),
        "plan": Decimal("0.25"),
        "simulate": Decimal("0.20"),
        "transform": Decimal("0.50"),
        "validate": Decimal("0.15"),
    }
    
    DURATION_PER_PHASE_SECONDS = {
        "analyze": 30,
        "plan": 45,
        "simulate": 30,
        "transform": 120,
        "validate": 45,
    }
    
    def match(self, intent: IntentObject) -> float:
        """
        Calculate match confidence (0.0 to 1.0).
        
        Returns high confidence if:
        - Intent type is REFACTOR
        - Keywords indicate refactoring goals
        - Scope is appropriate (file, module, or repository)
        """
        confidence = 0.0
        
        # Intent type match
        if intent.intent_type == IntentType.REFACTOR:
            confidence += 0.6
        
        # Scope match
        if intent.scope.scope_type in [ScopeType.FILE, ScopeType.MODULE, ScopeType.PACKAGE, ScopeType.REPOSITORY]:
            confidence += 0.2
        
        # Keyword match
        refactor_keywords = ["refactor", "clean", "architecture", "pattern", "solid", "dry"]
        goal_lower = intent.goal.lower()
        matching_keywords = sum(1 for kw in refactor_keywords if kw in goal_lower)
        confidence += min(matching_keywords * 0.05, 0.2)
        
        return min(confidence, 1.0)
    
    def to_plan(self, intent: IntentObject) -> RefactoringPlan:
        """
        Convert IntentObject to RefactoringPlan.
        
        Creates a multi-phase execution plan with:
        - Cost estimation per phase
        - Duration estimation per phase
        - Required capabilities per phase
        - Input/output dependencies
        """
        phases = []
        
        # Phase 1: Analyze current structure
        phases.append(RefactoringPhase(
            name="analyze",
            description="Analyze current code structure and identify refactoring opportunities",
            agent_capability="code_analysis",
            estimated_cost=self._scale_cost("analyze", intent),
            estimated_duration_seconds=self._scale_duration("analyze", intent),
            required_inputs=["source_code", "dependencies"],
            produces_outputs=["dependency_graph", "code_metrics", "refactoring_opportunities"],
            can_skip=False
        ))
        
        # Phase 2: Plan refactoring
        phases.append(RefactoringPhase(
            name="plan",
            description="Design target architecture and refactoring strategy",
            agent_capability="architectural_design",
            estimated_cost=self._scale_cost("plan", intent),
            estimated_duration_seconds=self._scale_duration("plan", intent),
            required_inputs=["dependency_graph", "code_metrics"],
            produces_outputs=["refactoring_plan", "target_architecture", "risk_assessment"],
            can_skip=False
        ))
        
        # Phase 3: Simulate changes (optional for low-risk)
        if intent.risk_profile != RiskProfile.LOW:
            phases.append(RefactoringPhase(
                name="simulate",
                description="Simulate refactoring changes and preview impact",
                agent_capability="code_simulation",
                estimated_cost=self._scale_cost("simulate", intent),
                estimated_duration_seconds=self._scale_duration("simulate", intent),
                required_inputs=["refactoring_plan", "source_code"],
                produces_outputs=["simulated_changes", "impact_report"],
                can_skip=True
            ))
        
        # Phase 4: Transform code
        phases.append(RefactoringPhase(
            name="transform",
            description="Apply refactoring transformations to code",
            agent_capability="code_transformation",
            estimated_cost=self._scale_cost("transform", intent),
            estimated_duration_seconds=self._scale_duration("transform", intent),
            required_inputs=["refactoring_plan", "source_code"],
            produces_outputs=["refactored_code", "change_summary"],
            can_skip=False
        ))
        
        # Phase 5: Validate results
        phases.append(RefactoringPhase(
            name="validate",
            description="Validate refactored code (tests, linting, type checking)",
            agent_capability="code_validation",
            estimated_cost=self._scale_cost("validate", intent),
            estimated_duration_seconds=self._scale_duration("validate", intent),
            required_inputs=["refactored_code", "test_suite"],
            produces_outputs=["validation_report", "test_results"],
            can_skip=False
        ))
        
        # Calculate totals
        total_cost = sum(p.estimated_cost for p in phases)
        total_duration = sum(p.estimated_duration_seconds for p in phases)
        
        # Check if approval required
        requires_approval = (
            intent.risk_profile == RiskProfile.SYSTEMIC or
            total_cost > Decimal("2.00")
        )
        
        return RefactoringPlan(
            intent_id=str(intent.id),
            phases=phases,
            total_estimated_cost=total_cost,
            total_estimated_duration_seconds=total_duration,
            risk_level=intent.risk_profile,
            requires_approval=requires_approval,
            metadata={
                "intent_type": intent.intent_type if isinstance(intent.intent_type, str) else intent.intent_type.value,
                "scope_type": intent.scope.scope_type if isinstance(intent.scope.scope_type, str) else intent.scope.scope_type.value,
                "target": intent.scope.target,
            }
        )
    
    def _scale_cost(self, phase_name: str, intent: IntentObject) -> Decimal:
        """Scale phase cost based on scope and complexity"""
        base_cost = self.COST_PER_PHASE[phase_name]
        
        # Scale by scope
        scope_multipliers = {
            ScopeType.FILE: Decimal("1.0"),
            ScopeType.MODULE: Decimal("1.5"),
            ScopeType.PACKAGE: Decimal("2.0"),
            ScopeType.REPOSITORY: Decimal("3.0"),
            ScopeType.SYSTEM: Decimal("5.0"),
        }
        multiplier = scope_multipliers.get(intent.scope.scope_type, Decimal("1.0"))
        
        # Scale by complexity
        complexity = intent.estimate_complexity()
        complexity_multiplier = Decimal("1.0") + (Decimal(str(complexity)) * Decimal("0.5"))
        
        return base_cost * multiplier * complexity_multiplier
    
    def _scale_duration(self, phase_name: str, intent: IntentObject) -> int:
        """Scale phase duration based on scope and complexity"""
        base_duration = self.DURATION_PER_PHASE_SECONDS[phase_name]
        
        # Scale by scope
        scope_multipliers = {
            ScopeType.FILE: 1.0,
            ScopeType.MODULE: 1.5,
            ScopeType.PACKAGE: 2.0,
            ScopeType.REPOSITORY: 3.0,
            ScopeType.SYSTEM: 5.0,
        }
        multiplier = scope_multipliers.get(intent.scope.scope_type, 1.0)
        
        # Scale by complexity
        complexity = intent.estimate_complexity()
        complexity_multiplier = 1.0 + (complexity * 0.5)
        
        return int(base_duration * multiplier * complexity_multiplier)
    
    def to_dsl(self, plan: RefactoringPlan) -> str:
        """
        Convert RefactoringPlan to Execution DSL.
        
        Generates declarative DSL representation of the refactoring workflow.
        """
        lines = [
            f'intent "refactor_{plan.intent_id[:8]}" {{',
            f'  risk_level = "{plan.risk_level.value}"',
            f'  estimated_cost = {plan.total_estimated_cost}',
            f'  estimated_duration = {plan.total_estimated_duration_seconds}',
            '',
        ]
        
        for i, phase in enumerate(plan.phases):
            lines.extend([
                f'  phase {phase.name} {{',
                f'    node {phase.name.capitalize()}Node {{',
                f'      agent_capability = "{phase.agent_capability}"',
                f'      cost = {phase.estimated_cost}',
                f'      timeout = {phase.estimated_duration_seconds}s',
            ])
            
            if phase.required_inputs:
                lines.append(f'      requires = {phase.required_inputs}')
            
            if phase.produces_outputs:
                lines.append(f'      produces = {phase.produces_outputs}')
            
            if i > 0:
                prev_phase = plan.phases[i - 1]
                lines.append(f'      depends_on = [{prev_phase.name.capitalize()}Node]')
            
            lines.extend([
                '    }',
                '  }',
                '',
            ])
        
        lines.append('}')
        return '\n'.join(lines)
    
    def estimate_cost(self, intent: IntentObject) -> Decimal:
        """Quick cost estimation without full planning"""
        plan = self.to_plan(intent)
        return plan.total_estimated_cost
    
    def estimate_duration(self, intent: IntentObject) -> int:
        """Quick duration estimation without full planning (in seconds)"""
        plan = self.to_plan(intent)
        return plan.total_estimated_duration_seconds


__all__ = ["RefactorTemplate", "RefactoringPlan", "RefactoringPhase"]

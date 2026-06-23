"""
Build App Template - Application Scaffolding Execution Plan

Transforms app building intents into structured scaffolding plans.

App Building Phases:
1. Requirements: Extract functional/non-functional requirements
2. Architecture: Design system architecture
3. Scaffolding: Generate project structure
4. Implementation: Generate core components
5. Configuration: Setup tooling (tests, CI/CD, docs)

Example:
    >>> template = BuildAppTemplate()
    >>> plan = template.to_plan(intent)
    >>> assert len(plan.phases) >= 4
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..intent_schema import IntentObject, IntentType, RiskProfile, ScopeType


@dataclass
class BuildPhase:
    """Individual phase in app building"""
    name: str
    description: str
    agent_capability: str
    estimated_cost: Decimal
    estimated_duration_seconds: int
    required_inputs: List[str] = field(default_factory=list)
    produces_outputs: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)


@dataclass
class BuildPlan:
    """Complete app building execution plan"""
    intent_id: str
    app_type: str                           # "web", "api", "cli", "mobile", etc.
    tech_stack: List[str]                   # ["python", "fastapi", "postgresql"]
    phases: List[BuildPhase]
    total_estimated_cost: Decimal
    total_estimated_duration_seconds: int
    artifacts: List[str]                    # Files/directories to be created
    metadata: Dict[str, Any] = field(default_factory=dict)


class BuildAppTemplate:
    """
    Template for application building/scaffolding intents.
    
    Supports:
    - Web applications (React, Vue, Next.js)
    - APIs (FastAPI, Express, Django)
    - CLI tools
    - Microservices
    - Mobile apps (basic structure)
    """
    
    APP_TYPE_KEYWORDS = {
        "web": ["web app", "website", "frontend", "ui", "dashboard"],
        "api": ["api", "backend", "service", "endpoint", "rest", "graphql"],
        "cli": ["cli", "command line", "tool", "script"],
        "microservice": ["microservice", "service", "microservices architecture"],
        "mobile": ["mobile app", "mobile", "ios", "android"],
        "fullstack": ["fullstack", "full stack", "complete app"],
    }
    
    TECH_STACK_KEYWORDS = {
        "python": ["python", "fastapi", "django", "flask"],
        "javascript": ["javascript", "node", "express", "react", "vue", "next"],
        "typescript": ["typescript", "ts"],
        "go": ["go", "golang"],
        "rust": ["rust"],
        "java": ["java", "spring"],
    }
    
    COST_PER_PHASE = {
        "requirements": Decimal("0.10"),
        "architecture": Decimal("0.30"),
        "scaffolding": Decimal("0.20"),
        "implementation": Decimal("0.80"),
        "configuration": Decimal("0.15"),
    }
    
    DURATION_PER_PHASE_SECONDS = {
        "requirements": 20,
        "architecture": 45,
        "scaffolding": 30,
        "implementation": 180,
        "configuration": 25,
    }
    
    def match(self, intent: IntentObject) -> float:
        """Calculate match confidence (0.0 to 1.0)"""
        confidence = 0.0
        
        # Intent type match
        if intent.intent_type == IntentType.BUILD_APP:
            confidence += 0.7
        
        # Keywords match
        build_keywords = ["build", "create", "scaffold", "generate", "new app"]
        goal_lower = intent.goal.lower()
        matching_keywords = sum(1 for kw in build_keywords if kw in goal_lower)
        confidence += min(matching_keywords * 0.1, 0.3)
        
        return min(confidence, 1.0)
    
    def to_plan(self, intent: IntentObject) -> BuildPlan:
        """Convert IntentObject to BuildPlan"""
        phases = []
        
        # Detect app type
        app_type = self._detect_app_type(intent)
        
        # Detect tech stack
        tech_stack = self._detect_tech_stack(intent)
        
        # Phase 1: Requirements Extraction
        phases.append(BuildPhase(
            name="requirements",
            description="Extract and document functional and non-functional requirements",
            agent_capability="requirements_analysis",
            estimated_cost=self._scale_cost("requirements", intent),
            estimated_duration_seconds=self._scale_duration("requirements", intent),
            required_inputs=["intent_description"],
            produces_outputs=["requirements_spec", "user_stories"],
            artifacts=["REQUIREMENTS.md"]
        ))
        
        # Phase 2: Architecture Design
        phases.append(BuildPhase(
            name="architecture",
            description="Design system architecture and tech stack",
            agent_capability="system_design",
            estimated_cost=self._scale_cost("architecture", intent),
            estimated_duration_seconds=self._scale_duration("architecture", intent),
            required_inputs=["requirements_spec"],
            produces_outputs=["architecture_diagram", "component_specs", "data_models"],
            artifacts=["ARCHITECTURE.md", "docs/architecture/"]
        ))
        
        # Phase 3: Project Scaffolding
        phases.append(BuildPhase(
            name="scaffolding",
            description="Generate project structure and boilerplate",
            agent_capability="code_generation",
            estimated_cost=self._scale_cost("scaffolding", intent),
            estimated_duration_seconds=self._scale_duration("scaffolding", intent),
            required_inputs=["architecture_diagram", "tech_stack"],
            produces_outputs=["project_structure", "config_files"],
            artifacts=self._get_scaffolding_artifacts(app_type, tech_stack)
        ))
        
        # Phase 4: Core Implementation
        phases.append(BuildPhase(
            name="implementation",
            description="Implement core application logic and components",
            agent_capability="code_implementation",
            estimated_cost=self._scale_cost("implementation", intent),
            estimated_duration_seconds=self._scale_duration("implementation", intent),
            required_inputs=["component_specs", "data_models", "project_structure"],
            produces_outputs=["source_code", "api_endpoints", "business_logic"],
            artifacts=self._get_implementation_artifacts(app_type, tech_stack)
        ))
        
        # Phase 5: Configuration & Tooling
        phases.append(BuildPhase(
            name="configuration",
            description="Setup testing, CI/CD, documentation, and deployment config",
            agent_capability="devops_setup",
            estimated_cost=self._scale_cost("configuration", intent),
            estimated_duration_seconds=self._scale_duration("configuration", intent),
            required_inputs=["source_code", "project_structure"],
            produces_outputs=["test_suite", "ci_config", "deployment_config"],
            artifacts=[
                "tests/",
                ".github/workflows/ci.yml",
                "Dockerfile",
                "docker-compose.yml",
                "README.md"
            ]
        ))
        
        # Calculate totals
        total_cost = sum(p.estimated_cost for p in phases)
        total_duration = sum(p.estimated_duration_seconds for p in phases)
        
        # Collect all artifacts
        all_artifacts = []
        for phase in phases:
            all_artifacts.extend(phase.artifacts)
        
        return BuildPlan(
            intent_id=str(intent.id),
            app_type=app_type,
            tech_stack=tech_stack,
            phases=phases,
            total_estimated_cost=total_cost,
            total_estimated_duration_seconds=total_duration,
            artifacts=all_artifacts,
            metadata={
                "intent_type": intent.intent_type if isinstance(intent.intent_type, str) else intent.intent_type.value,
                "complexity": intent.estimate_complexity(),
            }
        )
    
    def _detect_app_type(self, intent: IntentObject) -> str:
        """Detect application type from intent"""
        goal_lower = intent.goal.lower()
        
        # Check in priority order (most specific first)
        priority_order = ["cli", "microservice", "mobile", "api", "fullstack", "web"]
        
        for app_type in priority_order:
            keywords = self.APP_TYPE_KEYWORDS.get(app_type, [])
            if any(kw in goal_lower for kw in keywords):
                return app_type
        
        return "generic"  # Default
    
    def _detect_tech_stack(self, intent: IntentObject) -> List[str]:
        """Detect technology stack from intent"""
        goal_lower = intent.goal.lower()
        stack = []
        
        for tech, keywords in self.TECH_STACK_KEYWORDS.items():
            if any(kw in goal_lower for kw in keywords):
                stack.append(tech)
        
        # Default stack if none detected
        if not stack:
            stack = ["python", "fastapi"]  # Default to Python/FastAPI
        
        return stack
    
    def _get_scaffolding_artifacts(self, app_type: str, tech_stack: List[str]) -> List[str]:
        """Get list of files to scaffold"""
        artifacts = [
            ".gitignore",
            "README.md",
            "requirements.txt" if "python" in tech_stack else "package.json",
        ]
        
        if app_type == "api":
            artifacts.extend([
                "app/",
                "app/__init__.py",
                "app/main.py",
                "app/models.py",
                "app/schemas.py",
                "app/routes/",
            ])
        elif app_type == "web":
            artifacts.extend([
                "src/",
                "public/",
                "src/components/",
                "src/pages/",
                "src/styles/",
            ])
        elif app_type == "cli":
            artifacts.extend([
                "src/",
                "src/cli.py",
                "src/commands/",
            ])
        
        return artifacts
    
    def _get_implementation_artifacts(self, app_type: str, tech_stack: List[str]) -> List[str]:
        """Get list of implementation files"""
        if app_type == "api":
            return [
                "app/api/",
                "app/core/",
                "app/db/",
                "app/services/",
            ]
        elif app_type == "web":
            return [
                "src/components/",
                "src/hooks/",
                "src/utils/",
                "src/api/",
            ]
        elif app_type == "cli":
            return [
                "src/commands/",
                "src/utils/",
            ]
        return []
    
    def _scale_cost(self, phase_name: str, intent: IntentObject) -> Decimal:
        """Scale phase cost based on complexity and scope"""
        base_cost = self.COST_PER_PHASE[phase_name]
        
        # Scale by complexity (more aggressive)
        complexity = intent.estimate_complexity()
        complexity_multiplier = Decimal("1.0") + (Decimal(str(complexity)) * Decimal("2.0"))
        
        # Scale by scope
        scope_multipliers = {
            ScopeType.FILE: Decimal("1.0"),
            ScopeType.MODULE: Decimal("1.2"),
            ScopeType.PACKAGE: Decimal("1.5"),
            ScopeType.REPOSITORY: Decimal("2.0"),
            ScopeType.SYSTEM: Decimal("3.0"),
        }
        scope_multiplier = scope_multipliers.get(intent.scope.scope_type, Decimal("1.0"))
        
        # Implementation phase scales even more
        if phase_name == "implementation":
            complexity_multiplier *= Decimal("1.5")
        
        return base_cost * complexity_multiplier * scope_multiplier
    
    def _scale_duration(self, phase_name: str, intent: IntentObject) -> int:
        """Scale phase duration based on complexity and scope"""
        base_duration = self.DURATION_PER_PHASE_SECONDS[phase_name]
        
        # Scale by complexity (more aggressive)
        complexity = intent.estimate_complexity()
        complexity_multiplier = 1.0 + (complexity * 2.0)
        
        # Scale by scope
        scope_multipliers = {
            ScopeType.FILE: 1.0,
            ScopeType.MODULE: 1.2,
            ScopeType.PACKAGE: 1.5,
            ScopeType.REPOSITORY: 2.0,
            ScopeType.SYSTEM: 3.0,
        }
        scope_multiplier = scope_multipliers.get(intent.scope.scope_type, 1.0)
        
        # Implementation phase takes longer
        if phase_name == "implementation":
            complexity_multiplier *= 1.5
        
        return int(base_duration * complexity_multiplier * scope_multiplier)
    
    def to_dsl(self, plan: BuildPlan) -> str:
        """Convert BuildPlan to Execution DSL"""
        lines = [
            f'intent "build_app_{plan.intent_id[:8]}" {{',
            f'  app_type = "{plan.app_type}"',
            f'  tech_stack = {plan.tech_stack}',
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
                f'      produces_artifacts = {phase.artifacts}',
            ])
            
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
        """Quick cost estimation"""
        plan = self.to_plan(intent)
        return plan.total_estimated_cost
    
    def estimate_duration(self, intent: IntentObject) -> int:
        """Quick duration estimation (in seconds)"""
        plan = self.to_plan(intent)
        return plan.total_estimated_duration_seconds


__all__ = ["BuildAppTemplate", "BuildPlan", "BuildPhase"]

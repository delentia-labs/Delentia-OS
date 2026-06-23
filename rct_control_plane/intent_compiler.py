"""
Intent Compiler - Natural Language → Structured Intent

This module compiles natural language descriptions into structured IntentObject
that can be processed by the Control Plane execution graph builder.

Compilation Pipeline:
1. Lexical Analysis: Extract keywords, entities, constraints
2. Intent Classification: Determine IntentType
3. Template Matching: Match to execution template
4. Context Binding: Enrich with user/tier/metadata
5. Validation: Check against intent grammar

Example:
    >>> compiler = IntentCompiler()
    >>> result = compiler.compile(
    ...     "Refactor this module to use clean architecture patterns with max cost $2.50",
    ...     user_id="user123",
    ...     user_tier="PRO"
    ... )
    >>> assert result.intent.intent_type == IntentType.REFACTOR
    >>> assert result.intent.budget.max_cost_usd == Decimal("2.50")
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from .intent_schema import (
    BudgetSpec,
    ConstraintType,
    ContextBundle,
    IntentConstraint,
    IntentGrammar,
    IntentObject,
    IntentPriority,
    IntentType,
    RiskProfile,
    ScopeObject,
    ScopeType,
    ValidationResult,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .observability import ControlPlaneObserver


# ============================================================================
# LEXICAL TOKENS
# ============================================================================

@dataclass
class Token:
    """Lexical token extracted from natural language"""
    type: str                               # KEYWORD, ENTITY, CONSTRAINT, etc.
    value: str
    position: int
    confidence: float = 1.0


@dataclass
class LexicalResult:
    """Result of lexical analysis"""
    tokens: List[Token] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    entities: Dict[str, List[str]] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# COMPILATION RESULT
# ============================================================================

@dataclass
class CompilationResult:
    """Result of intent compilation"""
    success: bool
    intent: Optional[IntentObject] = None
    validation: Optional[ValidationResult] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    compilation_time_ms: float = 0.0
    
    def add_error(self, message: str) -> None:
        """Add compilation error"""
        self.errors.append(message)
        self.success = False

    def add_warning(self, message: str) -> None:
        """Add compilation warning"""
        self.warnings.append(message)


# ============================================================================
# INTENT COMPILER
# ============================================================================

class IntentCompiler:
    """
    Compiles natural language into structured IntentObject.
    
    This is the entry point for all Control Plane requests.
    """
    
    # Intent type keywords mapping
    INTENT_TYPE_KEYWORDS = {
        IntentType.REFACTOR: ["refactor", "restructure", "reorganize", "clean up", "improve code"],
        IntentType.BUILD_APP: ["build", "create", "scaffold", "generate app", "new application"],
        IntentType.ANALYZE_RISK: ["analyze", "assess", "evaluate risk", "security check", "audit"],
        IntentType.DEPLOY: ["deploy", "release", "ship", "publish", "launch"],
        IntentType.OPTIMIZE: ["optimize", "improve performance", "speed up", "reduce cost"],
        IntentType.DOCUMENT: ["document", "generate docs", "write documentation", "explain"],
        IntentType.STRATEGY: ["plan", "strategize", "roadmap", "design", "architect"],
        IntentType.TRANSFORM: ["transform", "convert", "migrate", "port", "translate"],
        IntentType.DEBUG: ["debug", "fix", "troubleshoot", "diagnose", "find bug"],
        IntentType.TEST: ["test", "verify", "validate", "check", "generate tests"],
    }
    
    # Risk indicators
    HIGH_RISK_KEYWORDS = ["deploy", "delete", "drop", "remove", "migrate", "system-wide"]
    MEDIUM_RISK_KEYWORDS = ["refactor", "modify", "change", "update", "transform"]
    
    # Priority indicators
    CRITICAL_PRIORITY_KEYWORDS = ["urgent", "critical", "emergency", "asap", "immediately"]
    HIGH_PRIORITY_KEYWORDS = ["important", "soon", "high priority", "quickly"]
    LOW_PRIORITY_KEYWORDS = ["whenever", "eventually", "low priority", "background"]
    
    # Scope indicators
    SCOPE_KEYWORDS = {
        ScopeType.FILE: ["this file", "current file", "file"],
        ScopeType.MODULE: ["this module", "module", "package"],
        ScopeType.REPOSITORY: ["repo", "repository", "entire codebase", "all code"],
        ScopeType.SYSTEM: ["system", "entire system", "infrastructure", "all services"],
        ScopeType.INFRASTRUCTURE: ["infra", "deployment", "kubernetes", "docker"],
    }
    
    def __init__(self, observer: Optional['ControlPlaneObserver'] = None):
        """Initialize compiler with default configuration
        
        Args:
            observer: Optional ControlPlaneObserver for event tracking
        """
        self.version = "1.0.0"
        self.compiled_count = 0
        self.observer = observer
    
    # ========================================================================
    # MAIN COMPILATION PIPELINE
    # ========================================================================
    
    def compile(
        self,
        natural_language: str,
        user_id: str,
        user_tier: str,
        organization_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CompilationResult:
        """
        Compile natural language into IntentObject.
        
        Args:
            natural_language: Natural language description of intent
            user_id: User identifier
            user_tier: User tier (FREE, PRO, ENTERPRISE, INTERNAL)
            organization_id: Optional organization ID
            metadata: Optional additional metadata
            
        Returns:
            CompilationResult with structured intent or errors
        """
        start_time = datetime.utcnow()
        result = CompilationResult(success=True)
        
        # Emit event: INTENT_RECEIVED
        if self.observer:
            from .observability import ControlPlaneEventType
            self.observer.observe_event(
                event_type=ControlPlaneEventType.INTENT_RECEIVED,
                data={"text": natural_language[:200], "user_id": user_id, "user_tier": user_tier},
                actor=user_id
            )
        
        try:
            # 1. Lexical analysis
            lexical = self.lex(natural_language)
            
            # 2. Classify intent type
            intent_type = self._classify_intent_type(lexical)
            if not intent_type:
                result.add_error("Could not determine intent type")
                result.success = False
                # Don't increment counter for failures
            else:
                # 3. Extract scope
                scope = self._extract_scope(lexical, natural_language)
                
                # 4. Extract constraints
                constraints = self._extract_constraints(lexical)
                
                # 5. Extract budget
                budget = self._extract_budget(lexical)
                
                # 6. Determine risk profile
                risk_profile = self._determine_risk_profile(intent_type, lexical)
                
                # 7. Determine priority
                priority = self._determine_priority(lexical)
                
                # 8. Build context
                context = ContextBundle(
                    user_id=user_id,
                    user_tier=user_tier,
                    organization_id=organization_id,
                    metadata=metadata or {}
                )
                
                # 9. Create IntentObject
                intent = IntentObject(
                    goal=natural_language[:500],  # Truncate to max length
                    intent_type=intent_type,
                    scope=scope,
                    constraints=constraints,
                    context=context,
                    priority=priority,
                    risk_profile=risk_profile,
                    budget=budget,
                    natural_language_input=natural_language,
                    compiler_version=self.version
                )
                
                # 10. Validate
                validation = IntentGrammar.validate(intent)
                
                # 11. Set result
                result.intent = intent
                result.validation = validation
                result.success = validation.is_valid
                result.errors.extend(validation.errors)
                result.warnings.extend(validation.warnings)
            
        except Exception as e:
            result.add_error(f"Compilation failed: {str(e)}")
        
        finally:
            end_time = datetime.utcnow()
            result.compilation_time_ms = (end_time - start_time).total_seconds() * 1000
            # Track all compilations (success or failure)
            if result.success:
                self.compiled_count += 1
            
            # Emit event: INTENT_COMPILED
            if self.observer:
                from .observability import ControlPlaneEventType
                intent_type_value = None
                if result.intent and hasattr(result.intent, 'intent_type'):
                    intent_type_value = result.intent.intent_type.value if hasattr(result.intent.intent_type, 'value') else str(result.intent.intent_type)
                self.observer.observe_event(
                    event_type=ControlPlaneEventType.INTENT_COMPILED,
                    intent_id=str(result.intent.id) if result.intent else None,
                    data={
                        "intent_type": intent_type_value,
                        "validation_valid": result.validation.is_valid if result.validation else False,
                        "errors": result.errors,
                        "warnings": result.warnings
                    },
                    duration_ms=result.compilation_time_ms,
                    success=result.success,
                    error_message="; ".join(result.errors) if result.errors else None,
                    actor=user_id
                )
        
        return result
    
    # ========================================================================
    # LEXICAL ANALYSIS
    # ========================================================================
    
    def lex(self, text: str) -> LexicalResult:
        """
        Perform lexical analysis on natural language text.
        
        Extracts:
        - Keywords (action verbs, modifiers)
        - Entities (files, modules, services)
        - Constraints (cost, time, quality)
        - Metadata (context clues)
        """
        result = LexicalResult()
        text_lower = text.lower()
        
        # Extract keywords
        result.keywords = self._extract_keywords(text_lower)
        
        # Extract entities
        result.entities = self._extract_entities(text, text_lower)
        
        # Extract constraints
        result.constraints = self._extract_constraint_values(text_lower)
        
        return result
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract action keywords from text"""
        keywords = []
        
        for intent_type, type_keywords in self.INTENT_TYPE_KEYWORDS.items():
            for keyword in type_keywords:
                if keyword in text:
                    keywords.append(keyword)
        
        # Add risk keywords
        for keyword in self.HIGH_RISK_KEYWORDS + self.MEDIUM_RISK_KEYWORDS:
            if keyword in text:
                keywords.append(keyword)
        
        # Add priority keywords
        for keyword in self.CRITICAL_PRIORITY_KEYWORDS + self.HIGH_PRIORITY_KEYWORDS + self.LOW_PRIORITY_KEYWORDS:
            if keyword in text:
                keywords.append(keyword)
        
        return keywords
    
    def _extract_entities(self, text: str, text_lower: str) -> Dict[str, List[str]]:
        """Extract named entities (files, modules, services)"""
        entities = {
            "files": [],
            "modules": [],
            "services": [],
            "paths": []
        }
        
        # File patterns: *.py, *.js, *.ts, specific filenames
        file_pattern = r'([a-z_][a-z0-9_]*\.(py|js|ts|java|cpp|go|rs|rb))'
        entities["files"] = re.findall(file_pattern, text_lower)
        
        # Path patterns
        path_pattern = r'([a-z_./][a-z0-9_./]*[a-z0-9_])'
        entities["paths"] = re.findall(path_pattern, text_lower)
        
        # Module patterns (Python/JS-style)
        if "module" in text_lower:
            # Extract quoted strings after "module"
            module_pattern = r'module[:\s]+["\']?([a-z_][a-z0-9_.]*)["\']?'
            entities["modules"] = re.findall(module_pattern, text_lower)
        
        return entities
    
    def _extract_constraint_values(self, text: str) -> Dict[str, Any]:
        """Extract constraint values from text"""
        constraints = {}
        
        # Cost constraints: $X.XX, $X, X dollars
        cost_patterns = [
            r'\$(\d+(?:\.\d{1,2})?)',           # $2.50
            r'(\d+(?:\.\d{1,2})?)\s*dollars?',  # 2.50 dollars
            r'(\d+(?:\.\d{1,2})?)\s*usd',       # 2.50 USD
        ]
        for pattern in cost_patterns:
            matches = re.findall(pattern, text)
            if matches:
                constraints["max_cost"] = Decimal(matches[0])
                break
        
        # Time constraints: X minutes, X hours, X days
        time_patterns = [
            (r'(\d+)\s*minutes?', lambda m: timedelta(minutes=int(m))),
            (r'(\d+)\s*hours?', lambda m: timedelta(hours=int(m))),
            (r'(\d+)\s*days?', lambda m: timedelta(days=int(m))),
        ]
        for pattern, converter in time_patterns:
            matches = re.findall(pattern, text)
            if matches:
                constraints["max_time"] = converter(matches[0])
                break
        
        # Token limits
        token_pattern = r'(\d+)\s*tokens?'
        token_matches = re.findall(token_pattern, text)
        if token_matches:
            constraints["max_tokens"] = int(token_matches[0])
        
        return constraints
    
    # ========================================================================
    # CLASSIFICATION & EXTRACTION
    # ========================================================================
    
    def _classify_intent_type(self, lexical: LexicalResult) -> Optional[IntentType]:
        """Classify intent type based on keywords"""
        scores = {}
        
        for intent_type, type_keywords in self.INTENT_TYPE_KEYWORDS.items():
            score = 0
            for keyword in type_keywords:
                if keyword in lexical.keywords:
                    score += 1
            if score > 0:
                scores[intent_type] = score
        
        if not scores:
            return None
        
        # Return type with highest score
        return max(scores, key=scores.get)
    
    def _extract_scope(self, lexical: LexicalResult, full_text: str) -> ScopeObject:
        """Extract scope from lexical analysis"""
        # Determine scope type
        scope_type = ScopeType.MODULE  # Default
        
        for stype, keywords in self.SCOPE_KEYWORDS.items():
            if any(kw in lexical.keywords or kw in full_text.lower() for kw in keywords):
                scope_type = stype
                break
        
        # Extract target from entities
        target = "."  # Default to current directory
        if lexical.entities["files"]:
            target = lexical.entities["files"][0][0]
        elif lexical.entities["paths"]:
            target = lexical.entities["paths"][0]
        elif lexical.entities["modules"]:
            target = lexical.entities["modules"][0]
        
        return ScopeObject(
            scope_type=scope_type,
            target=target
        )
    
    def _extract_constraints(self, lexical: LexicalResult) -> List[IntentConstraint]:
        """Convert extracted constraints to IntentConstraint objects"""
        constraints = []
        
        if "max_cost" in lexical.constraints:
            constraints.append(IntentConstraint(
                constraint_type=ConstraintType.COST,
                value=float(lexical.constraints["max_cost"]),
                operator="LTE",
                strict=True,
                reason="User-specified cost limit"
            ))
        
        if "max_time" in lexical.constraints:
            constraints.append(IntentConstraint(
                constraint_type=ConstraintType.TIME,
                value=lexical.constraints["max_time"].total_seconds(),
                operator="LTE",
                strict=True,
                reason="User-specified time limit"
            ))
        
        return constraints
    
    def _extract_budget(self, lexical: LexicalResult) -> BudgetSpec:
        """Extract budget specification"""
        budget = BudgetSpec()
        
        if "max_cost" in lexical.constraints:
            budget.max_cost_usd = lexical.constraints["max_cost"]
        
        if "max_time" in lexical.constraints:
            budget.max_time = lexical.constraints["max_time"]
        
        if "max_tokens" in lexical.constraints:
            budget.max_tokens = lexical.constraints["max_tokens"]
        
        return budget
    
    def _determine_risk_profile(self, intent_type: IntentType, lexical: LexicalResult) -> RiskProfile:
        """Determine risk profile based on intent type and keywords"""
        # Check for high-risk keywords
        if any(kw in lexical.keywords for kw in self.HIGH_RISK_KEYWORDS):
            return RiskProfile.SYSTEMIC
        
        # Check for medium-risk keywords
        if any(kw in lexical.keywords for kw in self.MEDIUM_RISK_KEYWORDS):
            return RiskProfile.STRUCTURAL
        
        # Intent type-based risk
        high_risk_types = [IntentType.DEPLOY, IntentType.TRANSFORM]
        medium_risk_types = [IntentType.REFACTOR, IntentType.OPTIMIZE, IntentType.BUILD_APP]
        
        if intent_type in high_risk_types:
            return RiskProfile.SYSTEMIC
        elif intent_type in medium_risk_types:
            return RiskProfile.STRUCTURAL
        else:
            return RiskProfile.LOW
    
    def _determine_priority(self, lexical: LexicalResult) -> IntentPriority:
        """Determine priority based on keywords"""
        if any(kw in lexical.keywords for kw in self.CRITICAL_PRIORITY_KEYWORDS):
            return IntentPriority.CRITICAL
        elif any(kw in lexical.keywords for kw in self.HIGH_PRIORITY_KEYWORDS):
            return IntentPriority.HIGH
        elif any(kw in lexical.keywords for kw in self.LOW_PRIORITY_KEYWORDS):
            return IntentPriority.LOW
        else:
            return IntentPriority.MEDIUM
    
    # ========================================================================
    # CONTEXT BINDING
    # ========================================================================
    
    def bind_context(
        self,
        intent: IntentObject,
        additional_context: Dict[str, Any]
    ) -> IntentObject:
        """
        Enrich intent with additional execution context.
        
        This can be used to add runtime context after initial compilation.
        """
        intent.context.metadata.update(additional_context)
        return intent
    
    # ========================================================================
    # TEMPLATE SUGGESTION
    # ========================================================================
    
    def suggest_template(self, intent: IntentObject) -> str:
        """
        Suggest execution template based on intent characteristics.
        
        Returns template name that can be used by template library.
        """
        template_map = {
            IntentType.REFACTOR: "refactor_template",
            IntentType.BUILD_APP: "build_app_template",
            IntentType.ANALYZE_RISK: "analyze_risk_template",
            IntentType.DEPLOY: "deploy_template",
            IntentType.OPTIMIZE: "optimize_template",
            IntentType.DOCUMENT: "document_template",
            IntentType.STRATEGY: "strategy_template",
            IntentType.TRANSFORM: "transform_template",
        }
        
        return template_map.get(intent.intent_type, "generic_template")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def quick_compile(
    text: str,
    user_id: str = "default_user",
    user_tier: str = "FREE"
) -> CompilationResult:
    """Quick compilation for testing/prototyping"""
    compiler = IntentCompiler()
    return compiler.compile(text, user_id, user_tier)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "IntentCompiler",
    "CompilationResult",
    "LexicalResult",
    "Token",
    "quick_compile",
]

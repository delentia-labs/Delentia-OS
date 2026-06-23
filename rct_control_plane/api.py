"""
Control Plane REST API

FastAPI-based REST API for Control Plane operations.
Provides endpoints for intent compilation, graph building, policy evaluation,
state management, observability, and deep health checks.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, status, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .intent_compiler import IntentCompiler, CompilationResult
from .dsl_parser import DSLParser
from .policy_language import PolicyEvaluator, PolicyEvaluationResult
from .control_plane_state import ControlPlaneState, ControlPlanePhase
from .observability import ControlPlaneObserver
from .default_policies import get_default_policies


# ============================================================================
# PYDANTIC MODELS (Request/Response)
# ============================================================================

class IntentCompileRequest(BaseModel):
    """Request to compile an intent"""
    natural_language: str = Field(..., description="Natural language intent description", min_length=1)
    user_id: str = Field(..., description="User identifier")
    user_tier: str = Field(..., description="User tier (FREE, PRO, ENTERPRISE, INTERNAL)")
    organization_id: Optional[str] = Field(None, description="Organization identifier")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "natural_language": "Refactor the authentication module using clean architecture",
                "user_id": "user-123",
                "user_tier": "PRO",
                "organization_id": "org-456",
                "metadata": {"source": "web_ui"}
            }
        }


class IntentCompileResponse(BaseModel):
    """Response from intent compilation"""
    success: bool
    intent_id: Optional[str] = None
    intent: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    compilation_time_ms: float

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "intent_id": "550e8400-e29b-41d4-a716-446655440000",
                "intent": {"intent_type": "REFACTOR", "priority": "MEDIUM"},
                "validation": {"is_valid": True, "errors": [], "warnings": []},
                "errors": [],
                "warnings": [],
                "compilation_time_ms": 145.3
            }
        }


class GraphBuildRequest(BaseModel):
    """Request to build execution graph"""
    dsl_text: str = Field(..., description="DSL text defining the execution graph")
    intent_id: str = Field(..., description="Associated intent ID")

    class Config:
        json_schema_extra = {
            "example": {
                "dsl_text": 'intent "refactor" { node n1 { node_type = "agent_capability" } }',
                "intent_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


class GraphBuildResponse(BaseModel):
    """Response from graph building"""
    success: bool
    graph_id: Optional[str] = None
    graph: Optional[Dict[str, Any]] = None
    node_count: int = 0
    edge_count: int = 0
    estimated_cost_usd: float = 0.0
    estimated_duration_seconds: int = 0
    errors: List[str] = Field(default_factory=list)


class PolicyEvaluateRequest(BaseModel):
    """Request to evaluate policies"""
    intent_id: str = Field(..., description="Intent ID to evaluate")
    intent: Dict[str, Any] = Field(..., description="Intent object as dict")
    graph: Optional[Dict[str, Any]] = Field(None, description="Optional execution graph")
    use_default_policies: bool = Field(True, description="Whether to use default policies")

    class Config:
        json_schema_extra = {
            "example": {
                "intent_id": "550e8400-e29b-41d4-a716-446655440000",
                "intent": {"intent_type": "REFACTOR"},
                "graph": None,
                "use_default_policies": True
            }
        }


class PolicyEvaluateResponse(BaseModel):
    """Response from policy evaluation"""
    intent_id: str
    decision: str
    decision_reason: str
    is_approved: bool
    requires_approval: bool
    violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    triggered_rules_count: int = 0
    evaluation_time_ms: float


class StateResponse(BaseModel):
    """Response containing state information"""
    state_id: str
    intent_id: str
    phase: str
    version: int
    is_terminal: bool
    is_completed: bool
    is_failed: bool
    started_at: str
    updated_at: str
    completed_at: Optional[str] = None
    estimated_cost_usd: float
    actual_cost_usd: float
    transitions_count: int


class IntentListItem(BaseModel):
    """Summary of an intent"""
    intent_id: str
    intent_type: str
    priority: str
    created_at: str
    phase: str
    is_terminal: bool


class AuditTrailResponse(BaseModel):
    """Audit trail for an intent"""
    intent_id: str
    events: List[Dict[str, Any]]
    event_count: int
    integrity_verified: bool


class MetricsResponse(BaseModel):
    """Metrics summary"""
    total_intents: int
    total_compilations: int
    total_graphs: int
    total_policy_evaluations: int
    total_executions: int
    total_nodes_executed: int
    total_failures: int
    avg_compilation_latency_ms: float
    avg_policy_evaluation_latency_ms: float
    avg_graph_build_latency_ms: float
    policy_violations: int
    approvals_required: int
    approvals_granted: int
    audit_trail_entries: int


class HealthResponse(BaseModel):
    """Health check response (basic)"""
    status: str
    version: str
    timestamp: str


# ---- Feature Flags models ----

class FlagSummary(BaseModel):
    """Compact flag representation for list views"""
    flag_key: str
    description: str
    enabled: bool
    rollout_percentage: int
    environments: List[str]
    owner: str
    tags: List[str]


class FlagPatchRolloutRequest(BaseModel):
    percentage: int = Field(..., ge=0, le=100)


class ServiceCheckResult(BaseModel):
    """Per-service health check result"""
    name: str
    status: str          # "healthy" | "degraded" | "unhealthy"
    latency_ms: float
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class DetailedHealthResponse(BaseModel):
    """Detailed health check response with per-subsystem status"""
    status: str                          # overall: healthy / degraded / unhealthy
    version: str
    timestamp: str
    uptime_seconds: float
    python_version: str
    environment: str
    services: List[ServiceCheckResult] = Field(default_factory=list)
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    memory_mb: float
    intents_in_memory: int
    states_in_memory: int


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

class ControlPlaneAPI:
    """
    Control Plane REST API
    
    Provides endpoints for:
    - Intent compilation
    - Graph building
    - Policy evaluation
    - State management
    - Audit trails
    - Metrics
    """
    
    def __init__(self):
        self.app = FastAPI(
            title="RCT Control Plane API",
            description="Intent-to-Execution Orchestration Infrastructure",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc"
        )
        
        # Track uptime
        self._start_time: float = time.time()
        
        # Initialize components
        self.observer = ControlPlaneObserver()
        self.compiler = IntentCompiler(observer=self.observer)
        self.parser = DSLParser(observer=self.observer)
        self.evaluator = PolicyEvaluator(observer=self.observer)
        
        # Storage for states and intents (in-memory for now)
        self.states: Dict[str, ControlPlaneState] = {}
        self.intents: Dict[str, Dict[str, Any]] = {}
        
        # Register routes
        self._register_routes()
    
    def _register_routes(self):
        """Register all API routes"""
        
        @self.app.get("/", response_model=HealthResponse)
        async def root():
            """Root endpoint - health check"""
            return HealthResponse(
                status="healthy",
                version="1.0.0",
                timestamp=datetime.utcnow().isoformat()
            )
        
        @self.app.get("/health", response_model=HealthResponse)
        async def health():
            """Health check endpoint"""
            return HealthResponse(
                status="healthy",
                version="1.0.0",
                timestamp=datetime.utcnow().isoformat()
            )
        
        @self.app.get("/health/detailed", response_model=DetailedHealthResponse)
        async def health_detailed():
            """
            Detailed health check — reports latency per subsystem.
            
            Checks: IntentCompiler, DSLParser, PolicyEvaluator, Observer,
                    in-memory stores, Python runtime, feature flags.
            """
            import resource as _resource

            now = datetime.utcnow().isoformat()
            uptime = time.time() - self._start_time

            service_checks: List[ServiceCheckResult] = []

            # --- 1. IntentCompiler ---
            t0 = time.perf_counter()
            try:
                _ok = self.compiler is not None
                svc_status = "healthy" if _ok else "unhealthy"
                msg = "IntentCompiler initialized" if _ok else "Not initialized"
            except Exception as exc:
                svc_status, msg = "unhealthy", str(exc)
            service_checks.append(ServiceCheckResult(
                name="intent_compiler",
                status=svc_status,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                message=msg,
            ))

            # --- 2. DSLParser ---
            t0 = time.perf_counter()
            try:
                _ok = self.parser is not None
                svc_status = "healthy" if _ok else "unhealthy"
                msg = "DSLParser initialized" if _ok else "Not initialized"
            except Exception as exc:
                svc_status, msg = "unhealthy", str(exc)
            service_checks.append(ServiceCheckResult(
                name="dsl_parser",
                status=svc_status,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                message=msg,
            ))

            # --- 3. PolicyEvaluator ---
            t0 = time.perf_counter()
            try:
                _ok = self.evaluator is not None
                svc_status = "healthy" if _ok else "unhealthy"
                msg = "PolicyEvaluator initialized" if _ok else "Not initialized"
            except Exception as exc:
                svc_status, msg = "unhealthy", str(exc)
            service_checks.append(ServiceCheckResult(
                name="policy_evaluator",
                status=svc_status,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                message=msg,
            ))

            # --- 4. Observer ---
            t0 = time.perf_counter()
            try:
                _ok = self.observer is not None
                svc_status = "healthy" if _ok else "unhealthy"
                msg = "Observer initialized" if _ok else "Not initialized"
            except Exception as exc:
                svc_status, msg = "unhealthy", str(exc)
            service_checks.append(ServiceCheckResult(
                name="observer",
                status=svc_status,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                message=msg,
            ))

            # --- 5. Finance Layer ---
            t0 = time.perf_counter()
            try:
                from rct_platform.services.finance import StripePaymentService, WalletService
                svc_status = "healthy"
                msg = "Finance layer importable"
            except ImportError as exc:
                svc_status, msg = "degraded", f"Finance layer not available: {exc}"
            service_checks.append(ServiceCheckResult(
                name="finance_layer",
                status=svc_status,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                message=msg,
            ))

            # --- 6. Feature Flags ---
            t0 = time.perf_counter()
            feature_flags_snapshot: Dict[str, bool] = {}
            try:
                from rct_control_plane.middleware import get_all_flags
                feature_flags_snapshot = get_all_flags()
                svc_status = "healthy"
                msg = f"{len(feature_flags_snapshot)} flags loaded"
            except ImportError:
                svc_status = "degraded"
                msg = "Feature flags middleware not yet available"
            except Exception as exc:
                svc_status, msg = "degraded", str(exc)
            service_checks.append(ServiceCheckResult(
                name="feature_flags",
                status=svc_status,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                message=msg,
            ))

            # Memory usage
            try:
                mem_bytes = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss * 1024
                mem_mb = round(mem_bytes / 1024 / 1024, 2)
            except Exception:
                mem_mb = -1.0

            # Overall status: unhealthy if any check is unhealthy; degraded if any degraded
            statuses = [s.status for s in service_checks]
            if "unhealthy" in statuses:
                overall = "unhealthy"
            elif "degraded" in statuses:
                overall = "degraded"
            else:
                overall = "healthy"

            return DetailedHealthResponse(
                status=overall,
                version="1.0.0",
                timestamp=now,
                uptime_seconds=round(uptime, 2),
                python_version=sys.version,
                environment=os.getenv("RCT_ENV", "development"),
                services=service_checks,
                feature_flags=feature_flags_snapshot,
                memory_mb=mem_mb,
                intents_in_memory=len(self.intents),
                states_in_memory=len(self.states),
            )
        
        @self.app.post("/v1/intent/compile", response_model=IntentCompileResponse)
        async def compile_intent(request: IntentCompileRequest):
            """
            Compile natural language into structured intent.
            
            This is the entry point for all Control Plane operations.
            Takes natural language input and produces a structured IntentObject.
            """
            try:
                result = self.compiler.compile(
                    natural_language=request.natural_language,
                    user_id=request.user_id,
                    user_tier=request.user_tier,
                    organization_id=request.organization_id,
                    metadata=request.metadata
                )
                
                # Store intent if successful
                if result.success and result.intent:
                    intent_id = str(result.intent.id)
                    self.intents[intent_id] = {
                        "intent": result.intent.to_dict(),
                        "compiled_at": datetime.now(timezone.utc).isoformat(),
                        "user_id": request.user_id
                    }
                    
                    # Create state and transition to INTENT_COMPILED
                    state = ControlPlaneState(
                        intent_id=intent_id,
                        observer=self.observer
                    )
                    state.transition_to(ControlPlanePhase.INTENT_COMPILED, actor="api")
                    self.states[intent_id] = state
                
                return IntentCompileResponse(
                    success=result.success,
                    intent_id=str(result.intent.id) if result.intent else None,
                    intent=result.intent.to_dict() if result.intent else None,
                    validation=result.validation.to_dict() if result.validation else None,
                    errors=result.errors,
                    warnings=result.warnings,
                    compilation_time_ms=result.compilation_time_ms
                )
            
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Intent compilation failed: {str(e)}"
                )
        
        @self.app.post("/v1/graph/build", response_model=GraphBuildResponse)
        async def build_graph(request: GraphBuildRequest):
            """
            Build execution graph from DSL.
            
            Parses DSL text into ExecutionGraph intermediate representation.
            """
            try:
                graph = self.parser.parse(request.dsl_text, request.intent_id)
                
                # Update state if exists
                if request.intent_id in self.states:
                    state = self.states[request.intent_id]
                    state.graph_snapshot = graph
                    state.transition_to(ControlPlanePhase.GRAPH_BUILT, actor="api")
                
                return GraphBuildResponse(
                    success=True,
                    graph_id=graph.graph_id,
                    graph=graph.to_dict(),
                    node_count=len(graph.nodes),
                    edge_count=len(graph.edges),
                    estimated_cost_usd=float(graph.total_estimated_cost),
                    estimated_duration_seconds=graph.total_estimated_duration_seconds,
                    errors=[]
                )
            
            except Exception as e:
                return GraphBuildResponse(
                    success=False,
                    errors=[f"Graph build failed: {str(e)}"]
                )
        
        @self.app.post("/v1/policy/evaluate", response_model=PolicyEvaluateResponse)
        async def evaluate_policy(request: PolicyEvaluateRequest):
            """
            Evaluate policies against intent and optional graph.
            
            Checks intents against governance policies for approval/rejection.
            """
            try:
                # Load default policies if requested
                if request.use_default_policies:
                    self.evaluator.clear_rules()
                    for policy in get_default_policies():
                        self.evaluator.add_rule(policy)
                
                # Reconstruct intent object
                from .intent_schema import IntentObject
                intent = IntentObject(**request.intent)
                
                # Reconstruct graph if provided
                graph = None
                if request.graph and request.intent_id in self.states:
                    state = self.states[request.intent_id]
                    if hasattr(state, 'graph_snapshot') and state.graph_snapshot:
                        graph = state.graph_snapshot
                
                # Evaluate
                eval_result = self.evaluator.evaluate_intent(intent, graph)
                
                # Update state if exists
                if request.intent_id in self.states:
                    state = self.states[request.intent_id]
                    state.transition_to(ControlPlanePhase.POLICY_CHECKED, actor="api")
                    state.requires_approval = eval_result.requires_approval
                    state.policy_violations = eval_result.violations
                
                return PolicyEvaluateResponse(
                    intent_id=eval_result.intent_id,
                    decision=eval_result.decision.value,
                    decision_reason=eval_result.decision_reason,
                    is_approved=eval_result.is_approved(),
                    requires_approval=eval_result.requires_approval,
                    violations=eval_result.violations,
                    warnings=eval_result.warnings,
                    triggered_rules_count=len(eval_result.triggered_rules),
                    evaluation_time_ms=eval_result.evaluation_time_ms
                )
            
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Policy evaluation failed: {str(e)}"
                )
        
        @self.app.get("/v1/state/{intent_id}", response_model=StateResponse)
        async def get_state(intent_id: str):
            """
            Get current state for an intent.
            
            Returns state information including phase, transitions, and metrics.
            """
            if intent_id not in self.states:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"State not found for intent_id: {intent_id}"
                )
            
            state = self.states[intent_id]
            
            return StateResponse(
                state_id=state.state_id,
                intent_id=state.intent_id,
                phase=state.phase.value,
                version=state.version,
                is_terminal=state.is_terminal(),
                is_completed=state.is_completed(),
                is_failed=state.is_failed(),
                started_at=state.started_at.isoformat(),
                updated_at=state.updated_at.isoformat(),
                completed_at=state.completed_at.isoformat() if state.completed_at else None,
                estimated_cost_usd=float(state.estimated_cost_usd),
                actual_cost_usd=float(state.actual_cost_usd),
                transitions_count=len(state.transitions)
            )
        
        @self.app.get("/v1/intents", response_model=List[IntentListItem])
        async def list_intents(
            limit: int = Query(10, ge=1, le=100),
            offset: int = Query(0, ge=0)
        ):
            """
            List all intents.
            
            Returns paginated list of intents with summary information.
            """
            items = []
            for intent_id, intent_data in list(self.intents.items())[offset:offset+limit]:
                state = self.states.get(intent_id)
                intent_obj = intent_data["intent"]
                
                items.append(IntentListItem(
                    intent_id=intent_id,
                    intent_type=intent_obj.get("intent_type", "UNKNOWN"),
                    priority=intent_obj.get("priority", "MEDIUM"),
                    created_at=intent_data["compiled_at"],
                    phase=state.phase.value if state else "UNKNOWN",
                    is_terminal=state.is_terminal() if state else False
                ))
            
            return items
        
        @self.app.get("/v1/audit/{intent_id}", response_model=AuditTrailResponse)
        async def get_audit_trail(intent_id: str):
            """
            Get audit trail for an intent.
            
            Returns chronological list of all events for the intent,
            with integrity verification.
            """
            events = self.observer.get_intent_timeline(intent_id)
            
            if not events:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No audit trail found for intent_id: {intent_id}"
                )
            
            return AuditTrailResponse(
                intent_id=intent_id,
                events=[e.to_dict() for e in events],
                event_count=len(events),
                integrity_verified=self.observer.verify_audit_integrity()
            )
        
        @self.app.get("/v1/metrics", response_model=MetricsResponse)
        async def get_metrics():
            """
            Get metrics summary.
            
            Returns aggregated metrics for all Control Plane operations.
            """
            summary = self.observer.get_metrics_summary()
            
            return MetricsResponse(**summary)
        
        @self.app.delete("/v1/state/{intent_id}")
        async def delete_state(intent_id: str):
            """
            Delete state and intent data.
            
            Cleanup endpoint for testing/development.
            """
            if intent_id in self.states:
                del self.states[intent_id]
            if intent_id in self.intents:
                del self.intents[intent_id]
            
            return {"message": f"State deleted for intent_id: {intent_id}"}
        
        @self.app.post("/v1/reset")
        async def reset_all():
            """
            Reset all state and metrics.
            
            Development/testing endpoint to clear all data.
            """
            self.states.clear()
            self.intents.clear()
            self.observer.reset_metrics()
            
            return {"message": "All state and metrics reset"}

        # ----------------------------------------------------------------
        # Feature Flags admin routes
        # ----------------------------------------------------------------
        
        @self.app.get("/v1/flags", response_model=List[FlagSummary])
        async def list_feature_flags():
            """List all feature flags with summary information."""
            from .middleware import FLAG_STORE
            raw = FLAG_STORE.list_flags()
            return [
                FlagSummary(
                    flag_key=f["flag_key"],
                    description=f["description"],
                    enabled=f["enabled"],
                    rollout_percentage=f["rollout_percentage"],
                    environments=f["environments"],
                    owner=f["owner"],
                    tags=f["tags"],
                )
                for f in raw
            ]

        @self.app.get("/v1/flags/{flag_key}")
        async def get_feature_flag(flag_key: str):
            """Get detailed info for a single flag."""
            from .middleware import FLAG_STORE
            flag = FLAG_STORE.get_flag(flag_key)
            if flag is None:
                raise HTTPException(status_code=404, detail=f"Flag '{flag_key}' not found")
            return flag.to_dict()

        @self.app.patch("/v1/flags/{flag_key}/enable")
        async def enable_flag(flag_key: str):
            """Enable a feature flag."""
            from .middleware import FLAG_STORE
            ok = FLAG_STORE.set_flag(flag_key, True)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Flag '{flag_key}' not found")
            return {"flag_key": flag_key, "enabled": True}

        @self.app.patch("/v1/flags/{flag_key}/disable")
        async def disable_flag(flag_key: str):
            """Disable a feature flag."""
            from .middleware import FLAG_STORE
            ok = FLAG_STORE.set_flag(flag_key, False)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Flag '{flag_key}' not found")
            return {"flag_key": flag_key, "enabled": False}

        @self.app.patch("/v1/flags/{flag_key}/toggle")
        async def toggle_feature_flag(flag_key: str):
            """Toggle a feature flag (on→off or off→on)."""
            from .middleware import FLAG_STORE
            new_state = FLAG_STORE.toggle_flag(flag_key)
            if new_state is None:
                raise HTTPException(status_code=404, detail=f"Flag '{flag_key}' not found")
            return {"flag_key": flag_key, "enabled": new_state}

        @self.app.patch("/v1/flags/{flag_key}/rollout")
        async def set_flag_rollout(flag_key: str, body: FlagPatchRolloutRequest):
            """Set rollout percentage (0-100) for a flag."""
            from .middleware import FLAG_STORE
            try:
                ok = FLAG_STORE.set_rollout(flag_key, body.percentage)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            if not ok:
                raise HTTPException(status_code=404, detail=f"Flag '{flag_key}' not found")
            return {"flag_key": flag_key, "rollout_percentage": body.percentage}

        @self.app.post("/v1/flags/{flag_key}/whitelist/{user_id}")
        async def whitelist_user(flag_key: str, user_id: str):
            """Add a user to a flag's whitelist (force enable for that user)."""
            from .middleware import FLAG_STORE
            ok = FLAG_STORE.add_to_whitelist(flag_key, user_id)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Flag '{flag_key}' not found")
            return {"flag_key": flag_key, "user_id": user_id, "action": "whitelisted"}

        @self.app.post("/v1/flags/{flag_key}/blacklist/{user_id}")
        async def blacklist_user(flag_key: str, user_id: str):
            """Add a user to a flag's blacklist (force disable for that user)."""
            from .middleware import FLAG_STORE
            ok = FLAG_STORE.add_to_blacklist(flag_key, user_id)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Flag '{flag_key}' not found")
            return {"flag_key": flag_key, "user_id": user_id, "action": "blacklisted"}

        @self.app.delete("/v1/flags/{flag_key}/overrides/{user_id}")
        async def remove_flag_override(flag_key: str, user_id: str):
            """Remove a user from both whitelist and blacklist for a flag."""
            from .middleware import FLAG_STORE
            ok = FLAG_STORE.remove_user_override(flag_key, user_id)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Flag '{flag_key}' not found")
            return {"flag_key": flag_key, "user_id": user_id, "action": "override_removed"}


# ============================================================================
# APPLICATION FACTORY
# ============================================================================

def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    api = ControlPlaneAPI()
    return api.app


# Create default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

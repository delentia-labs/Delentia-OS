"""
RCT Plan Engine — Intent Simulation Layer

Simulates intent execution BEFORE it happens, giving full visibility into:
  - Which HexaCore models will be called
  - What SignedAI tier is required
  - What the risk profile is (LOW / STRUCTURAL / SYSTEMIC)
  - Estimated cost in USD
  - Whether human approval (A=1) is required
  - Which policy rules would be triggered

Terraform/Kubernetes-style "plan before apply" workflow:
    rct plan "refactor auth module"    → shows full execution plan
    rct apply "refactor auth module"   → executes after plan confirmation

The plan engine does NOT execute — it only simulates.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rct_control_plane.intent_compiler import IntentCompiler
from rct_control_plane.intent_schema import IntentType, RiskProfile
from rct_control_plane.observability import ControlPlaneObserver
from rct_control_plane.policy_language import (
    PolicyAction,
    PolicyEvaluator,
)

try:
    from signedai.core import (
        HexaCoreRegistry,
        HexaCoreRole,
    )
    _HAS_SIGNEDAI = True
except ImportError:
    _HAS_SIGNEDAI = False


# ---------------------------------------------------------------------------
# Pricing loader
# ---------------------------------------------------------------------------

def _load_pricing() -> Dict[str, Any]:
    """Load model pricing from config/model_pricing.json.

    Falls back to empty dict on any error — callers must handle missing keys.
    """
    candidates = [
        Path(__file__).parent.parent / "config" / "model_pricing.json",
        Path("config") / "model_pricing.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
    return {}


# ---------------------------------------------------------------------------
# SignedAI Tier determination based on risk
# ---------------------------------------------------------------------------

_RISK_TO_TIER: Dict[str, str] = {
    RiskProfile.LOW.value:        "Tier 4 — 4/7 models, 75% consensus (standard)",
    RiskProfile.STRUCTURAL.value: "Tier 6 — 6/7 models, 86% consensus (elevated)",
    RiskProfile.SYSTEMIC.value:   "Tier 8 — 7/7 models, 100% consensus (maximum)",
}

_RISK_TO_A_REQUIREMENT: Dict[str, str] = {
    RiskProfile.LOW.value:        "A=1 auto-grant (low risk — no human approval required)",
    RiskProfile.STRUCTURAL.value: "A=1 recommended (code changes — review advised)",
    RiskProfile.SYSTEMIC.value:   "A=1 REQUIRED (systemic risk — human approval mandatory)",
}

_RISK_ORDER: Dict[str, int] = {
    RiskProfile.LOW.value: 0,
    RiskProfile.STRUCTURAL.value: 1,
    RiskProfile.SYSTEMIC.value: 2,
}


# ---------------------------------------------------------------------------
# PlanResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class ModelEntry:
    """A single model in the HexaCore roster for this plan."""
    role: str
    model_id: str
    provider: str
    country: str
    cost_input_per_1m: float
    cost_output_per_1m: float
    specialties: List[str] = field(default_factory=list)


@dataclass
class PlanResult:
    """
    Structured result of a pre-execution simulation.

    Contains everything needed to decide whether to proceed with rct apply.
    """
    intent_text: str
    intent_id: str
    intent_type: str
    risk_profile: str

    # SignedAI
    signedai_tier: str
    a_requirement: str
    requires_human_approval: bool

    # HexaCore model roster
    models_roster: List[ModelEntry]

    # Cost estimate
    estimated_cost_usd: float
    cost_breakdown: Dict[str, float]

    # Policy
    policy_decision: str
    triggered_policies: List[str]
    policy_warnings: List[str]

    # Data sources
    data_sources: List[str]

    # Simulation metadata
    simulation_time_ms: float
    is_valid: bool
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_text": self.intent_text,
            "intent_id": self.intent_id,
            "intent_type": self.intent_type,
            "risk_profile": self.risk_profile,
            "signedai_tier": self.signedai_tier,
            "a_requirement": self.a_requirement,
            "requires_human_approval": self.requires_human_approval,
            "models_roster": [
                {
                    "role": m.role,
                    "model_id": m.model_id,
                    "provider": m.provider,
                    "country": m.country,
                    "cost_input_per_1m": m.cost_input_per_1m,
                    "cost_output_per_1m": m.cost_output_per_1m,
                }
                for m in self.models_roster
            ],
            "estimated_cost_usd": self.estimated_cost_usd,
            "cost_breakdown": self.cost_breakdown,
            "policy_decision": self.policy_decision,
            "triggered_policies": self.triggered_policies,
            "policy_warnings": self.policy_warnings,
            "data_sources": self.data_sources,
            "simulation_time_ms": self.simulation_time_ms,
            "is_valid": self.is_valid,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# PlanEngine
# ---------------------------------------------------------------------------

class PlanEngine:
    """
    Pre-execution simulation engine for RCT intents.

    Simulates what WOULD happen if the intent were executed — without
    actually executing it.

    Usage:
        engine = PlanEngine()
        result = engine.simulate("refactor the authentication module")
        if result.is_valid:
            print(result.risk_profile)
    """

    def __init__(
        self,
        observer: Optional[ControlPlaneObserver] = None,
    ) -> None:
        self._observer = observer or ControlPlaneObserver()
        self._compiler = IntentCompiler(observer=self._observer)
        self._evaluator = PolicyEvaluator(observer=self._observer)
        self._pricing = _load_pricing()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(
        self,
        intent_text: str,
        user_id: str = "cli-user",
        user_tier: str = "PRO",
    ) -> PlanResult:
        """
        Simulate intent execution and return a structured PlanResult.

        Args:
            intent_text: Natural language intent description
            user_id: User ID for audit trail
            user_tier: User tier (FREE / PRO / ENTERPRISE)

        Returns:
            PlanResult with full simulation details
        """
        t_start = time.perf_counter()
        errors: List[str] = []

        # Step 1: Compile intent
        compilation = self._compiler.compile(
            intent_text,
            user_id=user_id,
            user_tier=user_tier,
        )

        if not compilation.success or compilation.intent is None:
            elapsed = (time.perf_counter() - t_start) * 1000
            return PlanResult(
                intent_text=intent_text,
                intent_id="—",
                intent_type="UNKNOWN",
                risk_profile=RiskProfile.LOW.value,
                signedai_tier=_RISK_TO_TIER[RiskProfile.LOW.value],
                a_requirement=_RISK_TO_A_REQUIREMENT[RiskProfile.LOW.value],
                requires_human_approval=False,
                models_roster=[],
                estimated_cost_usd=0.0,
                cost_breakdown={},
                policy_decision=PolicyAction.REJECT.value,
                triggered_policies=[],
                policy_warnings=[],
                data_sources=[],
                simulation_time_ms=elapsed,
                is_valid=False,
                errors=compilation.errors or ["Intent compilation failed"],
            )

        intent = compilation.intent
        intent_id = str(intent.id)
        intent_type = str(intent.intent_type)
        risk_profile = self._infer_risk_profile(intent_type, intent_text)

        # Step 2: Evaluate policies
        policy_result = self._evaluator.evaluate_intent(intent)

        triggered_policies = [r.name for r in policy_result.triggered_rules]
        policy_warnings = list(policy_result.warnings or [])
        policy_decision = policy_result.decision.value

        # Step 3: Build HexaCore model roster
        models_roster = self._build_model_roster(risk_profile)

        # Step 4: Estimate cost
        estimated_cost, cost_breakdown = self._estimate_cost(models_roster, risk_profile)

        # Step 5: Determine A-requirement
        requires_human_approval = (
            risk_profile == RiskProfile.SYSTEMIC.value
            or policy_result.requires_approval
            or policy_result.decision == PolicyAction.REQUIRE_APPROVAL
        )

        # Step 6: Infer data sources
        data_sources = self._infer_data_sources(intent, intent_text)

        elapsed = (time.perf_counter() - t_start) * 1000

        return PlanResult(
            intent_text=intent_text,
            intent_id=intent_id,
            intent_type=intent_type,
            risk_profile=risk_profile,
            signedai_tier=_RISK_TO_TIER[risk_profile],
            a_requirement=_RISK_TO_A_REQUIREMENT[risk_profile],
            requires_human_approval=requires_human_approval,
            models_roster=models_roster,
            estimated_cost_usd=estimated_cost,
            cost_breakdown=cost_breakdown,
            policy_decision=policy_decision,
            triggered_policies=triggered_policies,
            policy_warnings=policy_warnings,
            data_sources=data_sources,
            simulation_time_ms=elapsed,
            is_valid=True,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _infer_risk_profile(self, intent_type: str, intent_text: str) -> str:
        """Infer risk profile from intent type and text keywords."""
        systemic_keywords = {
            "deploy", "production", "migrate", "database", "infrastructure",
            "delete", "drop", "rm", "remove", "destroy", "rollback", "production",
            "kubernetes", "docker", "cloud", "aws", "gcp", "azure", "terraform",
        }
        structural_keywords = {
            "refactor", "rebuild", "restructure", "modify", "update", "change",
            "rename", "move", "split", "merge", "auth", "authentication", "security",
            "config", "configuration", "schema",
        }

        text_lower = intent_text.lower()

        # Check for systemic keywords first (highest risk)
        if any(kw in text_lower for kw in systemic_keywords):
            return RiskProfile.SYSTEMIC.value

        # IntentType-based risk mapping
        systemic_types = {IntentType.DEPLOY.value, IntentType.TRANSFORM.value}
        structural_types = {
            IntentType.REFACTOR.value, IntentType.BUILD_APP.value,
            IntentType.OPTIMIZE.value, IntentType.TEST.value,
        }

        if intent_type in systemic_types:
            return RiskProfile.SYSTEMIC.value
        if intent_type in structural_types:
            return RiskProfile.STRUCTURAL.value

        # Check structural keywords
        if any(kw in text_lower for kw in structural_keywords):
            return RiskProfile.STRUCTURAL.value

        return RiskProfile.LOW.value


    def _build_model_roster(self, risk_profile: str) -> List[ModelEntry]:
        """Build model roster based on risk level from HexaCoreRegistry."""
        if not _HAS_SIGNEDAI:
            return self._fallback_model_roster()

        # TODO: use registry.get_model_for_role(role) in v1.2.0 for dynamic model lookup
        models: List[ModelEntry] = []

        # Select roles based on risk tier
        if risk_profile == RiskProfile.SYSTEMIC.value:
            # Tier 8: all 7 roles
            selected_roles = list(HexaCoreRole)
        elif risk_profile == RiskProfile.STRUCTURAL.value:
            # Tier 6: 6 roles (exclude REGIONAL_THAI unless needed)
            selected_roles = [
                HexaCoreRole.SUPREME_ARCHITECT,
                HexaCoreRole.LEAD_BUILDER,
                HexaCoreRole.JUNIOR_BUILDER,
                HexaCoreRole.SPECIALIST,
                HexaCoreRole.LIBRARIAN,
                HexaCoreRole.HUMANIZER,
            ]
        else:
            # Tier 4: 4 roles (standard analysis)
            selected_roles = [
                HexaCoreRole.LEAD_BUILDER,
                HexaCoreRole.JUNIOR_BUILDER,
                HexaCoreRole.SPECIALIST,
                HexaCoreRole.LIBRARIAN,
            ]

        for role in selected_roles:
            model_info = HexaCoreRegistry.MODELS.get(role)
            if model_info:
                models.append(
                    ModelEntry(
                        role=role.value,
                        model_id=model_info.id,
                        provider=model_info.provider,
                        country=model_info.country,
                        cost_input_per_1m=model_info.cost_input,
                        cost_output_per_1m=model_info.cost_output,
                        specialties=list(model_info.specialties[:3]),
                    )
                )

        return models

    def _fallback_model_roster(self) -> List[ModelEntry]:
        """Fallback model roster — loaded from config/model_pricing.json."""
        pricing = self._pricing
        roster_cfg = pricing.get("fallback_roster", [])
        models_cfg = pricing.get("models", {})

        if not roster_cfg:
            # Hard fallback if JSON missing
            return [
                ModelEntry(
                    role="supreme_architect",
                    model_id="anthropic/claude-opus-4.6",
                    provider="Anthropic",
                    country="US",
                    cost_input_per_1m=15.0,
                    cost_output_per_1m=75.0,
                    specialties=["Architecture", "Planning"],
                ),
                ModelEntry(
                    role="lead_builder",
                    model_id="moonshotai/kimi-k2.5",
                    provider="Moonshot AI",
                    country="CN",
                    cost_input_per_1m=0.45,
                    cost_output_per_1m=2.25,
                    specialties=["Programming", "Code generation"],
                ),
            ]

        result: List[ModelEntry] = []
        for entry in roster_cfg:
            model_id = entry.get("model_id", "")
            m = models_cfg.get(model_id, {})
            result.append(
                ModelEntry(
                    role=entry.get("role", "unknown"),
                    model_id=model_id,
                    provider=m.get("provider", "Unknown"),
                    country=m.get("country", "??"),
                    cost_input_per_1m=float(m.get("cost_input_per_1m", 1.0)),
                    cost_output_per_1m=float(m.get("cost_output_per_1m", 5.0)),
                    specialties=entry.get("specialties", []),
                )
            )
        return result

    def _estimate_cost(
        self, models: List[ModelEntry], risk_profile: str
    ) -> Tuple[float, Dict[str, float]]:
        """Estimate execution cost based on model roster and risk profile."""
        # Load token estimates from pricing JSON (with fallback to hardcoded defaults)
        te_cfg = self._pricing.get("token_estimates", {})
        _defaults = {
            RiskProfile.LOW.value:        (2_000, 1_000),
            RiskProfile.STRUCTURAL.value: (8_000, 4_000),
            RiskProfile.SYSTEMIC.value:   (15_000, 8_000),
        }
        risk_key = risk_profile.upper()
        if risk_key in te_cfg:
            cfg_entry = te_cfg[risk_key]
            input_tokens = int(cfg_entry.get("input", 2_000))
            output_tokens = int(cfg_entry.get("output", 1_000))
        else:
            input_tokens, output_tokens = _defaults.get(risk_profile, (2_000, 1_000))

        breakdown: Dict[str, float] = {}
        total = 0.0

        for model in models:
            cost = (
                (model.cost_input_per_1m / 1_000_000) * input_tokens
                + (model.cost_output_per_1m / 1_000_000) * output_tokens
            )
            breakdown[model.role] = round(cost, 6)
            total += cost

        return round(total, 6), breakdown

    def _infer_data_sources(self, intent: Any, text: str) -> List[str]:
        """Infer data sources that would be accessed during execution."""
        sources: List[str] = []
        scope = getattr(intent, "scope", None)

        if scope:
            scope_type = str(getattr(scope, "scope_type", ""))
            target = str(getattr(scope, "target", ""))
            if scope_type and target:
                sources.append(f"{scope_type}: {target}")
            elif scope_type:
                sources.append(scope_type)

        # Keyword-based source detection
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["database", "db", "sql", "rctdb"]):
            sources.append("DelentiaDB v2.0 — 8D Schema")
        if any(kw in text_lower for kw in ["file", "module", "code", "function"]):
            sources.append("Local filesystem (read)")
        if any(kw in text_lower for kw in ["api", "endpoint", "service", "http"]):
            sources.append("External API endpoints")
        if any(kw in text_lower for kw in ["vector", "embed", "search", "rag"]):
            sources.append("Vector store (read)")

        if not sources:
            sources = ["In-context only (no external sources)"]

        return sources

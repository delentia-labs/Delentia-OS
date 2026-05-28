"""
SignedAI Core Registry — standalone public implementation

Provides HexaCoreRegistry, SignedAIRegistry, and all supporting enums/models
for tier selection, cost estimation, and consensus calculation.

No dependency on rct_platform private internals.

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Hexa-Core Registry
# ---------------------------------------------------------------------------

class HexaCoreRole(str, Enum):
    """The 9 core AI roles in RCT OS (Hexa-Core Architecture v2.3)."""
    SUPREME_ARCHITECT = "supreme_architect"
    LEAD_BUILDER = "lead_builder"
    JUNIOR_BUILDER = "junior_builder"
    SPECIALIST = "specialist"
    LIBRARIAN = "librarian"
    HUMANIZER = "humanizer"
    REGIONAL_THAI = "regional_thai"  # G38: Typhoon v2 — Thai NLP specialist (SCB10X)
    OLLAMA_ADAPTER = "ollama_adapter"  # Local SLM fallback via Ollama runtime
    GROQ_ADAPTER = "groq_adapter"      # Groq LPU ultra-low-latency inference (v2.3)


class ModelInfo(BaseModel):
    """Metadata for a single Hexa-Core model."""
    id: str = Field(description="OpenRouter model ID")
    role: HexaCoreRole
    provider: str
    country: str
    cost_input: float = Field(description="USD per 1M input tokens")
    cost_output: float = Field(description="USD per 1M output tokens")
    context_window: int
    specialties: List[str] = Field(default_factory=list)
    use_cases: List[str] = Field(default_factory=list)
    programming_rank: Optional[int] = None
    reasoning_rank: Optional[int] = None


class HexaCoreRegistry:
    """
    Registry of the 6 models in Hexa-Core Architecture (3 US + 3 CN).

    Design principles:
    - Geopolitical Balance (West/East parity in Tier 4/6/8)
    - Cost Efficiency (delegate simple tasks to cheaper models)
    - Specialisation (right model for the job)
    """

    MODELS: Dict[HexaCoreRole, ModelInfo] = {
        HexaCoreRole.SUPREME_ARCHITECT: ModelInfo(
            id="anthropic/claude-opus-4.6",
            role=HexaCoreRole.SUPREME_ARCHITECT,
            provider="Anthropic",
            country="US",
            cost_input=5.0,
            cost_output=25.0,
            context_window=1_000_000,
            specialties=["Architecture", "Planning", "Complex reasoning", "Final decisions"],
            use_cases=["System architecture design", "Crisis management", "Final arbitration in Tier 8", "Complex problem solving", "Code review (critical)"],
            programming_rank=1,
            reasoning_rank=1,
        ),
        HexaCoreRole.LEAD_BUILDER: ModelInfo(
            id="moonshotai/kimi-k2.5",
            role=HexaCoreRole.LEAD_BUILDER,
            provider="Moonshot AI",
            country="CN",
            cost_input=0.45,
            cost_output=2.25,
            context_window=1_000_000,
            specialties=["Programming", "Visual coding", "Code generation", "Debugging"],
            use_cases=["Complex code generation", "Visual analysis (screenshots)", "System integration", "Senior-level code review"],
            programming_rank=1,
        ),
        HexaCoreRole.JUNIOR_BUILDER: ModelInfo(
            id="minimax/minimax-m2.1",
            role=HexaCoreRole.JUNIOR_BUILDER,
            provider="MiniMax",
            country="CN",
            cost_input=0.27,
            cost_output=0.95,
            context_window=200_000,
            specialties=["Programming", "Unit tests", "JSON formatting"],
            use_cases=["Routine code generation", "Unit test writing", "JSON schema generation", "Simple automation scripts"],
            programming_rank=2,
        ),
        HexaCoreRole.SPECIALIST: ModelInfo(
            id="google/gemini-3-flash",
            role=HexaCoreRole.SPECIALIST,
            provider="Google",
            country="US",
            cost_input=0.50,
            cost_output=3.00,
            context_window=1_000_000,
            specialties=["Finance", "Health", "Speed", "Multimodal"],
            use_cases=["Financial calculations", "Health data analysis", "Real-time low-latency tasks", "Image + text multimodal analysis"],
        ),
        HexaCoreRole.LIBRARIAN: ModelInfo(
            id="x-ai/grok-4.1-fast",
            role=HexaCoreRole.LIBRARIAN,
            provider="xAI",
            country="US",
            cost_input=0.20,
            cost_output=0.50,
            context_window=2_000_000,
            specialties=["Long context", "Science", "Memory", "RAG"],
            use_cases=["RAG systems (long document retrieval)", "Scientific analysis", "Multi-document synthesis", "DelentiaDB context window tasks"],
            reasoning_rank=3,
        ),
        HexaCoreRole.HUMANIZER: ModelInfo(
            id="deepseek/deepseek-v3.2",
            role=HexaCoreRole.HUMANIZER,
            provider="DeepSeek",
            country="CN",
            cost_input=0.25,
            cost_output=0.38,
            context_window=200_000,
            specialties=["Roleplay", "Natural language", "Creative writing", "Translation"],
            use_cases=["User chat (natural conversation)", "General translation", "Creative content generation", "Empathetic response writing"],
            reasoning_rank=2,
        ),
        HexaCoreRole.REGIONAL_THAI: ModelInfo(
            id="scb10x/typhoon-v2-70b-instruct",
            role=HexaCoreRole.REGIONAL_THAI,
            provider="SCB10X",
            country="TH",
            cost_input=0.40,
            cost_output=1.20,
            context_window=128_000,
            specialties=["Thai NLP", "Thai culture", "Thai legal", "Thai finance", "Translation TH"],
            use_cases=["Thai language tasks (native quality)", "Thai legal/financial document analysis", "TH-EN translation", "Thai culture-aware dialogue"],
            reasoning_rank=None,
        ),
        HexaCoreRole.OLLAMA_ADAPTER: ModelInfo(
            id="ollama/llama-3.1-8b-instruct",
            role=HexaCoreRole.OLLAMA_ADAPTER,
            provider="Ollama",
            country="LOCAL",
            cost_input=0.0,
            cost_output=0.0,
            context_window=128_000,
            specialties=["Local inference", "Offline", "Privacy", "Edge deployment"],
            use_cases=["Air-gapped environments", "Cost-zero fallback", "Privacy-sensitive tasks", "Edge/offline inference"],
            reasoning_rank=None,
        ),
        HexaCoreRole.GROQ_ADAPTER: ModelInfo(
            id="groq/llama-3.3-70b-versatile",
            role=HexaCoreRole.GROQ_ADAPTER,
            provider="Groq",
            country="US",
            cost_input=0.59,
            cost_output=0.79,
            context_window=128_000,
            specialties=["Ultra-low latency", "LPU inference", "High throughput", "Real-time"],
            use_cases=["Real-time streaming responses", "High-throughput pipelines", "Low-latency agent loops", "Token-per-second sensitive workloads"],
            reasoning_rank=None,
        ),
    }

    @classmethod
    def get_model(cls, role: HexaCoreRole) -> ModelInfo:
        return cls.MODELS[role]

    @classmethod
    def get_model_id(cls, role: HexaCoreRole) -> str:
        """Return the OpenRouter model ID for *role*."""
        return cls.MODELS[role].id

    @classmethod
    def estimate_cost(cls, role: HexaCoreRole, input_tokens: int, output_tokens: int) -> float:
        """Estimate USD cost for one request to *role*."""
        model = cls.MODELS[role]
        return (input_tokens / 1_000_000) * model.cost_input + (output_tokens / 1_000_000) * model.cost_output

    @classmethod
    def get_geopolitical_balance(cls) -> Dict[str, int]:
        """Return count of models per country."""
        balance: Dict[str, int] = {}
        for model in cls.MODELS.values():
            balance[model.country] = balance.get(model.country, 0) + 1
        return balance

    @classmethod
    def get_cheapest_coder(cls) -> ModelInfo:
        """Return the most cost-effective coding model."""
        return cls.MODELS[HexaCoreRole.JUNIOR_BUILDER]

    @classmethod
    def get_smartest(cls) -> ModelInfo:
        """Return the highest-capability reasoning model."""
        return cls.MODELS[HexaCoreRole.SUPREME_ARCHITECT]

    @classmethod
    def get_longest_context(cls) -> ModelInfo:
        """Return the model with the largest context window."""
        return cls.MODELS[HexaCoreRole.LIBRARIAN]

    @classmethod
    def get_models_by_country(cls, country: str) -> List[ModelInfo]:
        """Return all models from a given country code (e.g. 'US', 'CN', 'TH')."""
        return [m for m in cls.MODELS.values() if m.country == country]


# ---------------------------------------------------------------------------
# SignedAI Tier Definitions
# ---------------------------------------------------------------------------

class SignedAITier(str, Enum):
    """Four-tier consensus system."""
    TIER_S = "tier_s"   # 1 signer  — fast, low-cost
    TIER_4 = "tier_4"   # 4 signers — 2 West + 2 East
    TIER_6 = "tier_6"   # 6 signers — 3 West + 3 East (production default)
    TIER_8 = "tier_8"   # 8 signers — Tier 6 + Chairman + Reasoner (God Mode)


class RiskLevel(str, Enum):
    """Risk classification used for automatic tier selection."""
    LOW = "low"         # → TIER_S
    MEDIUM = "medium"   # → TIER_4
    HIGH = "high"       # → TIER_6
    CRITICAL = "critical"  # → TIER_8


class TierConfig(BaseModel):
    """Per-tier consensus configuration."""
    tier: SignedAITier
    signers: List[HexaCoreRole] = Field(description="Models that vote in this tier")
    required_votes: int
    chairman_veto: bool = False
    west_count: int
    east_count: int
    cost_multiplier: float
    recommended_for: List[str] = Field(default_factory=list)


class ConsensusResult(BaseModel):
    """Result of a completed consensus vote."""
    tier: SignedAITier
    total_votes: int
    votes_for: int
    votes_against: int
    consensus_reached: bool
    confidence: float = Field(description="Fraction of votes for (0–1)")
    cost_usd: float
    signers: List[str] = Field(description="Model IDs that participated")


class SignedAIRegistry:
    """
    Registry for SignedAI consensus configurations and cost estimation.

    Tier selection guide:
    - TIER_S  : Chat, simple queries, low-stakes
    - TIER_4  : Code review, API design, standard deployments
    - TIER_6  : Production releases, DB migrations, security-critical
    - TIER_8  : Architecture changes, crisis management, legal decisions
    """

    TIERS: Dict[SignedAITier, TierConfig] = {
        SignedAITier.TIER_S: TierConfig(
            tier=SignedAITier.TIER_S,
            signers=[HexaCoreRole.HUMANIZER],
            required_votes=1,
            chairman_veto=False,
            west_count=0,
            east_count=1,
            cost_multiplier=1.0,
            recommended_for=["User chat", "Simple queries", "Low-risk decisions"],
        ),
        SignedAITier.TIER_4: TierConfig(
            tier=SignedAITier.TIER_4,
            signers=[
                HexaCoreRole.SUPREME_ARCHITECT,
                HexaCoreRole.SPECIALIST,
                HexaCoreRole.LEAD_BUILDER,
                HexaCoreRole.HUMANIZER,
            ],
            required_votes=3,
            chairman_veto=False,
            west_count=2,
            east_count=2,
            cost_multiplier=4.0,
            recommended_for=["Code review", "API design", "Standard deployments"],
        ),
        SignedAITier.TIER_6: TierConfig(
            tier=SignedAITier.TIER_6,
            signers=[
                HexaCoreRole.SUPREME_ARCHITECT,
                HexaCoreRole.SPECIALIST,
                HexaCoreRole.LIBRARIAN,
                HexaCoreRole.LEAD_BUILDER,
                HexaCoreRole.JUNIOR_BUILDER,
                HexaCoreRole.HUMANIZER,
            ],
            required_votes=4,
            chairman_veto=False,
            west_count=3,
            east_count=3,
            cost_multiplier=6.0,
            recommended_for=["Production releases", "DB migrations", "Security-critical code"],
        ),
        SignedAITier.TIER_8: TierConfig(
            tier=SignedAITier.TIER_8,
            signers=[
                HexaCoreRole.SUPREME_ARCHITECT,
                HexaCoreRole.SPECIALIST,
                HexaCoreRole.LIBRARIAN,
                HexaCoreRole.LEAD_BUILDER,
                HexaCoreRole.JUNIOR_BUILDER,
                HexaCoreRole.HUMANIZER,
            ],
            required_votes=6,
            chairman_veto=True,
            west_count=3,
            east_count=3,
            cost_multiplier=8.0,
            recommended_for=["Architecture changes", "Crisis management", "Legal decisions"],
        ),
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def get_tier(cls, tier: SignedAITier) -> TierConfig:
        """Return configuration for *tier*."""
        return cls.TIERS[tier]

    @classmethod
    def get_tier_config(cls, tier) -> TierConfig:
        """Alias for get_tier(). Accepts SignedAITier or TierLevel (models.py) enum."""
        # TierLevel uses hyphens ("tier-4"); SignedAITier uses underscores ("tier_4")
        if not isinstance(tier, SignedAITier):
            normalized = str(tier.value).replace("-", "_")
            tier = SignedAITier(normalized)
        return cls.get_tier(tier)

    @classmethod
    def get_tier_by_risk(cls, risk: RiskLevel) -> TierConfig:
        """Return the appropriate tier config for *risk*."""
        mapping = {
            RiskLevel.LOW: SignedAITier.TIER_S,
            RiskLevel.MEDIUM: SignedAITier.TIER_4,
            RiskLevel.HIGH: SignedAITier.TIER_6,
            RiskLevel.CRITICAL: SignedAITier.TIER_8,
        }
        return cls.TIERS[mapping[risk]]

    @classmethod
    def calculate_consensus(
        cls,
        tier: SignedAITier,
        votes_for: int,
        votes_against: int,
        chairman_override: Optional[bool] = None,
    ) -> ConsensusResult:
        """
        Calculate whether consensus is reached.

        Args:
            tier: Consensus tier.
            votes_for: Votes in favour.
            votes_against: Votes against.
            chairman_override: When ``True``/``False`` applies chairman veto
                (Tier 8 only; ignored otherwise).

        Returns:
            :class:`ConsensusResult`
        """
        config = cls.get_tier(tier)
        total_votes = votes_for + votes_against

        if config.chairman_veto and chairman_override is not None:
            consensus = chairman_override
            confidence = 1.0 if chairman_override else 0.0
        else:
            consensus = votes_for >= config.required_votes
            confidence = (votes_for / total_votes) if total_votes > 0 else 0.0

        avg_cost_per_call = 0.001  # rough estimate per signer request
        cost = len(config.signers) * avg_cost_per_call * config.cost_multiplier

        return ConsensusResult(
            tier=tier,
            total_votes=total_votes,
            votes_for=votes_for,
            votes_against=votes_against,
            consensus_reached=consensus,
            confidence=confidence,
            cost_usd=cost,
            signers=[HexaCoreRegistry.get_model_id(role) for role in config.signers],
        )

    @classmethod
    def estimate_tier_cost(
        cls,
        tier: SignedAITier,
        input_tokens: int,
        output_tokens: int,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Estimate total USD cost to run a consensus round for *tier*.

        Returns:
            ``(total_cost, breakdown_by_model_id)``
        """
        config = cls.get_tier(tier)
        breakdown: Dict[str, float] = {}
        total = 0.0
        for role in config.signers:
            cost = HexaCoreRegistry.estimate_cost(role, input_tokens, output_tokens)
            model_id = HexaCoreRegistry.get_model_id(role)
            breakdown[model_id] = breakdown.get(model_id, 0.0) + cost
            total += cost
        return total, breakdown


__all__ = [
    "HexaCoreRole",
    "ModelInfo",
    "HexaCoreRegistry",
    "SignedAITier",
    "RiskLevel",
    "TierConfig",
    "ConsensusResult",
    "SignedAIRegistry",
]

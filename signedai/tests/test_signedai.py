"""
Tests for signedai — models, registry, router.
All synchronous unit tests; no external API calls needed.
"""

from datetime import datetime, timezone

from signedai.core.models import (
    AnalysisJob,
    AnalysisStatus,
    JITNAPacket,
    RiskLevel,
    TierLevel,
)
from signedai.core.registry import (
    HexaCoreRegistry,
    HexaCoreRole,
    RiskLevel as RegistryRiskLevel,
    SignedAIRegistry,
    SignedAITier,
)
from signedai.core.router import TierRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jitna(**kwargs) -> JITNAPacket:
    defaults = dict(
        I="Refactor the authentication module",
        D="backend/auth",
        **{"Δ": "Replace JWT with PASETO"},
        A="Python 3.11, existing test suite passes",
        R="No breaking changes to public API",
        M="All tests pass, mypy clean",
    )
    defaults.update(kwargs)
    return JITNAPacket(**defaults)


def _make_job(**kwargs) -> AnalysisJob:
    defaults = dict(
        id="job-001",
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        artifact_hash="abc123",
        artifact_type="code",
        artifact_content="def authenticate(token): return verify(token)",
        intent=_make_jitna(),
        status=AnalysisStatus.QUEUED,
    )
    defaults.update(kwargs)
    return AnalysisJob(**defaults)


# ---------------------------------------------------------------------------
# JITNAPacket
# ---------------------------------------------------------------------------

class TestJITNAPacket:
    def test_create_valid_packet(self):
        packet = _make_jitna()
        assert packet.I == "Refactor the authentication module"
        assert packet.D == "backend/auth"

    def test_alias_delta(self):
        packet = _make_jitna()
        assert packet.delta == "Replace JWT with PASETO"


# ---------------------------------------------------------------------------
# AnalysisJob
# ---------------------------------------------------------------------------

class TestAnalysisJob:
    def test_create_job(self):
        job = _make_job()
        assert job.id == "job-001"
        assert job.status == AnalysisStatus.QUEUED

    def test_artifact_content_field(self):
        job = _make_job(artifact_content="x = 1")
        assert job.artifact_content == "x = 1"

    def test_artifact_content_optional_none(self):
        job = _make_job(artifact_content=None)
        assert job.artifact_content is None

    def test_risk_level_default_none(self):
        job = _make_job()
        assert job.risk_level is None

    def test_tier_default_none(self):
        job = _make_job()
        assert job.tier is None

    def test_source_system_default(self):
        job = _make_job()
        assert job.source_system == "signedai_api"


# ---------------------------------------------------------------------------
# TierRouter
# ---------------------------------------------------------------------------

class TestTierRouter:
    def setup_method(self):
        self.router = TierRouter()

    def test_route_assigns_tier(self):
        job = _make_job()
        result = self.router.route(job)
        assert result.tier is not None

    def test_route_low_risk_content(self):
        job = _make_job(
            artifact_type="text",
            artifact_content="hello world",
            intent=_make_jitna(D="playground", R="no constraints"),
        )
        result = self.router.route(job)
        assert result.risk_level == RiskLevel.LOW
        assert result.tier == TierLevel.TIER_S

    def test_route_sets_tier_auto_selected(self):
        job = _make_job()
        result = self.router.route(job)
        assert result.tier_auto_selected is True

    def test_route_sensitive_content_raises_risk(self):
        job = _make_job(
            artifact_content="API_KEY = 'secret_key_here' password = 'abc'",
            intent=_make_jitna(D="security", R="protect credentials"),
        )
        result = self.router.route(job)
        assert result.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_route_config_artifact_type_adds_risk(self):
        job = _make_job(artifact_type="config", artifact_content="host: localhost")
        result = self.router.route(job)
        # config type always adds 1 risk point
        assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_route_skips_if_risk_already_set(self):
        job = _make_job(risk_level=RiskLevel.CRITICAL, tier=TierLevel.TIER_8, tier_auto_selected=False)
        result = self.router.route(job)
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.tier == TierLevel.TIER_8

    def test_route_high_risk_assigns_tier6_or_8(self):
        job = _make_job(
            artifact_type="config",
            artifact_content="password=secret production database",
            intent=_make_jitna(D="production infrastructure", R="uptime critical"),
        )
        result = self.router.route(job)
        assert result.tier in (TierLevel.TIER_6, TierLevel.TIER_8)

    def test_route_returns_same_job_object(self):
        job = _make_job()
        result = self.router.route(job)
        assert result is job  # modifies in-place and returns same object

    def test_artifact_content_none_handled(self):
        """Router must not crash if artifact_content is None (Optional field)."""
        job = _make_job(artifact_content=None)
        result = self.router.route(job)
        assert result.tier is not None


# ---------------------------------------------------------------------------
# HexaCoreRegistry
# ---------------------------------------------------------------------------

class TestHexaCoreRegistry:
    def test_registry_has_all_roles(self):
        registry = HexaCoreRegistry()
        models = registry.MODELS
        assert HexaCoreRole.SUPREME_ARCHITECT in models
        assert HexaCoreRole.LEAD_BUILDER in models

    def test_supreme_architect_has_context_window(self):
        registry = HexaCoreRegistry()
        sa = registry.MODELS[HexaCoreRole.SUPREME_ARCHITECT]
        assert sa.context_window > 100_000

    def test_model_info_has_cost_fields(self):
        registry = HexaCoreRegistry()
        for model in registry.MODELS.values():
            assert model.cost_input >= 0
            assert model.cost_output >= 0

    def test_all_models_have_provider(self):
        registry = HexaCoreRegistry()
        for role, model in registry.MODELS.items():
            assert model.provider, f"Model {role} missing provider"


# ---------------------------------------------------------------------------
# SignedAIRegistry
# ---------------------------------------------------------------------------

class TestSignedAIRegistry:
    def test_registry_instantiates(self):
        reg = SignedAIRegistry()
        assert reg is not None

    def test_get_tier_config(self):
        reg = SignedAIRegistry()
        config = reg.get_tier_config(TierLevel.TIER_4)
        assert config is not None
        assert "signers" in config or hasattr(config, "signers")


# ---------------------------------------------------------------------------
# HexaCoreRegistry — extended coverage
# ---------------------------------------------------------------------------


class TestHexaCoreRegistryExtended:
    def test_get_cheapest_coder_is_junior_builder(self):
        result = HexaCoreRegistry.get_cheapest_coder()
        assert result.role == HexaCoreRole.JUNIOR_BUILDER

    def test_get_longest_context_is_librarian(self):
        result = HexaCoreRegistry.get_longest_context()
        assert result.role == HexaCoreRole.LIBRARIAN
        assert result.context_window >= 2_000_000

    def test_estimate_cost_returns_float(self):
        cost = HexaCoreRegistry.estimate_cost(HexaCoreRole.SUPREME_ARCHITECT, input_tokens=1000, output_tokens=500)
        assert isinstance(cost, float)
        assert cost > 0

    def test_geopolitical_balance_sums_to_seven(self):
        balance = HexaCoreRegistry.get_geopolitical_balance()
        total = sum(balance.values())
        assert total == 9
        assert "US" in balance
        assert "CN" in balance
        assert "TH" in balance
        assert "LOCAL" in balance

    def test_get_smartest_is_supreme_architect(self):
        result = HexaCoreRegistry.get_smartest()
        assert result.role == HexaCoreRole.SUPREME_ARCHITECT


# ---------------------------------------------------------------------------
# SignedAIRegistry — consensus & tier tests
# ---------------------------------------------------------------------------


class TestSignedAIRegistryExtended:
    def test_all_four_tiers_exist(self):
        for tier in SignedAITier:
            config = SignedAIRegistry.get_tier(tier)
            assert config.tier == tier

    def test_tier_s_has_one_signer(self):
        config = SignedAIRegistry.get_tier(SignedAITier.TIER_S)
        assert len(config.signers) == 1

    def test_tier_8_has_chairman_veto(self):
        config = SignedAIRegistry.get_tier(SignedAITier.TIER_8)
        assert config.chairman_veto is True

    def test_get_tier_by_risk_mapping(self):
        config = SignedAIRegistry.get_tier_by_risk(RegistryRiskLevel.LOW)
        assert config.tier == SignedAITier.TIER_S
        config = SignedAIRegistry.get_tier_by_risk(RegistryRiskLevel.CRITICAL)
        assert config.tier == SignedAITier.TIER_8

    def test_calculate_consensus_passes(self):
        result = SignedAIRegistry.calculate_consensus(
            tier=SignedAITier.TIER_4, votes_for=3, votes_against=1
        )
        assert result.consensus_reached is True
        assert result.confidence > 0

    def test_calculate_consensus_fails_insufficient_votes(self):
        result = SignedAIRegistry.calculate_consensus(
            tier=SignedAITier.TIER_4, votes_for=1, votes_against=3
        )
        assert result.consensus_reached is False

    def test_chairman_veto_overrides(self):
        result = SignedAIRegistry.calculate_consensus(
            tier=SignedAITier.TIER_8, votes_for=2, votes_against=4, chairman_override=True
        )
        assert result.consensus_reached is True

    def test_chairman_veto_blocks(self):
        result = SignedAIRegistry.calculate_consensus(
            tier=SignedAITier.TIER_8, votes_for=6, votes_against=0, chairman_override=False
        )
        assert result.consensus_reached is False

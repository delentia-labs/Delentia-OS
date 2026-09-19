"""
Real tests for Round 32's consensus-threshold fix and TIER_7_REGIONAL.

Round 31's audit found no >=X% ratio check existed anywhere in
calculate_consensus() before this - only a raw votes_for >= required_votes
count. It also found REGIONAL_THAI (Thai model) was declared in the
registry but never included in any real tier's signers, despite the
design doc's "3 US, 3 CN, 1 Thai" description. These tests prove both
gaps are now genuinely closed, while confirming every pre-existing tier's
behavior (especially TIER_6's documented "4/6 bare majority" real demo
scenario in examples/signed_ai_demo.py) is unchanged (Zero-Delete).
"""

from signedai.core.registry import HexaCoreRole, SignedAIRegistry, SignedAITier


class TestExistingTierBehaviorUnchanged:
    """Zero-Delete proof: every pre-Round-32 real test scenario still
    produces the same consensus_reached result."""

    def test_tier4_3_of_4_still_passes_at_exactly_75_percent(self):
        # Pre-existing real test scenario (test_signedai.py::test_calculate_consensus_passes)
        result = SignedAIRegistry.calculate_consensus(tier=SignedAITier.TIER_4, votes_for=3, votes_against=1)
        assert result.consensus_reached is True

    def test_tier4_1_of_4_still_fails(self):
        result = SignedAIRegistry.calculate_consensus(tier=SignedAITier.TIER_4, votes_for=1, votes_against=3)
        assert result.consensus_reached is False

    def test_tier8_chairman_override_true_still_passes(self):
        result = SignedAIRegistry.calculate_consensus(
            tier=SignedAITier.TIER_8, votes_for=2, votes_against=4, chairman_override=True,
        )
        assert result.consensus_reached is True

    def test_tier8_unanimous_6_of_6_with_no_chairman_override_passed_still_passes(self):
        # chairman_override left as the real default (None) - the vote-only
        # path this test targets, distinct from test_chairman_veto_blocks's
        # explicit chairman_override=False (a real veto denial, unaffected
        # by this round's ratio-threshold change either way).
        result = SignedAIRegistry.calculate_consensus(
            tier=SignedAITier.TIER_8, votes_for=6, votes_against=0,
        )
        assert result.consensus_reached is True

    def test_tier6_documented_bare_majority_4_of_6_still_passes(self):
        # Matches examples/signed_ai_demo.py's real "Bare majority (4/6)" scenario -
        # 4/6 ~= 66.7%, below the new 0.75 default, so TIER_6 must have its
        # own explicit consensus_threshold preserving this real behavior.
        result = SignedAIRegistry.calculate_consensus(tier=SignedAITier.TIER_6, votes_for=4, votes_against=2)
        assert result.consensus_reached is True

    def test_tier6_failed_consensus_3_of_6_still_fails(self):
        # Matches examples/signed_ai_demo.py's real "Failed consensus (3/6)" scenario.
        result = SignedAIRegistry.calculate_consensus(tier=SignedAITier.TIER_6, votes_for=3, votes_against=3)
        assert result.consensus_reached is False


class TestRealThresholdCheckDoesRealWork:
    def test_tier7_regional_has_seven_signers_including_thai(self):
        config = SignedAIRegistry.get_tier(SignedAITier.TIER_7_REGIONAL)
        assert len(config.signers) == 7
        assert HexaCoreRole.REGIONAL_THAI in config.signers

    def test_tier7_regional_6_of_7_reaches_real_75_percent_consensus(self):
        result = SignedAIRegistry.calculate_consensus(tier=SignedAITier.TIER_7_REGIONAL, votes_for=6, votes_against=1)
        assert result.consensus_reached is True
        assert result.confidence >= 0.75

    def test_tier7_regional_meets_required_votes_but_fails_the_real_ratio_check(self):
        # Construct a case that isolates the NEW ratio check: required_votes=6,
        # so votes_for=6 alone would have passed under the OLD vote-count-only
        # logic regardless of votes_against. Adding enough votes_against to
        # drop the ratio below 0.75 must now fail where it previously would
        # not even have been checked.
        result = SignedAIRegistry.calculate_consensus(tier=SignedAITier.TIER_7_REGIONAL, votes_for=6, votes_against=3)
        # 6/9 = 0.667, below the real 0.75 threshold, even though votes_for(6) >= required_votes(6)
        assert result.confidence < 0.75
        assert result.consensus_reached is False

    def test_tier_s_and_tier_4_configs_expose_a_real_consensus_threshold_field(self):
        for tier in [SignedAITier.TIER_S, SignedAITier.TIER_4, SignedAITier.TIER_8]:
            config = SignedAIRegistry.get_tier(tier)
            assert 0.0 < config.consensus_threshold <= 1.0

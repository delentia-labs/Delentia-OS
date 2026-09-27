"""
Round 45 item C (test coverage continuation): real tests for ALGO-30's
Adaptive Belief Validation engine - 0% coverage before this file. Pure
Python/pydantic/numpy math (Bayes' theorem, confidence scoring, Shannon
entropy, bootstrap/Monte Carlo uncertainty) - no external services, no
mocking needed anywhere in this module.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import math
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from rct_control_plane.algo_30_abv import (
    EvidenceType, EvidenceStrength, ConfidenceLevel, DecisionType,
    Evidence, BayesianParameters, ConfidenceFactors, UncertaintyMetrics, ThresholdConfig,
    ValidateBeliefRequest,
    BayesianEngine, ConfidenceCalculator, EvidenceEvaluator, UncertaintyQuantifier, ABVEngine,
    beta_distribution_prior, update_beta_distribution, sigmoid,
)


def _evidence(**overrides):
    defaults = dict(
        type=EvidenceType.DIRECT, source="witness_a", credibility=0.8,
        content="a real observed fact", relevance_score=0.0,
    )
    defaults.update(overrides)
    return Evidence(**defaults)


class TestSchemaValidators:
    def test_evidence_credibility_out_of_range_is_rejected(self):
        with pytest.raises(ValidationError):
            _evidence(credibility=1.5)

    def test_bayesian_parameters_zero_marginal_is_rejected(self):
        with pytest.raises(ValidationError):
            BayesianParameters(prior=0.5, likelihood=0.5, marginal=0.0, posterior=0.5)

    def test_confidence_factors_weights_must_sum_to_one(self):
        with pytest.raises(ValidationError):
            ConfidenceFactors(
                bayesian_posterior=0.5, source_credibility=0.5, evidence_strength=0.5,
                cross_verification=0.5, temporal_relevance=0.5,
                weights={"bayesian_posterior": 0.5, "source_credibility": 0.1,
                         "evidence_strength": 0.1, "cross_verification": 0.1, "temporal_relevance": 0.1},
            )

    def test_uncertainty_metrics_interval_must_be_ordered_and_bounded(self):
        with pytest.raises(ValidationError):
            UncertaintyMetrics(confidence_interval=[0.8, 0.2], standard_deviation=0.1, entropy=0.1, variance=0.01)

    def test_validate_belief_request_requires_at_least_one_evidence(self):
        with pytest.raises(ValidationError):
            ValidateBeliefRequest(belief="a real belief statement", evidence=[])


class TestThresholdConfig:
    def test_default_thresholds_ordering_is_valid(self):
        cfg = ThresholdConfig()
        assert cfg.high > cfg.moderate > cfg.low

    def test_moderate_must_be_less_than_high(self):
        with pytest.raises(ValidationError):
            ThresholdConfig(high=0.8, moderate=0.9, low=0.5)

    def test_low_must_be_less_than_moderate(self):
        with pytest.raises(ValidationError):
            ThresholdConfig(high=0.9, moderate=0.5, low=0.6)

    @pytest.mark.parametrize("score,level,decision", [
        (0.96, ConfidenceLevel.HIGH, DecisionType.ACCEPT),
        (0.85, ConfidenceLevel.MODERATE, DecisionType.REVIEW),
        (0.65, ConfidenceLevel.LOW, DecisionType.INVESTIGATE),
        (0.10, ConfidenceLevel.VERY_LOW, DecisionType.REJECT),
    ])
    def test_get_level_and_decision_cover_every_band(self, score, level, decision):
        cfg = ThresholdConfig()
        assert cfg.get_level(score) == level
        assert cfg.get_decision(score) == decision


class TestConfidenceFactorsWeightedScore:
    def test_weighted_score_matches_manual_calculation(self):
        factors = ConfidenceFactors(
            bayesian_posterior=1.0, source_credibility=1.0, evidence_strength=1.0,
            cross_verification=1.0, temporal_relevance=1.0,
        )
        assert factors.calculate_weighted_score() == pytest.approx(1.0)

    def test_weighted_score_is_clamped_to_one(self):
        factors = ConfidenceFactors(
            bayesian_posterior=1.0, source_credibility=1.0, evidence_strength=1.0,
            cross_verification=1.0, temporal_relevance=1.0,
            weights={"bayesian_posterior": 0.5, "source_credibility": 0.5,
                     "evidence_strength": 0.5, "cross_verification": -0.5, "temporal_relevance": 0.0},
        )
        # weights here don't sum to 1.0 within tolerance? they do: 0.5+0.5+0.5-0.5+0.0=1.0
        assert factors.calculate_weighted_score() <= 1.0


class TestModuleLevelHelpers:
    def test_beta_distribution_prior_is_the_mean(self):
        assert beta_distribution_prior(alpha=2, beta=2) == pytest.approx(0.5)
        assert beta_distribution_prior(alpha=8, beta=2) == pytest.approx(0.8)

    def test_update_beta_distribution_success_increments_alpha(self):
        assert update_beta_distribution(1, 1, success=True) == (2, 1)

    def test_update_beta_distribution_failure_increments_beta(self):
        assert update_beta_distribution(1, 1, success=False) == (1, 2)

    def test_sigmoid_at_midpoint_is_half(self):
        assert sigmoid(0.5, midpoint=0.5, steepness=10) == pytest.approx(0.5)

    def test_sigmoid_saturates_toward_extremes(self):
        assert sigmoid(1.0, midpoint=0.5, steepness=10) > 0.99
        assert sigmoid(0.0, midpoint=0.5, steepness=10) < 0.01


class TestBayesianEnginePriorAndLikelihood:
    @pytest.fixture
    def engine(self):
        return BayesianEngine()

    def test_calculate_prior_uses_historical_data_for_known_domain(self, engine):
        assert engine.calculate_prior("legal", {"legal": 0.7}) == 0.7

    def test_calculate_prior_falls_back_to_default(self, engine):
        assert engine.calculate_prior("unknown_domain", {"legal": 0.7}) == engine.default_prior

    def test_calculate_prior_is_clamped_to_min_max(self, engine):
        assert engine.calculate_prior("x", {"x": 5.0}) == engine.max_prior
        assert engine.calculate_prior("x", {"x": -5.0}) == engine.min_prior

    def test_likelihood_uses_explicit_strength_when_given(self, engine):
        ev = _evidence(strength=EvidenceStrength.VERY_STRONG, credibility=0.9)
        likelihood = engine.calculate_likelihood(ev)
        assert 0.01 <= likelihood <= 0.99

    def test_likelihood_infers_strength_from_credibility_when_not_given(self, engine):
        weak_ev = _evidence(credibility=0.2)
        strong_ev = _evidence(credibility=0.95)
        assert engine.calculate_likelihood(weak_ev) < engine.calculate_likelihood(strong_ev)

    def test_likelihood_for_contradicting_evidence_is_inverted(self, engine):
        ev = _evidence(credibility=0.9, strength=EvidenceStrength.VERY_STRONG)
        supporting = engine.calculate_likelihood(ev, supporting=True)
        contradicting = engine.calculate_likelihood(ev, supporting=False)
        assert contradicting == pytest.approx(1.0 - supporting)

    def test_relevance_score_scales_down_likelihood(self, engine):
        base = _evidence(credibility=0.9, strength=EvidenceStrength.VERY_STRONG, relevance_score=0.0)
        scaled = _evidence(credibility=0.9, strength=EvidenceStrength.VERY_STRONG, relevance_score=0.5)
        assert engine.calculate_likelihood(scaled) < engine.calculate_likelihood(base)


class TestBayesianEngineMarginalAndPosterior:
    @pytest.fixture
    def engine(self):
        return BayesianEngine()

    def test_marginal_never_goes_to_exact_zero(self, engine):
        assert engine.calculate_marginal(likelihood=0.0, prior=0.0, likelihood_neg=0.0) == 0.0001

    def test_posterior_matches_bayes_theorem_by_hand(self, engine):
        # P(H|E) = P(E|H) x P(H) / P(E)
        posterior = engine.calculate_posterior(likelihood=0.8, prior=0.5, marginal=0.6)
        assert posterior == pytest.approx((0.8 * 0.5) / 0.6)

    def test_posterior_guards_against_zero_marginal(self, engine):
        posterior = engine.calculate_posterior(likelihood=0.8, prior=0.5, marginal=0.0)
        assert 0.0 <= posterior <= 1.0

    def test_posterior_is_clamped_to_unit_interval(self, engine):
        assert engine.calculate_posterior(likelihood=10.0, prior=10.0, marginal=0.0001) == 1.0


class TestBayesianEngineUpdateBelief:
    @pytest.fixture
    def engine(self):
        return BayesianEngine()

    def test_supporting_strong_evidence_raises_posterior_above_prior(self, engine):
        ev = _evidence(credibility=0.95, strength=EvidenceStrength.VERY_STRONG, type=EvidenceType.DIRECT)
        params = engine.update_belief_single(prior=0.5, evidence=ev, supporting=True)
        assert params.posterior > 0.5

    def test_contradicting_strong_evidence_lowers_posterior_below_prior(self, engine):
        ev = _evidence(credibility=0.95, strength=EvidenceStrength.VERY_STRONG, type=EvidenceType.DIRECT)
        params = engine.update_belief_single(prior=0.5, evidence=ev, supporting=False)
        assert params.posterior < 0.5

    def test_update_belief_multiple_chains_posterior_into_next_prior(self, engine):
        evs = [_evidence(credibility=0.9) for _ in range(3)]
        final_posterior, params_list = engine.update_belief_multiple(0.5, evs)
        assert len(params_list) == 3
        # Each step's output prior feeds the next step's input prior.
        assert params_list[1].prior == params_list[0].posterior
        assert params_list[2].prior == params_list[1].posterior
        assert final_posterior == params_list[-1].posterior

    def test_update_belief_multiple_with_no_evidence_returns_prior_unchanged(self, engine):
        posterior, params_list = engine.update_belief_multiple(0.5, [])
        assert posterior == 0.5
        assert params_list == []

    def test_mismatched_supporting_flags_length_raises(self, engine):
        with pytest.raises(ValueError):
            engine.update_belief_multiple(0.5, [_evidence()], supporting_flags=[True, False])

    def test_weighted_posterior_with_no_params_returns_default_prior(self, engine):
        assert engine.calculate_weighted_posterior([], []) == engine.default_prior


class TestBayesianEngineIntegrateEvidence:
    @pytest.fixture
    def engine(self):
        return BayesianEngine()

    @pytest.fixture
    def evidence_list(self):
        return [_evidence(credibility=0.9), _evidence(credibility=0.7, source="witness_b")]

    def test_sequential_method_chains_through_update_belief_multiple(self, engine, evidence_list):
        posterior, params = engine.integrate_evidence(0.5, evidence_list, method="sequential")
        assert len(params) == 2
        assert 0.0 <= posterior <= 1.0

    def test_weighted_method_uses_the_same_prior_for_every_item(self, engine, evidence_list):
        posterior, params = engine.integrate_evidence(0.5, evidence_list, method="weighted")
        assert all(p.prior == 0.5 for p in params)

    def test_independent_method_combines_odds_multiplicatively(self, engine, evidence_list):
        posterior, params = engine.integrate_evidence(0.5, evidence_list, method="independent")
        assert len(params) == 2
        assert 0.0 <= posterior <= 1.0

    def test_empty_evidence_list_returns_prior_unchanged_for_any_method(self, engine):
        assert engine.integrate_evidence(0.5, [], method="sequential") == (0.5, [])

    def test_unknown_method_raises(self, engine, evidence_list):
        with pytest.raises(ValueError, match="Unknown integration method"):
            engine.integrate_evidence(0.5, evidence_list, method="bogus")


class TestBayesianEngineMonteCarloAndCI:
    @pytest.fixture
    def engine(self):
        return BayesianEngine()

    def test_monte_carlo_sampling_returns_bounded_posteriors(self, engine):
        mean, std, samples = engine.monte_carlo_sampling((0.5, 0.1), (0.7, 0.1), n_samples=500)
        assert 0.0 <= mean <= 1.0
        assert std >= 0.0
        assert len(samples) == 500
        assert all(0.0 <= s <= 1.0 for s in samples)

    @pytest.mark.parametrize("level,expected_z", [(0.95, 1.96), (0.99, 2.576), (0.90, 1.645), (0.80, 1.96)])
    def test_confidence_interval_uses_the_right_z_score_per_level(self, engine, level, expected_z):
        # posterior=0.5, n=20 keeps the margin well inside [0, 1] for every
        # z-score tested here, so the [0,1] clamp never masks the real
        # per-level z-score difference this test is checking for.
        evs = [_evidence() for _ in range(20)]
        lower, upper = engine.calculate_confidence_interval(0.5, evs, confidence_level=level)
        se = math.sqrt(0.5 * 0.5 / 20)
        assert upper - lower == pytest.approx(2 * expected_z * se, rel=1e-3)

    def test_confidence_interval_with_no_evidence_is_the_full_range(self, engine):
        assert engine.calculate_confidence_interval(0.7, []) == (0.0, 1.0)


class TestBayesianEngineQualityAndConflicts:
    @pytest.fixture
    def engine(self):
        return BayesianEngine()

    def test_assess_evidence_quality_weights_credibility_most_heavily(self, engine):
        high = engine.assess_evidence_quality(_evidence(credibility=0.95, type=EvidenceType.DIRECT))
        low = engine.assess_evidence_quality(_evidence(credibility=0.2, type=EvidenceType.CIRCUMSTANTIAL))
        assert high["quality_score"] > low["quality_score"]

    def test_detect_conflicting_evidence_flags_different_type_and_large_credibility_gap(self, engine):
        evs = [
            _evidence(type=EvidenceType.DIRECT, credibility=0.95),
            _evidence(type=EvidenceType.CIRCUMSTANTIAL, credibility=0.2, source="witness_c"),
        ]
        conflicts = engine.detect_conflicting_evidence(evs, threshold=0.3)
        assert conflicts == [(0, 1, pytest.approx(0.75))]

    def test_detect_conflicting_evidence_finds_nothing_for_similar_evidence(self, engine):
        evs = [_evidence(credibility=0.8), _evidence(credibility=0.82, source="witness_b")]
        assert engine.detect_conflicting_evidence(evs) == []

    def test_information_gain_is_zero_at_boundary_probabilities(self, engine):
        assert engine.calculate_information_gain(prior=0.0, posterior=0.5) == 0.0
        assert engine.calculate_information_gain(prior=0.5, posterior=1.0) == 0.0

    def test_information_gain_is_positive_when_posterior_diverges_from_prior(self, engine):
        gain = engine.calculate_information_gain(prior=0.5, posterior=0.9)
        assert gain > 0.0


class TestConfidenceCalculator:
    def test_init_rejects_weights_that_dont_sum_to_one(self):
        with pytest.raises(ValueError, match="must sum to 1.0"):
            ConfidenceCalculator(weights={"bayesian_posterior": 0.5, "source_credibility": 0.1,
                                           "evidence_strength": 0.1, "cross_verification": 0.1,
                                           "temporal_relevance": 0.1})

    def test_source_credibility_score_weights_by_relevance(self):
        calc = ConfidenceCalculator()
        evs = [_evidence(credibility=0.9, relevance_score=1.0), _evidence(credibility=0.1, relevance_score=0.0, source="b")]
        score = calc.calculate_source_credibility_score(evs)
        assert 0.0 <= score <= 1.0

    def test_source_credibility_score_empty_list_is_neutral(self):
        assert ConfidenceCalculator().calculate_source_credibility_score([]) == 0.5

    def test_cross_verification_single_evidence_is_low_fixed_score(self):
        calc = ConfidenceCalculator()
        assert calc.calculate_cross_verification_score([_evidence()]) == 0.3

    def test_cross_verification_improves_with_diverse_sources_and_types(self):
        calc = ConfidenceCalculator()
        diverse = [
            _evidence(source="a", type=EvidenceType.DIRECT, credibility=0.9),
            _evidence(source="b", type=EvidenceType.STATISTICAL, credibility=0.9),
            _evidence(source="c", type=EvidenceType.EXPERT_OPINION, credibility=0.9),
        ]
        same = [_evidence(source="a", type=EvidenceType.DIRECT, credibility=0.9) for _ in range(3)]
        assert calc.calculate_cross_verification_score(diverse) > calc.calculate_cross_verification_score(same)

    def test_temporal_relevance_defaults_when_no_timestamp(self):
        calc = ConfidenceCalculator()
        assert calc.calculate_temporal_relevance_score([_evidence()]) == 0.7

    def test_temporal_relevance_decays_with_age(self):
        calc = ConfidenceCalculator()
        recent = _evidence(timestamp=datetime.now() - timedelta(days=1))
        old = _evidence(timestamp=datetime.now() - timedelta(days=365))
        assert (calc.calculate_temporal_relevance_score([recent])
                > calc.calculate_temporal_relevance_score([old]))

    def test_adjust_for_uncertainty_penalizes_when_risk_averse(self):
        calc = ConfidenceCalculator()
        assert calc.adjust_for_uncertainty(0.8, uncertainty_std=0.1, risk_averse=True) < 0.8

    def test_adjust_for_uncertainty_is_a_no_op_when_not_risk_averse(self):
        calc = ConfidenceCalculator()
        assert calc.adjust_for_uncertainty(0.8, uncertainty_std=0.5, risk_averse=False) == 0.8

    def test_confidence_growth_reports_improvement(self):
        calc = ConfidenceCalculator()
        growth = calc.calculate_confidence_growth(new_confidence=0.8, old_confidence=0.5)
        assert growth["improved"] is True
        assert growth["absolute_change"] == pytest.approx(0.3)
        assert growth["confidence_loss"] == 0

    def test_confidence_growth_with_zero_old_confidence_has_zero_relative_change(self):
        calc = ConfidenceCalculator()
        growth = calc.calculate_confidence_growth(new_confidence=0.5, old_confidence=0.0)
        assert growth["relative_change"] == 0.0

    def test_compare_confidence_levels(self):
        calc = ConfidenceCalculator()
        result = calc.compare_confidence_levels(0.9, 0.3)
        assert result["higher"] is True
        assert result["same_level"] is False

    def test_calibrate_confidence_with_no_data_returns_prediction_unchanged(self):
        calc = ConfidenceCalculator()
        assert calc.calibrate_confidence(0.8, True, calibration_data=None) == 0.8

    def test_calibrate_confidence_pulls_toward_observed_accuracy(self):
        calc = ConfidenceCalculator()
        # 10 prior predictions near 0.8 that were ALL wrong (outcome False)
        calibration_data = [(0.8, False)] * 10
        calibrated = calc.calibrate_confidence(0.8, True, calibration_data=calibration_data)
        assert calibrated < 0.8  # pulled down toward the observed 0% accuracy

    def test_explain_confidence_mentions_the_weakest_factor_when_low(self):
        calc = ConfidenceCalculator()
        factors = ConfidenceFactors(
            bayesian_posterior=0.9, source_credibility=0.9, evidence_strength=0.9,
            cross_verification=0.9, temporal_relevance=0.2,
        )
        explanation = calc.explain_confidence(factors, final_score=0.8)
        assert "temporal relevance" in explanation


class TestEvidenceEvaluator:
    @pytest.fixture
    def evaluator(self):
        return EvidenceEvaluator()

    def test_assess_strength_very_strong_for_high_credibility_direct_evidence(self, evaluator):
        assert evaluator.assess_strength(_evidence(credibility=0.98, type=EvidenceType.DIRECT)) == EvidenceStrength.VERY_STRONG

    def test_assess_strength_weak_for_low_credibility_circumstantial_evidence(self, evaluator):
        assert evaluator.assess_strength(_evidence(credibility=0.1, type=EvidenceType.CIRCUMSTANTIAL)) == EvidenceStrength.WEAK

    def test_check_relevance_uses_explicit_score_when_set(self, evaluator):
        assert evaluator.check_relevance(_evidence(relevance_score=0.42)) == 0.42

    def test_check_relevance_falls_back_to_keyword_matching(self, evaluator):
        ev = _evidence(content="the payment retry logic failed silently")
        relevance = evaluator.check_relevance(ev, belief_keywords=["payment", "retry"])
        assert relevance > 0.0

    def test_check_relevance_default_when_no_keywords_or_score(self, evaluator):
        assert evaluator.check_relevance(_evidence(content="anything")) == 0.7

    def test_detect_conflicts_flags_same_source_credibility_mismatch(self, evaluator):
        evs = [_evidence(source="a", credibility=0.9), _evidence(source="a", credibility=0.2)]
        conflicts = evaluator.detect_conflicts(evs)
        assert any(c["type"] == "credibility_mismatch" for c in conflicts)

    def test_analyze_consistency_with_fewer_than_two_items_is_trivially_consistent(self, evaluator):
        result = evaluator.analyze_consistency([_evidence()])
        assert result["consistency_score"] == 1.0

    def test_analyze_consistency_flags_outliers(self, evaluator):
        evs = [_evidence(credibility=0.8) for _ in range(5)] + [_evidence(credibility=0.0, source="outlier")]
        result = evaluator.analyze_consistency(evs)
        assert result["variance"] > 0.0

    def test_track_provenance_reads_chain_of_custody_from_metadata(self, evaluator):
        ev = _evidence(metadata={"chain": ["a", "b"], "verified": True})
        result = evaluator.track_provenance(ev)
        assert result["chain_of_custody"] == ["a", "b"]
        assert result["verified"] is True

    def test_evaluate_temporal_validity_with_no_timestamp(self, evaluator):
        result = evaluator.evaluate_temporal_validity(_evidence())
        assert result["valid"] is True
        assert result["age_days"] is None

    def test_evaluate_temporal_validity_flags_expired_evidence(self, evaluator):
        ev = _evidence(timestamp=datetime.now() - timedelta(days=400))
        result = evaluator.evaluate_temporal_validity(ev, max_age_days=90)
        assert result["valid"] is False
        assert result["expired"] is True

    def test_calculate_evidence_weight_applies_strength_and_relevance_multipliers(self, evaluator):
        strong = _evidence(credibility=0.9, strength=EvidenceStrength.VERY_STRONG, relevance_score=1.0)
        weak = _evidence(credibility=0.9, strength=EvidenceStrength.WEAK, relevance_score=1.0)
        assert evaluator.calculate_evidence_weight(strong) > evaluator.calculate_evidence_weight(weak)

    def test_rank_evidence_orders_by_weight_descending(self, evaluator):
        evs = [_evidence(credibility=0.2, source="low"), _evidence(credibility=0.95, source="high")]
        ranked = evaluator.rank_evidence(evs)
        assert ranked[0][1].source == "high"

    def test_generate_evidence_report_empty_list(self, evaluator):
        assert evaluator.generate_evidence_report([]) == {"total_evidence": 0, "message": "No evidence provided"}

    def test_generate_evidence_report_full_shape(self, evaluator):
        evs = [_evidence(credibility=0.9, source="a"), _evidence(credibility=0.3, source="b", type=EvidenceType.CIRCUMSTANTIAL)]
        report = evaluator.generate_evidence_report(evs)
        assert report["total_evidence"] == 2
        assert "consistency" in report
        assert len(report["top_3_evidence"]) <= 3


class TestUncertaintyQuantifier:
    @pytest.fixture
    def quantifier(self):
        return UncertaintyQuantifier()

    def test_confidence_interval_single_evidence_uses_fixed_margin(self, quantifier):
        lower, upper = quantifier.calculate_confidence_interval(0.5, [_evidence()])
        assert upper - lower == pytest.approx(0.30)

    def test_confidence_interval_no_evidence_is_full_range(self, quantifier):
        assert quantifier.calculate_confidence_interval(0.5, []) == (0.0, 1.0)

    def test_standard_deviation_uses_posterior_values_when_given(self, quantifier):
        std = quantifier.calculate_standard_deviation([], posterior_values=[0.1, 0.9])
        assert std > 0.0

    def test_standard_deviation_single_evidence_fixed_fallback(self, quantifier):
        assert quantifier.calculate_standard_deviation([_evidence()]) == 0.1

    def test_standard_deviation_no_evidence_fixed_fallback(self, quantifier):
        assert quantifier.calculate_standard_deviation([]) == 0.3

    def test_entropy_is_zero_at_certainty(self, quantifier):
        assert quantifier.calculate_entropy(0.0) == 0.0
        assert quantifier.calculate_entropy(1.0) == 0.0

    def test_entropy_is_maximal_at_fifty_fifty(self, quantifier):
        assert quantifier.calculate_entropy(0.5) == pytest.approx(1.0)

    def test_risk_score_increases_with_lower_confidence(self, quantifier):
        assert quantifier.calculate_risk_score(0.2, impact=0.5) > quantifier.calculate_risk_score(0.9, impact=0.5)

    def test_quantify_all_metrics_returns_a_valid_model(self, quantifier):
        metrics = quantifier.quantify_all_metrics(confidence=0.7, evidence_list=[_evidence(), _evidence()])
        assert isinstance(metrics, UncertaintyMetrics)

    def test_sensitivity_analysis_shape(self, quantifier):
        result = quantifier.sensitivity_analysis(0.7, {"factor_a": 0.1, "factor_b": 0.0})
        assert set(result.keys()) == {"factor_a", "factor_b"}
        assert result["factor_b"] == 0.0

    def test_monte_carlo_uncertainty_bounds_samples_to_unit_interval(self, quantifier):
        result = quantifier.monte_carlo_uncertainty(mean=0.9, std=0.3, n_samples=500)
        assert 0.0 <= result["mean"] <= 1.0
        assert all(0.0 <= s <= 1.0 for s in result["samples"])

    def test_bootstrap_confidence_interval_with_no_data_is_full_range(self, quantifier):
        assert quantifier.bootstrap_confidence_interval([]) == (0.0, 1.0)

    def test_bootstrap_confidence_interval_produces_a_valid_ordered_interval(self, quantifier):
        lower, upper = quantifier.bootstrap_confidence_interval([0.7, 0.75, 0.8, 0.72], n_bootstrap=200)
        assert 0.0 <= lower <= upper <= 1.0

    def test_propagate_uncertainty_sum_and_max(self, quantifier):
        assert quantifier.propagate_uncertainty([0.3, 0.4], operation="sum") == pytest.approx(0.5)
        assert quantifier.propagate_uncertainty([0.3, 0.4], operation="max") == 0.4

    def test_propagate_uncertainty_empty_list_is_zero(self, quantifier):
        assert quantifier.propagate_uncertainty([]) == 0.0

    def test_propagate_uncertainty_unknown_operation_raises(self, quantifier):
        with pytest.raises(ValueError, match="Unknown operation"):
            quantifier.propagate_uncertainty([0.1], operation="bogus")

    def test_calibration_curve_data_mismatched_lengths_raises(self, quantifier):
        with pytest.raises(ValueError, match="same length"):
            quantifier.calibration_curve_data([0.5], [True, False])

    def test_calibration_curve_data_empty_is_empty(self, quantifier):
        assert quantifier.calibration_curve_data([], []) == {"bin_centers": [], "accuracies": []}

    def test_expected_calibration_error_is_zero_for_perfectly_calibrated_predictions(self, quantifier):
        # 10 predictions all at 1.0 confidence, all correct -> 0 calibration error.
        predictions = [1.0] * 10
        outcomes = [True] * 10
        assert quantifier.expected_calibration_error(predictions, outcomes) == pytest.approx(0.0, abs=1e-6)

    def test_uncertainty_report_mentions_interpretation_band(self, quantifier):
        metrics = UncertaintyMetrics(confidence_interval=[0.4, 0.6], standard_deviation=0.1, entropy=0.5, variance=0.01, risk_score=0.2)
        report = quantifier.uncertainty_report(metrics)
        assert "Interpretation" in report


class TestABVEngineEndToEnd:
    @pytest.fixture
    def engine(self):
        return ABVEngine()

    def test_validate_belief_returns_a_well_formed_response(self, engine):
        request = ValidateBeliefRequest(
            belief="the payment retry logic has a real, fixable bug",
            evidence=[
                _evidence(credibility=0.9, type=EvidenceType.DIRECT, source="log_analysis"),
                _evidence(credibility=0.6, type=EvidenceType.EXPERT_OPINION, source="reviewer"),
            ],
        )
        response = engine.validate_belief(request)
        assert 0.0 <= response.confidence_score <= 1.0
        assert response.decision in DecisionType
        assert response.belief_id in engine.beliefs
        assert engine.total_validations == 1

    def test_more_and_stronger_supporting_evidence_raises_confidence(self, engine):
        weak_request = ValidateBeliefRequest(
            belief="a real testable claim about the system",
            evidence=[_evidence(credibility=0.3, type=EvidenceType.CIRCUMSTANTIAL)],
        )
        strong_request = ValidateBeliefRequest(
            belief="a real testable claim about the system",
            evidence=[
                _evidence(credibility=0.95, type=EvidenceType.DIRECT, source="a"),
                _evidence(credibility=0.9, type=EvidenceType.STATISTICAL, source="b"),
            ],
        )
        weak_response = engine.validate_belief(weak_request)
        strong_response = engine.validate_belief(strong_request)
        assert strong_response.confidence_score > weak_response.confidence_score

    def test_custom_weights_are_honored(self, engine):
        request = ValidateBeliefRequest(
            belief="a real testable claim about the system",
            evidence=[_evidence(credibility=0.9)],
            custom_weights={"bayesian_posterior": 1.0, "source_credibility": 0.0,
                             "evidence_strength": 0.0, "cross_verification": 0.0, "temporal_relevance": 0.0},
        )
        response = engine.validate_belief(request)
        # With all weight on bayesian_posterior, final confidence should
        # equal that one factor almost exactly.
        assert response.confidence_score == pytest.approx(response.contributing_factors["bayesian_posterior"], abs=1e-6)

    def test_validate_batch_processes_every_request_and_summarizes(self, engine):
        requests = [
            ValidateBeliefRequest(belief="claim one is testable", evidence=[_evidence(credibility=0.8)]),
            ValidateBeliefRequest(belief="claim two is testable", evidence=[_evidence(credibility=0.4)]),
        ]
        responses, summary = engine.validate_batch(requests)
        assert len(responses) == 2
        assert "avg_time_per_belief" in summary

    def test_validate_batch_with_no_requests_avoids_division_by_zero(self, engine):
        responses, summary = engine.validate_batch([])
        assert responses == []
        assert summary["avg_time_per_belief"] == 0

    def test_update_belief_with_evidence_raises_for_unknown_belief(self, engine):
        with pytest.raises(ValueError, match="not found"):
            engine.update_belief_with_evidence("no-such-belief", _evidence())

    def test_update_belief_with_evidence_increments_evidence_count(self, engine):
        request = ValidateBeliefRequest(belief="a real testable claim", evidence=[_evidence(credibility=0.7)])
        response = engine.validate_belief(request)
        belief_before = engine.get_belief(response.belief_id)
        assert belief_before.evidence_count == 1

        engine.update_belief_with_evidence(response.belief_id, _evidence(credibility=0.95, source="new"))
        belief_after = engine.get_belief(response.belief_id)
        assert belief_after.evidence_count == 2
        assert len(engine.get_belief_history(response.belief_id)) == 2

    def test_get_belief_for_unknown_id_returns_none(self, engine):
        assert engine.get_belief("no-such-belief") is None

    def test_learn_from_outcome_records_calibration_data_for_known_belief(self, engine):
        request = ValidateBeliefRequest(belief="a real testable claim", evidence=[_evidence()])
        response = engine.validate_belief(request)
        engine.learn_from_outcome(response.belief_id, True)
        assert len(engine.calibration_data) == 1

    def test_learn_from_outcome_is_a_no_op_for_unknown_belief(self, engine):
        engine.learn_from_outcome("no-such-belief", True)
        assert engine.calibration_data == []

    def test_get_performance_metrics_reflects_real_validation_count(self, engine):
        request = ValidateBeliefRequest(belief="a real testable claim", evidence=[_evidence()])
        engine.validate_belief(request)
        metrics = engine.get_performance_metrics()
        assert metrics["total_validations"] == 1
        assert metrics["avg_time_seconds"] >= 0.0

    def test_performance_metrics_includes_calibration_accuracy_once_learned(self, engine):
        request = ValidateBeliefRequest(belief="a real testable claim", evidence=[_evidence()])
        response = engine.validate_belief(request)
        engine.learn_from_outcome(response.belief_id, True)
        metrics = engine.get_performance_metrics()
        assert "calibration_accuracy" in metrics

    def test_reset_metrics_clears_counters_but_not_beliefs(self, engine):
        request = ValidateBeliefRequest(belief="a real testable claim", evidence=[_evidence()])
        engine.validate_belief(request)
        engine.reset_metrics()
        assert engine.total_validations == 0
        assert len(engine.beliefs) == 1  # beliefs survive a metrics reset

    def test_clear_history_removes_everything(self, engine):
        request = ValidateBeliefRequest(belief="a real testable claim", evidence=[_evidence()])
        response = engine.validate_belief(request)
        engine.learn_from_outcome(response.belief_id, True)
        engine.clear_history()
        assert engine.beliefs == {}
        assert engine.belief_history == {}
        assert engine.calibration_data == []

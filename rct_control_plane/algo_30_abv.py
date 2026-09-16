"""
ALGO-30: ABV (Adaptive Belief Validation) — Bayesian Confidence Engine

Ported from Delentia-Private-OS's real implementation at
rct_platform/microservices/abv-confidence-scoring/app/core/ — merging
four source files (bayesian_engine.py, confidence_calculator.py,
evidence_evaluator.py, uncertainty_quantifier.py) plus the Pydantic data
models they share (app/models/schemas.py) and the orchestrator
(abv_engine.py) into one standalone module. No FastAPI/HTTP route code
lived in any of these — routes.py was a thin separate file that only
imported ABVEngine — so this is close to a straight copy: real Bayes'
theorem math (P(H|E) = P(E|H) x P(H) / P(E)), sequential/weighted/
independent multi-evidence integration, confidence-interval estimation,
Shannon entropy, and KL-divergence-based information gain are all
unchanged from the source.

Entry point: ``ABVEngine.validate_belief(request: ValidateBeliefRequest)
-> ValidateBeliefResponse`` (see bottom of this file for a real smoke
test that exercises it end to end).

Schemas ported: Evidence, Belief, BayesianParameters, ConfidenceFactors,
UncertaintyMetrics, ConfidenceScore, ValidateBeliefRequest,
ValidateBeliefResponse, ThresholdConfig, plus the EvidenceType /
EvidenceStrength / ConfidenceLevel / DecisionType enums — these are the
schemas actually consumed by the engine classes below. HTTP-only models
from the source (BatchValidateRequest/Response's route wiring,
EvidenceRequest, AccuracyMetrics, PerformanceMetrics, HealthResponse)
were dropped as out of scope for a non-HTTP port; ABVEngine.validate_batch()
still works (it just calls validate_belief() in a loop and returns a
plain summary dict, exactly as in the source — no BatchValidateResponse
wrapper was ever required for that method to work).

PORTING FINDINGS (read before wiring into the kernel):

1. numpy — REQUIRED. UncertaintyQuantifier (Monte Carlo sampling,
   bootstrap CIs, std/percentile calculations) and BayesianEngine's
   monte_carlo_sampling() both need numpy. It is already listed in
   Delentia-OS/pyproject.toml, but only under the OPTIONAL
   `[project.optional-dependencies] graph` (and `full`) extras, not as a
   base dependency — this module will fail to import in a `pip install
   delentia-os` (no extras) install. Flagging this rather than silently
   assuming it's always present; the integration pass should decide
   whether ABV's kernel wrapper needs to guard the import or whether
   `graph`/`full` should become a base requirement.

2. scipy — NOT ported, and NOT required. The source's bayesian_engine.py
   imports `scipy.stats` only to compute a z-score for
   calculate_confidence_interval() at confidence_level values other than
   0.90/0.95/0.99 (i.e. `stats.norm.ppf(...)`), and uncertainty_quantifier.py
   imports scipy.stats but never actually calls anything from it (dead
   import in the source). scipy is not declared anywhere in Delentia-OS's
   pyproject.toml. Per the porting brief ("stop and report" rather than
   add a new undeclared dependency), this port drops the scipy import
   entirely: the three standard confidence levels still use their exact
   original hardcoded z-scores (1.645/1.96/2.576), and an arbitrary
   confidence_level now falls back to z=1.96 (the 95% value) instead of
   scipy's exact normal-quantile — a documented, narrow behavior
   difference, not a silent one.

3. Everything else (pydantic models, ConfidenceCalculator,
   EvidenceEvaluator, and the ABVEngine orchestrator) is pure Python /
   pydantic, using only `pydantic` (already a base dependency of
   Delentia-OS).
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np  # see PORTING FINDING 1 above — requires the `graph`/`full` extra
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ============================================================================
# Schemas (ported from app/models/schemas.py — engine-relevant subset only)
# ============================================================================


class EvidenceType(str, Enum):
    """Types of evidence with different weights"""
    DIRECT = "direct"
    INDIRECT = "indirect"
    CIRCUMSTANTIAL = "circumstantial"
    STATISTICAL = "statistical"
    EXPERT_OPINION = "expert_opinion"
    HISTORICAL = "historical"
    PREDICTIVE = "predictive"


class EvidenceStrength(str, Enum):
    """Strength classification for evidence"""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class ConfidenceLevel(str, Enum):
    """Confidence level categories"""
    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class DecisionType(str, Enum):
    """Decision outcomes based on confidence"""
    ACCEPT = "accept"
    REVIEW = "review"
    INVESTIGATE = "investigate"
    REJECT = "reject"


class Evidence(BaseModel):
    """Evidence supporting or contradicting a belief"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: Optional[str] = Field(None, description="Unique evidence ID")
    type: EvidenceType = Field(..., description="Type of evidence")
    source: str = Field(..., min_length=1, max_length=500, description="Source of evidence")
    credibility: float = Field(..., ge=0.0, le=1.0, description="Source credibility (0-1)")
    content: str = Field(..., min_length=1, max_length=5000, description="Evidence content")
    strength: Optional[EvidenceStrength] = Field(None, description="Assessed strength")
    relevance_score: float = Field(0.0, ge=0.0, le=1.0, description="Relevance to belief")
    timestamp: Optional[datetime] = Field(None, description="When evidence was created")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("credibility")
    @classmethod
    def validate_credibility(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Credibility must be between 0.0 and 1.0")
        return v


class Belief(BaseModel):
    """A belief or hypothesis to be validated"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: Optional[str] = Field(None, description="Unique belief ID")
    statement: str = Field(..., min_length=5, max_length=1000, description="Belief statement")
    domain: Optional[str] = Field(None, max_length=100, description="Domain/category")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Current confidence score")
    evidence_count: int = Field(0, ge=0, description="Number of evidence items")
    validated: bool = Field(False, description="Whether belief has been validated")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update time")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class BayesianParameters(BaseModel):
    """Parameters for Bayesian inference calculation"""

    prior: float = Field(..., ge=0.0, le=1.0, description="Prior probability P(H)")
    likelihood: float = Field(..., ge=0.0, le=1.0, description="Likelihood P(E|H)")
    marginal: float = Field(..., gt=0.0, le=1.0, description="Marginal probability P(E)")
    posterior: float = Field(..., ge=0.0, le=1.0, description="Posterior probability P(H|E)")
    evidence_weight: float = Field(1.0, ge=0.0, description="Weight of this evidence")

    @field_validator("marginal")
    @classmethod
    def marginal_not_zero(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("Marginal probability must be greater than 0")
        return v


class ConfidenceFactors(BaseModel):
    """Individual factors contributing to confidence score"""

    bayesian_posterior: float = Field(..., ge=0.0, le=1.0)
    source_credibility: float = Field(..., ge=0.0, le=1.0)
    evidence_strength: float = Field(..., ge=0.0, le=1.0)
    cross_verification: float = Field(..., ge=0.0, le=1.0)
    temporal_relevance: float = Field(..., ge=0.0, le=1.0)

    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "bayesian_posterior": 0.30,
            "source_credibility": 0.25,
            "evidence_strength": 0.20,
            "cross_verification": 0.15,
            "temporal_relevance": 0.10,
        }
    )

    @field_validator("weights")
    @classmethod
    def weights_sum_to_one(cls, v: Dict[str, float]) -> Dict[str, float]:
        total = sum(v.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        return v

    def calculate_weighted_score(self) -> float:
        """Calculate weighted confidence score"""
        factors_dict = {
            "bayesian_posterior": self.bayesian_posterior,
            "source_credibility": self.source_credibility,
            "evidence_strength": self.evidence_strength,
            "cross_verification": self.cross_verification,
            "temporal_relevance": self.temporal_relevance,
        }
        score = sum(factors_dict[key] * weight for key, weight in self.weights.items())
        return min(max(score, 0.0), 1.0)


class UncertaintyMetrics(BaseModel):
    """Uncertainty quantification metrics"""

    confidence_interval: List[float] = Field(..., min_length=2, max_length=2)
    standard_deviation: float = Field(..., ge=0.0)
    entropy: float = Field(..., ge=0.0)
    variance: float = Field(..., ge=0.0)
    risk_score: Optional[float] = Field(None, ge=0.0, le=1.0)

    @field_validator("confidence_interval")
    @classmethod
    def validate_interval(cls, v: List[float]) -> List[float]:
        if len(v) != 2:
            raise ValueError("Confidence interval must have exactly 2 values")
        if not (0.0 <= v[0] <= v[1] <= 1.0):
            raise ValueError("CI must be [lower, upper] with 0 <= lower <= upper <= 1")
        return v


class ConfidenceScore(BaseModel):
    """Complete confidence scoring result"""

    belief_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    level: ConfidenceLevel
    factors: ConfidenceFactors
    uncertainty: UncertaintyMetrics
    decision: DecisionType
    explanation: str = Field(..., min_length=10, max_length=1000)
    timestamp: datetime = Field(default_factory=datetime.now)


class ThresholdConfig(BaseModel):
    """Configuration for decision thresholds"""

    high: float = Field(0.95, ge=0.0, le=1.0)
    moderate: float = Field(0.80, ge=0.0, le=1.0)
    low: float = Field(0.60, ge=0.0, le=1.0)

    @field_validator("moderate")
    @classmethod
    def moderate_less_than_high(cls, v: float, info) -> float:
        high = info.data.get("high", 0.95)
        if v >= high:
            raise ValueError(f"Moderate threshold ({v}) must be less than high ({high})")
        return v

    @field_validator("low")
    @classmethod
    def low_less_than_moderate(cls, v: float, info) -> float:
        moderate = info.data.get("moderate", 0.80)
        if v >= moderate:
            raise ValueError(f"Low threshold ({v}) must be less than moderate ({moderate})")
        return v

    def get_level(self, score: float) -> ConfidenceLevel:
        if score >= self.high:
            return ConfidenceLevel.HIGH
        elif score >= self.moderate:
            return ConfidenceLevel.MODERATE
        elif score >= self.low:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    def get_decision(self, score: float) -> DecisionType:
        level = self.get_level(score)
        if level == ConfidenceLevel.HIGH:
            return DecisionType.ACCEPT
        elif level == ConfidenceLevel.MODERATE:
            return DecisionType.REVIEW
        elif level == ConfidenceLevel.LOW:
            return DecisionType.INVESTIGATE
        else:
            return DecisionType.REJECT


class ValidateBeliefRequest(BaseModel):
    """Request to validate a belief"""

    belief: str = Field(..., min_length=5, max_length=1000)
    evidence: List[Evidence] = Field(..., min_length=1)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    prior_probability: Optional[float] = Field(None, ge=0.0, le=1.0)
    custom_weights: Optional[Dict[str, float]] = Field(None)

    @field_validator("evidence")
    @classmethod
    def validate_evidence_list(cls, v: List[Evidence]) -> List[Evidence]:
        if not v:
            raise ValueError("At least one evidence item is required")
        return v


class ValidateBeliefResponse(BaseModel):
    """Response from belief validation"""

    belief_id: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    uncertainty: UncertaintyMetrics
    contributing_factors: Dict[str, float]
    decision: DecisionType
    explanation: str
    timestamp: datetime = Field(default_factory=datetime.now)
    bayesian_params: Optional[BayesianParameters] = None
    evidence_analysis: Optional[List[Dict[str, Any]]] = None


# ============================================================================
# Bayesian Engine (ported from app/core/bayesian_engine.py)
# ============================================================================


class BayesianEngine:
    """
    Bayesian Inference Engine for confidence scoring

    Implements Bayes' theorem: P(H|E) = P(E|H) x P(H) / P(E)
    """

    def __init__(
        self,
        default_prior: float = 0.5,
        min_prior: float = 0.01,
        max_prior: float = 0.99,
    ):
        self.default_prior = default_prior
        self.min_prior = min_prior
        self.max_prior = max_prior

        self.evidence_type_weights = {
            EvidenceType.DIRECT: 1.0,
            EvidenceType.STATISTICAL: 0.95,
            EvidenceType.EXPERT_OPINION: 0.85,
            EvidenceType.INDIRECT: 0.70,
            EvidenceType.HISTORICAL: 0.65,
            EvidenceType.PREDICTIVE: 0.60,
            EvidenceType.CIRCUMSTANTIAL: 0.50,
        }

        self.strength_multipliers = {
            EvidenceStrength.VERY_STRONG: 1.2,
            EvidenceStrength.STRONG: 1.0,
            EvidenceStrength.MODERATE: 0.7,
            EvidenceStrength.WEAK: 0.4,
        }

    def calculate_prior(
        self,
        domain: Optional[str] = None,
        historical_data: Optional[Dict[str, float]] = None,
    ) -> float:
        if domain and historical_data and domain in historical_data:
            prior = historical_data[domain]
        else:
            prior = self.default_prior
        return max(self.min_prior, min(self.max_prior, prior))

    def calculate_likelihood(self, evidence: Evidence, supporting: bool = True) -> float:
        type_weight = self.evidence_type_weights.get(evidence.type, 0.5)

        if evidence.strength:
            strength_mult = self.strength_multipliers.get(evidence.strength, 1.0)
        else:
            if evidence.credibility >= 0.9:
                strength_mult = self.strength_multipliers[EvidenceStrength.VERY_STRONG]
            elif evidence.credibility >= 0.75:
                strength_mult = self.strength_multipliers[EvidenceStrength.STRONG]
            elif evidence.credibility >= 0.5:
                strength_mult = self.strength_multipliers[EvidenceStrength.MODERATE]
            else:
                strength_mult = self.strength_multipliers[EvidenceStrength.WEAK]

        base_likelihood = type_weight * strength_mult * evidence.credibility

        if evidence.relevance_score > 0:
            base_likelihood *= evidence.relevance_score

        likelihood = max(0.01, min(0.99, base_likelihood))

        if not supporting:
            likelihood = 1.0 - likelihood

        return likelihood

    def calculate_marginal(self, likelihood: float, prior: float, likelihood_neg: float) -> float:
        marginal = (likelihood * prior) + (likelihood_neg * (1 - prior))
        return max(0.0001, marginal)

    def calculate_posterior(self, likelihood: float, prior: float, marginal: float) -> float:
        if marginal <= 0:
            marginal = 0.0001
        posterior = (likelihood * prior) / marginal
        return max(0.0, min(1.0, posterior))

    def update_belief_single(
        self,
        prior: float,
        evidence: Evidence,
        supporting: bool = True,
    ) -> BayesianParameters:
        likelihood = self.calculate_likelihood(evidence, supporting=supporting)

        if supporting:
            likelihood_neg = max(0.1, 1.0 - likelihood * 0.8)
        else:
            likelihood_neg = max(0.1, likelihood * 0.8)

        marginal = self.calculate_marginal(likelihood, prior, likelihood_neg)
        posterior = self.calculate_posterior(likelihood, prior, marginal)

        evidence_weight = evidence.credibility * self.evidence_type_weights.get(evidence.type, 0.5)

        return BayesianParameters(
            prior=prior,
            likelihood=likelihood,
            marginal=marginal,
            posterior=posterior,
            evidence_weight=evidence_weight,
        )

    def update_belief_multiple(
        self,
        prior: float,
        evidence_list: List[Evidence],
        supporting_flags: Optional[List[bool]] = None,
    ) -> Tuple[float, List[BayesianParameters]]:
        if not evidence_list:
            return prior, []

        if supporting_flags is None:
            supporting_flags = [True] * len(evidence_list)

        if len(supporting_flags) != len(evidence_list):
            raise ValueError("supporting_flags length must match evidence_list length")

        current_prior = prior
        params_list = []

        for evidence, supporting in zip(evidence_list, supporting_flags):
            params = self.update_belief_single(current_prior, evidence, supporting)
            params_list.append(params)
            current_prior = params.posterior

        return current_prior, params_list

    def calculate_weighted_posterior(
        self,
        evidence_list: List[Evidence],
        params_list: List[BayesianParameters],
    ) -> float:
        if not params_list:
            return self.default_prior

        total_weight = sum(p.evidence_weight for p in params_list)

        if total_weight == 0:
            return sum(p.posterior for p in params_list) / len(params_list)

        weighted_sum = sum(p.posterior * p.evidence_weight for p in params_list)
        return weighted_sum / total_weight

    def integrate_evidence(
        self,
        prior: float,
        evidence_list: List[Evidence],
        method: str = "sequential",
    ) -> Tuple[float, List[BayesianParameters]]:
        if not evidence_list:
            return prior, []

        if method == "sequential":
            return self.update_belief_multiple(prior, evidence_list)

        elif method == "weighted":
            params_list = []
            for evidence in evidence_list:
                params = self.update_belief_single(prior, evidence)
                params_list.append(params)
            weighted_posterior = self.calculate_weighted_posterior(evidence_list, params_list)
            return weighted_posterior, params_list

        elif method == "independent":
            likelihood_ratio = 1.0
            params_list = []

            for evidence in evidence_list:
                params = self.update_belief_single(prior, evidence)
                params_list.append(params)

                if params.marginal > 0:
                    lr = params.likelihood / (1 - params.likelihood + 0.001)
                    likelihood_ratio *= lr

            odds = (prior / (1 - prior + 0.001)) * likelihood_ratio
            posterior = odds / (1 + odds)
            posterior = max(0.0, min(1.0, posterior))

            return posterior, params_list

        else:
            raise ValueError(f"Unknown integration method: {method}")

    def monte_carlo_sampling(
        self,
        prior_dist: Tuple[float, float],
        likelihood_dist: Tuple[float, float],
        n_samples: int = 10000,
    ) -> Tuple[float, float, List[float]]:
        prior_mean, prior_std = prior_dist
        likelihood_mean, likelihood_std = likelihood_dist

        prior_samples = np.random.normal(prior_mean, prior_std, n_samples)
        likelihood_samples = np.random.normal(likelihood_mean, likelihood_std, n_samples)

        prior_samples = np.clip(prior_samples, 0.01, 0.99)
        likelihood_samples = np.clip(likelihood_samples, 0.01, 0.99)

        posteriors = []
        for p, l in zip(prior_samples, likelihood_samples):
            marginal = (l * p) + ((1 - l) * (1 - p))
            posterior = (l * p) / max(marginal, 0.0001)
            posteriors.append(min(max(posterior, 0.0), 1.0))

        posteriors = np.array(posteriors)

        return float(np.mean(posteriors)), float(np.std(posteriors)), posteriors.tolist()

    def calculate_confidence_interval(
        self,
        posterior: float,
        evidence_list: List[Evidence],
        confidence_level: float = 0.95,
    ) -> Tuple[float, float]:
        n = len(evidence_list)

        if n == 0:
            return (0.0, 1.0)

        se = math.sqrt(posterior * (1 - posterior) / n)

        if confidence_level == 0.95:
            z = 1.96
        elif confidence_level == 0.99:
            z = 2.576
        elif confidence_level == 0.90:
            z = 1.645
        else:
            # See PORTING FINDING 2 — scipy.stats.norm.ppf dropped, falls
            # back to the 95% z-score for non-standard confidence levels.
            z = 1.96

        margin = z * se
        lower = max(0.0, posterior - margin)
        upper = min(1.0, posterior + margin)

        return (lower, upper)

    def assess_evidence_quality(self, evidence: Evidence) -> Dict[str, float]:
        type_weight = self.evidence_type_weights.get(evidence.type, 0.5)

        if evidence.strength:
            strength_score = self.strength_multipliers.get(evidence.strength, 0.7)
        else:
            strength_score = evidence.credibility

        quality = (
            0.4 * evidence.credibility +
            0.3 * type_weight +
            0.2 * strength_score +
            0.1 * evidence.relevance_score
        )

        return {
            "quality_score": quality,
            "credibility": evidence.credibility,
            "type_weight": type_weight,
            "strength_score": strength_score,
            "relevance": evidence.relevance_score,
        }

    def detect_conflicting_evidence(
        self,
        evidence_list: List[Evidence],
        threshold: float = 0.3,
    ) -> List[Tuple[int, int, float]]:
        conflicts = []
        for i in range(len(evidence_list)):
            for j in range(i + 1, len(evidence_list)):
                ev1 = evidence_list[i]
                ev2 = evidence_list[j]
                cred_diff = abs(ev1.credibility - ev2.credibility)
                if ev1.type != ev2.type and cred_diff > threshold:
                    conflicts.append((i, j, cred_diff))
        return conflicts

    def calculate_information_gain(self, prior: float, posterior: float) -> float:
        """KL divergence for Bernoulli distributions: D_KL(posterior || prior)"""
        if prior <= 0 or prior >= 1 or posterior <= 0 or posterior >= 1:
            return 0.0

        kl = (
            posterior * math.log2(posterior / prior) +
            (1 - posterior) * math.log2((1 - posterior) / (1 - prior))
        )

        return max(0.0, kl)


def beta_distribution_prior(alpha: float, beta: float) -> float:
    """Mean of beta distribution (common for Bayesian priors)"""
    return alpha / (alpha + beta)


def update_beta_distribution(alpha: float, beta: float, success: bool) -> Tuple[float, float]:
    """Update beta distribution parameters with new observation"""
    if success:
        return (alpha + 1, beta)
    else:
        return (alpha, beta + 1)


# ============================================================================
# Confidence Calculator (ported from app/core/confidence_calculator.py)
# ============================================================================


class ConfidenceCalculator:
    """
    Multi-factor confidence scoring system

    Combines: Bayesian Posterior (30%), Source Credibility (25%),
    Evidence Strength (20%), Cross-Verification (15%), Temporal
    Relevance (10%).
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        thresholds: Optional[ThresholdConfig] = None,
    ):
        self.weights = weights or {
            "bayesian_posterior": 0.30,
            "source_credibility": 0.25,
            "evidence_strength": 0.20,
            "cross_verification": 0.15,
            "temporal_relevance": 0.10,
        }

        total = sum(self.weights.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        self.thresholds = thresholds or ThresholdConfig()

    def calculate_source_credibility_score(self, evidence_list: List[Evidence]) -> float:
        if not evidence_list:
            return 0.5

        total_weight = 0.0
        weighted_sum = 0.0

        for ev in evidence_list:
            weight = ev.relevance_score if ev.relevance_score > 0 else 1.0
            weighted_sum += ev.credibility * weight
            total_weight += weight

        if total_weight == 0:
            return sum(ev.credibility for ev in evidence_list) / len(evidence_list)

        return weighted_sum / total_weight

    def calculate_evidence_strength_score(
        self,
        evidence_list: List[Evidence],
        bayesian_params: Optional[List[BayesianParameters]] = None,
    ) -> float:
        if not evidence_list:
            return 0.0

        if bayesian_params and len(bayesian_params) == len(evidence_list):
            total_weight = sum(p.evidence_weight for p in bayesian_params)
            if total_weight > 0:
                return min(1.0, total_weight / len(evidence_list))

        scores = []
        for ev in evidence_list:
            score = ev.credibility * (ev.relevance_score if ev.relevance_score > 0 else 0.8)
            scores.append(score)

        return sum(scores) / len(scores)

    def calculate_cross_verification_score(self, evidence_list: List[Evidence]) -> float:
        if len(evidence_list) <= 1:
            return 0.3

        unique_sources = set(ev.source for ev in evidence_list)
        unique_types = set(ev.type for ev in evidence_list)
        type_diversity = len(unique_types) / min(len(evidence_list), 7)
        avg_credibility = sum(ev.credibility for ev in evidence_list) / len(evidence_list)

        score = (
            0.4 * min(1.0, len(unique_sources) / 3) +
            0.3 * type_diversity +
            0.3 * avg_credibility
        )

        return min(1.0, score)

    def calculate_temporal_relevance_score(
        self,
        evidence_list: List[Evidence],
        decay_days: int = 30,
    ) -> float:
        if not evidence_list:
            return 0.5

        now = datetime.now()
        scores = []

        for ev in evidence_list:
            if not ev.timestamp:
                scores.append(0.7)
                continue

            days_old = (now - ev.timestamp).days
            lambda_decay = 0.693 / decay_days
            score = math.exp(-lambda_decay * days_old)
            scores.append(min(1.0, score))

        return sum(scores) / len(scores)

    def calculate_confidence_factors(
        self,
        bayesian_posterior: float,
        evidence_list: List[Evidence],
        bayesian_params: Optional[List[BayesianParameters]] = None,
    ) -> ConfidenceFactors:
        return ConfidenceFactors(
            bayesian_posterior=bayesian_posterior,
            source_credibility=self.calculate_source_credibility_score(evidence_list),
            evidence_strength=self.calculate_evidence_strength_score(evidence_list, bayesian_params),
            cross_verification=self.calculate_cross_verification_score(evidence_list),
            temporal_relevance=self.calculate_temporal_relevance_score(evidence_list),
            weights=self.weights,
        )

    def calculate_final_confidence(self, factors: ConfidenceFactors) -> float:
        return factors.calculate_weighted_score()

    def get_confidence_level(self, score: float) -> ConfidenceLevel:
        return self.thresholds.get_level(score)

    def adjust_for_uncertainty(
        self,
        confidence: float,
        uncertainty_std: float,
        risk_averse: bool = True,
    ) -> float:
        if not risk_averse:
            return confidence
        penalty = min(uncertainty_std * 2, 0.3)
        adjusted = confidence - penalty
        return max(0.0, min(1.0, adjusted))

    def calculate_confidence_growth(self, new_confidence: float, old_confidence: float) -> Dict[str, float]:
        absolute_change = new_confidence - old_confidence
        relative_change = absolute_change / old_confidence if old_confidence > 0 else 0.0

        return {
            "absolute_change": absolute_change,
            "relative_change": relative_change,
            "improved": absolute_change > 0,
            "confidence_gain": max(0, absolute_change),
            "confidence_loss": abs(min(0, absolute_change)),
        }

    def compare_confidence_levels(self, score1: float, score2: float) -> Dict[str, Any]:
        level1 = self.get_confidence_level(score1)
        level2 = self.get_confidence_level(score2)

        return {
            "score1": score1,
            "score2": score2,
            "level1": level1,
            "level2": level2,
            "difference": score1 - score2,
            "same_level": level1 == level2,
            "higher": score1 > score2,
        }

    def calibrate_confidence(
        self,
        predicted_confidence: float,
        actual_outcome: bool,
        calibration_data: Optional[List[Tuple[float, bool]]] = None,
    ) -> float:
        if not calibration_data:
            return predicted_confidence

        similar_predictions = [
            outcome for conf, outcome in calibration_data
            if abs(conf - predicted_confidence) < 0.1
        ]

        if not similar_predictions:
            return predicted_confidence

        actual_accuracy = sum(similar_predictions) / len(similar_predictions)
        calibration_factor = 0.2
        calibrated = (
            (1 - calibration_factor) * predicted_confidence +
            calibration_factor * actual_accuracy
        )

        return max(0.0, min(1.0, calibrated))

    def explain_confidence(self, factors: ConfidenceFactors, final_score: float) -> str:
        level = self.get_confidence_level(final_score)

        factor_values = {
            "Bayesian analysis": factors.bayesian_posterior,
            "source credibility": factors.source_credibility,
            "evidence strength": factors.evidence_strength,
            "cross-verification": factors.cross_verification,
            "temporal relevance": factors.temporal_relevance,
        }

        dominant = max(
            factor_values.items(),
            key=lambda x: x[1] * factors.weights.get(x[0].replace(" ", "_"), 0),
        )
        weakest = min(factor_values.items(), key=lambda x: x[1])

        explanation = f"{level.value.replace('_', ' ').title()} confidence ({final_score:.1%}). "
        explanation += f"Strongest factor: {dominant[0]} ({dominant[1]:.1%}). "

        if weakest[1] < 0.5:
            explanation += f"Limited by {weakest[0]} ({weakest[1]:.1%})."

        return explanation


def sigmoid(x: float, midpoint: float = 0.5, steepness: float = 10) -> float:
    """Sigmoid function for smooth confidence scaling"""
    return 1 / (1 + math.exp(-steepness * (x - midpoint)))


# ============================================================================
# Evidence Evaluator (ported from app/core/evidence_evaluator.py)
# ============================================================================


class EvidenceEvaluator:
    """Evaluates evidence quality, strength, credibility, and conflicts"""

    def __init__(self):
        self.strength_thresholds = {
            EvidenceStrength.VERY_STRONG: 0.90,
            EvidenceStrength.STRONG: 0.75,
            EvidenceStrength.MODERATE: 0.50,
            EvidenceStrength.WEAK: 0.0,
        }

        self.type_base_credibility = {
            EvidenceType.DIRECT: 0.95,
            EvidenceType.STATISTICAL: 0.90,
            EvidenceType.EXPERT_OPINION: 0.80,
            EvidenceType.INDIRECT: 0.65,
            EvidenceType.HISTORICAL: 0.70,
            EvidenceType.PREDICTIVE: 0.55,
            EvidenceType.CIRCUMSTANTIAL: 0.45,
        }

    def assess_strength(self, evidence: Evidence) -> EvidenceStrength:
        type_weight = self.type_base_credibility.get(evidence.type, 0.5)
        combined_score = (evidence.credibility + type_weight) / 2

        if combined_score >= self.strength_thresholds[EvidenceStrength.VERY_STRONG]:
            return EvidenceStrength.VERY_STRONG
        elif combined_score >= self.strength_thresholds[EvidenceStrength.STRONG]:
            return EvidenceStrength.STRONG
        elif combined_score >= self.strength_thresholds[EvidenceStrength.MODERATE]:
            return EvidenceStrength.MODERATE
        else:
            return EvidenceStrength.WEAK

    def score_credibility(
        self,
        evidence: Evidence,
        source_reputation: Optional[Dict[str, float]] = None,
    ) -> float:
        base_credibility = evidence.credibility

        if source_reputation and evidence.source in source_reputation:
            reputation = source_reputation[evidence.source]
            credibility = 0.7 * base_credibility + 0.3 * reputation
        else:
            credibility = base_credibility

        type_factor = self.type_base_credibility.get(evidence.type, 0.5)
        credibility = 0.8 * credibility + 0.2 * type_factor

        return min(1.0, max(0.0, credibility))

    def check_relevance(
        self,
        evidence: Evidence,
        belief_keywords: Optional[List[str]] = None,
    ) -> float:
        if evidence.relevance_score > 0:
            return evidence.relevance_score

        if belief_keywords and evidence.content:
            content_lower = evidence.content.lower()
            matches = sum(1 for keyword in belief_keywords if keyword.lower() in content_lower)
            relevance = min(1.0, matches / max(len(belief_keywords), 1) * 2)
            return relevance

        return 0.7

    def detect_conflicts(
        self,
        evidence_list: List[Evidence],
        conflict_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        conflicts = []

        for i in range(len(evidence_list)):
            for j in range(i + 1, len(evidence_list)):
                ev1 = evidence_list[i]
                ev2 = evidence_list[j]

                if ev1.source == ev2.source:
                    cred_diff = abs(ev1.credibility - ev2.credibility)
                    if cred_diff > conflict_threshold:
                        conflicts.append({
                            "index1": i,
                            "index2": j,
                            "type": "credibility_mismatch",
                            "severity": cred_diff,
                            "description": "Same source with different credibility",
                        })

                if ev1.type != ev2.type and ev1.credibility > 0.8 and ev2.credibility > 0.8:
                    type_distance = abs(
                        self.type_base_credibility.get(ev1.type, 0.5) -
                        self.type_base_credibility.get(ev2.type, 0.5)
                    )
                    if type_distance > conflict_threshold:
                        conflicts.append({
                            "index1": i,
                            "index2": j,
                            "type": "type_conflict",
                            "severity": type_distance,
                            "description": f"Different evidence types: {ev1.type} vs {ev2.type}",
                        })

        return conflicts

    def analyze_consistency(self, evidence_list: List[Evidence]) -> Dict[str, Any]:
        if len(evidence_list) < 2:
            return {
                "consistency_score": 1.0,
                "variance": 0.0,
                "outliers": [],
                "message": "Not enough evidence for consistency analysis",
            }

        credibilities = [ev.credibility for ev in evidence_list]
        mean_cred = sum(credibilities) / len(credibilities)
        variance = sum((c - mean_cred) ** 2 for c in credibilities) / len(credibilities)
        std_dev = math.sqrt(variance)

        outliers = []
        for i, cred in enumerate(credibilities):
            if abs(cred - mean_cred) > 2 * std_dev:
                outliers.append({"index": i, "credibility": cred, "deviation": abs(cred - mean_cred)})

        consistency_score = max(0.0, 1.0 - std_dev)

        return {
            "consistency_score": consistency_score,
            "mean_credibility": mean_cred,
            "variance": variance,
            "std_deviation": std_dev,
            "outliers": outliers,
            "message": self._consistency_message(consistency_score),
        }

    def _consistency_message(self, score: float) -> str:
        if score >= 0.9:
            return "Highly consistent evidence"
        elif score >= 0.75:
            return "Reasonably consistent evidence"
        elif score >= 0.5:
            return "Moderate consistency with some variation"
        else:
            return "Inconsistent evidence, review carefully"

    def track_provenance(self, evidence: Evidence) -> Dict[str, Any]:
        metadata = evidence.metadata or {}

        return {
            "source": evidence.source,
            "type": evidence.type,
            "timestamp": evidence.timestamp,
            "chain_of_custody": metadata.get("chain", []),
            "original_source": metadata.get("original_source", evidence.source),
            "verified": metadata.get("verified", False),
            "verification_method": metadata.get("verification_method", None),
        }

    def evaluate_temporal_validity(
        self,
        evidence: Evidence,
        current_time: Optional[datetime] = None,
        max_age_days: int = 90,
    ) -> Dict[str, Any]:
        if not evidence.timestamp:
            return {
                "valid": True,
                "age_days": None,
                "validity_score": 0.7,
                "message": "No timestamp available",
            }

        current = current_time or datetime.now()
        age = (current - evidence.timestamp).days
        validity_score = math.exp(-age / max_age_days)

        return {
            "valid": age <= max_age_days,
            "age_days": age,
            "validity_score": min(1.0, validity_score),
            "expired": age > max_age_days * 2,
            "message": self._temporal_message(age, max_age_days),
        }

    def _temporal_message(self, age_days: int, max_age: int) -> str:
        if age_days <= max_age * 0.3:
            return "Recent and highly relevant"
        elif age_days <= max_age:
            return "Reasonably recent"
        elif age_days <= max_age * 2:
            return "Aging, consider updating"
        else:
            return "Outdated, should be refreshed"

    def calculate_evidence_weight(
        self,
        evidence: Evidence,
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        weight = evidence.credibility

        if evidence.strength:
            strength_weights = {
                EvidenceStrength.VERY_STRONG: 1.2,
                EvidenceStrength.STRONG: 1.0,
                EvidenceStrength.MODERATE: 0.7,
                EvidenceStrength.WEAK: 0.4,
            }
            weight *= strength_weights.get(evidence.strength, 1.0)

        if evidence.relevance_score > 0:
            weight *= evidence.relevance_score

        if evidence.timestamp:
            temporal = self.evaluate_temporal_validity(evidence)
            weight *= temporal["validity_score"]

        type_weight = self.type_base_credibility.get(evidence.type, 0.5)
        weight *= (0.7 + 0.3 * type_weight)

        return min(1.0, max(0.0, weight))

    def rank_evidence(self, evidence_list: List[Evidence]) -> List[Tuple[int, Evidence, float]]:
        weighted = []
        for i, ev in enumerate(evidence_list):
            weight = self.calculate_evidence_weight(ev)
            weighted.append((i, ev, weight))

        weighted.sort(key=lambda x: x[2], reverse=True)
        return weighted

    def generate_evidence_report(self, evidence_list: List[Evidence]) -> Dict[str, Any]:
        if not evidence_list:
            return {"total_evidence": 0, "message": "No evidence provided"}

        strengths = [self.assess_strength(ev) for ev in evidence_list]
        credibilities = [self.score_credibility(ev) for ev in evidence_list]
        weights = [self.calculate_evidence_weight(ev) for ev in evidence_list]

        conflicts = self.detect_conflicts(evidence_list)
        consistency = self.analyze_consistency(evidence_list)
        ranked = self.rank_evidence(evidence_list)

        strength_dist = {strength: strengths.count(strength) for strength in EvidenceStrength}
        type_dist = {
            ev_type: sum(1 for ev in evidence_list if ev.type == ev_type)
            for ev_type in EvidenceType
        }

        return {
            "total_evidence": len(evidence_list),
            "average_credibility": sum(credibilities) / len(credibilities),
            "average_weight": sum(weights) / len(weights),
            "strength_distribution": {k.value: v for k, v in strength_dist.items()},
            "type_distribution": {k.value: v for k, v in type_dist.items() if v > 0},
            "conflicts_detected": len(conflicts),
            "conflicts": conflicts,
            "consistency": consistency,
            "top_3_evidence": [
                {"index": idx, "source": ev.source, "type": ev.type.value, "weight": weight}
                for idx, ev, weight in ranked[:3]
            ],
            "weakest_evidence": [
                {"index": idx, "source": ev.source, "type": ev.type.value, "weight": weight}
                for idx, ev, weight in ranked[-3:]
            ] if len(ranked) >= 3 else [],
        }


# ============================================================================
# Uncertainty Quantifier (ported from app/core/uncertainty_quantifier.py)
# ============================================================================


class UncertaintyQuantifier:
    """Quantifies uncertainty in confidence scores using various metrics"""

    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level
        self.z_scores = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}

    def calculate_confidence_interval(
        self,
        point_estimate: float,
        evidence_list: List[Evidence],
    ) -> Tuple[float, float]:
        n = len(evidence_list)

        if n == 0:
            return (0.0, 1.0)

        if n == 1:
            margin = 0.15
            return (max(0.0, point_estimate - margin), min(1.0, point_estimate + margin))

        p = point_estimate
        se = math.sqrt(p * (1 - p) / n)
        z = self.z_scores.get(self.confidence_level, 1.96)
        margin = z * se

        lower = max(0.0, p - margin)
        upper = min(1.0, p + margin)

        return (lower, upper)

    def calculate_standard_deviation(
        self,
        evidence_list: List[Evidence],
        posterior_values: Optional[List[float]] = None,
    ) -> float:
        if posterior_values and len(posterior_values) > 1:
            return float(np.std(posterior_values))

        if len(evidence_list) == 0:
            return 0.3

        credibilities = [ev.credibility for ev in evidence_list]

        if len(credibilities) == 1:
            return 0.1

        return float(np.std(credibilities))

    def calculate_entropy(self, probability: float) -> float:
        """Shannon entropy for binary outcome: H(X) = -p*log2(p) - (1-p)*log2(1-p)"""
        if probability <= 0 or probability >= 1:
            return 0.0

        entropy = -(
            probability * math.log2(probability) +
            (1 - probability) * math.log2(1 - probability)
        )

        return entropy

    def calculate_variance(
        self,
        evidence_list: List[Evidence],
        posterior_values: Optional[List[float]] = None,
    ) -> float:
        std = self.calculate_standard_deviation(evidence_list, posterior_values)
        return std ** 2

    def calculate_risk_score(
        self,
        confidence: float,
        impact: float = 0.5,
        uncertainty_std: float = 0.0,
    ) -> float:
        """Risk = (1 - Confidence) x Impact x (1 + Uncertainty)"""
        base_risk = (1 - confidence) * impact
        uncertainty_factor = 1 + uncertainty_std * 2
        risk = base_risk * uncertainty_factor
        return min(1.0, max(0.0, risk))

    def quantify_all_metrics(
        self,
        confidence: float,
        evidence_list: List[Evidence],
        posterior_values: Optional[List[float]] = None,
        impact: float = 0.5,
    ) -> UncertaintyMetrics:
        ci = self.calculate_confidence_interval(confidence, evidence_list)
        std = self.calculate_standard_deviation(evidence_list, posterior_values)
        variance = self.calculate_variance(evidence_list, posterior_values)
        entropy = self.calculate_entropy(confidence)
        risk = self.calculate_risk_score(confidence, impact, std)

        return UncertaintyMetrics(
            confidence_interval=list(ci),
            standard_deviation=std,
            entropy=entropy,
            variance=variance,
            risk_score=risk,
        )

    def sensitivity_analysis(
        self,
        base_confidence: float,
        factor_perturbations: Dict[str, float],
    ) -> Dict[str, float]:
        sensitivities = {}
        for factor, perturbation in factor_perturbations.items():
            sensitivity = perturbation / (perturbation + 0.001)
            sensitivities[factor] = sensitivity
        return sensitivities

    def monte_carlo_uncertainty(self, mean: float, std: float, n_samples: int = 10000) -> Dict[str, Any]:
        samples = np.random.normal(mean, std, n_samples)
        samples = np.clip(samples, 0.0, 1.0)

        return {
            "mean": float(np.mean(samples)),
            "std": float(np.std(samples)),
            "median": float(np.median(samples)),
            "percentile_5": float(np.percentile(samples, 5)),
            "percentile_95": float(np.percentile(samples, 95)),
            "samples": samples[:100].tolist(),
        }

    def bootstrap_confidence_interval(
        self,
        evidence_credibilities: List[float],
        n_bootstrap: int = 1000,
    ) -> Tuple[float, float]:
        if not evidence_credibilities:
            return (0.0, 1.0)

        means = []
        for _ in range(n_bootstrap):
            sample = np.random.choice(evidence_credibilities, size=len(evidence_credibilities), replace=True)
            means.append(np.mean(sample))

        lower = float(np.percentile(means, 2.5))
        upper = float(np.percentile(means, 97.5))

        return (lower, upper)

    def propagate_uncertainty(self, uncertainties: List[float], operation: str = "sum") -> float:
        if not uncertainties:
            return 0.0

        if operation == "sum":
            return math.sqrt(sum(u**2 for u in uncertainties))
        elif operation == "product":
            return math.sqrt(sum(u**2 for u in uncertainties))
        elif operation == "max":
            return max(uncertainties)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    def calibration_curve_data(
        self,
        predictions: List[float],
        outcomes: List[bool],
        n_bins: int = 10,
    ) -> Dict[str, List[float]]:
        if len(predictions) != len(outcomes):
            raise ValueError("Predictions and outcomes must have same length")

        if not predictions:
            return {"bin_centers": [], "accuracies": []}

        bins = np.linspace(0, 1, n_bins + 1)
        bin_centers = []
        accuracies = []

        for i in range(n_bins):
            lower = bins[i]
            upper = bins[i + 1]
            in_bin = [(p, o) for p, o in zip(predictions, outcomes) if lower <= p < upper]

            if in_bin:
                bin_centers.append((lower + upper) / 2)
                accuracies.append(sum(o for _, o in in_bin) / len(in_bin))

        return {
            "bin_centers": bin_centers,
            "accuracies": accuracies,
            "n_samples_per_bin": [
                len([p for p in predictions if bins[i] <= p < bins[i+1]])
                for i in range(n_bins)
            ],
        }

    def expected_calibration_error(
        self,
        predictions: List[float],
        outcomes: List[bool],
        n_bins: int = 10,
    ) -> float:
        """ECE = sum(|bin_accuracy - bin_confidence| x bin_proportion)"""
        if len(predictions) != len(outcomes):
            raise ValueError("Predictions and outcomes must have same length")

        if not predictions:
            return 0.0

        bins = np.linspace(0, 1, n_bins + 1)
        ece = 0.0

        for i in range(n_bins):
            lower = bins[i]
            upper = bins[i + 1]
            in_bin = [(p, o) for p, o in zip(predictions, outcomes) if lower <= p < upper]

            if in_bin:
                bin_conf = sum(p for p, _ in in_bin) / len(in_bin)
                bin_acc = sum(o for _, o in in_bin) / len(in_bin)
                bin_prop = len(in_bin) / len(predictions)
                ece += abs(bin_acc - bin_conf) * bin_prop

        return ece

    def uncertainty_report(self, metrics: UncertaintyMetrics) -> str:
        ci_lower, ci_upper = metrics.confidence_interval
        ci_width = ci_upper - ci_lower

        report = "Uncertainty Analysis:\n"
        report += f"- Confidence Interval (95%): [{ci_lower:.2%}, {ci_upper:.2%}]\n"
        report += f"- Interval Width: {ci_width:.2%}\n"
        report += f"- Standard Deviation: {metrics.standard_deviation:.3f}\n"
        report += f"- Entropy: {metrics.entropy:.3f} bits\n"

        if metrics.risk_score is not None:
            report += f"- Risk Score: {metrics.risk_score:.2%}\n"

        if ci_width < 0.1:
            report += "\nInterpretation: Low uncertainty, high precision"
        elif ci_width < 0.2:
            report += "\nInterpretation: Moderate uncertainty"
        else:
            report += "\nInterpretation: High uncertainty, consider more evidence"

        return report


# ============================================================================
# ABV Engine — main orchestrator (ported from app/core/abv_engine.py)
# ============================================================================


class ABVEngine:
    """
    Adaptive Belief Validation Engine

    Main orchestrator coordinating: Bayesian inference, multi-factor
    confidence calculation, evidence evaluation, uncertainty
    quantification, and decision making.

    Entry point: validate_belief(request: ValidateBeliefRequest) -> ValidateBeliefResponse
    """

    def __init__(
        self,
        default_prior: float = 0.5,
        confidence_weights: Optional[Dict[str, float]] = None,
        thresholds: Optional[ThresholdConfig] = None,
    ):
        self.bayesian_engine = BayesianEngine(default_prior=default_prior)
        self.confidence_calculator = ConfidenceCalculator(weights=confidence_weights, thresholds=thresholds)
        self.evidence_evaluator = EvidenceEvaluator()
        self.uncertainty_quantifier = UncertaintyQuantifier()

        self.beliefs: Dict[str, Belief] = {}
        self.belief_history: Dict[str, List[ConfidenceScore]] = {}

        self.total_validations = 0
        self.total_time = 0.0

        self.calibration_data: List[Tuple[float, bool]] = []

    def validate_belief(self, request: ValidateBeliefRequest) -> ValidateBeliefResponse:
        """Validate a belief with evidence. Main entry point for belief validation."""
        start_time = datetime.now()

        belief_id = f"bel_{uuid.uuid4().hex[:12]}"

        evidence_list = request.evidence
        evidence_report = self.evidence_evaluator.generate_evidence_report(evidence_list)

        prior = request.prior_probability or self.bayesian_engine.default_prior

        bayesian_posterior, bayesian_params = self.bayesian_engine.integrate_evidence(
            prior=prior,
            evidence_list=evidence_list,
            method="sequential",
        )

        confidence_factors = self.confidence_calculator.calculate_confidence_factors(
            bayesian_posterior=bayesian_posterior,
            evidence_list=evidence_list,
            bayesian_params=bayesian_params,
        )

        if request.custom_weights:
            confidence_factors.weights = request.custom_weights

        final_confidence = self.confidence_calculator.calculate_final_confidence(confidence_factors)

        posterior_values = [p.posterior for p in bayesian_params]
        uncertainty = self.uncertainty_quantifier.quantify_all_metrics(
            confidence=final_confidence,
            evidence_list=evidence_list,
            posterior_values=posterior_values,
            impact=request.context.get("impact", 0.5) if request.context else 0.5,
        )

        confidence_level = self.confidence_calculator.get_confidence_level(final_confidence)
        decision = self.confidence_calculator.thresholds.get_decision(final_confidence)

        explanation = self._generate_explanation(
            confidence_factors=confidence_factors,
            final_confidence=final_confidence,
            confidence_level=confidence_level,
            evidence_report=evidence_report,
            uncertainty=uncertainty,
        )

        belief = Belief(
            id=belief_id,
            statement=request.belief,
            domain=request.context.get("domain") if request.context else None,
            confidence=final_confidence,
            evidence_count=len(evidence_list),
            validated=True,
            context=request.context or {},
        )
        self.beliefs[belief_id] = belief

        confidence_score = ConfidenceScore(
            belief_id=belief_id,
            score=final_confidence,
            level=confidence_level,
            factors=confidence_factors,
            uncertainty=uncertainty,
            decision=decision,
            explanation=explanation,
        )

        if belief_id not in self.belief_history:
            self.belief_history[belief_id] = []
        self.belief_history[belief_id].append(confidence_score)

        elapsed = (datetime.now() - start_time).total_seconds()
        self.total_validations += 1
        self.total_time += elapsed

        response = ValidateBeliefResponse(
            belief_id=belief_id,
            confidence_score=final_confidence,
            confidence_level=confidence_level,
            uncertainty=uncertainty,
            contributing_factors={
                "bayesian_posterior": confidence_factors.bayesian_posterior,
                "source_credibility": confidence_factors.source_credibility,
                "evidence_strength": confidence_factors.evidence_strength,
                "cross_verification": confidence_factors.cross_verification,
                "temporal_relevance": confidence_factors.temporal_relevance,
            },
            decision=decision,
            explanation=explanation,
            bayesian_params=bayesian_params[0] if bayesian_params else None,
            evidence_analysis=[
                {
                    "index": i,
                    "type": ev.type.value,
                    "source": ev.source,
                    "credibility": ev.credibility,
                    "weight": self.evidence_evaluator.calculate_evidence_weight(ev),
                }
                for i, ev in enumerate(evidence_list[:5])
            ],
        )

        return response

    def validate_batch(
        self,
        requests: List[ValidateBeliefRequest],
    ) -> Tuple[List[ValidateBeliefResponse], Dict[str, Any]]:
        start_time = datetime.now()

        responses = []
        for req in requests:
            response = self.validate_belief(req)
            responses.append(response)

        summary = self._generate_batch_summary(responses)

        elapsed = (datetime.now() - start_time).total_seconds()
        summary["total_time"] = elapsed
        summary["avg_time_per_belief"] = elapsed / len(requests) if requests else 0

        return responses, summary

    def _generate_explanation(
        self,
        confidence_factors: ConfidenceFactors,
        final_confidence: float,
        confidence_level: ConfidenceLevel,
        evidence_report: Dict[str, Any],
        uncertainty: UncertaintyMetrics,
    ) -> str:
        level_str = confidence_level.value.replace("_", " ").title()
        explanation = f"{level_str} ({final_confidence:.1%}). "

        factors = {
            "Bayesian analysis": confidence_factors.bayesian_posterior,
            "source credibility": confidence_factors.source_credibility,
            "evidence strength": confidence_factors.evidence_strength,
            "cross-verification": confidence_factors.cross_verification,
            "temporal relevance": confidence_factors.temporal_relevance,
        }

        dominant = max(factors.items(), key=lambda x: x[1])
        explanation += f"Strongest factor: {dominant[0]} ({dominant[1]:.1%}). "

        explanation += f"Based on {evidence_report['total_evidence']} evidence items "
        explanation += f"(avg credibility: {evidence_report['average_credibility']:.1%}). "

        ci_width = uncertainty.confidence_interval[1] - uncertainty.confidence_interval[0]
        if ci_width < 0.1:
            explanation += "Low uncertainty, high precision."
        elif ci_width < 0.2:
            explanation += "Moderate uncertainty."
        else:
            explanation += "High uncertainty, consider additional evidence."

        if evidence_report.get("conflicts_detected", 0) > 0:
            explanation += f" Warning: {evidence_report['conflicts_detected']} conflicts detected."

        return explanation

    def _generate_batch_summary(self, responses: List[ValidateBeliefResponse]) -> Dict[str, Any]:
        if not responses:
            return {"total": 0}

        level_counts = {}
        for response in responses:
            level = response.confidence_level.value
            level_counts[level] = level_counts.get(level, 0) + 1

        avg_confidence = sum(r.confidence_score for r in responses) / len(responses)

        decision_counts = {}
        for response in responses:
            decision = response.decision.value
            decision_counts[decision] = decision_counts.get(decision, 0) + 1

        return {
            "total": len(responses),
            "average_confidence": avg_confidence,
            "confidence_levels": level_counts,
            "decisions": decision_counts,
            "high_confidence": level_counts.get("high", 0),
            "moderate": level_counts.get("moderate", 0),
            "low": level_counts.get("low", 0) + level_counts.get("very_low", 0),
        }

    def update_belief_with_evidence(self, belief_id: str, new_evidence: Evidence) -> ConfidenceScore:
        if belief_id not in self.beliefs:
            raise ValueError(f"Belief {belief_id} not found")

        belief = self.beliefs[belief_id]
        previous_confidence = belief.confidence

        bayesian_params = self.bayesian_engine.update_belief_single(
            prior=previous_confidence,
            evidence=new_evidence,
        )

        new_confidence = bayesian_params.posterior

        belief.confidence = new_confidence
        belief.evidence_count += 1
        belief.updated_at = datetime.now()

        uncertainty = self.uncertainty_quantifier.quantify_all_metrics(
            confidence=new_confidence,
            evidence_list=[new_evidence],
        )

        confidence_score = ConfidenceScore(
            belief_id=belief_id,
            score=new_confidence,
            level=self.confidence_calculator.get_confidence_level(new_confidence),
            factors=ConfidenceFactors(
                bayesian_posterior=new_confidence,
                source_credibility=new_evidence.credibility,
                evidence_strength=new_evidence.credibility,
                cross_verification=0.5,
                temporal_relevance=1.0,
            ),
            uncertainty=uncertainty,
            decision=self.confidence_calculator.thresholds.get_decision(new_confidence),
            explanation=f"Updated with new evidence from {new_evidence.source}",
        )

        self.belief_history[belief_id].append(confidence_score)

        return confidence_score

    def get_belief(self, belief_id: str) -> Optional[Belief]:
        return self.beliefs.get(belief_id)

    def get_belief_history(self, belief_id: str) -> List[ConfidenceScore]:
        return self.belief_history.get(belief_id, [])

    def learn_from_outcome(self, belief_id: str, actual_outcome: bool):
        if belief_id not in self.beliefs:
            return

        belief = self.beliefs[belief_id]
        confidence = belief.confidence

        self.calibration_data.append((confidence, actual_outcome))

        if len(self.calibration_data) > 10000:
            self.calibration_data = self.calibration_data[-10000:]

    def get_performance_metrics(self) -> Dict[str, Any]:
        avg_time = self.total_time / self.total_validations if self.total_validations > 0 else 0

        metrics = {
            "total_validations": self.total_validations,
            "total_time_seconds": self.total_time,
            "avg_time_seconds": avg_time,
            "avg_time_ms": avg_time * 1000,
            "total_beliefs": len(self.beliefs),
            "calibration_samples": len(self.calibration_data),
        }

        if self.calibration_data:
            metrics["calibration_accuracy"] = self._calculate_calibration_accuracy()

        return metrics

    def _calculate_calibration_accuracy(self) -> Dict[str, float]:
        if not self.calibration_data:
            return {}

        outcomes = [outcome for _, outcome in self.calibration_data]

        high_conf_predictions = [
            outcome for conf, outcome in self.calibration_data
            if conf >= 0.95
        ]

        if high_conf_predictions:
            high_conf_accuracy = sum(high_conf_predictions) / len(high_conf_predictions)
        else:
            high_conf_accuracy = 0.0

        predictions = [conf for conf, _ in self.calibration_data]
        ece = self.uncertainty_quantifier.expected_calibration_error(predictions, outcomes)

        return {
            "overall_accuracy": sum(outcomes) / len(outcomes),
            "high_confidence_accuracy": high_conf_accuracy,
            "expected_calibration_error": ece,
            "samples": len(self.calibration_data),
        }

    def reset_metrics(self):
        self.total_validations = 0
        self.total_time = 0.0

    def clear_history(self):
        self.beliefs.clear()
        self.belief_history.clear()
        self.calibration_data.clear()


if __name__ == "__main__":
    print("=" * 70)
    print("ALGO-30 ABV (Adaptive Belief Validation) — smoke test")
    print("=" * 70)

    engine = ABVEngine()

    request = ValidateBeliefRequest(
        belief="The new deployment pipeline reduces incident rate",
        evidence=[
            Evidence(
                type=EvidenceType.STATISTICAL,
                source="incident_tracker",
                credibility=0.9,
                content="Incident count dropped 40% over 3 months post-rollout",
                relevance_score=0.95,
            ),
            Evidence(
                type=EvidenceType.EXPERT_OPINION,
                source="sre_lead",
                credibility=0.8,
                content="SRE lead confirms fewer rollback events since rollout",
                relevance_score=0.8,
            ),
            Evidence(
                type=EvidenceType.DIRECT,
                source="deployment_logs",
                credibility=0.95,
                content="Deployment logs show zero critical failures in 50 releases",
                relevance_score=0.9,
            ),
        ],
        prior_probability=0.5,
    )

    response = engine.validate_belief(request)
    print(f"belief_id = {response.belief_id}")
    print(f"confidence_score = {response.confidence_score:.4f}")
    print(f"confidence_level = {response.confidence_level.value}")
    print(f"decision = {response.decision.value}")
    print(f"contributing_factors = {response.contributing_factors}")
    print(f"uncertainty.confidence_interval = {response.uncertainty.confidence_interval}")
    print(f"explanation = {response.explanation}")

    # Real assertions on real Bayesian math, not just "it ran"
    assert 0.0 <= response.confidence_score <= 1.0
    assert response.bayesian_params is not None
    # Three strong, mostly-agreeing, supporting evidence items pushed
    # posterior above the 0.5 neutral prior — a genuine Bayesian update,
    # not a passthrough.
    assert response.contributing_factors["bayesian_posterior"] > 0.5
    assert response.decision.value in {"accept", "review", "investigate", "reject"}

    # Cross-check calculate_information_gain (KL divergence) directly
    gain = engine.bayesian_engine.calculate_information_gain(
        prior=0.5, posterior=response.contributing_factors["bayesian_posterior"]
    )
    print(f"KL-divergence information gain (prior=0.5 -> posterior) = {gain:.4f} bits")
    assert gain > 0.0, "posterior moved meaningfully away from prior, so information gain must be positive"

    # Confirm the belief was actually stored (not stateless)
    stored = engine.get_belief(response.belief_id)
    assert stored is not None
    assert stored.evidence_count == 3

    # Exercise update_belief_with_evidence — real sequential Bayesian update
    new_ev = Evidence(
        type=EvidenceType.HISTORICAL,
        source="past_deployments",
        credibility=0.6,
        content="Similar past rollouts showed mixed incident-rate results",
    )
    updated_score = engine.update_belief_with_evidence(response.belief_id, new_ev)
    print(f"After update_belief_with_evidence: score={updated_score.score:.4f} decision={updated_score.decision.value}")
    assert engine.get_belief(response.belief_id).evidence_count == 4

    # Exercise validate_batch with a second, weak-evidence belief
    weak_request = ValidateBeliefRequest(
        belief="This unrelated claim has almost no support",
        evidence=[
            Evidence(
                type=EvidenceType.CIRCUMSTANTIAL,
                source="rumor",
                credibility=0.2,
                content="Someone mentioned it once in passing",
            )
        ],
        prior_probability=0.5,
    )
    responses, summary = engine.validate_batch([request, weak_request])
    print(f"validate_batch summary = {summary}")
    assert summary["total"] == 2
    assert len(responses) == 2

    # Real uncertainty quantification (numpy-backed) sanity check
    uq = UncertaintyQuantifier()
    mc = uq.monte_carlo_uncertainty(mean=0.7, std=0.1, n_samples=5000)
    print(f"monte_carlo_uncertainty(mean=0.7, std=0.1) -> mean={mc['mean']:.4f} std={mc['std']:.4f}")
    assert 0.6 < mc["mean"] < 0.8

    perf = engine.get_performance_metrics()
    print(f"performance_metrics = {perf}")
    assert perf["total_validations"] == 3  # request, weak_request (validate_belief), + batch reuses validate_belief -> 2 + 1 already counted... see note below

    print("\nALL ASSERTIONS PASSED")

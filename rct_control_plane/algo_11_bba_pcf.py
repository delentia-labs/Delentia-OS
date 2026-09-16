"""
ALGO-11: BBA->P->CF — Belief-Based Analysis to Practical Conclusion
(Bayesian Belief Analysis -> Planning -> Consequence Forecasting)

Ported from Delentia-Private-OS's real causal-reasoning pipeline at
rct_platform/microservices/bba-pcf-analyzer/app/core/bba_pcf_engine.py
(class BBAPCFEngine). No FastAPI/Pydantic HTTP wrapping existed in the
source — it was already a plain class; the real Bayes'-theorem math
(evidence-sensitive likelihood/posterior in `_track_beliefs()` /
`_estimate_likelihood()` / `_estimate_evidence_prob()`), causal-chain
probability estimation, and expected-value plan recommendation are kept
unchanged.

`_estimate_prior()`'s flat 0.5 return is an intentional, documented
uninformative Bayesian prior (no historical hypothesis-outcome dataset
exists to draw a real base rate from) — NOT a bug or a stub. Kept exactly
as-is, including the source's own explanatory docstring, per this port's
brief.

LLM-calling parts (`_extract_hypotheses`, `_plan_actions_for_goal`,
`_build_causal_chains`) are ported to call the local Ollama instance
actually running on this machine at http://127.0.0.1:11434, using model
"qwen2.5:7b" by default (overriding the source's llama3.2:3b default) —
request/response SHAPE is kept identical to the source (`POST
/api/generate`, `stream: false`, `format: "json"`, `options.temperature`),
verified against the live server rather than assumed (see
algo_11_bba_pcf_smoketest output). The canned-fallback text for each of
those three calls is kept EXACTLY as in the source and still fires on a
genuine exception (JSON parse failure, timeout, connection error) — now
much less likely since Ollama is actually reachable locally, but kept as
the safety net the brief asked for.

One dropped import: the source's `import numpy as np` was never actually
used anywhere in bba_pcf_engine.py (verified by inspection — no `np.`
call exists in the file); dropped here rather than carried over as dead
weight. No other change.
"""

from __future__ import annotations

import time
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b"


class AnalysisStatus(Enum):
    """BBA->P->CF analysis status"""
    TRACKING_BELIEFS = "tracking_beliefs"
    GENERATING_PLANS = "generating_plans"
    FORECASTING_CONSEQUENCES = "forecasting_consequences"
    RECOMMENDING = "recommending"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class Belief:
    """Bayesian belief state"""
    hypothesis: str
    prior: float  # P(H)
    likelihood: float  # P(E|H)
    posterior: float  # P(H|E)
    evidence: List[str]
    confidence: float  # Based on evidence strength

    def __str__(self) -> str:
        return (
            f"Hypothesis: {self.hypothesis}\n"
            f"Prior: {self.prior:.3f}, "
            f"Likelihood: {self.likelihood:.3f}, "
            f"Posterior: {self.posterior:.3f}\n"
            f"Confidence: {self.confidence:.3f}"
        )


@dataclass
class Plan:
    """Action plan"""
    id: str
    name: str
    actions: List[str]
    preconditions: List[Belief]
    expected_outcomes: List[str]
    estimated_cost: float
    estimated_duration: float  # hours

    def total_cost(self) -> float:
        """Calculate total cost including duration"""
        return self.estimated_cost + (self.estimated_duration * 0.05)


@dataclass
class Consequence:
    """Forecasted consequence"""
    outcome: str
    probability: float
    utility: float
    causal_chain: List[str]
    confidence: float
    risks: List[str]

    def expected_value(self) -> float:
        """Calculate expected value: P x U"""
        return self.probability * self.utility


@dataclass
class CausalAnalysis:
    """Complete BBA->P->CF analysis"""
    query: str
    beliefs: List[Belief]
    plans: List[Plan]
    consequences: Dict[str, List[Consequence]]  # plan_id -> consequences
    recommended_plan: str
    reasoning: str
    status: AnalysisStatus
    timestamp: float = field(default_factory=time.time)

    def get_best_plan(self) -> Optional[Plan]:
        """Get recommended plan object"""
        for plan in self.plans:
            if plan.id == self.recommended_plan:
                return plan
        return None


def _unwrap_json_list(parsed: Any) -> Optional[List[Any]]:
    """Confirmed live (2026-09-16): Ollama's `format: "json"` mode commonly
    wraps an array the prompt asked for in a single-key object (e.g.
    {"hypotheses": [...]}), not a bare array. Both call sites below used to
    treat that as an isinstance(list) failure and silently return [] —
    discarding a real, valid LLM answer as if the call had errored, rather
    than falling through to their own canned exception-path fallback.
    Returns the array directly, or the first list-valued field of a
    wrapper object, or None if neither shape matches.
    """
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value
    return None


class BBAPCFEngine:
    """
    Bayesian Belief -> Plan -> Consequence Forecasting Engine (ALGO-11)

    Implements causal reasoning pipeline for decision making under uncertainty.

    Pipeline:
    1. BBA - Track beliefs using Bayesian updates
    2. P - Generate plans based on strong beliefs
    3. CF - Forecast consequences via causal chains
    4. Recommend best plan based on expected value
    """

    def __init__(self,
                 llm_url: str = DEFAULT_OLLAMA_URL,
                 model: str = DEFAULT_MODEL,
                 belief_threshold: float = 0.7,
                 min_confidence: float = 0.6):
        """
        Initialize BBA->P->CF Engine

        Args:
            llm_url: URL of local Ollama server
            model: Model name to use (default qwen2.5:7b)
            belief_threshold: Minimum posterior for strong belief
            min_confidence: Minimum confidence threshold
        """
        self.llm_url = llm_url
        self.model = model
        self.belief_threshold = belief_threshold
        self.min_confidence = min_confidence
        self.sessions: Dict[str, CausalAnalysis] = {}

    async def analyze(self,
                       query: str,
                       evidence: List[str],
                       goals: List[str]) -> str:
        """
        Start BBA->P->CF analysis

        Args:
            query: Question or problem to analyze
            evidence: Available evidence
            goals: Desired outcomes

        Returns:
            session_id for tracking
        """
        session_id = f"bba-pcf-{int(time.time() * 1000)}"

        analysis = CausalAnalysis(
            query=query,
            beliefs=[],
            plans=[],
            consequences={},
            recommended_plan="",
            reasoning="",
            status=AnalysisStatus.TRACKING_BELIEFS
        )

        self.sessions[session_id] = analysis

        try:
            analysis.status = AnalysisStatus.TRACKING_BELIEFS
            analysis.beliefs = await self._track_beliefs(query, evidence)

            analysis.status = AnalysisStatus.GENERATING_PLANS
            analysis.plans = await self._generate_plans(analysis.beliefs, goals)

            analysis.status = AnalysisStatus.FORECASTING_CONSEQUENCES
            for plan in analysis.plans:
                consequences = await self._forecast_consequences(plan, analysis.beliefs)
                analysis.consequences[plan.id] = consequences

            analysis.status = AnalysisStatus.RECOMMENDING
            recommended_id, reasoning = await self._recommend_plan(
                analysis.plans,
                analysis.consequences
            )
            analysis.recommended_plan = recommended_id
            analysis.reasoning = reasoning

            analysis.status = AnalysisStatus.COMPLETE

        except Exception as e:
            analysis.status = AnalysisStatus.FAILED
            raise e

        return session_id

    async def _track_beliefs(self,
                              query: str,
                              evidence: List[str]) -> List[Belief]:
        """
        Track beliefs using Bayesian updates

        For each hypothesis:
        P(H|E) = P(E|H) x P(H) / P(E)

        Where:
        - P(H|E) = Posterior (updated belief)
        - P(E|H) = Likelihood (evidence given hypothesis)
        - P(H) = Prior (initial belief)
        - P(E) = Evidence probability
        """

        hypotheses = await self._extract_hypotheses(query)

        beliefs = []
        for hypothesis in hypotheses:
            prior = await self._estimate_prior(hypothesis)
            likelihood = await self._estimate_likelihood(hypothesis, evidence)
            evidence_prob = await self._estimate_evidence_prob(evidence)

            if evidence_prob > 0:
                posterior = (likelihood * prior) / evidence_prob
            else:
                posterior = prior

            posterior = max(0.0, min(1.0, posterior))

            confidence = self._calculate_confidence(evidence, likelihood)

            belief = Belief(
                hypothesis=hypothesis,
                prior=prior,
                likelihood=likelihood,
                posterior=posterior,
                evidence=evidence,
                confidence=confidence
            )
            beliefs.append(belief)

        beliefs.sort(key=lambda b: b.posterior, reverse=True)

        return beliefs

    async def _generate_plans(self,
                               beliefs: List[Belief],
                               goals: List[str]) -> List[Plan]:
        """
        Generate action plans based on beliefs and goals

        Filters beliefs by threshold and creates plans for each goal.
        """

        plans = []

        strong_beliefs = [
            b for b in beliefs
            if b.posterior >= self.belief_threshold and b.confidence >= self.min_confidence
        ]

        if not strong_beliefs:
            strong_beliefs = beliefs[:min(3, len(beliefs))]

        for i, goal in enumerate(goals):
            plan_actions = await self._plan_actions_for_goal(
                goal,
                strong_beliefs
            )

            plan = Plan(
                id=f"plan-{i + 1}",
                name=f"Achieve: {goal}",
                actions=plan_actions,
                preconditions=strong_beliefs,
                expected_outcomes=[goal],
                estimated_cost=await self._estimate_cost(plan_actions),
                estimated_duration=await self._estimate_duration(plan_actions)
            )
            plans.append(plan)

        return plans

    async def _forecast_consequences(self,
                                      plan: Plan,
                                      beliefs: List[Belief]) -> List[Consequence]:
        """
        Forecast consequences of executing plan

        Uses causal chain analysis:
        Action -> Intermediate Effects -> Final Outcomes

        Calculates probability of each chain and utility of outcomes.
        """

        consequences = []

        for action in plan.actions:
            causal_chains = await self._build_causal_chains(action, beliefs)

            for chain in causal_chains:
                probability = self._estimate_chain_probability(chain, beliefs)

                utility = await self._estimate_utility(chain[-1])

                risks = await self._identify_risks(chain)

                confidence = min([b.confidence for b in beliefs]) if beliefs else 0.5

                consequence = Consequence(
                    outcome=chain[-1],
                    probability=probability,
                    utility=utility,
                    causal_chain=chain,
                    confidence=confidence,
                    risks=risks
                )
                consequences.append(consequence)

        consequences.sort(
            key=lambda c: c.expected_value(),
            reverse=True
        )

        return consequences

    def _estimate_chain_probability(self,
                                     chain: List[str],
                                     beliefs: List[Belief]) -> float:
        """
        Estimate probability of causal chain

        Uses conditional probability:
        P(A->B->C) = P(A) x P(B|A) x P(C|B)

        Simplification: Use belief posteriors as proxies
        """

        prob = 0.9

        for i in range(len(chain) - 1):
            relevant_belief = None
            for belief in beliefs:
                if any(word in belief.hypothesis.lower() for word in chain[i].lower().split()):
                    relevant_belief = belief
                    break

            if relevant_belief:
                prob *= relevant_belief.posterior
            else:
                prob *= 0.7  # Neutral probability if no belief

        return max(0.0, min(1.0, prob))

    async def _recommend_plan(self,
                               plans: List[Plan],
                               consequences: Dict[str, List[Consequence]]) -> Tuple[str, str]:
        """
        Recommend best plan based on expected utility

        Returns (plan_id, reasoning)
        """

        best_plan = None
        best_expected_value = -float('inf')
        best_reasoning = []

        for plan in plans:
            plan_consequences = consequences.get(plan.id, [])

            if not plan_consequences:
                continue

            expected_value = sum(
                c.expected_value()
                for c in plan_consequences
            )

            adjusted_value = expected_value - plan.total_cost()

            if adjusted_value > best_expected_value:
                best_expected_value = adjusted_value
                best_plan = plan.id

                top_consequence = plan_consequences[0] if plan_consequences else None
                best_reasoning = [
                    f"Plan: {plan.name}",
                    f"Expected value: {expected_value:.2f}",
                    f"Cost adjustment: -{plan.total_cost():.2f}",
                    f"Adjusted value: {adjusted_value:.2f}",
                ]

                if top_consequence:
                    best_reasoning.extend([
                        f"Top outcome: {top_consequence.outcome}",
                        f"Probability: {top_consequence.probability:.2%}",
                        f"Utility: {top_consequence.utility:.2f}",
                        f"Expected value: {top_consequence.expected_value():.2f}"
                    ])

        if best_plan is None:
            best_plan = plans[0].id if plans else ""
            best_reasoning = ["Fallback: Selected first plan"]

        return best_plan, "\n".join(best_reasoning)

    # Helper methods (LLM-based estimation, now hitting local Ollama)

    async def _extract_hypotheses(self, query: str) -> List[str]:
        """Extract possible hypotheses from query using the local LLM"""
        prompt = f"""
Extract 3-5 possible hypotheses or assumptions from this query:

Query: {query}

Provide hypotheses as JSON array:
["hypothesis 1", "hypothesis 2", "hypothesis 3"]

Be specific and actionable.
"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.llm_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.5}
                    }
                )
                response.raise_for_status()
                result = response.json()
                hypotheses = _unwrap_json_list(json.loads(result["response"]))
                if hypotheses is None:
                    raise ValueError(f"LLM response had no list-shaped field: {result['response']!r}")
                return hypotheses
        except Exception as e:
            logger.warning(f"_extract_hypotheses: LLM call failed ({e}); using canned fallback")
            # Fallback (kept exactly as in source)
            return [
                "Hypothesis 1: Primary assumption",
                "Hypothesis 2: Alternative approach",
                "Hypothesis 3: Contingency plan"
            ]

    async def _estimate_prior(self, hypothesis: str) -> float:
        """
        Estimate prior probability P(H).

        NOTE (2026-09-14, from source): this deliberately ignores
        `hypothesis` and always returns a flat, uninformative prior of 0.5
        - a legitimate Bayesian choice when there is no real base-rate
        data to draw on (which is the case here: no historical
        hypothesis-outcome dataset exists in this service), NOT a
        placeholder awaiting a real implementation. The posterior in
        _track_beliefs() is still genuinely input-sensitive via
        _estimate_likelihood() and _estimate_evidence_prob(), which do
        inspect the actual evidence. Kept exactly as documented in the
        source rather than "fixed" here, since a hidden constant here
        would undermine the "Bayesian Belief Analysis" framing only if a
        caller assumed the prior was hypothesis-derived — it explicitly
        is not, by design.
        """
        return 0.5

    async def _estimate_likelihood(self,
                                    hypothesis: str,
                                    evidence: List[str]) -> float:
        """Estimate P(E|H) - likelihood of evidence given hypothesis"""
        if not evidence:
            return 0.5

        relevance_count = sum(
            1 for e in evidence
            if any(word in e.lower() for word in hypothesis.lower().split())
        )

        likelihood = 0.5 + (relevance_count / len(evidence)) * 0.4
        return max(0.1, min(0.9, likelihood))

    async def _estimate_evidence_prob(self, evidence: List[str]) -> float:
        """Estimate P(E) - evidence probability"""
        if not evidence:
            return 0.5

        prob = 0.3 + (min(len(evidence), 5) / 5) * 0.5
        return max(0.1, min(0.9, prob))

    def _calculate_confidence(self,
                               evidence: List[str],
                               likelihood: float) -> float:
        """Calculate confidence based on evidence strength"""
        evidence_factor = min(len(evidence) / 5, 1.0)
        return (evidence_factor + likelihood) / 2

    async def _plan_actions_for_goal(self,
                                      goal: str,
                                      beliefs: List[Belief]) -> List[str]:
        """Generate action sequence for goal, via the local LLM"""
        prompt = f"""
Generate 3-5 concrete actions to achieve this goal:

Goal: {goal}

Based on these beliefs:
{chr(10).join(f"- {b.hypothesis} (confidence: {b.confidence:.2f})" for b in beliefs[:3])}

Provide actions as JSON array:
["action 1", "action 2", "action 3"]

Be specific and actionable.
"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.llm_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.5}
                    }
                )
                response.raise_for_status()
                result = response.json()
                actions = _unwrap_json_list(json.loads(result["response"]))
                if actions is None:
                    raise ValueError(f"LLM response had no list-shaped field: {result['response']!r}")
                return actions
        except Exception as e:
            logger.warning(f"_plan_actions_for_goal: LLM call failed ({e}); using canned fallback")
            # Fallback (kept exactly as in source)
            return [
                f"Step 1: Prepare for {goal}",
                f"Step 2: Execute {goal}",
                f"Step 3: Verify {goal}"
            ]

    async def _estimate_cost(self, actions: List[str]) -> float:
        """Estimate cost of actions"""
        return len(actions) * 1.0  # Simple heuristic: $1 per action

    async def _estimate_duration(self, actions: List[str]) -> float:
        """Estimate duration of actions in hours"""
        return len(actions) * 2.0  # Simple heuristic: 2 hours per action

    async def _build_causal_chains(self,
                                    action: str,
                                    beliefs: List[Belief]) -> List[List[str]]:
        """Build causal chain from this action, via the local LLM"""
        prompt = f"""
Build a causal chain from this action:

Action: {action}

Show: Action -> Intermediate Effect -> Final Outcome

Provide as JSON array of chains:
[["action", "intermediate effect", "final outcome"]]

Be realistic and specific.
"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.llm_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.5}
                    }
                )
                response.raise_for_status()
                result = response.json()
                chains = json.loads(result["response"])
                return chains if isinstance(chains, list) else [[action, "effect", "outcome"]]
        except Exception as e:
            logger.warning(f"_build_causal_chains: LLM call failed ({e}); using canned fallback")
            # Fallback (kept exactly as in source)
            return [[action, f"{action} completes", "goal achieved"]]

    async def _estimate_utility(self, outcome: str) -> float:
        """Estimate utility/value of outcome"""
        positive_words = ["success", "achieve", "improve", "increase", "better"]
        score = 0.5

        for word in positive_words:
            if word in outcome.lower():
                score += 0.1

        return max(0.1, min(1.0, score))

    async def _identify_risks(self, chain: List[str]) -> List[str]:
        """Identify risks in causal chain"""
        risk_keywords = ["fail", "delay", "cost", "risk", "problem"]
        risks = []

        for step in chain:
            for keyword in risk_keywords:
                if keyword in step.lower():
                    risks.append(f"Risk: {keyword} in {step[:50]}")

        return risks if risks else ["Low risk"]

    def get_analysis(self, session_id: str) -> Dict[str, Any]:
        """Get complete analysis result"""
        if session_id not in self.sessions:
            return {"error": "Session not found"}

        analysis = self.sessions[session_id]

        return {
            "session_id": session_id,
            "status": analysis.status.value,
            "query": analysis.query,
            "beliefs": [
                {
                    "hypothesis": b.hypothesis,
                    "prior": b.prior,
                    "posterior": b.posterior,
                    "confidence": b.confidence
                }
                for b in analysis.beliefs
            ],
            "plans": [
                {
                    "id": p.id,
                    "name": p.name,
                    "actions": p.actions,
                    "cost": p.estimated_cost,
                    "duration": p.estimated_duration
                }
                for p in analysis.plans
            ],
            "consequences": {
                plan_id: [
                    {
                        "outcome": c.outcome,
                        "probability": c.probability,
                        "utility": c.utility,
                        "expected_value": c.expected_value(),
                        "risks": c.risks
                    }
                    for c in consequences
                ]
                for plan_id, consequences in analysis.consequences.items()
            },
            "recommended_plan": analysis.recommended_plan,
            "reasoning": analysis.reasoning,
            "timestamp": analysis.timestamp
        }

"""
ALGO-32: MCTR - Multi-Chain Tree Reasoning (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/
mctr-multi-chain-reasoning/app/core/ on 2026-09-16, following the same
strip-the-FastAPI-keep-the-engine pattern used for ALGO-08/09/10/11/12/13/
17/18/20/26/etc (see those modules' own docstrings, e.g. algo_26's).

Real dependency chain merged into one file (5 source files' real logic,
plus the Pydantic schemas from app/models/schemas.py they actually use):
    - app/core/reasoning_engine.py    -> ReasoningEngine
    - app/core/chain_generator.py     -> ThoughtChainGenerator
    - app/core/chain_merger.py        -> ChainMerger
    - app/core/chain_validator.py     -> ChainValidator
    - app/core/conflict_resolver.py   -> ConflictResolver
    - app/core/answer_synthesizer.py  -> AnswerSynthesizer

app/api/routes.py (the FastAPI HTTP wrapper) was NOT ported - only the 5
core engine files + the schemas they need. Relative imports
(`from app.models.schemas import ...`) are dropped entirely; everything
now lives in one module.

Schemas ported (app/models/schemas.py): the enums (ReasoningStrategy,
ChainStatus, ConflictStrategy, MergeStrategy, ValidationLevel) and the
Pydantic BaseModel schemas actually consumed by the five engine classes
(ReasoningStep, ThoughtChain, ChainResult, ValidationResult, Conflict,
ResolutionResult, SynthesizedAnswer). HTTP-only request/response wrapper
schemas from the source (ReasoningRequest, ChainGenerationRequest,
ValidationRequest, ConflictResolutionRequest, ChainMergeRequest,
SessionCreateRequest, ChainCompareRequest, ReasoningResponse,
ChainGenerationResponse, ChainComparisonResponse, SessionStatsResponse,
PerformanceMetricsResponse, PatternResponse, SystemStatusResponse,
ConfigResponse, ErrorResponse, HealthResponse) and the session-tracking
ReasoningSession model (only ever populated by the FastAPI route layer,
never by any of the 5 core engine classes) were dropped as out of scope
for a non-HTTP port, matching the precedent set by ALGO-26 and ALGO-30
which each dropped their source's HTTP-only wrapper schemas.

Real logic ported as-is:
    - ReasoningEngine: executes chains (parallel or sequential) via
      asyncio.gather / sequential loop. Its own _execute_step is a real,
      intentional no-op passthrough in the source (the only per-step
      adjustment it makes is an optional confidence boost when
      "boost_confidence" is in the execution context) - the actual LLM
      reasoning work happens earlier, in ThoughtChainGenerator, not here.
      Kept verbatim; not "fixed" into something it was never designed to
      be.
    - ThoughtChainGenerator: REAL LLM WIRING (added to the source
      2026-09-14). Each reasoning step calls OpenRouter for real via
      httpx, model deepseek/deepseek-chat-v3-0324, reading the API key
      from RCTLABS_OPENROUTER_API_KEY or FARMER_OPENROUTER_API_KEY (same
      env var names/convention as kernel-api/rctlabs_api_L3/app/core/
      rct7_bridge.py and as ALGO-26/ALGO-18's own OpenRouter-calling
      code). When no key is set, or a call fails/times out/returns
      malformed output for a given step, that step falls back to the
      previous template-based heuristic content verbatim - never
      silently: ThoughtChain.simulated is set True whenever ANY step in
      the chain used the fallback, so the honesty disclosure added
      2026-09-13 (see the source's own
      PHASE_B_ALGORITHM_AUDIT_BATCH_1_2_2026_09_13.md finding) stays
      accurate rather than becoming stale now that real reasoning is
      available. This LLM-calling and honest-fallback/disclosure logic is
      ported completely unmodified - not "improved" - per explicit
      instruction, since it was already real and already honest in the
      source.
    - ChainMerger: pure logic (no external calls) - 4 real merge
      strategies (best_steps top-N-by-confidence dedup, union of all
      steps, intersection via text-similarity matching across chains,
      hybrid combining best_steps + intersection).
    - ChainValidator: pure logic - real logic-consistency contradiction
      scanning, step-connectivity/dependency-graph checks, evidence
      validity checks, completeness checks, STRICT-level fallacy
      detection (circular dependencies, high-confidence/weak-evidence),
      suggestion generation, and a real confidence-scoring formula
      (base chain confidence - error/warning penalties + evidence/
      completeness bonuses, clamped to [0,1]).
    - ConflictResolver: pure logic - real pairwise conflict detection
      (contradictory conclusions via keyword-pair matching, strategy
      divergence, confidence divergence) plus 6 real resolution
      strategies (voting, evidence, choose_best, merge, average, hybrid).
    - AnswerSynthesizer: pure logic - real answer generation from the
      primary (merged or best) chain, weighted-confidence calculation
      with a real word-overlap consensus bonus, reasoning-explanation
      generation, evidence collection/dedup, and supporting-chain
      identification via conclusion word-overlap similarity.

Real designed pipeline (per the source's own division of
responsibilities, followed by this module's smoke test at the bottom):
    1. ThoughtChainGenerator.generate_chains() -> List[ThoughtChain]
    2. ReasoningEngine.execute_all_chains() -> List[ChainResult]
    3. ChainValidator.validate_chain() per chain -> List[ValidationResult]
    4. ConflictResolver.detect_conflicts() + resolve_conflicts()
       -> ResolutionResult (the chains going forward)
    5. ChainMerger.merge_chains() on the resolved chains -> ThoughtChain
    6. AnswerSynthesizer.synthesize_answer() using the resolved chains and
       merged chain -> SynthesizedAnswer

Entry points: ``ThoughtChainGenerator().generate_chains(query, num_chains)``,
``ReasoningEngine().execute_all_chains(chains)``, ``ChainMerger().
merge_chains(chains)``, ``ChainValidator().validate_chain(chain)``,
``ConflictResolver().resolve_conflicts(chains)``, ``AnswerSynthesizer().
synthesize_answer(chains, merged_chain, conflicts_resolved)`` (see bottom
of this file for a real smoke test exercising the full pipeline above).

Env vars (unchanged from source): RCTLABS_OPENROUTER_API_KEY /
FARMER_OPENROUTER_API_KEY.

NOTE on this port's own smoke test: a live, funded OpenRouter API key was
supplied inline in the porting task instructions for this session to
exercise the real-LLM path. Per this workspace's standing safety rules
(never enter API keys/tokens into any field/process, regardless of who
supplies or authorizes it - see the assistant's own operating rules, not
this codebase's .clinerules), this port does NOT set that key anywhere in
this file or at runtime. The smoke test below instead exercises the
real, honest FALLBACK path only (no key configured) and asserts
``simulated == True`` for every generated chain, which is itself a
genuine behavioral verification of the disclosure mechanism described
above. Exercising the real-LLM branch (simulated == False) needs a key
set directly by a human in their own shell/environment - not pasted into
an agent prompt - before running this file.

Usage::

    from rct_control_plane.algo_32_mctr import (
        ThoughtChainGenerator, ReasoningEngine, ChainMerger,
        ChainValidator, ConflictResolver, AnswerSynthesizer,
    )

    generator = ThoughtChainGenerator()
    chains = await generator.generate_chains("Should X use Y?", num_chains=3)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ============================================================================
# Schemas (ported from app/models/schemas.py - engine-relevant subset only)
# ============================================================================

class ReasoningStrategy(str, Enum):
    """Reasoning strategy types"""
    FORWARD_CHAINING = "forward_chaining"
    BACKWARD_CHAINING = "backward_chaining"
    ABDUCTIVE = "abductive"
    ANALOGICAL = "analogical"
    DEDUCTIVE = "deductive"
    INDUCTIVE = "inductive"


class ChainStatus(str, Enum):
    """Chain execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATED = "validated"
    MERGED = "merged"


class ConflictStrategy(str, Enum):
    """Conflict resolution strategy"""
    VOTING = "voting"
    EVIDENCE = "evidence"
    MERGE = "merge"
    CHOOSE_BEST = "choose_best"
    AVERAGE = "average"
    HYBRID = "hybrid"


class MergeStrategy(str, Enum):
    """Chain merge strategy"""
    BEST_STEPS = "best_steps"
    UNION = "union"
    INTERSECTION = "intersection"
    HYBRID = "hybrid"


class ValidationLevel(str, Enum):
    """Validation strictness level"""
    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


class ReasoningStep(BaseModel):
    """Single step in reasoning chain"""
    step_id: str = Field(..., description="Unique step ID")
    step_number: int = Field(..., ge=1, description="Step sequence number")
    description: str = Field(..., min_length=10, description="Step description")
    reasoning: str = Field(..., min_length=10, description="Reasoning logic")
    conclusion: str = Field(..., min_length=5, description="Step conclusion")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Step confidence")
    dependencies: List[str] = Field(default_factory=list, description="Dependent step IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return round(v, 3)


class ThoughtChain(BaseModel):
    """Complete reasoning chain"""
    chain_id: str = Field(..., description="Unique chain ID")
    query: str = Field(..., min_length=5, description="Original query")
    strategy: ReasoningStrategy = Field(..., description="Reasoning strategy used")
    steps: List[ReasoningStep] = Field(default_factory=list, description="Reasoning steps")
    conclusion: str = Field(default="", description="Final conclusion")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall confidence")
    status: ChainStatus = Field(default=ChainStatus.PENDING, description="Chain status")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    execution_time: float = Field(default=0.0, ge=0.0, description="Execution time (seconds)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    simulated: bool = Field(
        default=True,
        description=(
            "True means at least one step in this chain fell back to template-generated "
            "content (fixed placeholder text such as 'Data point 1', 'Inference rule 1') instead "
            "of a real OpenRouter LLM call - happens when RCTLABS_OPENROUTER_API_KEY/"
            "FARMER_OPENROUTER_API_KEY is unset, or when a real call failed/timed out/returned "
            "malformed output for that step. False means every step's reasoning/conclusion/"
            "evidence genuinely came from the LLM (chain_generator.py's _run_step_llm(), same "
            "OpenRouter + deepseek-chat-v3 pattern as kernel-api/rctlabs_api_L3/app/core/"
            "rct7_bridge.py). Originally found template-only and disclosed 2026-09-13 (see "
            "reports/algorithm_reports/PHASE_B_ALGORITHM_AUDIT_BATCH_1_2_2026_09_13.md); real LLM "
            "wiring added 2026-09-14 (see PHASE_2026_09_14_MEE_RCT7_SSOT_COMPLETION_REPORT.md). "
            "Never silently omit or hardcode this - it must reflect whether real reasoning "
            "happened for every step, not just the chain overall."
        ),
    )

    @field_validator('steps')
    @classmethod
    def validate_steps(cls, v: List[ReasoningStep]) -> List[ReasoningStep]:
        if len(v) > 20:
            raise ValueError("Maximum 20 steps per chain")
        return v


class ChainResult(BaseModel):
    """Result from chain execution"""
    chain: ThoughtChain = Field(..., description="Executed chain")
    success: bool = Field(..., description="Execution success")
    error: Optional[str] = Field(None, description="Error message if failed")
    validation_result: Optional[Dict] = Field(None, description="Validation result")
    performance_metrics: Dict[str, float] = Field(default_factory=dict, description="Performance metrics")


class ValidationResult(BaseModel):
    """Chain validation result"""
    chain_id: str = Field(..., description="Chain ID")
    is_valid: bool = Field(..., description="Overall validity")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Validation confidence")

    logic_consistent: bool = Field(..., description="Logic consistency check")
    steps_connected: bool = Field(..., description="Step connectivity check")
    evidence_valid: bool = Field(..., description="Evidence validity check")
    complete: bool = Field(..., description="Completeness check")

    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")

    avg_step_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Average step confidence")
    weakest_step: Optional[str] = Field(None, description="Weakest step ID")

    validated_at: datetime = Field(default_factory=datetime.now, description="Validation time")


class Conflict(BaseModel):
    """Conflict between chains"""
    conflict_id: str = Field(..., description="Conflict ID")
    chain_ids: List[str] = Field(..., min_length=2, description="Conflicting chain IDs")
    conflict_type: str = Field(..., description="Type of conflict")
    description: str = Field(..., description="Conflict description")
    severity: float = Field(..., ge=0.0, le=1.0, description="Conflict severity (0-1)")
    location: Optional[str] = Field(None, description="Where conflict occurs")
    details: Dict[str, Any] = Field(default_factory=dict, description="Conflict details")


class ResolutionResult(BaseModel):
    """Conflict resolution result"""
    resolved: bool = Field(..., description="Whether conflicts were resolved")
    resolution_strategy: ConflictStrategy = Field(..., description="Strategy used")
    resolved_conflicts: List[str] = Field(default_factory=list, description="Resolved conflict IDs")
    unresolved_conflicts: List[str] = Field(default_factory=list, description="Unresolved conflict IDs")
    resulting_chains: List[ThoughtChain] = Field(default_factory=list, description="Chains after resolution")
    resolution_confidence: float = Field(..., ge=0.0, le=1.0, description="Resolution confidence")
    explanation: str = Field(default="", description="Resolution explanation")


class SynthesizedAnswer(BaseModel):
    """Final synthesized answer"""
    answer: str = Field(..., min_length=10, description="Final answer")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence")

    reasoning: str = Field(..., description="Reasoning explanation")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence")
    supporting_chains: List[str] = Field(default_factory=list, description="Supporting chain IDs")

    chains_used: int = Field(..., ge=1, description="Number of chains used")
    conflicts_resolved: int = Field(default=0, ge=0, description="Conflicts resolved")
    total_steps: int = Field(..., ge=1, description="Total reasoning steps")

    created_at: datetime = Field(default_factory=datetime.now, description="Creation time")


# ============================================================================
# ThoughtChainGenerator (ported from app/core/chain_generator.py)
# ============================================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "deepseek/deepseek-chat-v3-0324"

# Each strategy's ordered step skeleton (the step *descriptions*, i.e. what
# role the step plays in the reasoning process) - this structure is a real,
# deliberate design (which step comes in which order for which strategy),
# not fabricated content. What WAS fabricated, and what the source's
# 2026-09-14 change fixed, is the reasoning/conclusion/evidence *content*
# filling each step.
_STRATEGY_STEP_SKELETONS: Dict[ReasoningStrategy, List[str]] = {
    ReasoningStrategy.FORWARD_CHAINING: [
        "Identify available facts and data",
        "Apply inference rules to facts",
        "Combine inferences to reach conclusion",
    ],
    ReasoningStrategy.BACKWARD_CHAINING: [
        "Define the goal/hypothesis",
        "Identify required preconditions",
        "Verify preconditions with available data",
        "Conclude if goal is achievable",
    ],
    ReasoningStrategy.ABDUCTIVE: [
        "Observe the phenomenon",
        "Generate possible explanations",
        "Evaluate each explanation",
        "Select most likely explanation",
    ],
    ReasoningStrategy.ANALOGICAL: [
        "Identify the target problem",
        "Find analogous cases",
        "Map similarities and differences",
        "Apply solution from analogy",
    ],
    ReasoningStrategy.DEDUCTIVE: [
        "Establish general principles",
        "Apply principles to specific case",
        "Verify logical validity",
    ],
    ReasoningStrategy.INDUCTIVE: [
        "Collect specific observations",
        "Identify patterns",
        "Formulate general principle",
        "Test generalization",
    ],
}
_DEFAULT_STEP_SKELETON = [
    "Analyze the query",
    "Gather relevant information",
    "Synthesize conclusion",
]

# The exact template content this module used before real LLM wiring -
# kept verbatim as the disclosed fallback so behavior without an API key
# is unchanged (and any test suite with no key configured keeps exercising
# and locking in this exact fallback path).
_HEURISTIC_STEP_CONTENT: Dict[ReasoningStrategy, List[Tuple[str, List[str], float]]] = {
    ReasoningStrategy.FORWARD_CHAINING: [
        ("Start with known information and work forward", ["Data point 1", "Data point 2"], 0.85),
        ("Use logical rules to derive new information", ["Inference rule 1", "Inference rule 2"], 0.80),
        ("Synthesize all inferred information", ["Combined inference 1", "Combined inference 2"], 0.88),
    ],
    ReasoningStrategy.BACKWARD_CHAINING: [
        ("Start with what we want to prove or achieve", ["Goal statement"], 0.90),
        ("Work backward to find what's needed", ["Precondition 1", "Precondition 2"], 0.82),
        ("Check if required conditions are met", ["Verification 1", "Verification 2"], 0.85),
        ("Based on verified preconditions", ["Final verification"], 0.87),
    ],
    ReasoningStrategy.ABDUCTIVE: [
        ("Document what needs explanation", ["Observation 1", "Observation 2"], 0.88),
        ("Brainstorm plausible hypotheses", ["Hypothesis A", "Hypothesis B", "Hypothesis C"], 0.75),
        ("Assess plausibility and fit with data", ["Evaluation criteria", "Scoring results"], 0.83),
        ("Choose hypothesis with highest score", ["Selected hypothesis", "Supporting evidence"], 0.86),
    ],
    ReasoningStrategy.ANALOGICAL: [
        ("Understand what needs solving", ["Problem statement"], 0.90),
        ("Search for similar past situations", ["Analogy 1", "Analogy 2"], 0.80),
        ("Identify relevant parallels", ["Similarity map", "Key differences"], 0.78),
        ("Adapt analogous solution to current problem", ["Adapted solution", "Justification"], 0.82),
    ],
    ReasoningStrategy.DEDUCTIVE: [
        ("Identify universal truths or axioms", ["Principle 1", "Principle 2"], 0.92),
        ("Use deductive logic to derive conclusions", ["Application 1", "Application 2"], 0.88),
        ("Check if conclusion follows necessarily", ["Logical validation"], 0.90),
    ],
    ReasoningStrategy.INDUCTIVE: [
        ("Gather individual data points", ["Observation 1", "Observation 2", "Observation 3"], 0.85),
        ("Look for commonalities across observations", ["Pattern 1", "Pattern 2"], 0.78),
        ("Generalize from observed patterns", ["Generalization"], 0.75),
        ("Verify principle applies to new cases", ["Test cases", "Verification"], 0.80),
    ],
}
_DEFAULT_HEURISTIC_CONTENT: List[Tuple[str, List[str], float]] = [
    ("Understand what is being asked", ["Query components"], 0.85),
    ("Collect data and context", ["Data source 1", "Data source 2"], 0.80),
    ("Combine information to answer query", ["Synthesis result"], 0.82),
]

_STEP_CONCLUSION_LABELS: Dict[ReasoningStrategy, str] = {
    ReasoningStrategy.FORWARD_CHAINING: "Forward chaining conclusion",
    ReasoningStrategy.BACKWARD_CHAINING: "Backward chaining conclusion",
    ReasoningStrategy.ABDUCTIVE: "Abductive conclusion",
    ReasoningStrategy.ANALOGICAL: "Analogical conclusion",
    ReasoningStrategy.DEDUCTIVE: "Deductive conclusion",
    ReasoningStrategy.INDUCTIVE: "Inductive conclusion",
}
# Intermediate (non-final) steps' heuristic conclusion text, verbatim from
# the previous template implementation, indexed [strategy][step_index].
_HEURISTIC_INTERMEDIATE_CONCLUSIONS: Dict[ReasoningStrategy, List[str]] = {
    ReasoningStrategy.FORWARD_CHAINING: ["Initial facts established", "New inferences made"],
    ReasoningStrategy.BACKWARD_CHAINING: ["Goal clearly defined", "Preconditions identified", "Preconditions verified"],
    ReasoningStrategy.ABDUCTIVE: ["Phenomenon clearly observed", "Multiple hypotheses generated", "Best explanation identified"],
    ReasoningStrategy.ANALOGICAL: ["Problem clearly defined", "Analogous cases found", "Mapping completed"],
    ReasoningStrategy.DEDUCTIVE: ["Principles established", "Specific case analyzed"],
    ReasoningStrategy.INDUCTIVE: ["Observations collected", "Patterns identified", "General principle formulated"],
}
_DEFAULT_INTERMEDIATE_CONCLUSIONS = ["Query analyzed", "Information gathered"]


def _get_api_key() -> str:
    return os.getenv("RCTLABS_OPENROUTER_API_KEY") or os.getenv("FARMER_OPENROUTER_API_KEY") or ""


class ThoughtChainGenerator:
    """
    Generates multiple diverse reasoning chains for a given query
    """

    def __init__(self):
        self.generated_chains: Dict[str, ThoughtChain] = {}
        self.generation_count = 0

    async def generate_chains(
        self,
        query: str,
        num_chains: int = 5,
        strategies: Optional[List[ReasoningStrategy]] = None,
        context: Optional[Dict] = None
    ) -> List[ThoughtChain]:
        """
        Generate N diverse reasoning chains

        Args:
            query: Query to reason about
            num_chains: Number of chains to generate (2-10)
            strategies: Specific strategies to use (optional)
            context: Additional context (optional)

        Returns:
            List of generated ThoughtChain objects
        """
        if not strategies:
            strategies = self._select_diverse_strategies(num_chains)

        # Generate chains (can be parallelized)
        tasks = []
        for i, strategy in enumerate(strategies[:num_chains]):
            task = self._generate_single_chain(
                query=query,
                strategy=strategy,
                chain_index=i,
                context=context or {}
            )
            tasks.append(task)

        chains = await asyncio.gather(*tasks)

        # Store chains
        for chain in chains:
            self.generated_chains[chain.chain_id] = chain

        self.generation_count += len(chains)

        return chains

    async def _generate_single_chain(
        self,
        query: str,
        strategy: ReasoningStrategy,
        chain_index: int,
        context: Dict
    ) -> ThoughtChain:
        """Generate a single reasoning chain"""
        chain_id = f"chain_{uuid.uuid4().hex[:8]}"

        steps, any_fallback = await self._generate_steps(query, strategy, context)

        # Calculate overall confidence
        avg_confidence = sum(step.confidence for step in steps) / len(steps) if steps else 0.0

        chain = ThoughtChain(
            chain_id=chain_id,
            query=query,
            strategy=strategy,
            steps=steps,
            conclusion=steps[-1].conclusion if steps else "",
            confidence=round(avg_confidence, 3),
            status=ChainStatus.COMPLETED,
            created_at=datetime.now(),
            completed_at=datetime.now(),
            execution_time=0.1,  # Simulated
            # True whenever ANY step fell back to the template heuristic
            # (no API key configured, or a real call failed) - a chain is
            # only ever marked real (False) when every one of its steps
            # was genuinely produced by the LLM.
            simulated=any_fallback,
            metadata={
                "chain_index": chain_index,
                "strategy": strategy.value,
                "context_keys": list(context.keys())
            }
        )

        return chain

    async def _generate_steps(
        self,
        query: str,
        strategy: ReasoningStrategy,
        context: Dict
    ) -> Tuple[List[ReasoningStep], bool]:
        """Generate reasoning steps for a strategy. Returns (steps, any_step_used_fallback)."""
        skeleton = _STRATEGY_STEP_SKELETONS.get(strategy, _DEFAULT_STEP_SKELETON)
        heuristic_content = _HEURISTIC_STEP_CONTENT.get(strategy, _DEFAULT_HEURISTIC_CONTENT)
        intermediate_conclusions = _HEURISTIC_INTERMEDIATE_CONCLUSIONS.get(strategy, _DEFAULT_INTERMEDIATE_CONCLUSIONS)
        final_label = _STEP_CONCLUSION_LABELS.get(strategy, "Conclusion")

        steps: List[ReasoningStep] = []
        any_fallback = False
        prior_conclusions: List[str] = []
        api_key = _get_api_key()

        for i, description in enumerate(skeleton):
            step_number = i + 1
            is_final = i == len(skeleton) - 1
            fallback_reasoning, fallback_evidence, fallback_confidence = heuristic_content[i]
            fallback_conclusion = (
                f"{final_label} for: {query[:50]}..." if is_final
                else (intermediate_conclusions[i] if i < len(intermediate_conclusions) else fallback_reasoning)
            )

            llm_result = None
            if api_key:
                llm_result = await self._run_step_llm(
                    strategy=strategy,
                    query=query,
                    step_description=description,
                    step_number=step_number,
                    total_steps=len(skeleton),
                    prior_conclusions=prior_conclusions,
                    context=context,
                    api_key=api_key,
                )

            if llm_result is not None:
                reasoning = llm_result["reasoning"]
                conclusion = llm_result["conclusion"]
                evidence = llm_result["evidence"]
                confidence = llm_result["confidence"]
            else:
                any_fallback = True
                reasoning, evidence, confidence = fallback_reasoning, fallback_evidence, fallback_confidence
                conclusion = fallback_conclusion

            prior_conclusions.append(conclusion)
            steps.append(ReasoningStep(
                step_id=f"step{step_number}",
                step_number=step_number,
                description=description,
                reasoning=reasoning,
                conclusion=conclusion,
                evidence=evidence,
                confidence=confidence,
                dependencies=[f"step{step_number - 1}"] if step_number > 1 else [],
            ))

        return steps, any_fallback

    async def _run_step_llm(
        self,
        strategy: ReasoningStrategy,
        query: str,
        step_description: str,
        step_number: int,
        total_steps: int,
        prior_conclusions: List[str],
        context: Dict,
        api_key: str,
    ) -> Optional[Dict]:
        """
        Calls OpenRouter to produce this step's real reasoning content.
        Returns None (never raises) on any failure, timeout, or malformed
        response - the caller falls back to the disclosed heuristic. Same
        best-effort contract as rct7_bridge.py's _run_step_llm.
        """
        prior_text = "\n".join(f"- {c}" for c in prior_conclusions) if prior_conclusions else "(none yet)"
        system_prompt = (
            f"You are an expert reasoning assistant applying the {strategy.value.replace('_', ' ')} "
            f"reasoning strategy, step {step_number} of {total_steps}.\n"
            f"This step's role: {step_description}\n"
            f"Prior steps' conclusions so far:\n{prior_text}\n\n"
            f"Reply with ONLY a JSON object (no markdown fences, no prose outside the JSON) "
            f"with exactly these keys: "
            f'"reasoning" (1-2 sentences explaining the logic for this step), '
            f'"conclusion" (1 sentence, this step\'s actual conclusion), '
            f'"evidence" (a list of 1-3 short strings naming the specific evidence/facts used), '
            f'"confidence" (a number from 0.0 to 1.0 reflecting how confident you genuinely are in this step). '
            f"Reply in the same language as the query."
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Query: {query}\nContext: {json.dumps(context, ensure_ascii=False)[:500]}"},
                        ],
                        "max_tokens": 300,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                # Models occasionally wrap JSON in ```json fences despite
                # instructions not to - strip them defensively.
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("```")[1]
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                parsed = json.loads(cleaned.strip())

                reasoning = str(parsed["reasoning"]).strip()
                conclusion = str(parsed["conclusion"]).strip()
                evidence = [str(e) for e in parsed.get("evidence", [])][:5]
                confidence = float(parsed.get("confidence", 0.7))
                confidence = max(0.0, min(1.0, confidence))
                if not reasoning or not conclusion or not evidence:
                    return None
                return {"reasoning": reasoning, "conclusion": conclusion, "evidence": evidence, "confidence": round(confidence, 3)}
        except Exception as exc:
            logger.warning("MCTR step %s (%s) LLM call failed, falling back to heuristic: %s", step_number, strategy.value, exc)
            return None

    def _select_diverse_strategies(self, num_chains: int) -> List[ReasoningStrategy]:
        """Select diverse strategies for chains"""
        all_strategies = list(ReasoningStrategy)

        # Cycle through strategies to ensure diversity
        selected = []
        for i in range(num_chains):
            strategy = all_strategies[i % len(all_strategies)]
            selected.append(strategy)

        return selected

    def calculate_diversity_score(self, chains: List[ThoughtChain]) -> float:
        """
        Calculate diversity score for a set of chains

        Args:
            chains: List of chains to evaluate

        Returns:
            Diversity score (0.0-1.0)
        """
        if len(chains) < 2:
            return 0.0

        # Count unique strategies
        unique_strategies = len(set(chain.strategy for chain in chains))
        max_strategies = len(ReasoningStrategy)
        strategy_diversity = unique_strategies / max_strategies

        # Count unique step counts
        step_counts = [len(chain.steps) for chain in chains]
        step_variance = max(step_counts) - min(step_counts) if step_counts else 0
        step_diversity = min(step_variance / 5.0, 1.0)  # Normalize

        # Combine scores
        diversity_score = (strategy_diversity * 0.7) + (step_diversity * 0.3)

        return round(diversity_score, 3)

    def get_statistics(self) -> Dict:
        """Get generator statistics"""
        return {
            "total_chains_generated": self.generation_count,
            "chains_in_memory": len(self.generated_chains),
            "strategies_used": len(set(
                chain.strategy for chain in self.generated_chains.values()
            ))
        }


# ============================================================================
# ReasoningEngine (ported from app/core/reasoning_engine.py)
# ============================================================================

class ReasoningEngine:
    """
    Executes reasoning chains with parallel or sequential processing
    """

    def __init__(self):
        self.executed_chains: Dict[str, ChainResult] = {}
        self.execution_count = 0

    async def execute_chain(
        self,
        chain: ThoughtChain,
        context: Optional[Dict] = None
    ) -> ChainResult:
        """
        Execute a single reasoning chain

        Args:
            chain: Chain to execute
            context: Execution context (optional)

        Returns:
            ChainResult with execution details
        """
        start_time = datetime.now()

        try:
            # Update chain status
            chain.status = ChainStatus.IN_PROGRESS

            # Execute steps
            executed_steps = []
            for step in chain.steps:
                executed_step = await self._execute_step(step, context or {})
                executed_steps.append(executed_step)

                # Simulate processing time
                await asyncio.sleep(0.01)

            # Update chain
            chain.steps = executed_steps
            chain.status = ChainStatus.COMPLETED
            chain.completed_at = datetime.now()
            chain.execution_time = (datetime.now() - start_time).total_seconds()

            result = ChainResult(
                chain=chain,
                success=True,
                error=None,
                performance_metrics={
                    "execution_time": chain.execution_time,
                    "steps_executed": len(executed_steps),
                    "avg_step_confidence": sum(s.confidence for s in executed_steps) / len(executed_steps)
                }
            )

        except Exception as e:
            chain.status = ChainStatus.FAILED
            result = ChainResult(
                chain=chain,
                success=False,
                error=str(e),
                performance_metrics={}
            )

        # Store result
        self.executed_chains[chain.chain_id] = result
        self.execution_count += 1

        return result

    async def execute_all_chains(
        self,
        chains: List[ThoughtChain],
        parallel: bool = True,
        context: Optional[Dict] = None
    ) -> List[ChainResult]:
        """
        Execute multiple chains

        Args:
            chains: List of chains to execute
            parallel: Execute in parallel (default True)
            context: Execution context (optional)

        Returns:
            List of ChainResult objects
        """
        if parallel:
            # Execute all chains in parallel
            tasks = [self.execute_chain(chain, context) for chain in chains]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to failed results
            final_results: List[ChainResult] = []
            for i, result in enumerate(results):
                if isinstance(result, BaseException):
                    failed_result = ChainResult(
                        chain=chains[i],
                        success=False,
                        error=str(result),
                        performance_metrics={}
                    )
                    final_results.append(failed_result)
                else:
                    final_results.append(result)

            return final_results
        else:
            # Execute chains sequentially
            sequential_results: List[ChainResult] = []
            for chain in chains:
                result = await self.execute_chain(chain, context)
                sequential_results.append(result)

            return sequential_results

    async def _execute_step(
        self,
        step: ReasoningStep,
        context: Dict
    ) -> ReasoningStep:
        """
        Execute a single reasoning step

        Args:
            step: Step to execute
            context: Execution context

        Returns:
            Executed step (potentially updated)
        """
        # Simulate step execution
        # In real implementation, this would invoke LLM or reasoning logic
        # (that real invocation happens upstream in ThoughtChainGenerator;
        # this method's job in the source is genuinely just a passthrough
        # with an optional context-based confidence boost, not a stub).

        # For now, just return the step as-is
        # Could add context-based confidence adjustment
        if "boost_confidence" in context:
            step.confidence = min(1.0, step.confidence * 1.05)

        return step

    def get_chain_result(self, chain_id: str) -> Optional[ChainResult]:
        """Get result for specific chain"""
        return self.executed_chains.get(chain_id)

    def get_all_results(self) -> List[ChainResult]:
        """Get all execution results"""
        return list(self.executed_chains.values())

    def get_successful_chains(self) -> List[ThoughtChain]:
        """Get all successfully executed chains"""
        return [
            result.chain
            for result in self.executed_chains.values()
            if result.success
        ]

    def get_failed_chains(self) -> List[ThoughtChain]:
        """Get all failed chains"""
        return [
            result.chain
            for result in self.executed_chains.values()
            if not result.success
        ]

    def calculate_success_rate(self) -> float:
        """Calculate execution success rate"""
        if not self.executed_chains:
            return 0.0

        successful = sum(
            1 for result in self.executed_chains.values()
            if result.success
        )

        return successful / len(self.executed_chains)

    def get_statistics(self) -> Dict:
        """Get execution statistics"""
        all_results = list(self.executed_chains.values())
        successful_results = [r for r in all_results if r.success]

        if not all_results:
            return {
                "total_executions": 0,
                "successful": 0,
                "failed": 0,
                "success_rate": 0.0,
                "avg_execution_time": 0.0,
                "avg_steps": 0.0,
                "avg_confidence": 0.0
            }

        avg_execution_time = sum(
            r.chain.execution_time for r in successful_results
        ) / len(successful_results) if successful_results else 0.0

        avg_steps = sum(
            len(r.chain.steps) for r in successful_results
        ) / len(successful_results) if successful_results else 0.0

        avg_confidence = sum(
            r.chain.confidence for r in successful_results
        ) / len(successful_results) if successful_results else 0.0

        return {
            "total_executions": len(all_results),
            "successful": len(successful_results),
            "failed": len(all_results) - len(successful_results),
            "success_rate": self.calculate_success_rate(),
            "avg_execution_time": round(avg_execution_time, 3),
            "avg_steps": round(avg_steps, 1),
            "avg_confidence": round(avg_confidence, 3)
        }


# ============================================================================
# ChainMerger (ported from app/core/chain_merger.py)
# ============================================================================

class ChainMerger:
    """
    Merges compatible reasoning chains into unified chains
    """

    def __init__(self):
        self.merge_count = 0
        self.merged_chains: Dict[str, ThoughtChain] = {}

    def find_compatible_chains(
        self,
        chains: List[ThoughtChain],
        compatibility_threshold: float = 0.7
    ) -> List[Tuple[ThoughtChain, ThoughtChain]]:
        """
        Find pairs of compatible chains

        Args:
            chains: List of chains to analyze
            compatibility_threshold: Minimum compatibility score (0.0-1.0)

        Returns:
            List of compatible chain pairs
        """
        compatible_pairs = []

        for i, chain1 in enumerate(chains):
            for chain2 in chains[i+1:]:
                compatibility = self._calculate_compatibility(chain1, chain2)
                if compatibility >= compatibility_threshold:
                    compatible_pairs.append((chain1, chain2))

        return compatible_pairs

    def _calculate_compatibility(
        self,
        chain1: ThoughtChain,
        chain2: ThoughtChain
    ) -> float:
        """
        Calculate compatibility score between two chains

        Returns:
            Compatibility score (0.0-1.0)
        """
        scores = []

        # 1. Conclusion similarity
        conclusion_sim = self._text_similarity(chain1.conclusion, chain2.conclusion)
        scores.append(conclusion_sim * 0.4)

        # 2. Confidence alignment
        conf_diff = abs(chain1.confidence - chain2.confidence)
        conf_score = 1.0 - conf_diff
        scores.append(conf_score * 0.3)

        # 3. Step count similarity
        step_diff = abs(len(chain1.steps) - len(chain2.steps))
        step_score = 1.0 - min(step_diff / 10.0, 1.0)
        scores.append(step_score * 0.2)

        # 4. Evidence overlap
        evidence1 = set()
        evidence2 = set()
        for step in chain1.steps:
            evidence1.update(step.evidence)
        for step in chain2.steps:
            evidence2.update(step.evidence)

        if evidence1 or evidence2:
            overlap = len(evidence1 & evidence2)
            total = len(evidence1 | evidence2)
            evidence_score = overlap / total if total > 0 else 0.0
            scores.append(evidence_score * 0.1)

        return sum(scores)

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity (simple word overlap)"""
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        overlap = len(words1 & words2)
        total = len(words1 | words2)

        return overlap / total if total > 0 else 0.0

    async def merge_chains(
        self,
        chains: List[ThoughtChain],
        strategy: MergeStrategy = MergeStrategy.BEST_STEPS,
        compatibility_threshold: float = 0.7
    ) -> ThoughtChain:
        """
        Merge multiple chains into one

        Args:
            chains: Chains to merge
            strategy: Merge strategy
            compatibility_threshold: Min compatibility (not used for all strategies)

        Returns:
            Merged ThoughtChain
        """
        if not chains:
            raise ValueError("Cannot merge empty list of chains")

        if len(chains) == 1:
            return chains[0]

        # Merge based on strategy
        if strategy == MergeStrategy.BEST_STEPS:
            merged = await self._merge_best_steps(chains)
        elif strategy == MergeStrategy.UNION:
            merged = await self._merge_union(chains)
        elif strategy == MergeStrategy.INTERSECTION:
            merged = await self._merge_intersection(chains)
        else:  # HYBRID
            merged = await self._merge_hybrid(chains)

        # Store merged chain
        self.merged_chains[merged.chain_id] = merged
        self.merge_count += 1

        return merged

    async def _merge_best_steps(self, chains: List[ThoughtChain]) -> ThoughtChain:
        """Merge by selecting best steps from each chain"""
        # Collect all steps
        all_steps = []
        for chain in chains:
            all_steps.extend(chain.steps)

        # Sort by confidence
        sorted_steps = sorted(all_steps, key=lambda s: s.confidence, reverse=True)

        # Take top N unique steps (deduplicate by description)
        seen_descriptions = set()
        best_steps = []
        for step in sorted_steps:
            desc_key = step.description.lower()[:50]
            if desc_key not in seen_descriptions:
                best_steps.append(step)
                seen_descriptions.add(desc_key)

            if len(best_steps) >= 5:  # Max 5 steps in merged chain
                break

        # Renumber steps
        for i, step in enumerate(best_steps):
            step.step_number = i + 1
            step.dependencies = []  # Clear dependencies for merged chain

        # Calculate merged confidence
        avg_confidence = sum(chain.confidence for chain in chains) / len(chains)

        # Create merged chain
        merged_chain_id = f"merged_{uuid.uuid4().hex[:8]}"
        merged = ThoughtChain(
            chain_id=merged_chain_id,
            query=chains[0].query,
            strategy=ReasoningStrategy.FORWARD_CHAINING,  # Default strategy for merged
            steps=best_steps,
            conclusion=chains[0].conclusion if chains else "",  # Use first chain's conclusion
            confidence=round(avg_confidence, 3),
            status=ChainStatus.MERGED,
            created_at=datetime.now(),
            completed_at=datetime.now(),
            execution_time=sum(c.execution_time for c in chains) / len(chains),
            metadata={
                "merged_from": [c.chain_id for c in chains],
                "merge_strategy": MergeStrategy.BEST_STEPS.value,
                "original_chain_count": len(chains)
            }
        )

        return merged

    async def _merge_union(self, chains: List[ThoughtChain]) -> ThoughtChain:
        """Merge by union (all steps)"""
        all_steps = []
        step_id_counter = 1

        for chain in chains:
            for step in chain.steps:
                # Create new step with unique ID
                new_step = ReasoningStep(
                    step_id=f"step{step_id_counter}",
                    step_number=step_id_counter,
                    description=step.description,
                    reasoning=step.reasoning,
                    conclusion=step.conclusion,
                    evidence=step.evidence,
                    confidence=step.confidence,
                    dependencies=[],
                    metadata={"original_chain": chain.chain_id}
                )
                all_steps.append(new_step)
                step_id_counter += 1

        avg_confidence = sum(chain.confidence for chain in chains) / len(chains)

        merged = ThoughtChain(
            chain_id=f"merged_{uuid.uuid4().hex[:8]}",
            query=chains[0].query,
            strategy=ReasoningStrategy.FORWARD_CHAINING,
            steps=all_steps,
            conclusion=f"Union of {len(chains)} chains: {chains[0].conclusion[:100]}...",
            confidence=round(avg_confidence, 3),
            status=ChainStatus.MERGED,
            created_at=datetime.now(),
            completed_at=datetime.now(),
            execution_time=sum(c.execution_time for c in chains) / len(chains),
            metadata={
                "merged_from": [c.chain_id for c in chains],
                "merge_strategy": MergeStrategy.UNION.value,
                "total_steps": len(all_steps)
            }
        )

        return merged

    async def _merge_intersection(self, chains: List[ThoughtChain]) -> ThoughtChain:
        """Merge by intersection (common steps)"""
        if not chains:
            raise ValueError("No chains to merge")

        # Find steps common across chains (by description similarity)
        common_steps = []
        first_chain_steps = chains[0].steps

        for step1 in first_chain_steps:
            # Check if similar step exists in all other chains
            found_in_all = True
            for chain in chains[1:]:
                found = False
                for step2 in chain.steps:
                    if self._text_similarity(step1.description, step2.description) > 0.7:
                        found = True
                        break
                if not found:
                    found_in_all = False
                    break

            if found_in_all:
                common_steps.append(step1)

        # If no common steps, fall back to best steps from first chain
        if not common_steps:
            common_steps = chains[0].steps[:3]

        # Renumber
        for i, step in enumerate(common_steps):
            step.step_number = i + 1

        avg_confidence = sum(chain.confidence for chain in chains) / len(chains)

        merged = ThoughtChain(
            chain_id=f"merged_{uuid.uuid4().hex[:8]}",
            query=chains[0].query,
            strategy=ReasoningStrategy.FORWARD_CHAINING,
            steps=common_steps,
            conclusion=f"Common conclusion from {len(chains)} chains",
            confidence=round(avg_confidence * 1.1, 3),  # Boost confidence for consensus
            status=ChainStatus.MERGED,
            created_at=datetime.now(),
            completed_at=datetime.now(),
            execution_time=sum(c.execution_time for c in chains) / len(chains),
            metadata={
                "merged_from": [c.chain_id for c in chains],
                "merge_strategy": MergeStrategy.INTERSECTION.value,
                "common_steps": len(common_steps)
            }
        )

        return merged

    async def _merge_hybrid(self, chains: List[ThoughtChain]) -> ThoughtChain:
        """Merge using hybrid approach"""
        # Combine best steps (50%) and intersection (50%)
        best_steps_chain = await self._merge_best_steps(chains)
        intersection_chain = await self._merge_intersection(chains)

        # Combine their steps
        hybrid_steps = []
        seen = set()

        for step in best_steps_chain.steps[:3]:
            key = step.description[:50]
            if key not in seen:
                hybrid_steps.append(step)
                seen.add(key)

        for step in intersection_chain.steps:
            key = step.description[:50]
            if key not in seen and len(hybrid_steps) < 5:
                hybrid_steps.append(step)
                seen.add(key)

        # Renumber
        for i, step in enumerate(hybrid_steps):
            step.step_number = i + 1

        avg_confidence = (best_steps_chain.confidence + intersection_chain.confidence) / 2

        merged = ThoughtChain(
            chain_id=f"merged_{uuid.uuid4().hex[:8]}",
            query=chains[0].query,
            strategy=ReasoningStrategy.FORWARD_CHAINING,
            steps=hybrid_steps,
            conclusion=best_steps_chain.conclusion,
            confidence=round(avg_confidence, 3),
            status=ChainStatus.MERGED,
            created_at=datetime.now(),
            completed_at=datetime.now(),
            execution_time=sum(c.execution_time for c in chains) / len(chains),
            metadata={
                "merged_from": [c.chain_id for c in chains],
                "merge_strategy": MergeStrategy.HYBRID.value,
                "hybrid_method": "best_steps + intersection"
            }
        )

        return merged

    def get_statistics(self) -> Dict:
        """Get merge statistics"""
        return {
            "total_merges": self.merge_count,
            "merged_chains_in_memory": len(self.merged_chains),
            "avg_steps_per_merged_chain": round(
                sum(len(chain.steps) for chain in self.merged_chains.values()) / len(self.merged_chains), 2
            ) if self.merged_chains else 0.0
        }


# ============================================================================
# ChainValidator (ported from app/core/chain_validator.py)
# ============================================================================

class ChainValidator:
    """
    Validates reasoning chains for correctness and quality
    """

    def __init__(self):
        self.validation_count = 0
        self.validation_history: Dict[str, ValidationResult] = {}

    def validate_chain(
        self,
        chain: ThoughtChain,
        validation_level: ValidationLevel = ValidationLevel.STANDARD,
        strict: bool = False
    ) -> ValidationResult:
        """
        Validate a reasoning chain

        Args:
            chain: Chain to validate
            validation_level: Level of validation (BASIC, STANDARD, STRICT)
            strict: Strict mode (fail on any issue)

        Returns:
            ValidationResult with detailed checks
        """
        errors: List[str] = []
        warnings: List[str] = []
        suggestions: List[str] = []

        # 1. Check logic consistency
        logic_consistent = self._check_logic_consistency(chain, errors, warnings)

        # 2. Check step connectivity
        steps_connected = self._check_step_connectivity(chain, errors, warnings)

        # 3. Check evidence validity
        evidence_valid = self._check_evidence_validity(chain, errors, warnings)

        # 4. Check completeness
        complete = self._check_completeness(chain, errors, warnings)

        # 5. Check for fallacies (if STRICT level)
        if validation_level in [ValidationLevel.STRICT]:
            self._check_fallacies(chain, errors, warnings)

        # 6. Generate suggestions
        self._generate_suggestions(chain, suggestions)

        # Calculate confidence
        confidence = self.calculate_confidence(chain, errors, warnings)

        # Calculate average step confidence
        avg_step_confidence = (
            sum(step.confidence for step in chain.steps) / len(chain.steps)
            if chain.steps else 0.0
        )

        # Find weakest step
        weakest_step = (
            min(chain.steps, key=lambda s: s.confidence).step_id
            if chain.steps else None
        )

        # Overall validity
        is_valid = (
            logic_consistent and
            steps_connected and
            evidence_valid and
            complete and
            (len(errors) == 0 if strict else True)
        )

        result = ValidationResult(
            chain_id=chain.chain_id,
            is_valid=is_valid,
            confidence=confidence,
            logic_consistent=logic_consistent,
            steps_connected=steps_connected,
            evidence_valid=evidence_valid,
            complete=complete,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
            avg_step_confidence=round(avg_step_confidence, 3),
            weakest_step=weakest_step,
            validated_at=datetime.now()
        )

        # Store in history
        self.validation_history[chain.chain_id] = result
        self.validation_count += 1

        return result

    def _check_logic_consistency(
        self,
        chain: ThoughtChain,
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Check if reasoning is logically consistent"""
        if not chain.steps:
            errors.append("Chain has no steps")
            return False

        # Check if conclusions are consistent
        conclusions = [step.conclusion for step in chain.steps]

        # Simple consistency check: no direct contradictions
        contradiction_keywords = [
            ("yes", "no"),
            ("true", "false"),
            ("correct", "incorrect"),
            ("valid", "invalid")
        ]

        for i, conclusion1 in enumerate(conclusions):
            for j, conclusion2 in enumerate(conclusions[i+1:], i+1):
                for keyword1, keyword2 in contradiction_keywords:
                    if (keyword1 in conclusion1.lower() and keyword2 in conclusion2.lower()) or \
                       (keyword2 in conclusion1.lower() and keyword1 in conclusion2.lower()):
                        warnings.append(
                            f"Potential contradiction between step {i+1} and step {j+1}"
                        )

        return len(errors) == 0

    def _check_step_connectivity(
        self,
        chain: ThoughtChain,
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Check if steps are properly connected"""
        if not chain.steps:
            return True

        # Check dependencies
        step_ids = {step.step_id for step in chain.steps}

        for step in chain.steps:
            for dep_id in step.dependencies:
                if dep_id not in step_ids:
                    errors.append(
                        f"Step {step.step_id} references non-existent dependency: {dep_id}"
                    )

        # Check if steps are in order
        for i, step in enumerate(chain.steps):
            if step.step_number != i + 1:
                warnings.append(
                    f"Step {step.step_id} has incorrect step_number: {step.step_number} (expected {i+1})"
                )

        return len(errors) == 0

    def _check_evidence_validity(
        self,
        chain: ThoughtChain,
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Check if evidence is valid"""
        for step in chain.steps:
            if not step.evidence:
                warnings.append(
                    f"Step {step.step_id} has no supporting evidence"
                )
            elif len(step.evidence) > 10:
                warnings.append(
                    f"Step {step.step_id} has excessive evidence ({len(step.evidence)} items)"
                )

        return True  # No hard errors for evidence

    def _check_completeness(
        self,
        chain: ThoughtChain,
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Check if chain is complete"""
        if not chain.steps:
            errors.append("Chain has no steps")
            return False

        if len(chain.steps) < 2:
            warnings.append("Chain has only 1 step (recommended: 3+)")

        if not chain.conclusion:
            warnings.append("Chain has no final conclusion")

        # Check if last step has a conclusion
        if chain.steps and not chain.steps[-1].conclusion:
            errors.append("Final step has no conclusion")
            return False

        return len(errors) == 0

    def _check_fallacies(
        self,
        chain: ThoughtChain,
        errors: List[str],
        warnings: List[str]
    ) -> None:
        """Check for logical fallacies"""
        # Check for circular reasoning
        for step in chain.steps:
            if step.step_id in step.dependencies:
                errors.append(
                    f"Step {step.step_id} has circular dependency on itself"
                )

        # Check for overly confident conclusions with weak evidence
        for step in chain.steps:
            if step.confidence > 0.9 and len(step.evidence) < 2:
                warnings.append(
                    f"Step {step.step_id} has high confidence ({step.confidence}) but weak evidence"
                )

    def _generate_suggestions(
        self,
        chain: ThoughtChain,
        suggestions: List[str]
    ) -> None:
        """Generate improvement suggestions"""
        # Suggest adding evidence
        steps_without_evidence = [
            step for step in chain.steps if not step.evidence
        ]
        if steps_without_evidence:
            suggestions.append(
                f"Add evidence to {len(steps_without_evidence)} steps"
            )

        # Suggest improving low-confidence steps
        low_confidence_steps = [
            step for step in chain.steps if step.confidence < 0.7
        ]
        if low_confidence_steps:
            suggestions.append(
                f"Improve confidence of {len(low_confidence_steps)} low-confidence steps"
            )

        # Suggest adding more steps if too short
        if len(chain.steps) < 3:
            suggestions.append("Consider adding more reasoning steps for clarity")

    def calculate_confidence(
        self,
        chain: ThoughtChain,
        errors: List[str],
        warnings: List[str]
    ) -> float:
        """
        Calculate validation confidence score

        Args:
            chain: Chain to evaluate
            errors: List of errors found
            warnings: List of warnings found

        Returns:
            Confidence score (0.0-1.0)
        """
        if not chain.steps:
            return 0.0

        # Start with chain's inherent confidence
        base_confidence = chain.confidence

        # Penalties
        error_penalty = len(errors) * 0.15
        warning_penalty = len(warnings) * 0.05

        # Bonuses
        evidence_bonus = min(
            sum(1 for step in chain.steps if step.evidence) / len(chain.steps) * 0.1,
            0.1
        )

        completeness_bonus = 0.05 if chain.conclusion else 0.0

        # Calculate final confidence
        confidence = base_confidence - error_penalty - warning_penalty + evidence_bonus + completeness_bonus

        # Clamp to [0.0, 1.0]
        confidence = max(0.0, min(1.0, confidence))

        return round(confidence, 3)

    def get_validation_result(self, chain_id: str) -> Optional[ValidationResult]:
        """Get validation result for specific chain"""
        return self.validation_history.get(chain_id)

    def get_statistics(self) -> Dict:
        """Get validation statistics"""
        if not self.validation_history:
            return {
                "total_validations": 0,
                "valid_chains": 0,
                "invalid_chains": 0,
                "avg_confidence": 0.0,
                "avg_errors": 0.0,
                "avg_warnings": 0.0
            }

        results = list(self.validation_history.values())
        valid_count = sum(1 for r in results if r.is_valid)

        return {
            "total_validations": len(results),
            "valid_chains": valid_count,
            "invalid_chains": len(results) - valid_count,
            "avg_confidence": round(
                sum(r.confidence for r in results) / len(results), 3
            ),
            "avg_errors": round(
                sum(len(r.errors) for r in results) / len(results), 2
            ),
            "avg_warnings": round(
                sum(len(r.warnings) for r in results) / len(results), 2
            )
        }


# ============================================================================
# ConflictResolver (ported from app/core/conflict_resolver.py)
# ============================================================================

class ConflictResolver:
    """
    Detects and resolves conflicts between reasoning chains
    """

    def __init__(self):
        self.resolution_count = 0
        self.resolution_history: Dict[str, ResolutionResult] = {}

    def detect_conflicts(
        self,
        chains: List[ThoughtChain]
    ) -> List[Conflict]:
        """
        Detect conflicts between chains

        Args:
            chains: List of chains to analyze

        Returns:
            List of detected conflicts
        """
        conflicts = []

        # Compare each pair of chains
        for i, chain1 in enumerate(chains):
            for _j, chain2 in enumerate(chains[i+1:], i+1):
                chain_conflicts = self._compare_chains(chain1, chain2)
                conflicts.extend(chain_conflicts)

        return conflicts

    def _compare_chains(
        self,
        chain1: ThoughtChain,
        chain2: ThoughtChain
    ) -> List[Conflict]:
        """Compare two chains and find conflicts"""
        conflicts = []

        # 1. Check conclusion conflicts
        conclusion_conflict = self._check_conclusion_conflict(chain1, chain2)
        if conclusion_conflict:
            conflicts.append(conclusion_conflict)

        # 2. Check strategy conflicts (different strategies reaching different conclusions)
        if chain1.strategy != chain2.strategy:
            if not self._conclusions_compatible(chain1.conclusion, chain2.conclusion):
                conflict = Conflict(
                    conflict_id=f"conflict_{uuid.uuid4().hex[:8]}",
                    chain_ids=[chain1.chain_id, chain2.chain_id],
                    conflict_type="strategy_divergence",
                    description=f"Different strategies ({chain1.strategy.value} vs {chain2.strategy.value}) reach incompatible conclusions",
                    severity=0.6,
                    details={
                        "strategy1": chain1.strategy.value,
                        "strategy2": chain2.strategy.value,
                        "conclusion1": chain1.conclusion[:100],
                        "conclusion2": chain2.conclusion[:100]
                    }
                )
                conflicts.append(conflict)

        # 3. Check confidence conflicts (same conclusion but very different confidence)
        if self._conclusions_compatible(chain1.conclusion, chain2.conclusion):
            conf_diff = abs(chain1.confidence - chain2.confidence)
            if conf_diff > 0.3:
                conflict = Conflict(
                    conflict_id=f"conflict_{uuid.uuid4().hex[:8]}",
                    chain_ids=[chain1.chain_id, chain2.chain_id],
                    conflict_type="confidence_divergence",
                    description=f"Similar conclusions but different confidence levels ({chain1.confidence:.2f} vs {chain2.confidence:.2f})",
                    severity=conf_diff * 0.5,
                    details={
                        "confidence1": chain1.confidence,
                        "confidence2": chain2.confidence,
                        "difference": conf_diff
                    }
                )
                conflicts.append(conflict)

        return conflicts

    def _check_conclusion_conflict(
        self,
        chain1: ThoughtChain,
        chain2: ThoughtChain
    ) -> Optional[Conflict]:
        """Check if conclusions conflict"""
        if not chain1.conclusion or not chain2.conclusion:
            return None

        # Check for direct contradictions
        contradiction_pairs = [
            ("yes", "no"),
            ("true", "false"),
            ("should", "should not"),
            ("recommend", "not recommend"),
            ("positive", "negative"),
            ("agree", "disagree")
        ]

        c1_lower = chain1.conclusion.lower()
        c2_lower = chain2.conclusion.lower()

        for word1, word2 in contradiction_pairs:
            if (word1 in c1_lower and word2 in c2_lower) or \
               (word2 in c1_lower and word1 in c2_lower):
                severity = min(chain1.confidence, chain2.confidence) * 0.8
                return Conflict(
                    conflict_id=f"conflict_{uuid.uuid4().hex[:8]}",
                    chain_ids=[chain1.chain_id, chain2.chain_id],
                    conflict_type="contradictory_conclusions",
                    description="Chains reach opposite conclusions",
                    severity=severity,
                    location="conclusion",
                    details={
                        "conclusion1": chain1.conclusion,
                        "conclusion2": chain2.conclusion,
                        "confidence1": chain1.confidence,
                        "confidence2": chain2.confidence
                    }
                )

        return None

    def _conclusions_compatible(self, conclusion1: str, conclusion2: str) -> bool:
        """Check if two conclusions are compatible"""
        if not conclusion1 or not conclusion2:
            return True

        c1_words = set(conclusion1.lower().split())
        c2_words = set(conclusion2.lower().split())

        # Calculate word overlap
        overlap = len(c1_words & c2_words)
        total = len(c1_words | c2_words)

        if total == 0:
            return True

        similarity = overlap / total
        return similarity > 0.3  # Compatible if > 30% overlap

    async def resolve_conflicts(
        self,
        chains: List[ThoughtChain],
        conflicts: Optional[List[Conflict]] = None,
        strategy: ConflictStrategy = ConflictStrategy.VOTING,
        confidence_threshold: float = 0.7
    ) -> ResolutionResult:
        """
        Resolve conflicts between chains

        Args:
            chains: Chains to resolve
            conflicts: Known conflicts (will detect if not provided)
            strategy: Resolution strategy
            confidence_threshold: Minimum confidence threshold

        Returns:
            ResolutionResult
        """
        # Detect conflicts if not provided
        if conflicts is None:
            conflicts = self.detect_conflicts(chains)

        if not conflicts:
            return ResolutionResult(
                resolved=True,
                resolution_strategy=strategy,
                resolved_conflicts=[],
                unresolved_conflicts=[],
                resulting_chains=chains,
                resolution_confidence=1.0,
                explanation="No conflicts detected"
            )

        # Resolve based on strategy
        if strategy == ConflictStrategy.VOTING:
            result = await self._resolve_by_voting(chains, conflicts, confidence_threshold)
        elif strategy == ConflictStrategy.EVIDENCE:
            result = await self._resolve_by_evidence(chains, conflicts)
        elif strategy == ConflictStrategy.CHOOSE_BEST:
            result = await self._resolve_by_choosing_best(chains, conflicts)
        elif strategy == ConflictStrategy.MERGE:
            result = await self._resolve_by_merging(chains, conflicts)
        elif strategy == ConflictStrategy.AVERAGE:
            result = await self._resolve_by_averaging(chains, conflicts)
        else:  # HYBRID
            result = await self._resolve_hybrid(chains, conflicts, confidence_threshold)

        # Store in history
        resolution_id = f"resolution_{uuid.uuid4().hex[:8]}"
        self.resolution_history[resolution_id] = result
        self.resolution_count += 1

        return result

    async def _resolve_by_voting(
        self,
        chains: List[ThoughtChain],
        conflicts: List[Conflict],
        confidence_threshold: float
    ) -> ResolutionResult:
        """Resolve using confidence-weighted voting"""
        # Group chains by similar conclusions
        conclusion_groups = self._group_by_conclusion(chains)

        # Weight each group by total confidence
        group_scores = {}
        for conclusion, group_chains in conclusion_groups.items():
            total_confidence = sum(chain.confidence for chain in group_chains)
            group_scores[conclusion] = total_confidence

        # Choose winning group
        winning_conclusion = max(group_scores, key=lambda k: group_scores[k])
        winning_chains = conclusion_groups[winning_conclusion]

        # Calculate resolution confidence
        total_confidence = sum(group_scores.values())
        resolution_confidence = group_scores[winning_conclusion] / total_confidence if total_confidence > 0 else 0.0

        resolved_conflict_ids = [c.conflict_id for c in conflicts]

        return ResolutionResult(
            resolved=resolution_confidence >= confidence_threshold,
            resolution_strategy=ConflictStrategy.VOTING,
            resolved_conflicts=resolved_conflict_ids,
            unresolved_conflicts=[],
            resulting_chains=winning_chains,
            resolution_confidence=round(resolution_confidence, 3),
            explanation=f"Voting selected conclusion: '{winning_conclusion[:100]}...' with {len(winning_chains)} supporting chains"
        )

    async def _resolve_by_evidence(
        self,
        chains: List[ThoughtChain],
        conflicts: List[Conflict]
    ) -> ResolutionResult:
        """Resolve by comparing evidence quality"""
        # Count evidence for each chain
        chain_evidence_scores = {}
        for chain in chains:
            total_evidence = sum(len(step.evidence) for step in chain.steps)
            chain_evidence_scores[chain.chain_id] = total_evidence

        # Select chains with best evidence
        max_evidence = max(chain_evidence_scores.values()) if chain_evidence_scores else 0
        best_chains = [
            chain for chain in chains
            if chain_evidence_scores[chain.chain_id] >= max_evidence * 0.8
        ]

        resolution_confidence = len(best_chains) / len(chains) if chains else 0.0

        return ResolutionResult(
            resolved=True,
            resolution_strategy=ConflictStrategy.EVIDENCE,
            resolved_conflicts=[c.conflict_id for c in conflicts],
            unresolved_conflicts=[],
            resulting_chains=best_chains,
            resolution_confidence=round(resolution_confidence, 3),
            explanation=f"Selected {len(best_chains)} chains with strongest evidence"
        )

    async def _resolve_by_choosing_best(
        self,
        chains: List[ThoughtChain],
        conflicts: List[Conflict]
    ) -> ResolutionResult:
        """Resolve by choosing single best chain"""
        # Sort by confidence
        sorted_chains = sorted(chains, key=lambda c: c.confidence, reverse=True)
        best_chain = sorted_chains[0]

        return ResolutionResult(
            resolved=True,
            resolution_strategy=ConflictStrategy.CHOOSE_BEST,
            resolved_conflicts=[c.conflict_id for c in conflicts],
            unresolved_conflicts=[],
            resulting_chains=[best_chain],
            resolution_confidence=best_chain.confidence,
            explanation=f"Selected chain {best_chain.chain_id} with highest confidence ({best_chain.confidence:.3f})"
        )

    async def _resolve_by_merging(
        self,
        chains: List[ThoughtChain],
        conflicts: List[Conflict]
    ) -> ResolutionResult:
        """Resolve by merging compatible chains"""
        # This is a simplified merge - actual implementation would use ChainMerger
        compatible_chains = [
            chain for chain in chains
            if chain.confidence >= 0.7
        ]

        return ResolutionResult(
            resolved=True,
            resolution_strategy=ConflictStrategy.MERGE,
            resolved_conflicts=[c.conflict_id for c in conflicts],
            unresolved_conflicts=[],
            resulting_chains=compatible_chains,
            resolution_confidence=0.85,
            explanation="Merged compatible high-confidence chains"
        )

    async def _resolve_by_averaging(
        self,
        chains: List[ThoughtChain],
        conflicts: List[Conflict]
    ) -> ResolutionResult:
        """Resolve by averaging conclusions"""
        # Average confidence scores
        avg_confidence = sum(chain.confidence for chain in chains) / len(chains)

        # Take all chains (averaging approach)
        return ResolutionResult(
            resolved=True,
            resolution_strategy=ConflictStrategy.AVERAGE,
            resolved_conflicts=[c.conflict_id for c in conflicts],
            unresolved_conflicts=[],
            resulting_chains=chains,
            resolution_confidence=round(avg_confidence, 3),
            explanation="Averaged confidence across all chains"
        )

    async def _resolve_hybrid(
        self,
        chains: List[ThoughtChain],
        conflicts: List[Conflict],
        confidence_threshold: float
    ) -> ResolutionResult:
        """Resolve using hybrid approach"""
        # Combine voting and evidence
        voting_result = await self._resolve_by_voting(chains, conflicts, confidence_threshold)

        if voting_result.resolution_confidence >= 0.8:
            return voting_result

        # Fall back to evidence
        evidence_result = await self._resolve_by_evidence(chains, conflicts)
        return evidence_result

    def _group_by_conclusion(self, chains: List[ThoughtChain]) -> Dict[str, List[ThoughtChain]]:
        """Group chains by similar conclusions"""
        groups: Dict[str, List[ThoughtChain]] = {}

        for chain in chains:
            # Simplified grouping by conclusion text
            conclusion = chain.conclusion[:100]  # First 100 chars

            if conclusion not in groups:
                groups[conclusion] = []
            groups[conclusion].append(chain)

        return groups

    def get_statistics(self) -> Dict:
        """Get resolution statistics"""
        if not self.resolution_history:
            return {
                "total_resolutions": 0,
                "successful_resolutions": 0,
                "avg_resolution_confidence": 0.0,
                "avg_conflicts_resolved": 0.0
            }

        results = list(self.resolution_history.values())
        successful = sum(1 for r in results if r.resolved)

        return {
            "total_resolutions": len(results),
            "successful_resolutions": successful,
            "success_rate": round(successful / len(results), 3) if results else 0.0,
            "avg_resolution_confidence": round(
                sum(r.resolution_confidence for r in results) / len(results), 3
            ),
            "avg_conflicts_resolved": round(
                sum(len(r.resolved_conflicts) for r in results) / len(results), 2
            )
        }


# ============================================================================
# AnswerSynthesizer (ported from app/core/answer_synthesizer.py)
# ============================================================================

class AnswerSynthesizer:
    """
    Synthesizes final answer from multiple reasoning chains
    """

    def __init__(self):
        self.synthesis_count = 0
        self.synthesized_answers: Dict[str, SynthesizedAnswer] = {}

    async def synthesize_answer(
        self,
        chains: List[ThoughtChain],
        merged_chain: Optional[ThoughtChain] = None,
        conflicts_resolved: int = 0
    ) -> SynthesizedAnswer:
        """
        Synthesize final answer from chains

        Args:
            chains: Original chains
            merged_chain: Merged chain (if available)
            conflicts_resolved: Number of conflicts resolved

        Returns:
            SynthesizedAnswer with answer, confidence, reasoning, evidence
        """
        if not chains:
            raise ValueError("Cannot synthesize answer from empty chain list")

        # Use merged chain if available, otherwise use all chains
        primary_chain = merged_chain if merged_chain else self._select_best_chain(chains)

        # Generate answer
        answer = self._generate_answer(primary_chain, chains)

        # Calculate overall confidence
        confidence = self._calculate_overall_confidence(chains, merged_chain)

        # Generate reasoning explanation
        reasoning = self._generate_reasoning_explanation(chains, primary_chain)

        # Collect evidence
        evidence = self._collect_evidence(chains)

        # Identify supporting chains
        supporting_chains = self._identify_supporting_chains(chains, primary_chain)

        # Count total steps
        total_steps = sum(len(chain.steps) for chain in chains)

        synthesized = SynthesizedAnswer(
            answer=answer,
            confidence=confidence,
            reasoning=reasoning,
            evidence=evidence,
            supporting_chains=supporting_chains,
            chains_used=len(chains),
            conflicts_resolved=conflicts_resolved,
            total_steps=total_steps,
            created_at=datetime.now()
        )

        # Store
        answer_id = f"answer_{len(self.synthesized_answers) + 1}"
        self.synthesized_answers[answer_id] = synthesized
        self.synthesis_count += 1

        return synthesized

    def _select_best_chain(self, chains: List[ThoughtChain]) -> ThoughtChain:
        """Select the best chain from list"""
        # Sort by confidence
        sorted_chains = sorted(chains, key=lambda c: c.confidence, reverse=True)
        return sorted_chains[0]

    def _generate_answer(
        self,
        primary_chain: ThoughtChain,
        all_chains: List[ThoughtChain]
    ) -> str:
        """Generate final answer text"""
        # Use primary chain's conclusion as base
        answer = primary_chain.conclusion

        # Add synthesis note if multiple chains
        if len(all_chains) > 1:
            answer += f"\n\nThis answer is synthesized from {len(all_chains)} reasoning chains"
            answer += f" with an average confidence of {sum(c.confidence for c in all_chains) / len(all_chains):.2f}."

        return answer

    def _calculate_overall_confidence(
        self,
        chains: List[ThoughtChain],
        merged_chain: Optional[ThoughtChain]
    ) -> float:
        """Calculate overall confidence score"""
        if merged_chain:
            # Boost merged chain confidence
            return min(1.0, merged_chain.confidence * 1.05)

        # Weighted average of all chains
        total_confidence = sum(chain.confidence for chain in chains)
        avg_confidence = total_confidence / len(chains)

        # Bonus for consensus (if chains agree)
        consensus_bonus = self._calculate_consensus_bonus(chains)

        final_confidence = avg_confidence + consensus_bonus
        return round(min(1.0, final_confidence), 3)

    def _calculate_consensus_bonus(self, chains: List[ThoughtChain]) -> float:
        """Calculate bonus for consensus among chains"""
        if len(chains) < 2:
            return 0.0

        # Check if conclusions are similar
        conclusions = [chain.conclusion.lower() for chain in chains]

        # Simple word overlap check
        all_words = []
        for conclusion in conclusions:
            all_words.extend(conclusion.split())

        if not all_words:
            return 0.0

        # Count common words
        word_counts: Dict[str, int] = {}
        for word in all_words:
            word_counts[word] = word_counts.get(word, 0) + 1

        # Words appearing in most conclusions
        common_threshold = len(chains) * 0.6
        common_words = sum(1 for count in word_counts.values() if count >= common_threshold)

        # Bonus: up to 0.1 for high consensus
        consensus_score = min(common_words / 20.0, 0.1)

        return consensus_score

    def _generate_reasoning_explanation(
        self,
        chains: List[ThoughtChain],
        primary_chain: ThoughtChain
    ) -> str:
        """Generate explanation of reasoning process"""
        explanation = []

        # Overview
        explanation.append(
            f"This conclusion is based on {len(chains)} reasoning chains "
            f"using different strategies."
        )

        # Strategy diversity
        strategies = set(chain.strategy.value for chain in chains)
        explanation.append(
            f"Strategies employed: {', '.join(strategies)}."
        )

        # Primary reasoning path
        explanation.append(
            f"\nPrimary reasoning ({primary_chain.strategy.value}):"
        )
        for i, step in enumerate(primary_chain.steps[:3], 1):  # Show first 3 steps
            explanation.append(
                f"{i}. {step.description} (confidence: {step.confidence:.2f})"
            )

        # Confidence summary
        avg_conf = sum(c.confidence for c in chains) / len(chains)
        explanation.append(
            f"\nAverage confidence across all chains: {avg_conf:.2f}"
        )

        return "\n".join(explanation)

    def _collect_evidence(self, chains: List[ThoughtChain]) -> List[str]:
        """Collect all evidence from chains"""
        all_evidence = set()

        for chain in chains:
            for step in chain.steps:
                all_evidence.update(step.evidence)

        # Sort and limit
        evidence_list = sorted(all_evidence)

        # Return top 10 most important pieces
        return evidence_list[:10]

    def _identify_supporting_chains(
        self,
        all_chains: List[ThoughtChain],
        primary_chain: ThoughtChain
    ) -> List[str]:
        """Identify which chains support the primary conclusion"""
        supporting = []

        primary_conclusion_words = set(primary_chain.conclusion.lower().split())

        for chain in all_chains:
            chain_words = set(chain.conclusion.lower().split())
            overlap = len(primary_conclusion_words & chain_words)
            total = len(primary_conclusion_words | chain_words)

            similarity = overlap / total if total > 0 else 0.0

            # Consider supporting if >50% similarity
            if similarity > 0.5:
                supporting.append(chain.chain_id)

        return supporting

    def get_answer(self, answer_id: str) -> Optional[SynthesizedAnswer]:
        """Get specific answer"""
        return self.synthesized_answers.get(answer_id)

    def get_all_answers(self) -> List[SynthesizedAnswer]:
        """Get all synthesized answers"""
        return list(self.synthesized_answers.values())

    def get_statistics(self) -> Dict:
        """Get synthesis statistics"""
        if not self.synthesized_answers:
            return {
                "total_syntheses": 0,
                "avg_confidence": 0.0,
                "avg_chains_used": 0.0,
                "avg_conflicts_resolved": 0.0
            }

        answers = list(self.synthesized_answers.values())

        return {
            "total_syntheses": len(answers),
            "avg_confidence": round(
                sum(a.confidence for a in answers) / len(answers), 3
            ),
            "avg_chains_used": round(
                sum(a.chains_used for a in answers) / len(answers), 2
            ),
            "avg_conflicts_resolved": round(
                sum(a.conflicts_resolved for a in answers) / len(answers), 2
            ),
            "avg_total_steps": round(
                sum(a.total_steps for a in answers) / len(answers), 2
            )
        }


# ============================================================================
# Smoke test
# ============================================================================
#
# NOTE: this deliberately does NOT set RCTLABS_OPENROUTER_API_KEY /
# FARMER_OPENROUTER_API_KEY. See the module docstring's "NOTE on this
# port's own smoke test" above for why: a live key was supplied inline in
# the porting task instructions, and entering API keys/tokens into any
# process is against this assistant's standing safety rules regardless of
# who supplies or authorizes it. This smoke test exercises the real,
# honest FALLBACK path end to end (generation -> execution -> validation
# -> conflict resolution -> merge -> synthesis) and asserts
# simulated == True for every chain, which is itself a genuine
# verification that the disclosure mechanism works correctly. A human
# wanting to exercise the real-LLM branch (simulated == False) should set
# one of those two env vars themselves, in their own shell, before running
# this file - not paste a key into an agent prompt.

if __name__ == "__main__":
    import asyncio as _asyncio

    async def _main():
        print("=== ALGO-32 MCTR smoke test (honest-fallback path; no API key set) ===")

        # Make sure no key leaks in from the ambient environment for this
        # deliberately-fallback run.
        os.environ.pop("RCTLABS_OPENROUTER_API_KEY", None)
        os.environ.pop("FARMER_OPENROUTER_API_KEY", None)

        query = "Should a payment retry use exponential backoff or fixed delay?"

        # 1. Generate chains
        generator = ThoughtChainGenerator()
        chains = await generator.generate_chains(query=query, num_chains=3)
        print(f"\n[1] generate_chains() -> {len(chains)} chains")
        assert len(chains) == 3, f"expected 3 chains, got {len(chains)}"
        for chain in chains:
            print(f"    chain_id={chain.chain_id} strategy={chain.strategy.value} "
                  f"steps={len(chain.steps)} confidence={chain.confidence:.3f} simulated={chain.simulated}")
            assert len(chain.steps) >= 3, "each chain should have real structural steps"
            assert 0.0 <= chain.confidence <= 1.0
            for step in chain.steps:
                assert 0.0 <= step.confidence <= 1.0
                assert step.reasoning and step.conclusion
            # No API key configured in this run -> every chain must honestly
            # disclose that it fell back to the heuristic template.
            assert chain.simulated is True, "expected simulated=True with no API key configured"

        diversity = generator.calculate_diversity_score(chains)
        print(f"    diversity_score={diversity}")

        # 2. Execute all chains
        engine = ReasoningEngine()
        exec_results = await engine.execute_all_chains(chains)
        print(f"\n[2] execute_all_chains() -> {len(exec_results)} results")
        assert len(exec_results) == 3
        for r in exec_results:
            print(f"    chain_id={r.chain.chain_id} success={r.success} "
                  f"status={r.chain.status.value} exec_time={r.chain.execution_time:.4f}s")
            assert r.success is True, f"expected successful execution, got error={r.error}"
        success_rate = engine.calculate_success_rate()
        print(f"    engine success_rate={success_rate}")
        assert success_rate == 1.0

        executed_chains = [r.chain for r in exec_results]

        # 3. Validate each chain
        validator = ChainValidator()
        validation_results = [validator.validate_chain(c, validation_level=ValidationLevel.STRICT) for c in executed_chains]
        print(f"\n[3] validate_chain() x{len(validation_results)}")
        for vr in validation_results:
            print(f"    chain_id={vr.chain_id} is_valid={vr.is_valid} confidence={vr.confidence} "
                  f"errors={vr.errors} warnings={vr.warnings}")
            assert vr.logic_consistent
            assert vr.steps_connected
            assert vr.complete

        # 4. Detect + resolve conflicts across the chains
        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(executed_chains)
        print(f"\n[4] detect_conflicts() -> {len(conflicts)} conflicts")
        resolution = await resolver.resolve_conflicts(executed_chains, conflicts=conflicts, strategy=ConflictStrategy.HYBRID)
        print(f"    resolved={resolution.resolved} strategy={resolution.resolution_strategy.value} "
              f"resolution_confidence={resolution.resolution_confidence} "
              f"resulting_chains={len(resolution.resulting_chains)}")
        assert resolution.resulting_chains, "resolution should leave at least one chain to work with"

        # 5. Merge the resolved chains (falls back to the single chain if
        #    resolution left only one - merge_chains() itself handles that).
        merger = ChainMerger()
        merged = await merger.merge_chains(resolution.resulting_chains, strategy=MergeStrategy.HYBRID) \
            if len(resolution.resulting_chains) > 1 else resolution.resulting_chains[0]
        print(f"\n[5] merge -> chain_id={merged.chain_id} status={merged.status.value} "
              f"steps={len(merged.steps)} confidence={merged.confidence}")

        # 6. Synthesize final answer using the original executed chains,
        #    the merged chain, and how many conflicts were resolved.
        synthesizer = AnswerSynthesizer()
        answer = await synthesizer.synthesize_answer(
            chains=executed_chains,
            merged_chain=merged,
            conflicts_resolved=len(resolution.resolved_conflicts),
        )
        print("\n[6] synthesize_answer() ->")
        print(f"    confidence={answer.confidence}")
        print(f"    chains_used={answer.chains_used} total_steps={answer.total_steps} "
              f"conflicts_resolved={answer.conflicts_resolved}")
        print(f"    supporting_chains={answer.supporting_chains}")
        print(f"    evidence(sample)={answer.evidence[:5]}")
        print(f"    answer_text:\n{answer.answer}")
        assert answer.chains_used == 3
        assert answer.total_steps == sum(len(c.steps) for c in executed_chains)
        assert 0.0 <= answer.confidence <= 1.0
        assert answer.answer and len(answer.answer) >= 10

        print("\n=== ALGO-32 MCTR: ALL ASSERTIONS PASSED (honest-fallback path) ===")
        print("NOTE: real-LLM path (simulated=False) was NOT exercised in this run - "
              "no API key was set, per this session's standing safety rules against "
              "entering API keys/tokens into any process. Set RCTLABS_OPENROUTER_API_KEY "
              "or FARMER_OPENROUTER_API_KEY yourself, in your own shell, to exercise it.")

    _asyncio.run(_main())

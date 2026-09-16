"""
ALGO-21: Fast/Slow Router — original design (2026-09-16, Round 20+).

No existing code to port anywhere in Delentia-Private-OS or Delentia-OS
(confirmed by a prior audit, and by the user's own repeated framing of
this algorithm as needing "a separate design session") — this is a
from-scratch design, built explicitly to integrate with this kernel's
already-real algorithms rather than invent a parallel, disconnected
classifier:

- PRIMARY signal: `IntentCompiler.compile()` (intent_compiler.py) — the
  SAME real compiler algorithm_kernel_41.py's `synthesize_fdia_inputs()`
  already runs for every intent through ALGO-01 FDIA. Reusing it (not a
  second, independently-invented notion of risk) keeps routing decisions
  consistent with the kernel's own real risk/scope math.
- SECONDARY signal: ALGO-26 `IntentClassifier` — used only when
  IntentCompiler cannot classify the text as a recognized dev-operation
  intent at all (e.g. general conversational text), to avoid defaulting
  everything non-dev-operation-shaped to the expensive SLOW path.
- DISPATCH targets: ALGO-09 (Reflexion+), ALGO-11 (BBA->P->CF), and
  ALGO-32 (MCTR, optional — duck-typed so this router works today with
  just the first two and gains MCTR the moment it's wired, with no
  redesign) — this router is the first thing in this kernel that unifies
  all three "slow, LLM-backed reasoning engines" under one coherent
  front door instead of leaving callers to pick one ad hoc.

Concept (Kahneman-style dual-process routing applied to intent
handling): most real developer intents ("document this function", "add
a test for X") are low-risk and don't need multi-step LLM reasoning —
routing everything through a deep reasoning chain would be both slower
and more expensive than necessary. This router makes one explicit,
deterministic, explainable decision per intent instead.

Decision policy (ties intentionally break toward SLOW — safety first,
matching the same direction the kernel's own FDIA I-bonus table already
takes for SYSTEMIC/INFRASTRUCTURE intents):

  IntentCompiler compiles successfully:
    - risk_profile == LOW and scope_type in {FILE, MODULE}: FAST
    - risk_profile == LOW but scope_type in {PACKAGE, REPOSITORY, SYSTEM,
      INFRASTRUCTURE}: SLOW (blast radius trumps a low keyword-matched
      risk_profile — a low-risk-looking sentence that touches the whole
      repository is still not a FAST-path candidate)
    - risk_profile in {STRUCTURAL, SYSTEMIC}: SLOW

  IntentCompiler fails to compile (not a recognized dev-operation
  intent):
    - ALGO-26 confidently classifies it (confidence >= threshold) as a
      simple conversational category (SOCIAL/QUERY): FAST (a greeting or
      a simple question genuinely doesn't need deep reasoning either)
    - otherwise: SLOW (unclassifiable AND not simple = genuinely
      uncertain input, which is exactly when deliberate reasoning is
      warranted)

Slow-strategy selection (only when routed SLOW) maps each real
IntentType to whichever of the three real reasoning engines' own actual
design best fits that task shape — not an arbitrary assignment:
    - DEBUG / ANALYZE_RISK / TEST: Reflexion+ (its real generate->judge->
      reflect->refine loop fits root-cause/verification tasks)
    - BUILD_APP / DEPLOY / OPTIMIZE / TRANSFORM: BBA->P->CF (its real
      belief->plan->consequence-forecast pipeline fits action/execution
      tasks with real downstream consequences to forecast)
    - STRATEGY / REFACTOR / DOCUMENT, or no recognized intent_type at
      all (unclassifiable-but-still-routed-SLOW case): MCTR when
      available (its real diverse multi-chain-strategy design fits
      open-ended/ambiguous problems best), else Reflexion+ as an
      honestly-reported fallback.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from rct_control_plane.intent_compiler import IntentCompiler
from rct_control_plane.intent_schema import IntentType, RiskProfile, ScopeType


class RoutingPath(str, Enum):
    FAST = "fast"
    SLOW = "slow"


class SlowStrategy(str, Enum):
    REFLEXION = "reflexion_plus"   # ALGO-09
    BBA_PCF = "bba_pcf"            # ALGO-11
    MCTR = "mctr"                  # ALGO-32 (optional)


# Real, documented mapping — not arbitrary (see module docstring for the
# reasoning behind each grouping).
_DEBUG_VERIFY_TYPES = {IntentType.DEBUG, IntentType.ANALYZE_RISK, IntentType.TEST}
_ACTION_EXECUTION_TYPES = {IntentType.BUILD_APP, IntentType.DEPLOY, IntentType.OPTIMIZE, IntentType.TRANSFORM}
_OPEN_ENDED_TYPES = {IntentType.STRATEGY, IntentType.REFACTOR, IntentType.DOCUMENT}

_LOW_BLAST_RADIUS_SCOPES = {ScopeType.FILE, ScopeType.MODULE}
_SIMPLE_CONVERSATIONAL_CATEGORIES = {"social", "query"}


@dataclass
class RoutingDecision:
    """A real, explainable routing decision — every field is a genuine
    signal that fed the decision, not decorative metadata."""
    path: RoutingPath
    reason: str
    compiler_success: bool
    risk_profile: Optional[str] = None
    scope_type: Optional[str] = None
    intent_type: Optional[str] = None
    classifier_confidence: Optional[float] = None
    classifier_category: Optional[str] = None
    slow_strategy: Optional[SlowStrategy] = None
    slow_strategy_fallback_reason: Optional[str] = None


@dataclass
class RoutingResult:
    """The decision plus what actually executing it produced."""
    text: str
    decision: RoutingDecision
    result: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


class FastSlowRouter:
    """
    ALGO-21: real dual-process router over this kernel's own already-real
    algorithms. See module docstring for the full decision policy.
    """

    def __init__(
        self,
        intent_compiler: IntentCompiler,
        intent_classifier: Optional[Any] = None,
        reflexion_engine: Optional[Any] = None,
        bba_pcf_engine: Optional[Any] = None,
        mctr_generator: Optional[Any] = None,
        mctr_reasoning_engine: Optional[Any] = None,
        fast_confidence_threshold: float = 0.5,
    ):
        # 0.5 (not a stricter round number like 0.6) deliberately matches
        # ALGO-26 IntentClassifier's OWN real confidence ceiling: its
        # documented real scoring formula caps a clean, unambiguous
        # single-intent match at exactly 0.5 (verified in this session -
        # e.g. a plain "Hello, good morning!" greeting genuinely scores
        # 0.500, not higher). A stricter threshold here would silently
        # route every simple, correctly-classified conversational intent
        # to the expensive SLOW path for no real reason.
        self._intent_compiler = intent_compiler
        self._intent_classifier = intent_classifier
        self._reflexion_engine = reflexion_engine
        self._bba_pcf_engine = bba_pcf_engine
        self._mctr_generator = mctr_generator
        self._mctr_reasoning_engine = mctr_reasoning_engine
        self.fast_confidence_threshold = fast_confidence_threshold

        self._route_counts: Dict[str, int] = {"fast": 0, "slow": 0}
        self._strategy_counts: Dict[str, int] = {s.value: 0 for s in SlowStrategy}
        self._latencies_ms: Dict[str, List[float]] = {"fast": [], "slow": []}

    # ------------------------------------------------------------------
    # Decision (pure, synchronous, no I/O — real logic, fully unit-testable
    # without touching Ollama/OpenRouter)
    # ------------------------------------------------------------------
    def decide(self, text: str, context: Optional[Dict[str, Any]] = None) -> RoutingDecision:
        compilation = self._intent_compiler.compile(natural_language=text, user_id="algo21-router", user_tier="PRO")

        if compilation.success and compilation.intent is not None:
            intent_obj = compilation.intent
            risk_value = getattr(intent_obj.risk_profile, "value", str(intent_obj.risk_profile))
            scope_type = intent_obj.scope.scope_type
            scope_value = getattr(scope_type, "value", str(scope_type))
            intent_type = intent_obj.intent_type
            intent_type_value = getattr(intent_type, "value", str(intent_type))

            if intent_obj.risk_profile == RiskProfile.LOW and scope_type in _LOW_BLAST_RADIUS_SCOPES:
                return RoutingDecision(
                    path=RoutingPath.FAST,
                    reason=f"IntentCompiler: risk=LOW, scope={scope_value} (low blast radius)",
                    compiler_success=True,
                    risk_profile=risk_value,
                    scope_type=scope_value,
                    intent_type=intent_type_value,
                )

            if intent_obj.risk_profile == RiskProfile.LOW:
                reason = f"IntentCompiler: risk=LOW but scope={scope_value} (blast radius too wide for FAST)"
            else:
                reason = f"IntentCompiler: risk={risk_value}, scope={scope_value}"

            strategy, fallback_reason = self._choose_slow_strategy(intent_type)
            return RoutingDecision(
                path=RoutingPath.SLOW,
                reason=reason,
                compiler_success=True,
                risk_profile=risk_value,
                scope_type=scope_value,
                intent_type=intent_type_value,
                slow_strategy=strategy,
                slow_strategy_fallback_reason=fallback_reason,
            )

        # IntentCompiler couldn't classify this as a recognized
        # dev-operation intent — fall back to ALGO-26 as a secondary
        # signal before defaulting to SLOW.
        if self._intent_classifier is not None:
            response = self._intent_classifier.classify(text, context=context)
            confidence = response.intents[0].confidence if response.intents else 0.0
            category = response.intents[0].category if response.intents else None

            if confidence >= self.fast_confidence_threshold and category in _SIMPLE_CONVERSATIONAL_CATEGORIES:
                return RoutingDecision(
                    path=RoutingPath.FAST,
                    reason=f"IntentCompiler could not classify; ALGO-26 confidently ({confidence:.2f}) "
                           f"found a simple conversational intent (category={category})",
                    compiler_success=False,
                    classifier_confidence=confidence,
                    classifier_category=category,
                )

            strategy, fallback_reason = self._choose_slow_strategy(None)
            return RoutingDecision(
                path=RoutingPath.SLOW,
                reason=f"IntentCompiler could not classify; ALGO-26 confidence={confidence:.2f} "
                       f"category={category} — not simple/confident enough for FAST",
                compiler_success=False,
                classifier_confidence=confidence,
                classifier_category=category,
                slow_strategy=strategy,
                slow_strategy_fallback_reason=fallback_reason,
            )

        # No secondary classifier injected at all — genuinely uncertain
        # input defaults to SLOW (safety-first).
        strategy, fallback_reason = self._choose_slow_strategy(None)
        return RoutingDecision(
            path=RoutingPath.SLOW,
            reason="IntentCompiler could not classify and no ALGO-26 classifier was injected",
            compiler_success=False,
            slow_strategy=strategy,
            slow_strategy_fallback_reason=fallback_reason,
        )

    def _choose_slow_strategy(self, intent_type: Optional[IntentType]) -> tuple:
        """Returns (strategy, fallback_reason). fallback_reason is set
        (non-None) only when the ideally-chosen strategy's engine wasn't
        injected and a real, disclosed substitution had to be made."""
        if intent_type in _DEBUG_VERIFY_TYPES and self._reflexion_engine is not None:
            return SlowStrategy.REFLEXION, None
        if intent_type in _ACTION_EXECUTION_TYPES and self._bba_pcf_engine is not None:
            return SlowStrategy.BBA_PCF, None
        if (intent_type in _OPEN_ENDED_TYPES or intent_type is None) and self._mctr_generator is not None:
            return SlowStrategy.MCTR, None

        # Ideal engine unavailable (or intent_type didn't match a group) —
        # fall back, in real preference order, to whichever engine WAS
        # injected. Never fabricate a strategy for an engine that isn't
        # there.
        if self._reflexion_engine is not None:
            return SlowStrategy.REFLEXION, f"preferred strategy unavailable for intent_type={intent_type}; using Reflexion+ (available)"
        if self._bba_pcf_engine is not None:
            return SlowStrategy.BBA_PCF, f"preferred strategy unavailable for intent_type={intent_type}; using BBA-PCF (available)"
        if self._mctr_generator is not None:
            return SlowStrategy.MCTR, f"preferred strategy unavailable for intent_type={intent_type}; using MCTR (available)"
        return SlowStrategy.REFLEXION, "no slow-reasoning engine was injected into this router at all"

    # ------------------------------------------------------------------
    # Execution (async — actually dispatches to the real engines)
    # ------------------------------------------------------------------
    async def route(self, text: str, context: Optional[Dict[str, Any]] = None) -> RoutingResult:
        t_start = time.perf_counter()
        decision = self.decide(text, context=context)

        if decision.path == RoutingPath.FAST:
            result = await self._execute_fast(text, context, decision)
        else:
            result = await self._execute_slow(text, context, decision)

        latency_ms = (time.perf_counter() - t_start) * 1000
        self._route_counts[decision.path.value] += 1
        self._latencies_ms[decision.path.value].append(latency_ms)
        if decision.slow_strategy is not None:
            self._strategy_counts[decision.slow_strategy.value] += 1

        return RoutingResult(text=text, decision=decision, result=result, latency_ms=round(latency_ms, 4))

    async def _execute_fast(self, text: str, context: Optional[Dict[str, Any]], decision: RoutingDecision) -> Dict[str, Any]:
        """FAST path: no LLM call. If IntentCompiler classified it, that
        classification IS the answer (this kernel already trusts it
        enough to route FAST). If ALGO-26 classified it, report that."""
        if decision.compiler_success:
            return {"path": "fast", "source": "IntentCompiler", "action": "proceed_directly"}
        return {
            "path": "fast", "source": "ALGO-26 IntentClassifier",
            "confidence": decision.classifier_confidence, "category": decision.classifier_category,
        }

    async def _execute_slow(self, text: str, context: Optional[Dict[str, Any]], decision: RoutingDecision) -> Dict[str, Any]:
        """SLOW path: real dispatch into whichever engine decide() chose."""
        strategy = decision.slow_strategy

        if strategy == SlowStrategy.REFLEXION and self._reflexion_engine is not None:
            session_id = await self._reflexion_engine.start_reflexion(text, context=context)
            return {"path": "slow", "strategy": "reflexion_plus", **self._reflexion_engine.get_final_result(session_id)}

        if strategy == SlowStrategy.BBA_PCF and self._bba_pcf_engine is not None:
            session_id = await self._bba_pcf_engine.analyze(
                query=text, evidence=(context or {}).get("evidence", []), goals=(context or {}).get("goals", [text])
            )
            return {"path": "slow", "strategy": "bba_pcf", **self._bba_pcf_engine.get_analysis(session_id)}

        if strategy == SlowStrategy.MCTR and self._mctr_generator is not None and self._mctr_reasoning_engine is not None:
            chains = await self._mctr_generator.generate_chains(query=text, num_chains=3)
            results = await self._mctr_reasoning_engine.execute_all_chains(chains)
            return {
                "path": "slow", "strategy": "mctr",
                "chains_generated": len(chains),
                "chains_succeeded": sum(1 for r in results if r.success),
            }

        return {"path": "slow", "strategy": "none", "error": "no slow-reasoning engine available to execute this decision"}

    def get_statistics(self) -> Dict[str, Any]:
        def _avg(vals: List[float]) -> float:
            return round(sum(vals) / len(vals), 4) if vals else 0.0

        return {
            "route_counts": dict(self._route_counts),
            "strategy_counts": {k: v for k, v in self._strategy_counts.items() if v > 0},
            "avg_latency_ms": {
                "fast": _avg(self._latencies_ms["fast"]),
                "slow": _avg(self._latencies_ms["slow"]),
            },
            "total_routed": sum(self._route_counts.values()),
        }


if __name__ == "__main__":
    import asyncio
    import os
    import sys

    # Running this file directly (`python rct_control_plane/algo_21_...py`)
    # sets sys.path[0] to this file's own directory, which can shadow the
    # editable-installed `rct_control_plane` package for the sibling
    # cross-imports below. Insert the real project root explicitly so this
    # works the same way regardless of how the script is invoked.
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    async def _smoke_test():
        print("=" * 78)
        print("ALGO-21 Fast/Slow Router smoke test")
        print("=" * 78)

        from rct_control_plane.algo_09_reflexion_plus import ReflexionEngine
        from rct_control_plane.algo_11_bba_pcf import BBAPCFEngine
        from rct_control_plane.algo_26_intent_classification import IntentClassifier

        router = FastSlowRouter(
            intent_compiler=IntentCompiler(),
            intent_classifier=IntentClassifier(),
            reflexion_engine=ReflexionEngine(),
            bba_pcf_engine=BBAPCFEngine(),
            # mctr_generator / mctr_reasoning_engine intentionally omitted
            # here — ALGO-32 is still being ported in parallel; the
            # decision logic below proves the honest-fallback path works
            # correctly when MCTR isn't available yet.
        )

        # --- Pure decision tests (no LLM calls, fast, deterministic) ---
        print("\n--- Decision logic (no LLM calls) ---")

        d1 = router.decide("document this function")
        print(f"'document this function' -> path={d1.path.value} risk={d1.risk_profile} scope={d1.scope_type} reason={d1.reason}")
        assert d1.path == RoutingPath.FAST, "low-risk, file-scoped DOCUMENT intent must route FAST"

        d2 = router.decide("deploy the entire infrastructure to production")
        print(f"'deploy the entire infrastructure...' -> path={d2.path.value} risk={d2.risk_profile} scope={d2.scope_type} strategy={d2.slow_strategy} reason={d2.reason}")
        assert d2.path == RoutingPath.SLOW, "DEPLOY + INFRASTRUCTURE scope must route SLOW"
        assert d2.slow_strategy == SlowStrategy.BBA_PCF, "DEPLOY is an action/execution intent type -> BBA-PCF"

        d3 = router.decide("refactor the entire codebase")
        print(f"'refactor the entire codebase' -> path={d3.path.value} risk={d3.risk_profile} scope={d3.scope_type} strategy={d3.slow_strategy} fallback={d3.slow_strategy_fallback_reason}")
        assert d3.path == RoutingPath.SLOW, "REFACTOR across the whole codebase (REPOSITORY scope) must route SLOW"
        # REFACTOR is an "open-ended" type -> ideally MCTR, but it's not
        # injected in this test -> must honestly report a real fallback.
        assert d3.slow_strategy in (SlowStrategy.MCTR, SlowStrategy.REFLEXION, SlowStrategy.BBA_PCF)
        if d3.slow_strategy != SlowStrategy.MCTR:
            assert d3.slow_strategy_fallback_reason is not None, "a non-ideal strategy substitution must be disclosed, not silent"

        d4 = router.decide("Hello, good morning!")
        print(f"'Hello, good morning!' -> path={d4.path.value} compiler_success={d4.compiler_success} "
              f"classifier_confidence={d4.classifier_confidence} category={d4.classifier_category} reason={d4.reason}")
        assert d4.compiler_success is False, "a greeting is not a recognized dev-operation intent"
        assert d4.path == RoutingPath.FAST, "ALGO-26 must confidently recognize this as a simple SOCIAL intent -> FAST"

        d5 = router.decide("asdkjfh qwoeiru xzcvn")
        print(f"'asdkjfh qwoeiru xzcvn' (gibberish) -> path={d5.path.value} reason={d5.reason}")
        assert d5.path == RoutingPath.SLOW, "genuinely unclassifiable, non-simple input must default to SLOW (safety-first)"

        # --- Real end-to-end execution (real Ollama calls via ALGO-09/11) ---
        print("\n--- Real end-to-end execution (real local-Ollama LLM calls) ---")

        fast_result = await router.route("test this module")
        print(f"FAST route result: {fast_result.result} (latency={fast_result.latency_ms}ms)")
        assert fast_result.decision.path == RoutingPath.FAST
        assert fast_result.latency_ms < 50, "the FAST path must genuinely be fast (no LLM call) — under 50ms"

        # "entire system" triggers ScopeType.SYSTEM (outside the FAST
        # path's low-blast-radius scopes), so this DEBUG-type intent
        # genuinely routes SLOW -> Reflexion+, unlike a narrowly-scoped
        # debug request (e.g. "debug this file"), which would legitimately
        # route FAST under this router's own risk/scope policy.
        slow_result = await router.route(
            "debug why the entire system's payment retry logic sometimes double-charges customers"
        )
        print(f"SLOW route result: strategy={slow_result.decision.slow_strategy.value} "
              f"latency={slow_result.latency_ms}ms")
        print(f"  engine output keys: {list(slow_result.result.keys())}")
        assert slow_result.decision.path == RoutingPath.SLOW
        assert slow_result.decision.slow_strategy == SlowStrategy.REFLEXION, "DEBUG intent -> Reflexion+"
        assert "error" not in slow_result.result, f"real Reflexion+ dispatch must not error: {slow_result.result}"
        assert slow_result.latency_ms > fast_result.latency_ms, "a real LLM-backed SLOW call must measure slower than the no-LLM FAST path"

        stats = router.get_statistics()
        print(f"\nRouter statistics: {stats}")
        assert stats["route_counts"]["fast"] >= 1
        assert stats["route_counts"]["slow"] >= 1
        assert stats["avg_latency_ms"]["slow"] > stats["avg_latency_ms"]["fast"], "real aggregate slow latency must exceed real aggregate fast latency"

        print("\nALL ALGO-21 ASSERTIONS PASSED")

    asyncio.run(_smoke_test())

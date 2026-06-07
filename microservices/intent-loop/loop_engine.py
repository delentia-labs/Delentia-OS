"""
Intent Loop Engine: The Evolutionary Intelligence Core

This is the heart of RCT Ecosystem - a self-optimizing loop that learns from every interaction.

The Master Equation:
FDIA + JITNA + Delta Engine + SignedAI + DelentiaDB = Evolutionary Compound Intelligence

Philosophy:
- Cold Start: First time = 3-5 seconds (full computation)
- Warm Recall: Next time = <50ms (memory retrieval)
- Evolution: System gets smarter, faster, cheaper over time
- Cost → 0 as system matures
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum
from datetime import datetime
import asyncio
import logging
import hashlib
import json
import sys
import os

# Ensure project root is on the path so core.* and signedai.* are importable
# when the module is loaded directly (e.g. during unit tests) rather than via
# the installed package.
_LOOP_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_LOOP_ENGINE_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.fdia.fdia import FDIAScorer, NPCAction, NPCIntentType  # Gap 4  # noqa: E402
from core.delta_engine.memory_delta import MemoryDeltaEngine  # Gap 5  # noqa: E402
from signedai.core.registry import HexaCoreRegistry, HexaCoreRole  # Gap 7  # noqa: E402

logger = logging.getLogger(__name__)


class IntentState(Enum):
    """States in the intent processing loop"""
    RECEIVED = "received"
    VALIDATED = "validated"
    MEMORY_CHECK = "memory_check"
    COMPUTING = "computing"
    VERIFYING = "verifying"
    COMMITTING = "committing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JITNAPacket:
    """Just-In-Time Natural Architecture packet"""
    intent: str
    context: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    intent_hash: Optional[str] = None  # Optional pre-computed hash (Gap 5: MemoryDeltaEngine)
    priority: int = 3

    
    def compute_hash(self) -> str:
        """Compute semantic hash for similarity matching"""
        # Normalize intent for matching
        normalized = self.intent.lower().strip()
        content = f"{normalized}:{json.dumps(self.context, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class MemoryHit:
    """Cached wisdom from previous execution"""
    intent_hash: str
    result: Dict[str, Any]
    confidence: float  # 0.0 - 1.0
    created_at: datetime
    access_count: int
    last_accessed: datetime
    delta_size: int  # Bytes saved by compression


@dataclass
class LoopMetrics:
    """Runtime metrics for the Intent Loop Engine."""
    total_processed: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_latency_ms: float = 0.0
    error_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def cache_hit_rate(self) -> float:
        """Fraction of requests served from cache (0.0–1.0)."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0


@dataclass
class IntentResult:
    """Result from intent processing"""
    intent_hash: str
    state: IntentState
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    cache_hit: bool = False
    verification_passed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class FDIAGatekeeper:
    """
    Pillar 1: FDIA Gatekeeper (Input Layer)

    Enforces: F = (D^I) × A
    - F: Final Output
    - D: Data Quality
    - I: Intent Clarity
    - A: Architect Approval (Human-in-the-loop)

    Integration: Uses FDIAScorer from core.fdia.fdia for mathematical scoring
    in addition to keyword/length pre-filtering.
    """

    # FDIA score threshold — intents below this are rejected as low quality
    FDIA_THRESHOLD: float = 0.25

    def __init__(self):
        self.constitution_rules = {
            "max_intent_length": 1000,
            "forbidden_keywords": ["hack", "exploit", "bypass"],
            "require_human_approval": False  # Can be enabled for sensitive ops
        }
        # SDK integration: use FDIAScorer for mathematical quality scoring
        self.scorer = FDIAScorer()
        logger.info("FDIAGatekeeper initialized (FDIAScorer active)")

    # --- static helpers ------------------------------------------------

    @staticmethod
    def _map_intent_to_npc_type(intent_text: str) -> NPCIntentType:
        """Map free-text intent to the closest NPCIntentType for FDIA scoring."""
        text = intent_text.lower()
        if any(k in text for k in ("protect", "secure", "defend", "guard", "prevent", "safety")):
            return NPCIntentType.PROTECT
        if any(k in text for k in ("buy", "sell", "trade", "invest", "profit", "market", "earn", "revenue")):
            return NPCIntentType.ACCUMULATE
        if any(k in text for k in ("join", "connect", "share", "collaborate", "team", "partner")):
            return NPCIntentType.BELONG
        # Default: DISCOVER — covers analyze, research, learn, build, find, etc.
        return NPCIntentType.DISCOVER

    @staticmethod
    def _action_type_for(intent_type: NPCIntentType) -> str:
        """Return a compatible action type string for the given NPCIntentType."""
        mapping = {
            NPCIntentType.PROTECT:    "defend",
            NPCIntentType.ACCUMULATE: "trade",
            NPCIntentType.BELONG:     "cooperate",
            NPCIntentType.DISCOVER:   "explore",
            NPCIntentType.DOMINATE:   "attack",
            NPCIntentType.NEUTRAL:    "idle",
        }
        return mapping.get(intent_type, "explore")

    async def validate(self, packet: JITNAPacket) -> bool:
        """
        Validate intent against FDIA constitution.

        Pipeline:
        1. Length guard (fast pre-filter)
        2. Forbidden keyword check (fast pre-filter)
        3. FDIAScorer mathematical quality gate
        4. Human approval gate (if enabled)

        Returns:
            True if intent passes all checks

        Raises:
            SecurityViolation if intent violates rules
        """
        # Rule 1: Intent length check
        if len(packet.intent) > self.constitution_rules["max_intent_length"]:
            logger.warning(f"Intent too long: {len(packet.intent)} chars")
            raise SecurityViolation("Intent exceeds maximum length")

        # Rule 2: Forbidden keyword check
        intent_lower = packet.intent.lower()
        for keyword in self.constitution_rules["forbidden_keywords"]:
            if keyword in intent_lower:
                logger.error(f"Forbidden keyword detected: {keyword}")
                raise SecurityViolation(f"Intent contains forbidden keyword: {keyword}")

        # Rule 3: FDIAScorer mathematical quality gate
        intent_type = self._map_intent_to_npc_type(packet.intent)
        action_type = self._action_type_for(intent_type)
        action = NPCAction(
            action_id=packet.compute_hash()[:16],
            action_type=action_type,
        )
        fdia_score = self.scorer.score_action(
            agent_intent=intent_type,
            action=action,
            agent_reputation=1.0,
            governance_penalty=0.0,
        )
        if fdia_score < self.FDIA_THRESHOLD:
            logger.warning(f"FDIA score too low: {fdia_score:.3f} < {self.FDIA_THRESHOLD}")
            raise SecurityViolation(f"FDIA score below threshold: {fdia_score:.3f}")

        # Rule 4: Human approval (if required)
        if self.constitution_rules["require_human_approval"]:
            # In production: send to approval queue
            logger.info("Intent requires human approval")

        logger.info(f"Intent validated (FDIA={fdia_score:.3f}): {packet.intent[:50]}...")
        return True


class MemoryLayer:
    """
    Pillar 2: DelentiaDB + Delta Engine (Memory Layer)
    
    Responsibilities:
    - Store processed intents with results
    - Perform semantic similarity search
    - Apply Delta compression (store only differences)
    """
    
    def __init__(self):
        # In-memory cache (production: use Redis/Qdrant)
        self.cache: Dict[str, MemoryHit] = {}
        # SDK integration: MemoryDeltaEngine for live compression tracking (Gap 5)
        self.delta_engine = MemoryDeltaEngine()
        self._tick: int = 0  # monotonic tick counter for delta recording
        logger.info("MemoryLayer initialized (MemoryDeltaEngine active)")

    @property
    def compression_ratio(self) -> float:
        """Live compression ratio from MemoryDeltaEngine (replaces hardcoded 3.74)."""
        cr = self.delta_engine.compute_compression_ratio()
        if cr <= 0.0 or cr >= 1.0:
            return 3.74  # fallback before enough data is recorded
        # cr is 0-1 fractional compression; convert to multiplier form
        return round(1.0 / (1.0 - cr), 2)
    
    async def recall(self, packet: JITNAPacket) -> Optional[MemoryHit]:
        """
        Search for similar intent in memory
        
        Args:
            packet: Input JITNA packet
        
        Returns:
            MemoryHit if found with confidence > 0.95, else None
        """
        intent_hash = packet.compute_hash()
        
        # Exact match first
        if intent_hash in self.cache:
            hit = self.cache[intent_hash]
            hit.access_count += 1
            hit.last_accessed = datetime.now()
            logger.info(f"Memory HIT (exact): {packet.intent[:50]}... (accessed {hit.access_count}x)")
            return hit
        
        # Semantic similarity search (production: use vector DB)
        # For MVP: simple substring matching
        for cached_hash, cached_hit in self.cache.items():
            # This is simplified - production uses embeddings
            similarity = self._calculate_similarity(packet.intent, cached_hit.result.get("original_intent", ""))
            if similarity > 0.95:
                cached_hit.confidence = similarity
                cached_hit.access_count += 1
                cached_hit.last_accessed = datetime.now()
                logger.info(f"Memory HIT (semantic): similarity={similarity:.2f}")
                return cached_hit
        
        logger.info("Memory MISS: will compute fresh")
        return None
    
    def _calculate_similarity(self, intent1: str, intent2: str) -> float:
        """Simple similarity calculation (MVP)"""
        # Production: use sentence-transformers embeddings
        words1 = set(intent1.lower().split())
        words2 = set(intent2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    async def store(self, packet: JITNAPacket, result: Dict[str, Any]) -> None:
        """
        Store result in memory with Delta compression
        
        Args:
            packet: Original JITNA packet
            result: Computation result
        """
        intent_hash = packet.intent_hash or packet.compute_hash()
        original_size = len(json.dumps(result))

        # Register this intent in the DeltaEngine if not already tracked (Gap 5)
        if intent_hash not in self.delta_engine.baseline_states:
            self.delta_engine.register_agent(
                agent_id=intent_hash,
                initial_intent=NPCIntentType.DISCOVER,
                initial_resources={"size_bytes": float(original_size)},
            )

        # Record a delta for this store operation
        self._tick += 1
        self.delta_engine.record_delta(
            agent_id=intent_hash,
            tick=self._tick,
            intent_type=NPCIntentType.DISCOVER,
            action_type="process",
            outcome="success",
            resource_changes={"size_bytes": float(original_size)},
            extra_changes={"intent_preview": packet.intent[:50]},
        )

        # Compute compressed size via live compression ratio
        ratio = self.compression_ratio  # uses delta_engine under the hood
        compressed_size = int(original_size / max(ratio, 1.0))

        memory_hit = MemoryHit(
            intent_hash=intent_hash,
            result={
                "original_intent": packet.intent,
                "output": result
            },
            confidence=1.0,
            created_at=datetime.now(),
            access_count=0,
            last_accessed=datetime.now(),
            delta_size=compressed_size
        )

        self.cache[intent_hash] = memory_hit
        logger.info(
            f"Stored in memory: {intent_hash[:16]}... "
            f"(delta tick={self._tick}, {original_size} → {compressed_size} bytes, "
            f"ratio={ratio:.2f}x)"
        )


class SpecialistExecutor:
    """
    Pillar 3: Specialist Execution (Compute Layer)

    Routes intent to the appropriate HexaCore specialist model for processing.
    Integration: HexaCoreRegistry from signedai.core.registry (Gap 7)
    """

    # Maps intent keywords → HexaCoreRole for model selection
    _TASK_ROLE_MAP: Dict[str, HexaCoreRole] = {
        # Regional check first (most specific)
        "thai":      HexaCoreRole.REGIONAL_CORE,
        "ภาษา":      HexaCoreRole.REGIONAL_CORE,
        "viet":      HexaCoreRole.REGIONAL_CORE,
        "indo":      HexaCoreRole.REGIONAL_CORE,
        "korean":    HexaCoreRole.REGIONAL_CORE,
        "japanese":  HexaCoreRole.REGIONAL_CORE,
        "chinese":   HexaCoreRole.REGIONAL_CORE,
        # Builder roles
        "code":      HexaCoreRole.LEAD_BUILDER,
        "program":   HexaCoreRole.LEAD_BUILDER,
        "debug":     HexaCoreRole.LEAD_BUILDER,
        # Specialist roles
        "analyze":   HexaCoreRole.SPECIALIST,
        "finance":   HexaCoreRole.SPECIALIST,
        "health":    HexaCoreRole.SPECIALIST,
        # Librarian roles
        "research":  HexaCoreRole.LIBRARIAN,
        "document":  HexaCoreRole.LIBRARIAN,
        "rag":       HexaCoreRole.LIBRARIAN,
        # Humanizer roles
        "translate":  HexaCoreRole.HUMANIZER,
        "creative":  HexaCoreRole.HUMANIZER,
    }

    def __init__(self):
        self.specialists: Dict[str, Any] = {}
        # SDK integration: HexaCoreRegistry for dynamic model routing (Gap 7)
        self.registry = HexaCoreRegistry()
        logger.info("SpecialistExecutor initialized (HexaCoreRegistry active)")

    def _select_model(self, intent: str) -> tuple[str, HexaCoreRole]:
        """Select model ID + role from HexaCoreRegistry based on intent content."""
        intent_lower = intent.lower()
        for keyword, role in self._TASK_ROLE_MAP.items():
            if keyword in intent_lower:
                if role == HexaCoreRole.REGIONAL_CORE:
                    try:
                        from core.regional_adapter.regional_adapter import get_regional_router
                        _TASK_REGIONAL_MAP = {
                            "thai": ("th", "TH"),
                            "ภาษา": ("th", "TH"),
                            "viet": ("vi", "VN"),
                            "indo": ("id", "ID"),
                            "korean": ("ko", "KR"),
                            "japanese": ("ja", "JP"),
                            "chinese": ("zh", "CN"),
                        }
                        lang, reg = _TASK_REGIONAL_MAP.get(keyword, ("en", "US"))
                        router = get_regional_router()
                        entry = router.resolve(lang, reg)
                        return entry.model_id, role
                    except Exception:
                        pass
                model_id = self.registry.get_model_id(role)
                return model_id, role

        # If no keyword matches, try dynamic language detection for regional LLMs
        try:
            from core.regional_adapter.regional_adapter import detect_language, resolve_model_for_text
            detected = detect_language(intent)
            if detected.code in ["th", "ja", "ko", "zh", "vi", "id", "fil", "ms"] and detected.confidence >= 0.5:
                entry = resolve_model_for_text(intent)
                return entry.model_id, HexaCoreRole.REGIONAL_CORE
        except Exception:
            pass

        # Default: SUPREME_ARCHITECT for complex / unclassified intents
        role = HexaCoreRole.SUPREME_ARCHITECT
        return self.registry.get_model_id(role), role

    async def execute(self, packet: JITNAPacket) -> Dict[str, Any]:
        """
        Execute intent using the HexaCore-selected specialist model.

        Args:
            packet: JITNA packet with intent

        Returns:
            Result from specialist processing
        """
        model_id, role = self._select_model(packet.intent)

        # In production: send packet.intent to model_id via OpenRouter API
        # For reference implementation: simulate processing
        await asyncio.sleep(0.1)  # Simulate API latency

        result = {
            "intent": packet.intent,
            "processed_at": datetime.now().isoformat(),
            "specialist": model_id,
            "specialist_role": role.value,
            "output": f"Processed: {packet.intent}",
            "confidence": 0.95,
        }

        logger.info(f"Specialist executed via {role.value} ({model_id}): {packet.intent[:50]}...")
        return result


class TOONPayloadOptimizer:
    """
    Pillar 2.5: ALGO-42 — TOON Payload Optimization Layer

    Inserted between Delta Engine (memory recall) and Specialist Execution.
    Converts structured context payloads from JSON-style dicts into
    TOON (Token-Oriented Object Notation) before they are injected into
    the LLM context window.

    Benefits:
      - 40-50% token reduction vs JSON
      - Removes syntax noise ({}, [], "") that degrades Attention quality
      - Improves FDIA Intent precision (I) by reducing noise
      - Compatible with round-trip deserialization back to dict

    Pipeline position:
      1. FDIA Validates → 2. Memory Recall (Delta) → **2.5 TOON Optimize** →
      3. Specialist Execute → 4. SignedAI Verify → 5. Commit
    """

    def __init__(self) -> None:
        self._enabled = True
        self._stats = {
            "total_optimized": 0,
            "total_json_chars": 0,
            "total_toon_chars": 0,
        }
        logger.info("TOONPayloadOptimizer initialized (ALGO-42 active)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def optimize(self, context: Dict[str, Any]) -> str:
        """
        Convert a context dict to TOON format for LLM consumption.

        Args:
            context: Structured data dict (memory recall, delta state, etc.)

        Returns:
            TOON-formatted string (compact, token-efficient)
        """
        if not self._enabled:
            import json
            return json.dumps(context, ensure_ascii=False, default=str)

        try:
            from rct_control_plane.toon_formatter import (
                toon_serialize,
                toon_token_savings_estimate,
            )

            toon_str = toon_serialize(context)

            # Track savings statistics
            stats = toon_token_savings_estimate(context)
            self._stats["total_optimized"] += 1
            self._stats["total_json_chars"] += stats["json_chars"]
            self._stats["total_toon_chars"] += stats["toon_chars"]

            logger.info(
                f"TOON optimized: {stats['json_chars']} → {stats['toon_chars']} chars "
                f"({stats['savings_pct']}% savings)"
            )
            return toon_str

        except ImportError:
            logger.warning("toon_formatter not available — falling back to JSON")
            import json
            return json.dumps(context, ensure_ascii=False, default=str)

    def get_stats(self) -> Dict[str, Any]:
        """Return cumulative optimization statistics."""
        total_json = self._stats["total_json_chars"]
        total_toon = self._stats["total_toon_chars"]
        savings_pct = (
            ((total_json - total_toon) / total_json * 100)
            if total_json > 0
            else 0.0
        )
        return {
            "total_optimized": self._stats["total_optimized"],
            "total_json_chars": total_json,
            "total_toon_chars": total_toon,
            "cumulative_savings_pct": round(savings_pct, 1),
        }

class SignedAIVerifier:
    """
    Pillar 4: SignedAI Verification (Verification Layer)

    Multi-LLM consensus voting to verify correctness.
    Integration: Model IDs sourced from HexaCoreRegistry (Gap 7)
    """

    def __init__(self):
        # SDK integration: use HexaCoreRegistry model IDs (Gap 7)
        _reg = HexaCoreRegistry()
        self.models = [
            _reg.get_model_id(HexaCoreRole.SUPREME_ARCHITECT),   # claude-opus-4.6
            _reg.get_model_id(HexaCoreRole.LEAD_BUILDER),        # kimi-k2.5
            _reg.get_model_id(HexaCoreRole.SPECIALIST),          # gemini-3-flash
        ]
        self.consensus_threshold = 0.67  # 2 out of 3
        logger.info(f"SignedAIVerifier initialized with models: {self.models}")
        logger.info("SignedAIVerifier initialized")
    
    async def verify(
        self, 
        result: Dict[str, Any],
        strict_mode: bool = False
    ) -> tuple[bool, float]:
        """
        Verify result using multi-model consensus
        
        Args:
            result: Result to verify
            strict_mode: Require 100% consensus
        
        Returns:
            (passed, confidence_score)
        """
        # In production: actually query multiple LLMs
        # For MVP: simulate verification
        
        await asyncio.sleep(0.05)  # Simulate API calls
        
        # Simulate voting
        votes = [True, True, True]  # All models agree (simplified)
        confidence = sum(votes) / len(votes)
        
        threshold = 1.0 if strict_mode else self.consensus_threshold
        passed = confidence >= threshold
        
        logger.info(f"Verification: {confidence*100:.0f}% consensus (threshold: {threshold*100:.0f}%)")
        return passed, confidence


class EvolutionCommitter:
    """
    Pillar 5: Evolution Committer (Feedback Layer)
    
    Commits verified knowledge back to memory for future use
    """
    
    def __init__(self, memory: MemoryLayer):
        self.memory = memory
        logger.info("EvolutionCommitter initialized")
    
    async def commit(
        self, 
        packet: JITNAPacket, 
        result: Dict[str, Any],
        verification_score: float
    ) -> None:
        """
        Commit verified result to memory
        
        Args:
            packet: Original JITNA packet
            result: Verified result
            verification_score: Confidence from SignedAI
        """
        # Add metadata
        result["verification_score"] = verification_score
        result["committed_at"] = datetime.now().isoformat()
        
        # Store in memory
        await self.memory.store(packet, result)
        
        logger.info(f"Knowledge committed: score={verification_score:.2f}")


class IntentLoopEngine:
    """
    The Complete Intent Loop: Evolutionary Compound Intelligence
    
    Workflow:
    1. FDIA validates input
    2. Memory checks for cached wisdom
    3. Specialist computes if needed
    4. SignedAI verifies result
    5. Evolution commits knowledge
    
    Result: System that gets smarter, faster, cheaper over time
    """
    
    def __init__(self):
        self.gatekeeper = FDIAGatekeeper()
        self.memory = MemoryLayer()
        self.toon_optimizer = TOONPayloadOptimizer()  # ALGO-42
        self.executor = SpecialistExecutor()
        self.verifier = SignedAIVerifier()
        self.committer = EvolutionCommitter(self.memory)
        
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "verification_failures": 0
        }
        
        logger.info("IntentLoopEngine initialized - ready for evolution (ALGO-42 TOON active)")
    
    async def process(self, packet: JITNAPacket) -> IntentResult:
        """
        Main processing loop
        
        Args:
            packet: JITNA packet with intent
        
        Returns:
            IntentResult with output and metadata
        """
        start_time = datetime.now()
        self.metrics["total_requests"] += 1
        
        try:
            # Step 1: FDIA Validation
            await self.gatekeeper.validate(packet)
            
            # Step 2: Memory Lookup (The Fast Path)
            cached = await self.memory.recall(packet)
            
            if cached and cached.confidence > 0.95:
                # Cache hit - return immediately
                self.metrics["cache_hits"] += 1
                latency = (datetime.now() - start_time).total_seconds() * 1000
                
                logger.info(f"⚡ Fast path: {latency:.1f}ms (cache hit)")
                
                return IntentResult(
                    intent_hash=packet.compute_hash(),
                    state=IntentState.COMPLETED,
                    output=cached.result,
                    latency_ms=latency,
                    cache_hit=True,
                    verification_passed=True,
                    metadata={
                        "access_count": cached.access_count,
                        "original_created": cached.created_at.isoformat()
                    }
                )
            
            # Step 3: TOON Optimize Context (ALGO-42) → reduces tokens 40-50%
            context_for_llm = {
                "intent": packet.intent,
                "priority": packet.priority,
                "cached_memory": cached.result if cached else None,
            }
            toon_context = self.toon_optimizer.optimize(context_for_llm)
            logger.info(f"TOON context prepared ({len(toon_context)} chars)")
            
            # Step 4: Compute (The Slow Path)
            self.metrics["cache_misses"] += 1
            result = await self.executor.execute(packet)
            
            # Step 4: Verification
            passed, confidence = await self.verifier.verify(result)
            
            if not passed:
                self.metrics["verification_failures"] += 1
                logger.error("Verification failed - result rejected")
                return IntentResult(
                    intent_hash=packet.compute_hash(),
                    state=IntentState.FAILED,
                    error="Failed verification consensus",
                    latency_ms=(datetime.now() - start_time).total_seconds() * 1000
                )
            
            # Step 5: Commit to Memory (async, don't block response)
            asyncio.create_task(self.committer.commit(packet, result, confidence))
            
            latency = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"🧠 Slow path: {latency:.1f}ms (computed fresh)")
            
            return IntentResult(
                intent_hash=packet.compute_hash(),
                state=IntentState.COMPLETED,
                output=result,
                latency_ms=latency,
                cache_hit=False,
                verification_passed=True,
                metadata={"verification_confidence": confidence}
            )
            
        except SecurityViolation as e:
            logger.error(f"Security violation: {e}")
            return IntentResult(
                intent_hash=packet.compute_hash(),
                state=IntentState.FAILED,
                error=str(e),
                latency_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
        except Exception as e:
            logger.error(f"Processing error: {e}")
            return IntentResult(
                intent_hash=packet.compute_hash(),
                state=IntentState.FAILED,
                error=str(e),
                latency_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get system metrics"""
        cache_hit_rate = 0.0
        if self.metrics["total_requests"] > 0:
            cache_hit_rate = self.metrics["cache_hits"] / self.metrics["total_requests"]
        
        return {
            "total_requests": self.metrics["total_requests"],
            "cache_hits": self.metrics["cache_hits"],
            "cache_misses": self.metrics["cache_misses"],
            "cache_hit_rate": f"{cache_hit_rate * 100:.1f}%",
            "verification_failures": self.metrics["verification_failures"],
            "memory_size": len(self.memory.cache),
            "compression_ratio": f"{self.memory.compression_ratio}x",
            "delta_engine_agents": self.memory.delta_engine.registered_agent_count(),
            "delta_engine_deltas": self.memory.delta_engine.total_delta_count(),
            "verifier_models": self.verifier.models,
        }


class SecurityViolation(Exception):
    """Raised when intent violates FDIA rules"""
    pass


# Example usage
async def demo():
    print("=" * 80)
    print("Intent Loop Engine: Evolutionary Compound Intelligence Demo")
    print("=" * 80)
    print()
    
    engine = IntentLoopEngine()
    
    # Test 1: Cold start (first time)
    print("Test 1: Cold Start (First Request)")
    print("-" * 80)
    
    packet1 = JITNAPacket(
        intent="Calculate tax for income 1,000,000 THB",
        context={"income": 1000000, "country": "TH"},
        user_id="user_001"
    )
    
    result1 = await engine.process(packet1)
    print(f"Intent: {packet1.intent}")
    print(f"State: {result1.state.value}")
    print(f"Latency: {result1.latency_ms:.1f}ms")
    print(f"Cache Hit: {result1.cache_hit}")
    print(f"Output: {result1.output}")
    print()
    
    # Test 2: Warm recall (second time - same intent)
    print("Test 2: Warm Recall (Repeated Request)")
    print("-" * 80)
    
    packet2 = JITNAPacket(
        intent="Calculate tax for income 1,000,000 THB",
        context={"income": 1000000, "country": "TH"},
        user_id="user_001"
    )
    
    result2 = await engine.process(packet2)
    print(f"Intent: {packet2.intent}")
    print(f"State: {result2.state.value}")
    print(f"Latency: {result2.latency_ms:.1f}ms ⚡ (should be much faster!)")
    print(f"Cache Hit: {result2.cache_hit} ✓")
    print(f"Speedup: {result1.latency_ms / result2.latency_ms:.1f}x faster")
    print()
    
    # Test 3: Security violation
    print("Test 3: Security Check (Forbidden Intent)")
    print("-" * 80)
    
    packet3 = JITNAPacket(
        intent="Hack into database and exploit vulnerabilities",
        user_id="user_002"
    )
    
    result3 = await engine.process(packet3)
    print(f"Intent: {packet3.intent}")
    print(f"State: {result3.state.value}")
    print(f"Error: {result3.error}")
    print()
    
    # Test 4: Multiple requests to show evolution
    print("Test 4: Evolution Demo (10 requests)")
    print("-" * 80)
    
    intents = [
        "Calculate tax for 500,000 THB",
        "Calculate tax for 1,000,000 THB",  # Repeat
        "Calculate tax for 2,000,000 THB",
        "Calculate tax for 1,000,000 THB",  # Repeat
        "Calculate tax for 500,000 THB",    # Repeat
    ]
    
    print(f"{'Request':<5} {'Intent':<40} {'Latency':<12} {'Cache'}")
    print("-" * 80)
    
    for i, intent in enumerate(intents, 1):
        packet = JITNAPacket(intent=intent)
        result = await engine.process(packet)
        cache_status = "HIT ⚡" if result.cache_hit else "MISS"
        print(f"{i:<5} {intent[:38]:<40} {result.latency_ms:<12.1f} {cache_status}")
    
    print()
    
    # Metrics
    print("System Metrics:")
    print("-" * 80)
    metrics = engine.get_metrics()
    for key, value in metrics.items():
        print(f"  {key.replace('_', ' ').title()}: {value}")
    print()
    
    print("=" * 80)
    print("🎉 Evolution Proof:")
    print("   - First request: ~100ms (cold start)")
    print("   - Repeated requests: <10ms (warm recall)")
    print(f"   - Cache hit rate: {metrics['cache_hit_rate']}")
    print(f"   - Cost reduction: ~{(1 - float(metrics['cache_hit_rate'].strip('%')) / 100) * 100:.0f}% savings")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(demo())

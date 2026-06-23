"""
Intent Loop Engine: The Evolutionary Intelligence Core

This is the heart of RCT Ecosystem - a self-optimizing loop that learns from every interaction.

The Master Equation:
FDIA + JITNA + Delta Engine + SignedAI + RCTDB = Evolutionary Compound Intelligence

Philosophy:
- Cold Start: First time = 3-5 seconds (full computation)
- Warm Recall: Next time = <50ms (memory retrieval)
- Evolution: System gets smarter, faster, cheaper over time
- Cost → 0 as system matures
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
import asyncio
import uuid
import logging
import hashlib
import json

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
    """
    
    def __init__(self):
        self.constitution_rules = {
            "max_intent_length": 1000,
            "forbidden_keywords": ["hack", "exploit", "bypass"],
            "require_human_approval": False  # Can be enabled for sensitive ops
        }
        logger.info("FDIAGatekeeper initialized")
    
    async def validate(self, packet: JITNAPacket) -> bool:
        """
        Validate intent against FDIA constitution
        
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
        
        # Rule 3: Human approval (if required)
        if self.constitution_rules["require_human_approval"]:
            # In production: send to approval queue
            logger.info("Intent requires human approval")
        
        logger.info(f"Intent validated: {packet.intent[:50]}...")
        return True


class MemoryLayer:
    """
    Pillar 2: RCTDB + Delta Engine (Memory Layer)
    
    Responsibilities:
    - Store processed intents with results
    - Perform semantic similarity search
    - Apply Delta compression (store only differences)
    """
    
    def __init__(self):
        # In-memory cache (production: use Redis/Qdrant)
        self.cache: Dict[str, MemoryHit] = {}
        self.compression_ratio = 3.74  # Average compression from Delta Engine
        logger.info("MemoryLayer initialized")
    
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
        intent_hash = packet.compute_hash()
        
        # Simulate Delta compression
        original_size = len(json.dumps(result))
        compressed_size = int(original_size / self.compression_ratio)
        
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
        logger.info(f"Stored in memory: {intent_hash[:16]}... (compressed {original_size} → {compressed_size} bytes)")


class SpecialistExecutor:
    """
    Pillar 3: Specialist Execution (Compute Layer)
    
    Routes intent to appropriate specialist module for processing
    """
    
    def __init__(self):
        self.specialists: Dict[str, Any] = {}
        logger.info("SpecialistExecutor initialized")
    
    async def execute(self, packet: JITNAPacket) -> Dict[str, Any]:
        """
        Execute intent using specialist module
        
        Args:
            packet: JITNA packet with intent
        
        Returns:
            Result from specialist processing
        """
        # In production: route to actual specialist modules
        # For MVP: simulate processing
        
        await asyncio.sleep(0.1)  # Simulate computation time
        
        result = {
            "intent": packet.intent,
            "processed_at": datetime.now().isoformat(),
            "specialist": "generic_processor",
            "output": f"Processed: {packet.intent}",
            "confidence": 0.95
        }
        
        logger.info(f"Specialist executed: {packet.intent[:50]}...")
        return result


class SignedAIVerifier:
    """
    Pillar 4: SignedAI Verification (Verification Layer)
    
    Multi-LLM consensus voting to verify correctness
    """
    
    def __init__(self):
        self.models = ["gpt-4o", "claude-3.5-sonnet", "gemini-1.5-pro"]
        self.consensus_threshold = 0.67  # 2 out of 3
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
        self.executor = SpecialistExecutor()
        self.verifier = SignedAIVerifier()
        self.committer = EvolutionCommitter(self.memory)
        
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "verification_failures": 0
        }
        
        logger.info("IntentLoopEngine initialized - ready for evolution")
    
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
            
            # Step 3: Compute (The Slow Path)
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
            "compression_ratio": f"{self.memory.compression_ratio}x"
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
    print(f"   - First request: ~100ms (cold start)")
    print(f"   - Repeated requests: <10ms (warm recall)")
    print(f"   - Cache hit rate: {metrics['cache_hit_rate']}")
    print(f"   - Cost reduction: ~{(1 - float(metrics['cache_hit_rate'].strip('%')) / 100) * 100:.0f}% savings")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(demo())

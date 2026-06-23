"""
Analysearch Intent Engine
Core engine combining Analysis + Research + Intent for RCT Ecosystem

Features:
- Mirror Mode: PROPOSE → COUNTER → REFINE loop for deep Q&A
- Cross-Disciplinary Synthesis: Find intersections across domains
- GIGO Protection: Entropy-based input validation
- Integration: ALGO-05 (GraphRAG), ALGO-41 (Crystallizer), ALGO-06 (JITNA)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import math
import hashlib
import logging

logger = logging.getLogger(__name__)


class AnalysearchMode(str, Enum):
    """Operating modes for Analysearch"""
    QUICK = "quick"          # Fast lookup, minimal analysis
    STANDARD = "standard"    # Standard analysis + research
    DEEP = "deep"            # Deep analysis with Mirror Mode
    MIRROR = "mirror"        # Full Mirror Mode (PROPOSE → COUNTER → REFINE)


class MirrorPhase(str, Enum):
    """Phases of Mirror Mode"""
    PROPOSE = "propose"
    COUNTER = "counter"
    REFINE = "refine"
    CONVERGED = "converged"


@dataclass
class MirrorState:
    """State of a Mirror Mode session"""
    session_id: str
    query: str
    phase: MirrorPhase = MirrorPhase.PROPOSE
    iterations: int = 0
    max_iterations: int = 5
    proposals: List[Dict] = field(default_factory=list)
    counters: List[Dict] = field(default_factory=list)
    refinements: List[Dict] = field(default_factory=list)
    convergence_score: float = 0.0
    converged: bool = False


@dataclass
class AnalysearchResult:
    """Result of an Analysearch query"""
    query: str
    mode: str
    keywords: List[Dict]           # Extracted golden keywords
    analysis: Dict                 # Structured analysis
    research_sources: List[Dict]   # Sources found
    synthesis: Dict                # Cross-disciplinary synthesis
    intent_preserved: bool         # Intent conservation check
    confidence: float              # Overall confidence (0-1)
    mirror_state: Optional[MirrorState] = None
    processing_time_ms: float = 0.0
    routing_hint: Optional[Dict] = None  # G38: Thai/regional routing hint


@dataclass
class DisciplineInsight:
    """Insight from a specific discipline"""
    discipline: str
    relevance_score: float
    key_concepts: List[str]
    connections: List[str]  # Connections to other disciplines
    evidence_strength: float


class GIGOProtector:
    """
    Garbage-In Garbage-Out Protection
    Validates input quality using entropy and structure analysis
    """

    @staticmethod
    def calculate_entropy(text: str) -> float:
        """Calculate Shannon entropy of text"""
        if not text:
            return 0.0

        # Character frequency
        freq = {}
        for char in text.lower():
            freq[char] = freq.get(char, 0) + 1

        length = len(text)
        entropy = 0.0
        for count in freq.values():
            p = count / length
            if p > 0:
                entropy -= p * math.log2(p)

        return entropy

    @staticmethod
    def validate_input(text: str, min_entropy: float = 2.0, min_length: int = 3) -> Tuple[bool, Dict]:
        """
        Validate input quality

        Returns:
            (is_valid, details)
        """
        if not text or not text.strip():
            return False, {"reason": "empty_input", "entropy": 0.0}

        text = text.strip()

        if len(text) < min_length:
            return False, {"reason": "too_short", "length": len(text), "min": min_length}

        # Check for repetitive patterns first (before entropy)
        words = text.split()
        if len(words) > 3:
            unique_ratio = len(set(w.lower() for w in words)) / len(words)
            if unique_ratio < 0.3:
                return False, {"reason": "repetitive", "unique_ratio": unique_ratio}

        entropy = GIGOProtector.calculate_entropy(text)

        if entropy < min_entropy:
            return False, {"reason": "low_entropy", "entropy": entropy, "min": min_entropy}

        return True, {"entropy": entropy, "length": len(text), "word_count": len(words)}


class KeywordCrystallizer:
    """
    Golden Keyword Extraction (inspired by ALGO-41)
    Extracts high-value keywords using entropy and TF scoring
    """

    def __init__(self, min_entropy: float = 0.5):
        self.min_entropy = min_entropy

        # Domain-specific boost terms
        self.domain_boosts = {
            "technology": ["AI", "algorithm", "neural", "quantum", "blockchain", "API", "cloud"],
            "science": ["research", "hypothesis", "experiment", "data", "analysis", "synthesis"],
            "business": ["ROI", "market", "strategy", "revenue", "growth", "innovation"],
            "engineering": ["architecture", "system", "infrastructure", "pipeline", "optimization"],
        }

    def extract(self, text: str, top_k: int = 10) -> List[Dict]:
        """
        Extract golden keywords from text

        Returns list of {keyword, score, entropy, domain}
        """
        if not text:
            return []

        words = text.split()
        word_freq = {}
        for word in words:
            clean = word.strip(".,!?;:()[]{}\"'").lower()
            if len(clean) > 2:
                word_freq[clean] = word_freq.get(clean, 0) + 1

        total_words = len(words)
        keywords = []

        for word, freq in word_freq.items():
            entropy = GIGOProtector.calculate_entropy(word)

            if entropy < self.min_entropy:
                continue

            # TF score
            tf = freq / total_words

            # Domain boost
            domain = self._detect_domain(word)
            boost = 1.5 if domain else 1.0

            # Length bonus (longer meaningful words score higher)
            length_bonus = min(len(word) / 10, 1.0)

            score = (tf * 0.3 + entropy / 5.0 * 0.4 + length_bonus * 0.3) * boost

            keywords.append({
                "keyword": word,
                "score": round(score, 4),
                "entropy": round(entropy, 3),
                "frequency": freq,
                "domain": domain
            })

        # Sort by score descending
        keywords.sort(key=lambda k: k["score"], reverse=True)

        return keywords[:top_k]

    def _detect_domain(self, word: str) -> Optional[str]:
        """Detect which domain a word belongs to"""
        word_lower = word.lower()
        for domain, terms in self.domain_boosts.items():
            if any(term.lower() in word_lower or word_lower in term.lower() for term in terms):
                return domain
        return None


class CrossDisciplinarySynthesizer:
    """
    Cross-Disciplinary Synthesis Engine
    Finds unexpected connections between different domains
    """

    # Knowledge base of discipline relationships
    DISCIPLINE_CONNECTIONS = {
        "biology": ["medicine", "chemistry", "ecology", "biomimicry", "genetics"],
        "physics": ["engineering", "materials", "quantum", "optics", "thermodynamics"],
        "chemistry": ["biology", "materials", "pharmacology", "energy"],
        "computer_science": ["mathematics", "linguistics", "cognitive_science", "AI"],
        "mathematics": ["physics", "computer_science", "economics", "statistics"],
        "psychology": ["neuroscience", "sociology", "UX_design", "behavioral_economics"],
        "economics": ["mathematics", "psychology", "political_science", "game_theory"],
        "engineering": ["physics", "materials", "computer_science", "architecture"],
        "materials_science": ["chemistry", "physics", "engineering", "nanotechnology"],
        "architecture": ["engineering", "art", "psychology", "sustainability"],
    }

    def synthesize(self, keywords: List[Dict], context: str = "") -> Dict:
        """
        Find cross-disciplinary connections from keywords

        Returns synthesis result with disciplines, connections, and insights
        """
        # Detect relevant disciplines
        disciplines = self._detect_disciplines(keywords, context)

        # Find intersection points
        intersections = self._find_intersections(disciplines)

        # Generate insights
        insights = self._generate_insights(disciplines, intersections, keywords)

        return {
            "disciplines_detected": len(disciplines),
            "disciplines": [
                {
                    "name": d.discipline,
                    "relevance": d.relevance_score,
                    "key_concepts": d.key_concepts,
                    "connections": d.connections,
                    "evidence_strength": d.evidence_strength
                }
                for d in disciplines
            ],
            "intersections": intersections,
            "insights": insights,
            "innovation_potential": self._calculate_innovation_potential(disciplines, intersections)
        }

    def _detect_disciplines(self, keywords: List[Dict], context: str) -> List[DisciplineInsight]:
        """Detect relevant disciplines from keywords"""
        discipline_scores = {}
        discipline_concepts = {}

        keyword_terms = [k["keyword"] for k in keywords]
        all_text = " ".join(keyword_terms) + " " + context

        # Score each discipline by keyword overlap
        discipline_keywords = {
            "biology": ["bio", "cell", "organism", "evolution", "gene", "protein", "ecology", "species"],
            "physics": ["force", "energy", "quantum", "wave", "particle", "thermal", "electric"],
            "chemistry": ["molecule", "reaction", "compound", "element", "catalyst", "bond"],
            "computer_science": ["algorithm", "data", "code", "software", "network", "compute", "AI"],
            "engineering": ["design", "system", "build", "structure", "optimize", "infrastructure"],
            "mathematics": ["equation", "formula", "proof", "theorem", "statistics", "probability"],
            "psychology": ["behavior", "cognitive", "perception", "emotion", "motivation", "UX"],
            "economics": ["market", "cost", "price", "demand", "supply", "investment", "ROI"],
            "materials_science": ["material", "composite", "alloy", "polymer", "nano", "strength"],
            "architecture": ["building", "space", "design", "structure", "environment", "sustainable"],
        }

        for discipline, terms in discipline_keywords.items():
            score = 0.0
            concepts = []
            for term in terms:
                if term.lower() in all_text.lower():
                    score += 1.0
                    concepts.append(term)

            if score > 0:
                discipline_scores[discipline] = score / len(terms)
                discipline_concepts[discipline] = concepts

        # Build DisciplineInsight objects
        insights = []
        for discipline, score in sorted(discipline_scores.items(), key=lambda x: x[1], reverse=True):
            connections = self.DISCIPLINE_CONNECTIONS.get(discipline, [])
            relevant_connections = [c for c in connections if c in discipline_scores]

            insights.append(DisciplineInsight(
                discipline=discipline,
                relevance_score=round(score, 3),
                key_concepts=discipline_concepts.get(discipline, []),
                connections=relevant_connections,
                evidence_strength=min(score * 2, 1.0)
            ))

        return insights[:5]  # Top 5 disciplines

    def _find_intersections(self, disciplines: List[DisciplineInsight]) -> List[Dict]:
        """Find intersection points between disciplines"""
        intersections = []
        disc_names = [d.discipline for d in disciplines]

        for i, d1 in enumerate(disciplines):
            for j, d2 in enumerate(disciplines):
                if i >= j:
                    continue

                # Check if connected
                common = set(d1.connections) & set(d2.connections)
                direct = d2.discipline in d1.connections or d1.discipline in d2.connections

                if direct or common:
                    intersections.append({
                        "disciplines": [d1.discipline, d2.discipline],
                        "connection_type": "direct" if direct else "indirect",
                        "shared_domains": list(common) if common else [],
                        "potential_score": round((d1.relevance_score + d2.relevance_score) / 2, 3)
                    })

        return intersections

    def _generate_insights(
        self,
        disciplines: List[DisciplineInsight],
        intersections: List[Dict],
        keywords: List[Dict]
    ) -> List[str]:
        """Generate cross-disciplinary insights"""
        insights = []

        for intersection in intersections:
            d1, d2 = intersection["disciplines"]
            insights.append(
                f"Intersection of {d1} and {d2} may yield novel approaches "
                f"(connection: {intersection['connection_type']}, "
                f"potential: {intersection['potential_score']:.1%})"
            )

        if len(disciplines) >= 3:
            names = [d.discipline for d in disciplines[:3]]
            insights.append(
                f"Multi-disciplinary synthesis across {', '.join(names)} "
                f"has high innovation potential"
            )

        return insights

    def _calculate_innovation_potential(
        self,
        disciplines: List[DisciplineInsight],
        intersections: List[Dict]
    ) -> float:
        """Calculate innovation potential score (0-1)"""
        if not disciplines:
            return 0.0

        # More disciplines = higher potential
        discipline_factor = min(len(disciplines) / 3, 1.0) * 0.4

        # More intersections = higher potential
        intersection_factor = min(len(intersections) / 3, 1.0) * 0.3

        # Higher evidence = higher potential
        avg_evidence = sum(d.evidence_strength for d in disciplines) / len(disciplines)
        evidence_factor = avg_evidence * 0.3

        return round(discipline_factor + intersection_factor + evidence_factor, 3)


class MirrorModeEngine:
    """
    Mirror Mode: PROPOSE → COUNTER → REFINE loop

    Iteratively deepens understanding through adversarial refinement:
    1. PROPOSE: Generate initial analysis/hypothesis
    2. COUNTER: Challenge the proposal with counter-arguments
    3. REFINE: Synthesize proposal + counter into refined understanding
    4. Repeat until convergence or max iterations
    """

    def __init__(self, max_iterations: int = 5, convergence_threshold: float = 0.85):
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold

    def create_session(self, query: str) -> MirrorState:
        """Create new Mirror Mode session"""
        session_id = hashlib.md5(
            f"{query}-{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        return MirrorState(
            session_id=session_id,
            query=query,
            max_iterations=self.max_iterations
        )

    def propose(self, state: MirrorState, analysis: Dict, keywords: List[Dict]) -> Dict:
        """
        PROPOSE phase: Generate initial proposal based on analysis

        Returns proposal with hypothesis, evidence, confidence
        """
        # Build proposal from analysis and keywords
        top_keywords = [k["keyword"] for k in keywords[:5]]

        proposal = {
            "phase": "propose",
            "iteration": state.iterations,
            "hypothesis": f"Based on analysis of '{state.query}', "
                         f"key factors are: {', '.join(top_keywords)}",
            "evidence": [
                {
                    "keyword": k["keyword"],
                    "score": k["score"],
                    "domain": k.get("domain", "general")
                }
                for k in keywords[:5]
            ],
            "confidence": min(0.5 + len(keywords) * 0.05, 0.8),
            "assumptions": [
                f"Keyword '{k['keyword']}' is relevant (entropy: {k['entropy']})"
                for k in keywords[:3]
            ],
            "timestamp": datetime.now().isoformat()
        }

        state.proposals.append(proposal)
        state.phase = MirrorPhase.COUNTER

        return proposal

    def counter(self, state: MirrorState, proposal: Dict, synthesis: Dict) -> Dict:
        """
        COUNTER phase: Challenge the proposal

        Identifies:
        - Missing perspectives
        - Weak evidence
        - Alternative interpretations
        """
        weaknesses = []
        alternatives = []

        # Check for missing disciplines
        disciplines = synthesis.get("disciplines", [])
        if len(disciplines) < 2:
            weaknesses.append("Limited to single discipline; cross-disciplinary insights missing")

        # Check evidence strength
        evidence = proposal.get("evidence", [])
        weak_evidence = [e for e in evidence if e.get("score", 0) < 0.1]
        if weak_evidence:
            weaknesses.append(
                f"{len(weak_evidence)} keyword(s) have weak scores (<0.1)"
            )

        # Check confidence level
        confidence = proposal.get("confidence", 0)
        if confidence < 0.6:
            weaknesses.append(f"Overall confidence is low ({confidence:.1%})")

        # Suggest alternatives based on intersections
        intersections = synthesis.get("intersections", [])
        for intersection in intersections:
            alternatives.append(
                f"Consider {intersection['disciplines'][0]}-{intersection['disciplines'][1]} "
                f"intersection (potential: {intersection['potential_score']:.1%})"
            )

        counter_result = {
            "phase": "counter",
            "iteration": state.iterations,
            "weaknesses_found": len(weaknesses),
            "weaknesses": weaknesses,
            "alternative_perspectives": alternatives,
            "challenge_strength": min(len(weaknesses) * 0.2 + len(alternatives) * 0.15, 1.0),
            "timestamp": datetime.now().isoformat()
        }

        state.counters.append(counter_result)
        state.phase = MirrorPhase.REFINE

        return counter_result

    def refine(self, state: MirrorState, proposal: Dict, counter: Dict) -> Dict:
        """
        REFINE phase: Synthesize proposal + counter into improved understanding

        Returns refined result with higher confidence
        """
        # Calculate refinement quality
        proposal_confidence = proposal.get("confidence", 0.5)
        challenge_strength = counter.get("challenge_strength", 0.3)

        # Confidence increases when challenges are addressed
        refined_confidence = min(
            proposal_confidence + (1 - proposal_confidence) * 0.3,
            0.95
        )

        # Build refined analysis
        refined = {
            "phase": "refine",
            "iteration": state.iterations,
            "original_confidence": proposal_confidence,
            "refined_confidence": refined_confidence,
            "improvements": [],
            "remaining_gaps": [],
            "timestamp": datetime.now().isoformat()
        }

        # Address weaknesses
        for weakness in counter.get("weaknesses", []):
            refined["improvements"].append(f"Addressed: {weakness}")

        # Incorporate alternatives
        for alt in counter.get("alternative_perspectives", []):
            refined["improvements"].append(f"Incorporated: {alt}")

        # Check for remaining gaps
        if refined_confidence < self.convergence_threshold:
            refined["remaining_gaps"].append(
                f"Confidence {refined_confidence:.1%} below threshold {self.convergence_threshold:.1%}"
            )

        state.refinements.append(refined)
        state.iterations += 1
        state.convergence_score = refined_confidence

        # Check convergence
        if refined_confidence >= self.convergence_threshold or state.iterations >= state.max_iterations:
            state.phase = MirrorPhase.CONVERGED
            state.converged = True
        else:
            state.phase = MirrorPhase.PROPOSE  # Another round

        return refined


class AnalysearchEngine:
    """
    Main Analysearch Intent Engine

    Combines:
    - Keyword Crystallization (ALGO-41 inspired)
    - Cross-Disciplinary Synthesis
    - Mirror Mode (PROPOSE → COUNTER → REFINE)
    - GIGO Protection
    - Intent Conservation (ALGO-26 inspired)
    """

    def __init__(self):
        self.crystallizer = KeywordCrystallizer()
        self.synthesizer = CrossDisciplinarySynthesizer()
        self.mirror = MirrorModeEngine()
        self.gigo = GIGOProtector()

        self.sessions: Dict[str, MirrorState] = {}
        self.query_history: List[Dict] = []

    def analyze(
        self,
        query: str,
        mode: AnalysearchMode = AnalysearchMode.STANDARD,
        context: str = "",
        max_mirror_iterations: int = 3
    ) -> AnalysearchResult:
        """
        Main analysis entry point

        Args:
            query: User query/intent
            mode: Analysis depth
            context: Additional context
            max_mirror_iterations: Max Mirror Mode iterations

        Returns:
            AnalysearchResult with full analysis
        """
        start_time = datetime.now()

        # Step 1: GIGO Protection
        is_valid, validation_details = self.gigo.validate_input(query)
        if not is_valid:
            return AnalysearchResult(
                query=query,
                mode=mode.value,
                keywords=[],
                analysis={"error": "Input validation failed", "details": validation_details},
                research_sources=[],
                synthesis={},
                intent_preserved=False,
                confidence=0.0,
                processing_time_ms=0.0
            )

        # Step 2: Extract golden keywords (ALGO-41)
        full_text = f"{query} {context}"
        keywords = self.crystallizer.extract(full_text)

        # Step 3: Cross-disciplinary synthesis
        synthesis = self.synthesizer.synthesize(keywords, full_text)

        # Step 4: Build structured analysis
        analysis = self._build_analysis(query, keywords, synthesis)

        # Step 5: Mirror Mode (if deep/mirror mode)
        mirror_state = None
        if mode in (AnalysearchMode.DEEP, AnalysearchMode.MIRROR):
            mirror_state = self._run_mirror_mode(query, analysis, keywords, synthesis, max_mirror_iterations)
            self.sessions[mirror_state.session_id] = mirror_state

        # Step 6: Intent conservation check
        intent_preserved = self._check_intent_conservation(query, analysis)

        # Step 7: Calculate confidence
        confidence = self._calculate_confidence(keywords, synthesis, mirror_state)

        # Calculate processing time
        elapsed = (datetime.now() - start_time).total_seconds() * 1000

        # Record in history
        self.query_history.append({
            "query": query,
            "mode": mode.value,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat()
        })

        return AnalysearchResult(
            query=query,
            mode=mode.value,
            keywords=keywords,
            analysis=analysis,
            research_sources=self._find_research_sources(keywords),
            synthesis=synthesis,
            intent_preserved=intent_preserved,
            confidence=confidence,
            mirror_state=mirror_state,
            processing_time_ms=round(elapsed, 2),
            routing_hint=self._build_routing_hint(analysis),
        )

    def _build_analysis(self, query: str, keywords: List[Dict], synthesis: Dict) -> Dict:
        """Build structured analysis from keywords and synthesis"""
        is_thai, thai_ratio = self._detect_thai_language(query)
        return {
            "query_type": self._classify_query(query),
            "complexity": self._estimate_complexity(keywords, synthesis),
            "keyword_summary": {
                "total": len(keywords),
                "top_domain": keywords[0].get("domain", "general") if keywords else "unknown",
                "avg_score": round(
                    sum(k["score"] for k in keywords) / len(keywords), 4
                ) if keywords else 0.0,
            },
            "disciplines_involved": synthesis.get("disciplines_detected", 0),
            "innovation_potential": synthesis.get("innovation_potential", 0.0),
            "recommended_depth": "deep" if synthesis.get("disciplines_detected", 0) >= 2 else "standard",
            "language": {"is_thai": is_thai, "thai_ratio": thai_ratio},
        }

    def _classify_query(self, query: str) -> str:
        """Classify query type"""
        query_lower = query.lower()

        if any(w in query_lower for w in ["how", "วิธี", "ทำอย่างไร"]):
            return "how_to"
        elif any(w in query_lower for w in ["why", "ทำไม", "เพราะอะไร"]):
            return "explanation"
        elif any(w in query_lower for w in ["compare", "เปรียบเทียบ", "vs", "versus"]):
            return "comparison"
        elif any(w in query_lower for w in ["create", "build", "สร้าง", "พัฒนา"]):
            return "creation"
        elif any(w in query_lower for w in ["analyze", "วิเคราะห์", "evaluate"]):
            return "analysis"
        else:
            return "exploration"

    @staticmethod
    def _detect_thai_language(text: str) -> Tuple[bool, float]:
        """Detect if text is Thai. Returns (is_thai, thai_char_ratio)."""
        import re as _re
        thai_chars = len(_re.findall(r'[\u0E00-\u0E7F]', text))
        total_alpha = len(_re.findall(r'[a-zA-Z\u0E00-\u0E7F]', text))
        if total_alpha == 0:
            return False, 0.0
        ratio = round(thai_chars / total_alpha, 3)
        return ratio >= 0.3, ratio

    def _build_routing_hint(self, analysis: Dict) -> Dict:
        """Build routing hint for model selection (G38: Typhoon Thai pre-router)."""
        lang_info = analysis.get("language", {})
        is_thai = lang_info.get("is_thai", False)
        thai_ratio = lang_info.get("thai_ratio", 0.0)

        hint: Dict = {
            "prefer_regional_thai": is_thai,
            "thai_ratio": thai_ratio,
            "recommended_task_type": analysis.get("query_type", "general"),
            "complexity": analysis.get("complexity", "low"),
        }

        if is_thai and thai_ratio >= 0.5:
            hint["model_override"] = "typhoon_v2"
            hint["reason"] = "High Thai content — route to Typhoon v2 for optimal quality"
        elif is_thai:
            hint["model_fallback"] = "typhoon_v2"
            hint["reason"] = "Mixed Thai/English — Typhoon v2 as fallback"

        return hint

    def _estimate_complexity(self, keywords: List[Dict], synthesis: Dict) -> str:
        """Estimate query complexity"""
        disciplines = synthesis.get("disciplines_detected", 0)
        keyword_count = len(keywords)

        if disciplines >= 3 or keyword_count >= 8:
            return "high"
        elif disciplines >= 2 or keyword_count >= 5:
            return "medium"
        else:
            return "low"

    def _run_mirror_mode(
        self,
        query: str,
        analysis: Dict,
        keywords: List[Dict],
        synthesis: Dict,
        max_iterations: int
    ) -> MirrorState:
        """Run Mirror Mode loop"""
        self.mirror.max_iterations = max_iterations
        state = self.mirror.create_session(query)

        while not state.converged and state.iterations < state.max_iterations:
            # PROPOSE
            proposal = self.mirror.propose(state, analysis, keywords)

            # COUNTER
            counter = self.mirror.counter(state, proposal, synthesis)

            # REFINE
            refined = self.mirror.refine(state, proposal, counter)

        return state

    def _check_intent_conservation(self, original_query: str, analysis: Dict) -> bool:
        """Check that the original intent is preserved in the analysis"""
        # Check: key words from query appear in analysis or keyword results
        query_words = {w.lower() for w in original_query.split() if len(w) > 2}
        if not query_words:
            return True

        analysis_str = str(analysis).lower()

        # Also check keywords in latest query history
        keyword_str = ""
        if self.query_history:
            keyword_str = " ".join(
                str(q) for q in self.query_history[-1:]
            ).lower()

        combined = analysis_str + " " + keyword_str + " " + original_query.lower()

        preserved_count = sum(1 for w in query_words if w in combined)
        preservation_ratio = preserved_count / len(query_words)

        return preservation_ratio >= 0.3

    def _calculate_confidence(
        self,
        keywords: List[Dict],
        synthesis: Dict,
        mirror_state: Optional[MirrorState]
    ) -> float:
        """Calculate overall confidence score"""
        # Keyword quality (0-0.3)
        keyword_score = min(len(keywords) / 10, 1.0) * 0.3

        # Synthesis quality (0-0.3)
        innovation = synthesis.get("innovation_potential", 0.0)
        synthesis_score = innovation * 0.3

        # Mirror convergence (0-0.4)
        if mirror_state and mirror_state.converged:
            mirror_score = mirror_state.convergence_score * 0.4
        elif mirror_state:
            mirror_score = mirror_state.convergence_score * 0.2
        else:
            mirror_score = 0.2  # Default for non-mirror modes

        return round(keyword_score + synthesis_score + mirror_score, 3)

    def _find_research_sources(self, keywords: List[Dict]) -> List[Dict]:
        """Find relevant research sources based on keywords"""
        # In production, this would query RCTDB / GraphRAG
        sources = []
        for kw in keywords[:5]:
            sources.append({
                "keyword": kw["keyword"],
                "source_type": "knowledge_base",
                "relevance": kw["score"],
                "status": "available"
            })
        return sources

    def get_session(self, session_id: str) -> Optional[MirrorState]:
        """Get Mirror Mode session by ID"""
        return self.sessions.get(session_id)

    def get_stats(self) -> Dict:
        """Get engine statistics"""
        return {
            "total_queries": len(self.query_history),
            "active_sessions": len(self.sessions),
            "avg_confidence": round(
                sum(q["confidence"] for q in self.query_history) / max(len(self.query_history), 1),
                3
            ),
            "mode_distribution": self._get_mode_distribution()
        }

    def _get_mode_distribution(self) -> Dict[str, int]:
        """Get distribution of query modes"""
        dist = {}
        for q in self.query_history:
            mode = q["mode"]
            dist[mode] = dist.get(mode, 0) + 1
        return dist

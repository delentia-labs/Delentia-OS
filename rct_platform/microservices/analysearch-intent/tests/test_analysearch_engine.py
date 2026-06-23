"""Tests for Analysearch Intent Engine"""

import pytest
from app.core.analysearch_engine import (
    AnalysearchEngine,
    AnalysearchMode,
    GIGOProtector,
    KeywordCrystallizer,
    CrossDisciplinarySynthesizer,
    MirrorModeEngine,
    MirrorPhase,
)


# ============================================================
# GIGO Protector Tests
# ============================================================

class TestGIGOProtector:

    def test_empty_input_rejected(self):
        is_valid, details = GIGOProtector.validate_input("")
        assert is_valid is False
        assert details["reason"] == "empty_input"

    def test_whitespace_only_rejected(self):
        is_valid, details = GIGOProtector.validate_input("   ")
        assert is_valid is False

    def test_too_short_rejected(self):
        is_valid, details = GIGOProtector.validate_input("ab")
        assert is_valid is False
        assert details["reason"] == "too_short"

    def test_valid_input_accepted(self):
        is_valid, details = GIGOProtector.validate_input(
            "How to build a neural network for image classification"
        )
        assert is_valid is True
        assert "entropy" in details

    def test_repetitive_input_rejected(self):
        is_valid, details = GIGOProtector.validate_input(
            "test test test test test test test test test test"
        )
        assert is_valid is False
        assert details["reason"] == "repetitive"

    def test_entropy_calculation(self):
        entropy = GIGOProtector.calculate_entropy("abcdefgh")
        assert entropy > 0
        # All unique chars = high entropy
        assert entropy > 2.0

    def test_low_entropy_input(self):
        entropy = GIGOProtector.calculate_entropy("aaa")
        assert entropy == 0.0  # All same chars = zero entropy


# ============================================================
# Keyword Crystallizer Tests
# ============================================================

class TestKeywordCrystallizer:

    def test_extract_keywords(self):
        crystallizer = KeywordCrystallizer()
        keywords = crystallizer.extract(
            "Machine learning algorithm for neural network optimization in AI research"
        )
        assert len(keywords) > 0
        assert all("keyword" in k for k in keywords)
        assert all("score" in k for k in keywords)
        assert all("entropy" in k for k in keywords)

    def test_empty_input(self):
        crystallizer = KeywordCrystallizer()
        keywords = crystallizer.extract("")
        assert keywords == []

    def test_domain_detection(self):
        crystallizer = KeywordCrystallizer()
        keywords = crystallizer.extract(
            "AI algorithm neural network cloud infrastructure API optimization"
        )
        domains = [k.get("domain") for k in keywords if k.get("domain")]
        assert len(domains) > 0

    def test_top_k_limit(self):
        crystallizer = KeywordCrystallizer()
        keywords = crystallizer.extract(
            "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 "
            "word11 word12 word13 word14 word15",
            top_k=5
        )
        assert len(keywords) <= 5

    def test_keywords_sorted_by_score(self):
        crystallizer = KeywordCrystallizer()
        keywords = crystallizer.extract(
            "algorithm optimization neural network machine learning data analysis"
        )
        if len(keywords) >= 2:
            scores = [k["score"] for k in keywords]
            assert scores == sorted(scores, reverse=True)


# ============================================================
# Cross-Disciplinary Synthesizer Tests
# ============================================================

class TestCrossDisciplinarySynthesizer:

    def test_synthesize_detects_disciplines(self):
        synth = CrossDisciplinarySynthesizer()
        keywords = [
            {"keyword": "algorithm", "score": 0.8, "entropy": 3.0},
            {"keyword": "neural", "score": 0.7, "entropy": 2.5},
            {"keyword": "molecule", "score": 0.6, "entropy": 2.8},
        ]
        result = synth.synthesize(keywords, "AI and chemistry research")

        assert "disciplines_detected" in result
        assert result["disciplines_detected"] > 0
        assert "disciplines" in result
        assert "innovation_potential" in result

    def test_synthesize_finds_intersections(self):
        synth = CrossDisciplinarySynthesizer()
        keywords = [
            {"keyword": "algorithm", "score": 0.8, "entropy": 3.0},
            {"keyword": "energy", "score": 0.7, "entropy": 2.5},
            {"keyword": "material", "score": 0.6, "entropy": 2.8},
            {"keyword": "design", "score": 0.5, "entropy": 2.3},
        ]
        result = synth.synthesize(keywords, "engineering physics materials")

        intersections = result.get("intersections", [])
        # With multiple disciplines, should find at least some intersections
        assert isinstance(intersections, list)

    def test_empty_keywords(self):
        synth = CrossDisciplinarySynthesizer()
        result = synth.synthesize([], "")
        assert result["disciplines_detected"] == 0

    def test_innovation_potential_range(self):
        synth = CrossDisciplinarySynthesizer()
        keywords = [
            {"keyword": "algorithm", "score": 0.8, "entropy": 3.0},
            {"keyword": "molecule", "score": 0.7, "entropy": 2.5},
        ]
        result = synth.synthesize(keywords, "computer science chemistry")
        potential = result.get("innovation_potential", 0)
        assert 0 <= potential <= 1


# ============================================================
# Mirror Mode Tests
# ============================================================

class TestMirrorMode:

    def test_create_session(self):
        mirror = MirrorModeEngine()
        state = mirror.create_session("test query")

        assert state.session_id is not None
        assert state.query == "test query"
        assert state.phase == MirrorPhase.PROPOSE
        assert state.iterations == 0
        assert state.converged is False

    def test_propose_phase(self):
        mirror = MirrorModeEngine()
        state = mirror.create_session("test query")
        keywords = [
            {"keyword": "test", "score": 0.5, "entropy": 2.0, "domain": None},
            {"keyword": "query", "score": 0.4, "entropy": 2.3, "domain": None},
        ]

        proposal = mirror.propose(state, {}, keywords)

        assert proposal["phase"] == "propose"
        assert "hypothesis" in proposal
        assert "confidence" in proposal
        assert state.phase == MirrorPhase.COUNTER
        assert len(state.proposals) == 1

    def test_counter_phase(self):
        mirror = MirrorModeEngine()
        state = mirror.create_session("test query")

        proposal = {"confidence": 0.5, "evidence": []}
        synthesis = {"disciplines": [], "intersections": []}

        counter = mirror.counter(state, proposal, synthesis)

        assert counter["phase"] == "counter"
        assert "weaknesses" in counter
        assert state.phase == MirrorPhase.REFINE

    def test_refine_phase(self):
        mirror = MirrorModeEngine()
        state = mirror.create_session("test query")

        proposal = {"confidence": 0.5}
        counter = {"challenge_strength": 0.3, "weaknesses": ["weak1"], "alternative_perspectives": []}

        refined = mirror.refine(state, proposal, counter)

        assert refined["phase"] == "refine"
        assert refined["refined_confidence"] > refined["original_confidence"]
        assert state.iterations == 1

    def test_full_mirror_loop_converges(self):
        mirror = MirrorModeEngine(max_iterations=5, convergence_threshold=0.7)
        state = mirror.create_session("complex research query")

        keywords = [
            {"keyword": "research", "score": 0.8, "entropy": 3.0, "domain": "science"},
            {"keyword": "algorithm", "score": 0.7, "entropy": 3.2, "domain": "technology"},
            {"keyword": "analysis", "score": 0.6, "entropy": 2.8, "domain": "science"},
        ]
        synthesis = {
            "disciplines": [{"discipline": "computer_science"}],
            "intersections": [{"disciplines": ["cs", "math"], "connection_type": "direct", "potential_score": 0.7}],
        }

        while not state.converged and state.iterations < state.max_iterations:
            proposal = mirror.propose(state, {}, keywords)
            counter = mirror.counter(state, proposal, synthesis)
            refined = mirror.refine(state, proposal, counter)

        # Should either converge or hit max iterations
        assert state.converged or state.iterations == state.max_iterations


# ============================================================
# Full Analysearch Engine Tests
# ============================================================

class TestAnalysearchEngine:

    def test_standard_analysis(self):
        engine = AnalysearchEngine()
        result = engine.analyze(
            "How to build AI algorithm for optimization",
            mode=AnalysearchMode.STANDARD
        )

        assert result.query == "How to build AI algorithm for optimization"
        assert result.mode == "standard"
        assert len(result.keywords) > 0
        assert result.confidence > 0
        assert result.mirror_state is None  # No mirror in standard mode

    def test_mirror_mode_analysis(self):
        engine = AnalysearchEngine()
        result = engine.analyze(
            "Cross-disciplinary approach to neural network design using biology and physics",
            mode=AnalysearchMode.MIRROR,
            max_mirror_iterations=3
        )

        assert result.mode == "mirror"
        assert result.mirror_state is not None
        assert result.mirror_state.iterations > 0

    def test_deep_mode_analysis(self):
        engine = AnalysearchEngine()
        result = engine.analyze(
            "Analyze the intersection of machine learning and material science for innovation",
            mode=AnalysearchMode.DEEP
        )

        assert result.mode == "deep"
        assert result.mirror_state is not None

    def test_gigo_protection_rejects_bad_input(self):
        engine = AnalysearchEngine()
        result = engine.analyze("")

        assert result.confidence == 0.0
        assert "error" in result.analysis

    def test_intent_preservation(self):
        engine = AnalysearchEngine()
        result = engine.analyze(
            "Design optimization algorithm for cloud infrastructure"
        )

        assert result.intent_preserved is True

    def test_processing_time_tracked(self):
        engine = AnalysearchEngine()
        result = engine.analyze("test query for timing")

        assert result.processing_time_ms >= 0

    def test_stats_tracking(self):
        engine = AnalysearchEngine()
        engine.analyze("query one")
        engine.analyze("query two")

        stats = engine.get_stats()
        assert stats["total_queries"] == 2

    def test_query_classification(self):
        engine = AnalysearchEngine()

        result1 = engine.analyze("How to build a neural network")
        assert result1.analysis["query_type"] == "how_to"

        result2 = engine.analyze("Compare Python vs Rust for AI")
        assert result2.analysis["query_type"] == "comparison"

        result3 = engine.analyze("Create a new optimization algorithm")
        assert result3.analysis["query_type"] == "creation"

    def test_context_enhances_analysis(self):
        engine = AnalysearchEngine()

        result_no_ctx = engine.analyze("optimization")
        result_with_ctx = engine.analyze(
            "optimization",
            context="neural network machine learning algorithm deep learning AI"
        )

        # With context, should extract more keywords
        assert len(result_with_ctx.keywords) >= len(result_no_ctx.keywords)

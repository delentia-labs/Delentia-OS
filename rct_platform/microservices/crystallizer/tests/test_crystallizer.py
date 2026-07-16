"""
Tests for ALGO-41: The Crystallizer — Golden Keyword Extraction & Auto-Concept Expansion
"""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from crystallizer.crystallizer import (
    KeywordCategory,
    GoldenKeyword,
    ConceptNode,
    ConceptMap,
    EntropyScanner,
    KnowledgeBase,
)


# ──────────────────────────────────────────
# KeywordCategory enum
# ──────────────────────────────────────────

class TestKeywordCategory:
    def test_enum_values(self):
        assert KeywordCategory.TECHNICAL.value == "technical"
        assert KeywordCategory.CONCEPTUAL.value == "conceptual"
        assert KeywordCategory.BUSINESS.value == "business"
        assert KeywordCategory.DOMAIN.value == "domain"

    def test_all_categories_exist(self):
        categories = {k.value for k in KeywordCategory}
        assert categories == {"technical", "conceptual", "business", "domain"}


# ──────────────────────────────────────────
# GoldenKeyword dataclass
# ──────────────────────────────────────────

class TestGoldenKeyword:
    def _make_keyword(self, word="sovereignty", score=0.95, category=KeywordCategory.CONCEPTUAL):
        return GoldenKeyword(
            word=word,
            entropy_score=score,
            category=category,
            context="want **sovereignty** over data",
            position=2,
            related_intents=["self-hosting", "privacy"],
        )

    def test_to_dict_keys(self):
        kw = self._make_keyword()
        d = kw.to_dict()
        assert set(d.keys()) == {"word", "entropy_score", "category", "context", "position", "related_intents"}

    def test_to_dict_values(self):
        kw = self._make_keyword()
        d = kw.to_dict()
        assert d["word"] == "sovereignty"
        assert d["entropy_score"] == 0.95
        assert d["category"] == "conceptual"
        assert d["related_intents"] == ["self-hosting", "privacy"]

    def test_to_dict_empty_related_intents(self):
        kw = GoldenKeyword(
            word="kubernetes",
            entropy_score=0.9,
            category=KeywordCategory.TECHNICAL,
            context="using **kubernetes** cluster",
            position=1,
        )
        d = kw.to_dict()
        assert d["related_intents"] == []


# ──────────────────────────────────────────
# ConceptNode dataclass
# ──────────────────────────────────────────

class TestConceptNode:
    def _make_node(self):
        return ConceptNode(
            keyword="sovereignty",
            definition="Complete ownership and control over data",
            related_concepts=["privacy", "self-hosting"],
            tech_stack_implications=["Self-hosted PostgreSQL", "Local LLM"],
            suggested_actions=[{"id": "setup_local_db", "label": "Setup self-hosted database"}],
            examples=["Nextcloud", "Gitea"],
        )

    def test_to_dict_keys(self):
        node = self._make_node()
        d = node.to_dict()
        assert set(d.keys()) == {
            "keyword", "definition", "related_concepts",
            "tech_stack_implications", "suggested_actions", "examples",
        }

    def test_to_dict_values(self):
        node = self._make_node()
        d = node.to_dict()
        assert d["keyword"] == "sovereignty"
        assert len(d["related_concepts"]) == 2
        assert len(d["suggested_actions"]) == 1
        assert d["suggested_actions"][0]["id"] == "setup_local_db"

    def test_to_dict_empty_examples(self):
        node = ConceptNode(
            keyword="realtime",
            definition="Instant bidirectional communication",
            related_concepts=[],
            tech_stack_implications=[],
            suggested_actions=[],
        )
        assert node.to_dict()["examples"] == []


# ──────────────────────────────────────────
# ConceptMap dataclass
# ──────────────────────────────────────────

class TestConceptMap:
    def _make_map(self):
        kw = GoldenKeyword(
            word="sovereignty",
            entropy_score=0.95,
            category=KeywordCategory.CONCEPTUAL,
            context="want **sovereignty** over data",
            position=2,
        )
        node = ConceptNode(
            keyword="sovereignty",
            definition="Complete ownership",
            related_concepts=["privacy"],
            tech_stack_implications=["PostgreSQL"],
            suggested_actions=[],
        )
        return ConceptMap(
            root_keyword=kw,
            definition="Complete ownership and control",
            expansion_nodes=[node],
            actionable_next_steps=[{"id": "plan_infra", "label": "Plan infrastructure"}],
            ui_schema={"type": "accordion", "expandable": True},
        )

    def test_to_dict_keys(self):
        cm = self._make_map()
        d = cm.to_dict()
        assert set(d.keys()) == {
            "root_keyword", "definition", "expansion_nodes",
            "actionable_next_steps", "ui_schema",
        }

    def test_to_dict_nested_root_keyword(self):
        cm = self._make_map()
        d = cm.to_dict()
        assert d["root_keyword"]["word"] == "sovereignty"
        assert d["root_keyword"]["category"] == "conceptual"

    def test_to_dict_expansion_nodes_serialized(self):
        cm = self._make_map()
        d = cm.to_dict()
        assert len(d["expansion_nodes"]) == 1
        assert d["expansion_nodes"][0]["keyword"] == "sovereignty"


# ──────────────────────────────────────────
# EntropyScanner
# ──────────────────────────────────────────

class TestEntropyScanner:
    @pytest.fixture
    def scanner(self):
        return EntropyScanner()

    def test_scan_technical_term(self, scanner):
        keywords = scanner.scan_stream("I want to use kubernetes for deployment")
        words = [kw.word.lower() for kw in keywords]
        assert "kubernetes" in words

    def test_scan_conceptual_term(self, scanner):
        keywords = scanner.scan_stream("I care about sovereignty and privacy")
        words = [kw.word.lower() for kw in keywords]
        assert "sovereignty" in words

    def test_scan_business_term(self, scanner):
        keywords = scanner.scan_stream("I need an inventory management system")
        words = [kw.word.lower() for kw in keywords]
        assert "inventory" in words

    def test_scan_empty_text(self, scanner):
        keywords = scanner.scan_stream("")
        assert keywords == []

    def test_scan_stop_words_excluded(self, scanner):
        keywords = scanner.scan_stream("the and or but in on at")
        assert len(keywords) == 0

    def test_scan_returns_golden_keywords(self, scanner):
        keywords = scanner.scan_stream("Build a docker kubernetes react application")
        for kw in keywords:
            assert isinstance(kw, GoldenKeyword)
            assert kw.entropy_score >= 0.8

    def test_scan_position_tracking(self, scanner):
        keywords = scanner.scan_stream("I want kubernetes for realtime")
        for kw in keywords:
            assert kw.position >= 0

    def test_entropy_score_capped_at_1(self, scanner):
        keywords = scanner.scan_stream("sovereignty privacy security kubernetes docker")
        for kw in keywords:
            assert kw.entropy_score <= 1.0

    def test_categorization_technical(self, scanner):
        keywords = scanner.scan_stream("Use react framework")
        react_kw = next((kw for kw in keywords if kw.word.lower() == "react"), None)
        if react_kw:
            assert react_kw.category == KeywordCategory.TECHNICAL

    def test_categorization_conceptual(self, scanner):
        keywords = scanner.scan_stream("Prioritize sovereignty above all")
        sov_kw = next((kw for kw in keywords if kw.word.lower() == "sovereignty"), None)
        if sov_kw:
            assert sov_kw.category == KeywordCategory.CONCEPTUAL


# ──────────────────────────────────────────
# KnowledgeBase
# ──────────────────────────────────────────

class TestKnowledgeBase:
    @pytest.fixture
    def kb(self):
        return KnowledgeBase()

    def test_sovereignty_concept_exists(self, kb):
        assert "sovereignty" in kb.concepts

    def test_realtime_concept_exists(self, kb):
        assert "realtime" in kb.concepts

    def test_inventory_concept_exists(self, kb):
        assert "inventory" in kb.concepts

    def test_concept_has_required_keys(self, kb):
        concept = kb.concepts["sovereignty"]
        assert "definition" in concept
        assert "related" in concept
        assert "tech_implications" in concept
        assert "actions" in concept

    def test_concept_actions_have_id_and_label(self, kb):
        for _, concept in kb.concepts.items():
            for action in concept["actions"]:
                assert "id" in action
                assert "label" in action

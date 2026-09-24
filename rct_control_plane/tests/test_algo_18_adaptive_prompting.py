"""
Round 43 item 5: real coverage for algo_18_adaptive_prompting.py, previously
untested (0 test files existed) despite having a real, working __main__
smoke test. PromptEngine is pure/deterministic (no I/O). RAGEngine wraps a
real ALGO-16 VectorEngine (FAISSBackend) in-process, no HTTP/mocking.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.algo_18_adaptive_prompting import (
    PromptEngine, PromptTemplate, RAGEngine,
)
from rct_control_plane.algo_16_vector import VectorEngine, FAISSBackend


def _qa_template():
    return PromptTemplate(
        template_id="qa", name="QA Template", description="Answer a question given context",
        template="Context:\n{{context}}\n\nQuestion: {{question}}\nAnswer:",
        variables=["context", "question"], category="question_answering",
    )


def _qa_template_v2_with_list():
    return PromptTemplate(
        template_id="qa", name="QA Template v2", description="list-aware",
        template="Context:\n{{context}}\n\nSources:\n{{#sources}}- {{.}}\n{{/sources}}\nQuestion: {{question}}\nAnswer:",
        variables=["context", "question", "sources"], category="question_answering",
    )


class TestTemplateVersioning:
    def test_add_template_starts_at_version_1(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        assert engine.templates["qa"].version == 1
        assert engine.template_versions.get("qa", []) == []

    def test_readding_same_id_bumps_version_and_keeps_history(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        engine.add_template(_qa_template_v2_with_list())
        assert engine.templates["qa"].version == 2
        assert engine.template_versions["qa"] == [1]

    def test_invalid_template_raises(self):
        engine = PromptEngine()
        bad = PromptTemplate(template_id="", name="x", description="", template="",
                              variables=[], category="x")
        with pytest.raises(ValueError):
            engine.add_template(bad)

    def test_get_template_returns_none_for_unknown_id(self):
        engine = PromptEngine()
        assert engine.get_template("ghost") is None

    def test_get_template_with_stale_version_warns_but_returns_latest(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        result = engine.get_template("qa", version=999)
        assert result.version == 1

    def test_list_templates_filters_by_category(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        engine.add_template(PromptTemplate(
            template_id="code", name="Code", description="", template="{{code}}",
            variables=["code"], category="code_analysis",
        ))
        assert [t.template_id for t in engine.list_templates(category="code_analysis")] == ["code"]

    def test_list_templates_filters_by_tags(self):
        engine = PromptEngine()
        t = _qa_template()
        t.tags = ["v2", "prod"]
        engine.add_template(t)
        assert engine.list_templates(tags=["prod"]) == [t]
        assert engine.list_templates(tags=["nope"]) == []


class TestGeneratePrompt:
    def test_renders_simple_variables(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        result = engine.generate_prompt("qa", {"context": "c", "question": "q?"})
        assert "c" in result.prompt and "q?" in result.prompt
        assert result.template_version == 1
        assert result.tokens >= 1

    def test_renders_list_iteration_block(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        engine.add_template(_qa_template_v2_with_list())
        result = engine.generate_prompt("qa", {
            "context": "c", "question": "q?", "sources": ["a.py", "b.py"],
        })
        assert "a.py" in result.prompt and "b.py" in result.prompt

    def test_missing_required_variable_raises(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        with pytest.raises(ValueError):
            engine.generate_prompt("qa", {"context": "only this"})

    def test_unknown_template_id_raises(self):
        engine = PromptEngine()
        with pytest.raises(ValueError):
            engine.generate_prompt("ghost", {})

    def test_token_count_floors_at_1_for_short_text(self):
        engine = PromptEngine()
        engine.add_template(PromptTemplate(
            template_id="tiny", name="t", description="", template="{{x}}",
            variables=["x"], category="c",
        ))
        result = engine.generate_prompt("tiny", {"x": "a"})
        assert result.tokens == 1

    def test_token_count_collapses_whitespace_before_counting(self):
        engine = PromptEngine()
        engine.add_template(PromptTemplate(
            template_id="ws", name="t", description="", template="{{x}}",
            variables=["x"], category="c",
        ))
        # A ~40-char payload -> ~10 tokens whether or not whitespace is
        # collapsed first; use a long run of spaces to prove collapsing
        # actually happens (else char_count would be much larger).
        padded = "word" + (" " * 100) + "word"
        collapsed = engine.generate_prompt("ws", {"x": padded})
        tight = engine.generate_prompt("ws", {"x": "word word"})
        assert collapsed.tokens == tight.tokens


class TestSelectTemplate:
    def test_routes_by_code_keyword(self):
        engine = PromptEngine()
        engine.add_template(PromptTemplate(
            template_id="code", name="c", description="", template="{{x}}",
            variables=["x"], category="code_analysis",
        ))
        assert engine.select_template("please review this code", {}) == "code"

    def test_routes_by_question_keyword(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        assert engine.select_template("answer this question", {}) == "qa"

    def test_no_matching_category_returns_none(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        assert engine.select_template("classify sentiment", {}) is None

    def test_picks_highest_scored_by_tracked_performance(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        engine.add_template(PromptTemplate(
            template_id="qa2", name="qa2", description="", template="{{question}}",
            variables=["question"], category="question_answering",
        ))
        engine.track_performance("qa", 1, success=True, quality_score=1.0, execution_time_ms=1, tokens=1)
        engine.track_performance("qa2", 1, success=True, quality_score=5.0, execution_time_ms=1, tokens=1)
        assert engine.select_template("answer this question", {}) == "qa2"

    def test_untracked_candidate_still_wins_via_the_initial_sentinel_score(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        # add_template() always seeds an empty PerformanceMetrics entry, so
        # `metrics` is truthy even with zero uses - selection succeeds via
        # the real score-vs-sentinel(-1.0) comparison, not a missing-metrics
        # fallback.
        assert engine.select_template("answer this question", {}) == "qa"

    def test_no_keyword_match_falls_back_to_the_full_template_set(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        # "summarize this document" matches none of the code/classify/
        # question keyword branches - real fallback to ALL templates.
        assert engine.select_template("summarize this document", {}) == "qa"

    def test_a_candidate_with_no_metrics_entry_uses_the_first_seen_fallback(self):
        engine = PromptEngine()
        engine.add_template(_qa_template())
        # add_template() always seeds a metrics entry; deleting it directly
        # is the only way to exercise the "elif not best_template" branch -
        # a genuinely defensive path for a template that somehow has no
        # tracked metrics at all.
        del engine.performance_metrics["qa_v1"]
        assert engine.select_template("answer this question", {}) == "qa"


class TestFewShotPrompt:
    def test_includes_all_examples_up_to_num_examples(self):
        engine = PromptEngine()
        prompt = engine.generate_few_shot_prompt(
            "Classify sentiment.",
            examples=[{"input": "great", "output": "pos"}, {"input": "bad", "output": "neg"}],
            query="ok",
        )
        assert "Example 1:" in prompt and "Example 2:" in prompt
        assert "Input: ok" in prompt

    def test_truncates_to_num_examples(self):
        engine = PromptEngine()
        examples = [{"input": str(i), "output": str(i)} for i in range(5)]
        prompt = engine.generate_few_shot_prompt("t", examples, "q", num_examples=2)
        assert "Example 3:" not in prompt


class TestTrackPerformanceAndStats:
    def test_running_average_quality_score(self):
        engine = PromptEngine()
        engine.track_performance("t", 1, success=True, quality_score=4.0, execution_time_ms=10, tokens=5)
        engine.track_performance("t", 1, success=False, quality_score=2.0, execution_time_ms=20, tokens=5)
        metrics = engine.performance_metrics["t_v1"]
        assert metrics.total_uses == 2
        assert metrics.success_count == 1
        assert metrics.avg_quality_score == pytest.approx(3.0)
        assert metrics.avg_execution_time_ms == pytest.approx(15.0)

    def test_get_stats_reports_most_used_template(self):
        engine = PromptEngine()
        engine.track_performance("a", 1, success=True, quality_score=1, execution_time_ms=1, tokens=1)
        engine.track_performance("a", 1, success=True, quality_score=1, execution_time_ms=1, tokens=1)
        engine.track_performance("b", 1, success=True, quality_score=1, execution_time_ms=1, tokens=1)
        stats = engine.get_stats()
        assert stats["most_used_template"] == "a"
        assert stats["total_generations"] == 3

    def test_get_stats_with_no_data_is_a_real_zeroed_result(self):
        engine = PromptEngine()
        stats = engine.get_stats()
        assert stats == {
            "total_templates": 0, "total_generations": 0,
            "avg_quality_score": 0.0, "avg_tokens_per_prompt": 0.0,
            "most_used_template": None,
        }


@pytest.fixture
def rag_engine():
    faiss = pytest.importorskip("faiss")
    dim = 8
    backend = FAISSBackend(index_type="flat", metric="cosine")
    backend.initialize(dimension=dim)
    vector_engine = VectorEngine(backend, dimension=dim)
    docs = [
        ("doc1", [1.0] * dim, {"content": "Delentia OS ports 41 algorithms from a private monorepo."}),
        ("doc2", [-1.0] * dim, {"content": "The Stardew-Delentia-Bridge mod is an unrelated side project."}),
        ("doc3", [0.9] * dim, {"content": "ALGO-16 is a real FAISS-backed vector search engine."}),
    ]
    vector_engine.index(vectors=[d[1] for d in docs], ids=[d[0] for d in docs], metadata=[d[2] for d in docs])
    return RAGEngine(vector_engine, default_top_k=2)


class TestRAGEngineRetrieval:
    def test_retrieves_top_k_by_similarity(self, rag_engine):
        query_vector = [0.95] * 8
        docs = rag_engine.retrieve_context(query_vector, top_k=2, threshold=0.0)
        assert len(docs) == 2
        assert "doc2" not in {d["id"] for d in docs}

    def test_threshold_excludes_everything_above_cosines_real_max(self, rag_engine):
        docs = rag_engine.retrieve_context([0.95] * 8, top_k=3, threshold=1.01)
        assert docs == []

    def test_default_top_k_is_used_when_not_specified(self, rag_engine):
        docs = rag_engine.retrieve_context([0.95] * 8, threshold=0.0)
        assert len(docs) == 2  # default_top_k=2 from the fixture

    def test_retrieval_error_is_handled_and_returns_empty_list(self, rag_engine):
        # A wrong-dimension vector triggers a real exception inside
        # VectorEngine.search() - retrieve_context() must not propagate it.
        docs = rag_engine.retrieve_context([0.1, 0.2], threshold=0.0)
        assert docs == []


class TestRAGEngineAugmentAndFormat:
    def test_augment_prompt_with_no_context_returns_base_prompt_unchanged(self, rag_engine):
        assert rag_engine.augment_prompt("base", []) == "base"

    def test_augment_prompt_includes_context_section(self, rag_engine):
        docs = [{"content": "real content here", "score": 0.9}]
        result = rag_engine.augment_prompt("base prompt", docs)
        assert "Context:" in result and "base prompt" in result and "real content here" in result

    def test_augment_prompt_truncates_beyond_max_context_length(self, rag_engine):
        # remaining (150) must be > 100 to hit the truncate-with-"..." branch -
        # a smaller max_context_length instead hits the "not worth a
        # fragment" break branch with no "..." at all (see the next test).
        docs = [{"content": "x" * 500, "score": 0.9}]
        result = rag_engine.augment_prompt("base", docs, max_context_length=150)
        assert "..." in result

    def test_augment_prompt_drops_a_doc_entirely_when_remaining_room_is_too_small(self, rag_engine):
        docs = [{"content": "x" * 500, "score": 0.9}]
        result = rag_engine.augment_prompt("base", docs, max_context_length=50)
        assert "..." not in result
        assert "x" * 10 not in result  # none of the doc's real content made it in
        assert result == "Context:\n\n\nbase"

    def test_check_vector_service_reports_real_health(self, rag_engine):
        assert rag_engine.check_vector_service() is True

    def test_format_context_for_display_truncates_long_content(self, rag_engine):
        docs = [{"id": "d1", "content": "y" * 300, "score": 0.123456}]
        formatted = rag_engine.format_context_for_display(docs)
        assert formatted[0]["content"].endswith("...")
        assert len(formatted[0]["content"]) == 203
        assert formatted[0]["score"] == 0.123

    def test_format_context_for_display_keeps_short_content_as_is(self, rag_engine):
        docs = [{"id": "d1", "content": "short", "score": 0.5}]
        formatted = rag_engine.format_context_for_display(docs)
        assert formatted[0]["content"] == "short"

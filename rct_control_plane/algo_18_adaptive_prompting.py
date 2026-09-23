"""
ALGO-18: Adaptive Prompting (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/adaptive-prompting/
app/core/prompt_engine.py and rag_engine.py on 2026-09-16, following the same
strip-the-FastAPI-keep-the-engine pattern used for ALGO-15/16/19 (see those
modules' own docstrings). No HTTP framework code - stdlib only for
PromptEngine; RAGEngine now depends on ALGO-16's real VectorEngine directly
(see ADAPTATION note below) instead of httpx.

Real logic ported as-is (PromptEngine, prompt_engine.py):
    - PromptTemplate versioning: add_template() bumps `.version` and keeps
      version history per template_id when re-adding an existing id.
    - generate_prompt(): real variable-substitution rendering
      (_render_template - {{var}} substitution plus {{#list}}...{{/list}}
      iteration via regex) and word/char-based token counting
      (_count_tokens - char_count / 4 approximation, floored at 1).
    - select_template(): real rule-based category matching by task keywords,
      then scores candidates by a real weighted combination of tracked
      avg_quality_score and total_uses (0.7/0.3 split) from
      PerformanceMetrics accumulated via track_performance().
    - generate_few_shot_prompt(): real few-shot prompt assembly from
      examples + query.

ADAPTATION - RAGEngine (rag_engine.py), a real design judgment call:
    The source's RAGEngine.retrieve_context() called
    `POST {vector_service_url}/vector/search-by-text` with a raw `text`
    query, expecting the ALGO-16 vector-search microservice to embed the
    text server-side. Checked the real ALGO-16 source
    (Delentia-Private-OS/rct_platform/microservices/vector-search/app/api/
    routes.py) before adapting: that endpoint does not exist there - there
    is no `/vector/search-by-text` route and no text-embedding code
    anywhere in that microservice's real (non-README) source. The HTTP call
    this port is replacing was already calling a service endpoint that was
    never actually implemented on the other end, not a working integration
    this port is downgrading.

    Since this repo's ALGO-16 port (algo_16_vector.py's VectorEngine) only
    ever exposes `search(query_vector: List[float], k, metric, filter_dict)`
    - vectors in, never text in - and no real text-embedding component
    exists anywhere in this port set, RAGEngine here is changed to accept a
    pre-computed `query_vector: List[float]` directly (matching
    VectorEngine.search()'s real signature) rather than a `query: str`.
    Fabricating a fake/toy text embedder (e.g. a hash-based bag-of-words
    vector) would have made retrieve_context() "run" but silently replaced
    one dishonest piece (a call to a nonexistent endpoint) with another
    (semantically meaningless embeddings dressed up as real retrieval) -
    rejected as a bad trade. Callers that have a real embedding pipeline
    (e.g. wired in later at the kernel level) can produce `query_vector`
    themselves and pass it in.

    `retrieve_context()` and `check_vector_service()` are also changed from
    `async def` to plain `def`: they awaited network I/O before; now they
    call VectorEngine's own (synchronous) methods directly in-process, and
    keeping the `async` keyword with nothing to await would be misleading
    ceremony, not a preserved feature. `threshold` filtering (score >=
    threshold) is now applied locally after the call, since
    VectorEngine.search() itself has no threshold parameter to forward it
    to.

    augment_prompt() and format_context_for_display() are pure functions
    with no I/O in the source and are ported unchanged.

Usage::

    from rct_control_plane.algo_16_vector import VectorEngine, FAISSBackend
    from rct_control_plane.algo_18_adaptive_prompting import PromptEngine, RAGEngine, PromptTemplate

    backend = FAISSBackend(index_type="flat", metric="cosine")
    backend.initialize(dimension=8)
    vector_engine = VectorEngine(backend, dimension=8)
    rag = RAGEngine(vector_engine)

    engine = PromptEngine()
    engine.add_template(PromptTemplate(
        template_id="qa", name="QA", description="", category="question_answering",
        template="Answer using context:\\n{{context}}\\n\\nQ: {{question}}", variables=["context", "question"],
    ))
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from rct_control_plane.algo_16_vector import VectorEngine

logger = logging.getLogger(__name__)


# ============================================================================
# PromptEngine - template management, generation, selection (prompt_engine.py)
# ============================================================================

@dataclass
class PromptTemplate:
    """Prompt template structure"""
    template_id: str
    name: str
    description: str
    template: str
    variables: List[str]
    category: str
    tags: List[str] = field(default_factory=list)
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass
class GeneratedPrompt:
    """Generated prompt result"""
    prompt: str
    template_id: str
    template_version: int
    tokens: int
    variables_used: Dict[str, Any]
    context_retrieved: List[Dict[str, Any]] = field(default_factory=list)
    selection_reason: Optional[str] = None


@dataclass
class PerformanceMetrics:
    """Performance tracking for prompts"""
    template_id: str
    template_version: int
    total_uses: int = 0
    success_count: int = 0
    avg_quality_score: float = 0.0
    avg_execution_time_ms: float = 0.0
    avg_tokens: float = 0.0


class PromptEngine:
    """
    Core prompt engineering engine

    Features:
    - Template management and versioning
    - Dynamic prompt generation
    - Context-aware selection
    - Variable substitution
    - Token counting
    - Performance tracking
    """

    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {}
        self.performance_metrics: Dict[str, PerformanceMetrics] = {}
        self.template_versions: Dict[str, List[int]] = {}

        logger.info("Prompt engine initialized")

    def add_template(self, template: PromptTemplate) -> bool:
        """Add a prompt template, bumping version if template_id already exists."""
        if template.template_id in self.templates:
            existing = self.templates[template.template_id]
            template.version = existing.version + 1

            if template.template_id not in self.template_versions:
                self.template_versions[template.template_id] = []
            self.template_versions[template.template_id].append(existing.version)

        if not self._validate_template(template):
            raise ValueError(f"Invalid template: {template.template_id}")

        self.templates[template.template_id] = template

        metrics_key = f"{template.template_id}_v{template.version}"
        if metrics_key not in self.performance_metrics:
            self.performance_metrics[metrics_key] = PerformanceMetrics(
                template_id=template.template_id,
                template_version=template.version
            )

        logger.info(f"Added template: {template.template_id} v{template.version}")
        return True

    def get_template(self, template_id: str, version: Optional[int] = None) -> Optional[PromptTemplate]:
        """Get template by ID (latest version only; see source's own note)."""
        if template_id not in self.templates:
            return None

        template = self.templates[template_id]

        if version and version != template.version:
            logger.warning(f"Version {version} not available, returning latest")

        return template

    def list_templates(self, category: Optional[str] = None,
                        tags: Optional[List[str]] = None) -> List[PromptTemplate]:
        """List all templates with optional category/tag filtering."""
        templates = list(self.templates.values())

        if category:
            templates = [t for t in templates if t.category == category]

        if tags:
            templates = [
                t for t in templates
                if any(tag in t.tags for tag in tags)
            ]

        return templates

    def generate_prompt(self, template_id: str,
                         variables: Dict[str, Any],
                         context: Optional[Dict[str, Any]] = None) -> GeneratedPrompt:
        """Generate prompt from template via real variable substitution + token counting."""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        missing_vars = set(template.variables) - set(variables.keys())
        if missing_vars:
            raise ValueError(f"Missing variables: {missing_vars}")

        prompt = self._render_template(template.template, variables)
        tokens = self._count_tokens(prompt)

        logger.info(f"Generated prompt from {template_id}: {tokens} tokens")

        return GeneratedPrompt(
            prompt=prompt,
            template_id=template.template_id,
            template_version=template.version,
            tokens=tokens,
            variables_used=variables
        )

    def select_template(self, task: str, context: Dict[str, Any]) -> Optional[str]:
        """Rule-based candidate filtering by task keywords, then real performance-based scoring."""
        task_lower = task.lower()

        if "code" in task_lower or "review" in task_lower:
            candidates = [t for t in self.templates.values()
                          if t.category == "code_analysis"]
        elif "classify" in task_lower or "sentiment" in task_lower:
            candidates = [t for t in self.templates.values()
                          if t.category == "text_processing"]
        elif "question" in task_lower or "answer" in task_lower:
            candidates = [t for t in self.templates.values()
                          if t.category == "question_answering"]
        else:
            candidates = list(self.templates.values())

        if not candidates:
            return None

        best_template = None
        best_score = -1.0

        for template in candidates:
            metrics_key = f"{template.template_id}_v{template.version}"
            metrics = self.performance_metrics.get(metrics_key)

            if metrics:
                score = (metrics.avg_quality_score * 0.7 +
                         (metrics.total_uses / 100) * 0.3)

                if score > best_score:
                    best_score = score
                    best_template = template
            elif not best_template:
                best_template = template

        if best_template:
            logger.info(f"Selected template: {best_template.template_id} (score: {best_score:.2f})")
            return best_template.template_id

        return None

    def generate_few_shot_prompt(self, task_description: str,
                                  examples: List[Dict[str, str]],
                                  query: str,
                                  num_examples: int = 3) -> str:
        """Real few-shot prompt assembly from task description + examples + query."""
        examples = examples[:num_examples]

        prompt_parts = [task_description, ""]

        for i, example in enumerate(examples, 1):
            prompt_parts.append(f"Example {i}:")
            prompt_parts.append(f"Input: {example['input']}")
            prompt_parts.append(f"Output: {example['output']}")
            prompt_parts.append("")

        prompt_parts.append("Now process the following:")
        prompt_parts.append(f"Input: {query}")
        prompt_parts.append("Output:")

        prompt = "\n".join(prompt_parts)

        logger.info(f"Generated few-shot prompt with {len(examples)} examples")

        return prompt

    def track_performance(self, template_id: str, version: int,
                           success: bool, quality_score: float,
                           execution_time_ms: float, tokens: int):
        """Track prompt performance with real running-average updates."""
        metrics_key = f"{template_id}_v{version}"

        if metrics_key not in self.performance_metrics:
            self.performance_metrics[metrics_key] = PerformanceMetrics(
                template_id=template_id,
                template_version=version
            )

        metrics = self.performance_metrics[metrics_key]

        metrics.total_uses += 1
        if success:
            metrics.success_count += 1

        n = metrics.total_uses
        metrics.avg_quality_score = (
            (metrics.avg_quality_score * (n - 1) + quality_score) / n
        )
        metrics.avg_execution_time_ms = (
            (metrics.avg_execution_time_ms * (n - 1) + execution_time_ms) / n
        )
        metrics.avg_tokens = (
            (metrics.avg_tokens * (n - 1) + tokens) / n
        )

        logger.info(f"Tracked performance for {template_id}: {metrics.total_uses} uses")

    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics."""
        total_templates = len(self.templates)
        total_generations = sum(m.total_uses for m in self.performance_metrics.values())

        if self.performance_metrics:
            avg_quality = sum(m.avg_quality_score for m in self.performance_metrics.values()) / len(self.performance_metrics)
            avg_tokens = sum(m.avg_tokens for m in self.performance_metrics.values()) / len(self.performance_metrics)
        else:
            avg_quality = 0.0
            avg_tokens = 0.0

        most_used = None
        max_uses = 0
        for metrics in self.performance_metrics.values():
            if metrics.total_uses > max_uses:
                max_uses = metrics.total_uses
                most_used = metrics.template_id

        return {
            "total_templates": total_templates,
            "total_generations": total_generations,
            "avg_quality_score": round(avg_quality, 2),
            "avg_tokens_per_prompt": round(avg_tokens, 1),
            "most_used_template": most_used
        }

    def _validate_template(self, template: PromptTemplate) -> bool:
        """Validate template structure."""
        if not template.template_id or not template.template:
            return False

        for var in template.variables:
            if f"{{{{{var}}}}}" not in template.template:
                logger.warning(f"Variable {var} not found in template")

        return True

    def _render_template(self, template: str, variables: Dict[str, Any]) -> str:
        """
        Render template with variables.

        Simple Jinja2-like substitution:
        - {{variable}} - simple substitution
        - {{#list}} ... {{.}} ... {{/list}} - list iteration
        """
        result = template

        for key, value in variables.items():
            if isinstance(value, list):
                list_pattern = rf"{{\{{#{key}\}}}}.+?{{\{{/{key}\}}}}"
                match = re.search(list_pattern, result, re.DOTALL)

                if match:
                    list_template = match.group(0)
                    inner = re.search(r"{{#.+?}}(.+?){{/.+?}}", list_template, re.DOTALL)
                    if inner:
                        inner_template = inner.group(1)
                        rendered_items = []
                        for item in value:
                            rendered_item = inner_template.replace("{{.}}", str(item))
                            rendered_items.append(rendered_item)

                        result = result.replace(list_template, "".join(rendered_items))
            else:
                result = result.replace(f"{{{{{key}}}}}", str(value))

        return result

    def _count_tokens(self, text: str) -> int:
        """Simple token counting: 1 token ~ 4 characters (English)."""
        text = re.sub(r'\s+', ' ', text).strip()
        char_count = len(text)
        tokens = int(char_count / 4)
        return max(tokens, 1)


# ============================================================================
# RAGEngine - retrieval-augmented generation, adapted to call ALGO-16's
# VectorEngine directly in-process (see ADAPTATION note in module docstring)
# ============================================================================

class RAGEngine:
    """
    Retrieval-Augmented Generation Engine

    Features:
    - Context retrieval directly from an injected ALGO-16 VectorEngine
      (constructor-injected, real in-process call - no HTTP)
    - Prompt augmentation
    - Context ranking and filtering
    - Token-aware context selection
    """

    def __init__(self, vector_engine: VectorEngine, default_top_k: int = 5):
        """
        Args:
            vector_engine: a real algo_16_vector.VectorEngine instance
                (already initialized with a backend/dimension) to query
                directly in-process.
            default_top_k: default number of results to retrieve
        """
        self.vector_engine = vector_engine
        self.default_top_k = default_top_k

        logger.info("RAG engine initialized with direct in-process VectorEngine")

    def retrieve_context(self, query_vector: List[float], top_k: Optional[int] = None,
                          threshold: float = 0.0,
                          filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for a pre-computed query vector via a
        real, direct VectorEngine.search() call (see module docstring's
        ADAPTATION note for why this takes a vector, not raw text).

        Args:
            query_vector: pre-computed embedding matching the VectorEngine's dimension
            top_k: number of results (None for default)
            threshold: minimum similarity score (applied locally - VectorEngine.search()
                has no threshold parameter of its own)
            filter_dict: optional metadata filter forwarded to VectorEngine.search()

        Returns:
            List of context documents with scores
        """
        top_k = top_k or self.default_top_k

        try:
            search_result = self.vector_engine.search(query_vector, k=top_k, filter_dict=filter_dict)

            context_docs = []
            for result in search_result.get("results", []):
                if result.get("score", 0.0) < threshold:
                    continue
                context_docs.append({
                    "id": result.get("id"),
                    "content": (result.get("metadata") or {}).get("content", ""),
                    "score": result.get("score", 0.0),
                    "metadata": result.get("metadata", {})
                })

            logger.info(f"Retrieved {len(context_docs)} context documents")
            return context_docs

        except Exception as e:
            logger.error(f"Context retrieval error: {e}")
            return []

    def augment_prompt(self, base_prompt: str, context_docs: List[Dict[str, Any]],
                        max_context_length: int = 2000) -> str:
        """Augment prompt with retrieved context (pure function, unchanged from source)."""
        if not context_docs:
            return base_prompt

        context_parts = ["Context:\n"]
        current_length = 0

        for i, doc in enumerate(context_docs, 1):
            content = doc.get("content", "")
            score = doc.get("score", 0.0)

            if current_length + len(content) > max_context_length:
                remaining = max_context_length - current_length
                if remaining > 100:
                    content = content[:remaining] + "..."
                else:
                    break

            context_parts.append(f"{i}. (Score: {score:.2f}) {content}")
            current_length += len(content)

        context_section = "\n".join(context_parts)
        augmented = f"{context_section}\n\n{base_prompt}"

        logger.info(f"Augmented prompt with {len(context_docs)} context docs")

        return augmented

    def check_vector_service(self) -> bool:
        """
        Check if the injected VectorEngine is healthy. Real in-process
        health_check() call (see module docstring - no longer async,
        there is no I/O left to await).
        """
        try:
            health = self.vector_engine.health_check()
            return health.get("status") == "healthy"
        except Exception as e:
            logger.error(f"Vector service check failed: {e}")
            return False

    def format_context_for_display(self, context_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format context documents for API response (pure function, unchanged from source)."""
        formatted = []

        for doc in context_docs:
            formatted.append({
                "source": doc.get("id", "unknown"),
                "content": doc.get("content", "")[:200] + "..." if len(doc.get("content", "")) > 200 else doc.get("content", ""),
                "score": round(doc.get("score", 0.0), 3)
            })

        return formatted


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    print("=== ALGO-18 Adaptive Prompting smoke test ===")

    # --- PromptEngine: template versioning + rendering + token counting + selection ---
    engine = PromptEngine()

    tmpl_v1 = PromptTemplate(
        template_id="qa",
        name="QA Template",
        description="Answer a question given context",
        template="Context:\n{{context}}\n\nQuestion: {{question}}\nAnswer:",
        variables=["context", "question"],
        category="question_answering",
    )
    assert engine.add_template(tmpl_v1)
    assert engine.templates["qa"].version == 1

    # Re-adding the same template_id must bump the version (real versioning)
    tmpl_v2 = PromptTemplate(
        template_id="qa",
        name="QA Template v2",
        description="Answer a question given context, list-aware",
        template="Context:\n{{context}}\n\nSources:\n{{#sources}}- {{.}}\n{{/sources}}\nQuestion: {{question}}\nAnswer:",
        variables=["context", "question", "sources"],
        category="question_answering",
    )
    assert engine.add_template(tmpl_v2)
    assert engine.templates["qa"].version == 2
    assert engine.template_versions["qa"] == [1]
    print(f"Template versioning: qa is now v{engine.templates['qa'].version}, history={engine.template_versions['qa']}")

    generated = engine.generate_prompt(
        "qa",
        variables={
            "context": "Delentia OS ports real algorithms from a private monorepo.",
            "question": "What does ALGO-18 do?",
            "sources": ["prompt_engine.py", "rag_engine.py"],
        },
    )
    print(f"Generated prompt ({generated.tokens} tokens):\n{generated.prompt}")
    assert "prompt_engine.py" in generated.prompt and "rag_engine.py" in generated.prompt, \
        "real {{#list}}...{{/list}} iteration must have rendered both sources"
    assert generated.tokens >= 1

    # Missing-variable validation
    try:
        engine.generate_prompt("qa", variables={"context": "x"})
        raise AssertionError("expected ValueError for missing variables")
    except ValueError as e:
        print(f"Missing-variable validation raised as expected: {e}")

    # select_template(): real performance-weighted scoring
    engine.track_performance("qa", 2, success=True, quality_score=4.5, execution_time_ms=12.0, tokens=generated.tokens)
    engine.track_performance("qa", 2, success=True, quality_score=4.0, execution_time_ms=10.0, tokens=generated.tokens)
    selected = engine.select_template("Please answer this question about the repo", context={})
    print(f"select_template() -> {selected}")
    assert selected == "qa"

    few_shot = engine.generate_few_shot_prompt(
        "Classify sentiment as positive/negative.",
        examples=[{"input": "I love this", "output": "positive"}, {"input": "I hate this", "output": "negative"}],
        query="This is fine I guess",
    )
    print(f"Few-shot prompt:\n{few_shot}")
    assert "Example 1:" in few_shot and "Example 2:" in few_shot

    stats = engine.get_stats()
    print(f"PromptEngine stats: {stats}")
    assert stats["total_generations"] == 2
    assert stats["most_used_template"] == "qa"

    # --- RAGEngine: real direct in-process VectorEngine.search() call ---
    from rct_control_plane.algo_16_vector import FAISSBackend

    try:
        import faiss  # noqa: F401
        FAISS_INSTALLED = True
    except ImportError as e:
        FAISS_INSTALLED = False
        print(f"faiss-cpu is NOT importable in this environment: {e}")
        print("Skipping the RAGEngine/VectorEngine portion (same pyproject.toml gap as ALGO-16).")

    if FAISS_INSTALLED:
        dim = 8
        backend = FAISSBackend(index_type="flat", metric="cosine")
        backend.initialize(dimension=dim)
        vector_engine = VectorEngine(backend, dimension=dim)

        docs = [
            ("doc1", [1.0] * dim, {"content": "Delentia OS ports 41 algorithms from a private monorepo."}),
            ("doc2", [-1.0] * dim, {"content": "The Stardew-Delentia-Bridge mod is an unrelated side project."}),
            ("doc3", [0.9] * dim, {"content": "ALGO-16 is a real FAISS-backed vector search engine."}),
        ]
        vector_engine.index(
            vectors=[d[1] for d in docs],
            ids=[d[0] for d in docs],
            metadata=[d[2] for d in docs],
        )

        rag = RAGEngine(vector_engine, default_top_k=2)

        query_vector = [0.95] * dim  # should match doc1/doc3's cluster, not doc2
        context_docs = rag.retrieve_context(query_vector, top_k=2, threshold=0.0)
        print(f"RAGEngine.retrieve_context() -> {context_docs}")
        assert len(context_docs) == 2
        retrieved_ids = {d["id"] for d in context_docs}
        assert "doc2" not in retrieved_ids, "the dissimilar doc2 must not be in top-2 for a doc1/doc3-biased query"

        augmented = rag.augment_prompt("Answer the question below.", context_docs)
        print(f"Augmented prompt:\n{augmented}")
        assert "Context:" in augmented
        assert "Answer the question below." in augmented

        healthy = rag.check_vector_service()
        print(f"RAGEngine.check_vector_service() -> {healthy}")
        assert healthy is True

        displayed = rag.format_context_for_display(context_docs)
        print(f"format_context_for_display() -> {displayed}")
        assert len(displayed) == 2

        # Threshold filtering (applied locally, since VectorEngine.search() has none)
        high_threshold_docs = rag.retrieve_context(query_vector, top_k=3, threshold=1.01)
        print(f"retrieve_context() with an unreachable threshold -> {high_threshold_docs}")
        assert high_threshold_docs == [], "threshold filtering must actually exclude everything above cosine's 1.0 max"

    print("=== ALGO-18 Adaptive Prompting: ALL ASSERTIONS PASSED ===")

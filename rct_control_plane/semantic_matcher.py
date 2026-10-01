"""
Semantic Matcher — Shared module from Analysearch Phase 3
Copied from analysearch-intent/app/core/semantic_matcher.py for kernel use.

Ported verbatim from Delentia-Private-OS/rct_platform/microservices/kernel/
semantic_matcher.py (Round 22 Phase 9) — its optional WangchanBERTa path
already has a real try/except ImportError fallback, so it degrades safely
to the Jaccard-composite path here where thai_embedding_engine isn't
importable.

Computes semantic similarity between queries and document sets using:
  - JACCARD mode:       token-level Jaccard + n-gram overlap (original)
  - WANGCHANBERTA mode: WangchanBERTa sentence embeddings (Thai-optimised)
  - AUTO mode (default): WangchanBERTa when available, fallback to Jaccard
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

_THAI_RANGE = re.compile(r'[฀-๿]')


class EmbeddingMode(str, Enum):
    JACCARD       = "jaccard"        # Pure token Jaccard (always available)
    WANGCHANBERTA = "wangchanberta"  # Thai sentence embeddings
    AUTO          = "auto"           # WangchanBERTa if available, else Jaccard


def _tokenize(text: str) -> set[str]:
    """Lowercase word-token set, stripping punctuation.
    For Thai text (no word boundaries), also produces character n-grams."""
    words = set(re.findall(r"[a-zA-Z฀-๿]{2,}", text.lower()))
    tokens = set()
    for w in words:
        tokens.add(w)
        # If the token is a Thai sequence (no word boundaries),
        # generate character bigrams and trigrams for partial matching
        if len(w) >= 2 and _THAI_RANGE.search(w):
            for n in (2, 3):
                for i in range(len(w) - n + 1):
                    tokens.add(w[i:i + n])
    return tokens


class SemanticMatcher:
    """
    Token-level semantic matcher for Analysearch Phase 3.
    Supports Jaccard (original) and WangchanBERTa (Thai embeddings) modes.
    """

    def __init__(
        self,
        min_token_length: int = 2,
        mode: EmbeddingMode = EmbeddingMode.AUTO,
    ):
        self.min_token_length = min_token_length
        self.mode = mode
        # Any, not object: ThaiEmbeddingEngine lives in the private
        # rct_platform package (only imported lazily below, may not be
        # importable at all in a public checkout), so there is no real
        # static type to name here - matching algo_16_vector.py's
        # faiss_index precedent for the same lazy-optional-dependency shape.
        self._embedding_engine: Optional[Any] = None

    def _get_embedding_engine(self) -> Optional[Any]:
        """Lazily load ThaiEmbeddingEngine; return None on ImportError."""
        if self._embedding_engine is not None:
            return self._embedding_engine
        try:
            from rct_platform.microservices.kernel.thai_embedding_engine import (
                ThaiEmbeddingEngine,
            )
            engine = ThaiEmbeddingEngine.instance()
            # Only store if actually available (model loaded successfully)
            if engine.available:
                self._embedding_engine = engine
            return self._embedding_engine
        except Exception:
            return None

    def compute_jaccard(self, text_a: str, text_b: str) -> float:
        """Compute Jaccard similarity: |A ∩ B| / |A ∪ B|."""
        tokens_a = _tokenize(text_a)
        tokens_b = _tokenize(text_b)
        if not tokens_a and not tokens_b:
            return 1.0
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        return intersection / union

    def semantic_similarity(self, text_a: str, text_b: str) -> float:
        """
        Compute similarity using the configured mode.
        AUTO/WANGCHANBERTA: use embedding cosine similarity if available.
        Fallback or JACCARD: composite Jaccard + overlap score.
        Result is clamped to [0.0, 1.0].
        """
        if self.mode in (EmbeddingMode.AUTO, EmbeddingMode.WANGCHANBERTA):
            engine = self._get_embedding_engine()
            if engine is not None:
                try:
                    return engine.cosine_similarity(text_a, text_b)
                except Exception:
                    pass  # Fall through to Jaccard

        return self._jaccard_composite(text_a, text_b)

    def _jaccard_composite(self, text_a: str, text_b: str) -> float:
        """
        Composite similarity: Jaccard + length-normalised overlap bonus.
        Result is clamped to [0.0, 1.0].
        """
        jaccard = self.compute_jaccard(text_a, text_b)
        tokens_a = _tokenize(text_a)
        tokens_b = _tokenize(text_b)
        if not tokens_a or not tokens_b:
            return jaccard
        overlap_ab = len(tokens_a & tokens_b) / len(tokens_a)
        overlap_ba = len(tokens_a & tokens_b) / len(tokens_b)
        soft = (overlap_ab + overlap_ba) / 2
        score = 0.6 * jaccard + 0.4 * soft
        return round(min(max(score, 0.0), 1.0), 4)

    def match(
        self,
        query: str,
        candidates: List[str],
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> List[Dict]:
        """
        Rank candidates by semantic similarity to query.
        Returns dicts with keys: ``text``, ``score``, ``rank``.
        """
        if not query or not candidates:
            return []

        scored: List[Tuple[float, int, str]] = []
        for idx, candidate in enumerate(candidates):
            score = self.semantic_similarity(query, candidate)
            if score >= threshold:
                scored.append((score, idx, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {"text": text, "score": score, "rank": rank + 1}
            for rank, (score, _idx, text) in enumerate(scored[:top_k])
        ]


# ---------------------------------------------------------------------------------------------
# Round 52: memory recall compares what a text is ABOUT, not every word in it.
#
# The plain word-set matcher above counts "the", "is", "my" as evidence and treats "releases",
# "release" and "manages"/"manager" as unrelated words, so a fact stored in one wording was
# missed (or ranked behind noise) when asked in another (scripts/measure_memory_retrieval.py).
# ContentMatcher drops function words and folds a few English endings; Thai tokens (character
# n-grams) pass through untouched. It is used by AgentMemory only: the intent check and the other
# users of SemanticMatcher keep their tuned thresholds.
# ---------------------------------------------------------------------------------------------

_STOPWORDS = frozenset("""
a an the and or but if then than so as at by for from in into of on onto to up with without about over under
is are was were be been being am do does did done have has had having can could will would shall should may might must
i me my mine we us our ours you your yours he him his she her hers it its they them their theirs this that these those
what which who whom whose when where why how whether there here not no nor
tell give show name find list please just also very any some each every all more most other such own same too
""".split())
_ENDINGS = ("ations", "ation", "ingly", "ments", "ment", "ness", "ings", "ing", "ers", "ies", "ed", "er", "es", "s")


def _stem(word: str) -> str:
    if len(word) <= 3 or not word.isascii():
        return word
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            word = word[: -len(ending)] + ("y" if ending == "ies" else "")
            break
    # release / releases / released, manage / manager / manages, invoice / invoices: one stem each
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]
    return word


def content_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in _tokenize(text):
        if token in _STOPWORDS:
            continue
        terms.add(_stem(token))
    return terms


class ContentMatcher(SemanticMatcher):
    """SemanticMatcher whose fallback score compares stemmed content words only."""

    def _jaccard_composite(self, text_a: str, text_b: str) -> float:
        a, b = content_terms(text_a), content_terms(text_b)
        if not a and not b:
            return 1.0 if text_a.strip() == text_b.strip() else 0.0
        if not a or not b:
            return 0.0
        shared = len(a & b)
        jaccard = shared / len(a | b)
        soft = (shared / len(a) + shared / len(b)) / 2
        return round(min(max(0.6 * jaccard + 0.4 * soft, 0.0), 1.0), 4)

"""
Analysearch Phase 3 — Semantic Matcher
Computes semantic similarity between queries and document sets using
token-level Jaccard similarity and keyword overlap scoring.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

# Detects Thai Unicode range (U+0E00–U+0E7F)
_THAI_RANGE = re.compile(r'[\u0E00-\u0E7F]')


def _tokenize(text: str) -> set[str]:
    """Lowercase word-token set. For Thai sequences (no word boundaries),
    also generates character bigrams and trigrams for partial matching."""
    words = set(re.findall(r"[a-zA-Z\u0E00-\u0E7F]{2,}", text.lower()))
    tokens = set()
    for w in words:
        tokens.add(w)
        # Thai has no spaces between words — generate n-grams for overlap
        if len(w) >= 2 and _THAI_RANGE.search(w):
            for n in (2, 3):
                for i in range(len(w) - n + 1):
                    tokens.add(w[i:i + n])
    return tokens


class SemanticMatcher:
    """
    Token-level semantic matcher for Analysearch Phase 3.

    Uses Jaccard similarity extended with TF-weighted scoring.
    """

    def __init__(self, min_token_length: int = 2):
        self.min_token_length = min_token_length

    # ── Core similarity ─────────────────────────────────────────────────

    def compute_jaccard(self, text_a: str, text_b: str) -> float:
        """
        Compute Jaccard similarity: |A ∩ B| / |A ∪ B|.
        Returns 0.0 for empty inputs, 1.0 for identical token sets.
        """
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
        Composite similarity: Jaccard + length-normalised overlap bonus.
        Result is clamped to [0.0, 1.0].
        """
        jaccard = self.compute_jaccard(text_a, text_b)
        tokens_a = _tokenize(text_a)
        tokens_b = _tokenize(text_b)
        if not tokens_a or not tokens_b:
            return jaccard
        # Soft overlap: bidirectional containment ratio
        overlap_ab = len(tokens_a & tokens_b) / len(tokens_a)
        overlap_ba = len(tokens_a & tokens_b) / len(tokens_b)
        soft = (overlap_ab + overlap_ba) / 2
        score = 0.6 * jaccard + 0.4 * soft
        return round(min(max(score, 0.0), 1.0), 4)

    # ── Matching ─────────────────────────────────────────────────────────

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

    def batch_match(
        self,
        queries: List[str],
        corpus: List[str],
        top_k: int = 3,
    ) -> Dict[str, List[Dict]]:
        """
        Match each query against the corpus. Returns a dict keyed by query.
        """
        return {q: self.match(q, corpus, top_k=top_k) for q in queries}

    # ── Utility ──────────────────────────────────────────────────────────

    def agreement_score(self, responses: List[str]) -> float:
        """
        Compute pairwise Jaccard agreement across a list of responses.
        Returns 1.0 for a single response or empty list.
        """
        if len(responses) <= 1:
            return 1.0
        pairs = 0
        total = 0.0
        for i in range(len(responses)):
            for j in range(i + 1, len(responses)):
                total += self.compute_jaccard(responses[i], responses[j])
                pairs += 1
        return round(total / pairs, 4) if pairs else 1.0

    def find_common_theme(self, texts: List[str]) -> List[str]:
        """
        Extract tokens that appear in ALL input texts (common themes).
        """
        if not texts:
            return []
        token_sets = [_tokenize(t) for t in texts]
        common = token_sets[0].copy()
        for ts in token_sets[1:]:
            common &= ts
        return sorted(common)

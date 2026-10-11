"""
Round 69: how memories are ordered when the embedding model is on (DELENTIA_MEMORY_EMBED=ollama). One place, measured in research/recall_lab_r69.py.

 * The ORDER uses the raw cosine (no clipping: the calibrated value of Round 68 clips at 1.0 and can tie, which cost 2 of 30 questions on the development set).
 * A question that is mostly Thai (at least 20% of its letters) leans on BM25 over character trigrams instead (dense weight 0.25), because an English embedding model cannot read Thai:
   hit@3 on 40 Thai questions was 4 with the embedding alone and 20 with this fusion on the set it was chosen on (H2); the second Thai set H5 was measured once, see the Round 69 document.
 * A memory that has no vector yet (the service was down when it was stored and the backfill has not reached it) is scored from its words alone, on the cosine scale, so it can still be found.
 * `relevance`, the number D reads, is NOT the order score: it is max(lexical similarity, calibrated cosine) as in Round 68, so noise from the model never raises D.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from rct_control_plane import memory_embeddings
from rct_control_plane.memory_lexical import BM25, identifier_tokens, thai_fraction, tokens, zscores

THAI_QUESTION_AT = 0.20                         # share of Thai letters from which a question is treated as Thai
DENSE_WEIGHT_THAI = 0.25                        # a model that cannot read Thai (nomic-embed-text): chosen on H2 (the Thai development set); English questions use the cosine alone
DENSE_WEIGHT_THAI_READS = 0.80                  # a model that reads Thai (bge-m3): chosen on H2 by the rule written before bge-m3 was run (best hit@3, then hit@1); H5 was measured once with it
NO_VECTOR_BASE, NO_VECTOR_SLOPE = 0.45, 0.35    # a memory with no vector: cosine-like score from its word overlap (0.45 + 0.35 * jaccard)
EXACT_IDENTIFIER_BONUS = 0.15                   # a memory that contains an identifier the question typed exactly outranks a merely similar one (a bare id: the embedding found 18 of 22, BM25 22 of 22)

Ranked = Tuple[float, float, float, Dict[str, Any]]


def rank(query: str, candidates: List[Dict[str, Any]], cosines: Dict[str, float], lexical: Dict[str, float], *, importance_bonus: Optional[Dict[str, float]] = None) -> List[Ranked]:
    """(order score, relevance, lexical similarity, candidate), best first. `cosines` maps memory id -> raw cosine for the memories that have a vector; `lexical` maps memory TEXT -> Jaccard similarity."""
    dense = []
    for c in candidates:
        cos = cosines.get(c["id"])
        dense.append(cos if cos is not None else NO_VECTOR_BASE + NO_VECTOR_SLOPE * lexical.get(c["content"], 0.0))
    if thai_fraction(query) >= THAI_QUESTION_AT and len(candidates) > 1:
        zd, zl = zscores(dense), zscores(BM25([c["content"] for c in candidates]).scores(query))
        weight = DENSE_WEIGHT_THAI_READS if memory_embeddings.reads_thai() else DENSE_WEIGHT_THAI
        order = [weight * d + (1 - weight) * s for d, s in zip(zd, zl, strict=True)]
    else:
        order = dense
        wanted = set(identifier_tokens(query))
        if wanted:                                                       # an exact id, host, e-mail, code or time in the question: a memory holding it exactly gets a fixed bonus
            order = [score + (EXACT_IDENTIFIER_BONUS if wanted & set(tokens(c["content"])) else 0.0) for c, score in zip(candidates, order, strict=True)]
    out: List[Ranked] = []
    sighted = memory_embeddings.reads_thai()
    thai_query = thai_fraction(query) >= THAI_QUESTION_AT
    for c, score in zip(candidates, order, strict=True):
        lex = lexical.get(c["content"], 0.0)
        cos = cosines.get(c["id"])
        # A model that cannot read Thai puts every Thai text on almost the same point (cosine ~1.0): such a cosine says nothing, and "calibrated" it would read as a perfect match for ANY Thai question.
        # Measured through the loop with nomic-embed-text: 10 of 20 unrelated questions still showed a memory and raised D by up to 0.15. For those pairs only the words count towards relevance.
        blind = not sighted and (thai_query or thai_fraction(c["content"]) >= THAI_QUESTION_AT)
        relevance = max(lex, memory_embeddings.relevance(cos)) if cos is not None and not blind else lex
        out.append((score + (importance_bonus or {}).get(c["id"], 0.0), relevance, lex, c))
    out.sort(key=lambda t: t[0], reverse=True)
    return out

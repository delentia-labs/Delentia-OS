"""
Round 69: a plain BM25 over a person's memories, used beside the embedding model.

Why it exists (research/recall_lab_r69.py, held-out sets measured once): nomic-embed-text is an English model. On 40 Thai questions it found the right memory in its top 3 for 4 of them; BM25 over overlapping
character trigrams (Thai has no spaces, so a trigram needs no word segmenter) found 17, and a fusion that leans on BM25 for Thai questions found 20 on the set it was chosen on. For English questions the
embedding alone ranked best, so BM25 is added only where the language calls for it (see memory_ranking.py).

No dependencies, no state: the index is built from the candidate texts of one recall (the person's own memories, already loaded by the caller).
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Sequence

_STOP = frozenset("the a an of and or to in on at for is are was were be been it its this that with from by as our we you your their they them he she his her who whom what which when where how do does did "
                  "can may must should will would any all each every per".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.@:/#,-]*|[฀-๿]+")
_JOINERS = re.compile(r"[-_./@:,]")


def thai_fraction(text: str) -> float:
    """The share of the letters of `text` that are Thai (0 when there are no letters)."""
    letters = [c for c in str(text or "") if c.isalpha()]
    return sum(1 for c in letters if "฀" <= c <= "๿") / len(letters) if letters else 0.0


def tokens(text: str) -> List[str]:
    out: List[str] = []
    for raw in _TOKEN.findall(str(text or "").lower()):
        if "฀" <= raw[0] <= "๿":
            out.extend(raw[i:i + 3] for i in range(max(1, len(raw) - 2)))          # overlapping character trigrams
        else:
            raw = raw.strip(".:/#,-_")
            if len(raw) >= 2 and raw not in _STOP:
                out.append(raw)
                if _JOINERS.search(raw):                                          # "stg-db-1" is also found by "stg" and "db"
                    out.extend(p for p in _JOINERS.split(raw) if len(p) >= 2 and p not in _STOP)
    return out


_IDENTIFIER_JOINER = re.compile(r"[-_.@#:/]|\d,\d")


def identifier_tokens(query: str) -> List[str]:
    """Tokens of the query that look like an identifier a person would type exactly: an id, a host, an e-mail, a path piece, a code, a time ("stg-db-1", "northwind-core", "4433", "WH-LKB", "12:00").
    A joiner inside, or letters mixed with digits, or four or more digits. Plain words and short numbers are not identifiers."""
    out: List[str] = []
    for raw in _TOKEN.findall(str(query or "").lower()):
        if "\u0e00" <= raw[0] <= "\u0e7f":
            continue
        raw = raw.strip(".:/#,-_")
        if len(raw) < 3 or raw in _STOP:
            continue
        has_digit, has_alpha = any(c.isdigit() for c in raw), any(c.isalpha() for c in raw)
        if _IDENTIFIER_JOINER.search(raw) or (has_digit and has_alpha) or (has_digit and not has_alpha and len(raw) >= 4):
            out.append(raw)
    return out


class BM25:
    def __init__(self, docs: Sequence[str], k1: float = 1.2, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self._docs = [tokens(d) for d in docs]
        self._avg = (sum(len(d) for d in self._docs) / len(self._docs)) if self._docs else 1.0
        self._avg = self._avg or 1.0
        frequency: Dict[str, int] = {}
        self._tf: List[Dict[str, int]] = []
        for d in self._docs:
            counts: Dict[str, int] = {}
            for t in d:
                counts[t] = counts.get(t, 0) + 1
            self._tf.append(counts)
            for t in counts:
                frequency[t] = frequency.get(t, 0) + 1
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in frequency.items()}

    def scores(self, query: str) -> List[float]:
        wanted = set(tokens(query))
        out: List[float] = []
        for doc, counts in zip(self._docs, self._tf, strict=True):
            norm = self.k1 * (1 - self.b + self.b * len(doc) / self._avg)
            out.append(sum(self._idf.get(t, 0.0) * counts[t] * (self.k1 + 1) / (counts[t] + norm) for t in wanted if t in counts))
        return out


def zscores(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) or 1.0
    return [(v - mean) / sd for v in values]

"""
Round 69: the recall lab. Which way of ranking memories finds the right one? Criteria and the adoption rule are in research/round69_criteria.md (written before this file).

    python research/recall_lab_r69.py --set dev                       # variants A..F on the Round 68 set (used to CHOOSE)
    python research/recall_lab_r69.py --set h1 --variants A,E          # a held-out set: only variants already frozen on DEV; each held-out set is measured ONCE
    python research/recall_lab_r69.py --set scale

The lab ranks raw vectors and token statistics (no database, no LLM) so that many variants run in seconds; the variant that wins is then built into AgentMemory and checked end to end by the tests.
Embeddings come from the local Ollama (nomic-embed-text) and are cached in a file outside the repository.

Variants
  A  the shipped fusion: max(lexical Jaccard, calibrated cosine), the calibrated cosine clipped to [0, 1]
  B  A with nomic's task prefixes ("search_query: " / "search_document: ")
  C  rank on the raw cosine (no clipping, so nothing ties at 1.0)
  D  BM25 (IDF over this person's memories; words for Latin text, character trigrams for Thai) instead of Jaccard, alone
  E  weighted fusion of the z-scored cosine and the z-scored BM25, the weight chosen on DEV only
  F  reciprocal-rank fusion (k = 60) of C and D
  G  query expansion: the local model writes 3 paraphrases of the question; the best cosine over the 4 queries, plus a little BM25 (weight as E)
  S  store-time questions: the local model writes 3 questions each memory answers (once, at store time); the best cosine over the memory and its questions
  GS both
  L  language-aware: C for English questions, the 0.25-dense fusion for Thai ones (weights from DEV and H2; H5 is the test)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))
CACHE = Path(os.environ.get("RECALL_LAB_CACHE", str(Path.home() / ".recall_lab_cache.json")))
OLLAMA = os.environ.get("DELENTIA_OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("RECALL_LAB_MODEL", "nomic-embed-text")
Q_PREFIX, D_PREFIX = "search_query: ", "search_document: "

_cache: Dict[str, List[float]] = {}


def _load_cache() -> None:
    global _cache
    if not _cache and CACHE.exists():
        _cache = json.loads(CACHE.read_text(encoding="utf-8"))


def _save_cache() -> None:
    CACHE.write_text(json.dumps(_cache), encoding="utf-8")


def embed(texts: Sequence[str], prefix: str = "") -> List[List[float]]:
    _load_cache()
    keys = [hashlib.sha256(f"{MODEL}|{prefix}|{t}".encode("utf-8")).hexdigest() for t in texts]
    missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in _cache]
    for start in range(0, len(missing), 64):
        chunk = missing[start:start + 64]
        req = urllib.request.Request(OLLAMA + "/api/embed", data=json.dumps({"model": MODEL, "input": [prefix + t for _k, t in chunk], "keep_alive": "30m"}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        vectors = json.loads(urllib.request.urlopen(req, timeout=300).read())["embeddings"]
        for (k, _t), v in zip(chunk, vectors, strict=True):
            _cache[k] = v
    if missing:
        _save_cache()
    return [_cache[k] for k in keys]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0


# ---------------------------------------------------------------- the local model (variants G and S; opt-in features, they need a model)

LLM_CACHE = Path(os.environ.get("RECALL_LAB_LLM_CACHE", str(Path.home() / ".recall_lab_llm_cache.json")))
LLM_MODEL = os.environ.get("RECALL_LAB_LLM", "qwen2.5:7b")
_llm: Dict[str, List[str]] = {}
G_PROMPT = ("Rewrite the question below in 3 different ways. Use different words (synonyms, other phrasing) but ask for the same thing. "
            "Output exactly 3 lines, one rewrite per line, no numbering, no extra text.\n\nQuestion: ")
S_PROMPT = ("Below is a note. Write 3 different short questions that this note answers. Use different words than the note (synonyms, other phrasing). "
            "Output exactly 3 lines, one question per line, no numbering, no extra text.\n\nNote: ")


def llm_lines(kind: str, text: str) -> List[str]:
    global _llm
    if not _llm and LLM_CACHE.exists():
        _llm = json.loads(LLM_CACHE.read_text(encoding="utf-8"))
    key = hashlib.sha256(f"{LLM_MODEL}|{kind}|{text}".encode("utf-8")).hexdigest()
    if key not in _llm:
        prompt = (G_PROMPT if kind == "G" else S_PROMPT) + text
        req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps({"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False, "keep_alive": "30m",
                                                                         "options": {"temperature": 0.2, "num_predict": 120}}).encode("utf-8"), headers={"Content-Type": "application/json"})
        started = time.perf_counter()
        body = json.loads(urllib.request.urlopen(req, timeout=600).read())
        lines = [re.sub(r"^[\s\-*\d.)]+", "", ln).strip() for ln in body["message"]["content"].splitlines()]
        _llm[key] = [ln for ln in lines if len(ln) >= 6][:3]
        _llm[key + ":seconds"] = [str(round(time.perf_counter() - started, 1))]
        LLM_CACHE.write_text(json.dumps(_llm, ensure_ascii=False), encoding="utf-8")
    return _llm[key]


# ---------------------------------------------------------------- lexical

_STOP = frozenset("the a an of and or to in on at for is are was were be been it its this that with from by as our we you your their they them he she his her who whom what which when where how do does did "
                  "can may must should will would any all each every per".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.@:/#-]*|[฀-๿]+")


def tokens(text: str) -> List[str]:
    out: List[str] = []
    for raw in _TOKEN.findall(text.lower()):
        if "฀" <= raw[0] <= "๿":
            out.extend([raw[i:i + 3] for i in range(max(1, len(raw) - 2))])      # Thai has no spaces: overlapping character trigrams
        else:
            raw = raw.strip(".:/#-_")
            if len(raw) >= 2 and raw not in _STOP:
                out.append(raw)
                if re.search(r"[-_./@:]", raw):
                    out.extend(p for p in re.split(r"[-_./@:]", raw) if len(p) >= 2 and p not in _STOP)
    return out


class BM25:
    def __init__(self, docs: Sequence[str], k1: float = 1.2, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [tokens(d) for d in docs]
        self.avg = (sum(len(d) for d in self.docs) / len(self.docs)) or 1.0
        df: Dict[str, int] = {}
        for d in self.docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = []
        for d in self.docs:
            f: Dict[str, int] = {}
            for t in d:
                f[t] = f.get(t, 0) + 1
            self.tf.append(f)

    def score(self, query: str) -> List[float]:
        q = set(tokens(query))
        out = []
        for d, f in zip(self.docs, self.tf, strict=True):
            s = 0.0
            for t in q:
                if t in f:
                    s += self.idf.get(t, 0.0) * f[t] * (self.k1 + 1) / (f[t] + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            out.append(s)
        return out


def jaccard_scores(query: str, docs: Sequence[str]) -> List[float]:
    from rct_control_plane.semantic_matcher import SemanticMatcher
    matcher = SemanticMatcher()
    by_text = {m["text"]: m["score"] for m in matcher.match(query, list(docs), top_k=len(docs), threshold=0.0)}
    return [by_text.get(d, 0.0) for d in docs]


# ---------------------------------------------------------------- the variants

FLOOR, SPAN = 0.50, 0.15


def calibrated(cos: float) -> float:
    return max(0.0, min(1.0, (cos - FLOOR) / SPAN))


def zscore(values: Sequence[float]) -> List[float]:
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) or 1.0
    return [(v - mean) / sd for v in values]


def ranks(scores: Sequence[float]) -> List[int]:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    r = [0] * len(scores)
    for pos, i in enumerate(order):
        r[i] = pos + 1
    return r


class Corpus:
    def __init__(self, docs: List[str]) -> None:
        self.docs = docs
        self.plain = embed(docs)
        self.prefixed = embed(docs, D_PREFIX)
        self.bm25 = BM25(docs)
        self._sq: Dict[int, List[List[float]]] = {}

    def store_question_vectors(self) -> List[List[List[float]]]:
        """S: the vectors of the questions the model wrote for each memory (generated once per memory, at store time)."""
        if not self._sq:
            for i, d in enumerate(self.docs):
                qs = llm_lines("S", d)
                self._sq[i] = embed(qs) if qs else []
        return [self._sq[i] for i in range(len(self.docs))]

    def scores(self, variant: str, query: str, weight: float = 0.7) -> List[float]:
        n = len(self.docs)
        if variant == "A":
            qv = embed([query])[0]
            jac = jaccard_scores(query, self.docs)
            return [max(jac[i], calibrated(cosine(qv, self.plain[i]))) for i in range(n)]
        if variant == "B":
            qv = embed([query], Q_PREFIX)[0]
            jac = jaccard_scores(query, self.docs)
            return [max(jac[i], calibrated(cosine(qv, self.prefixed[i]))) for i in range(n)]
        if variant in ("C", "E", "F", "E-prefix"):
            prefixed = variant == "E-prefix"
            qv = embed([query], Q_PREFIX if prefixed else "")[0]
            vec = self.prefixed if prefixed else self.plain
            cos = [cosine(qv, vec[i]) for i in range(n)]
            if variant == "C":
                return cos
            lex = self.bm25.score(query)
            if variant == "F":
                rc, rl = ranks(cos), ranks(lex)
                return [1.0 / (60 + rc[i]) + 1.0 / (60 + rl[i]) for i in range(n)]
            zc, zl = zscore(cos), zscore(lex)
            return [weight * zc[i] + (1 - weight) * zl[i] for i in range(n)]
        if variant in ("G", "S", "GS"):
            queries = [query] + (llm_lines("G", query) if variant in ("G", "GS") else [])
            qvs = embed(queries)
            sq = self.store_question_vectors() if variant in ("S", "GS") else None
            cos = []
            for i in range(n):
                best = max(cosine(qv, self.plain[i]) for qv in qvs)
                if sq is not None:
                    best = max([best] + [cosine(qv, v) for qv in qvs for v in sq[i]])
                cos.append(best)
            lex = self.bm25.score(query)
            zc, zl = zscore(cos), zscore(lex)
            return [weight * zc[i] + (1 - weight) * zl[i] for i in range(n)]
        if variant == "L":                                                   # language-aware: raw cosine for English questions, 0.25 dense + 0.75 BM25 (character trigrams) for Thai ones
            letters = [c for c in query if c.isalpha()]
            thai = sum(1 for c in letters if "฀" <= c <= "๿") / (len(letters) or 1)
            return self.scores("C", query) if thai < 0.2 else self.scores("E", query, 0.25)
        if variant == "L2":                                                  # multilingual model: C for questions under 20% Thai letters, the fusion with the Thai weight chosen on H2 for the others
            letters = [c for c in query if c.isalpha()]
            thai = sum(1 for c in letters if "\u0e00" <= c <= "\u0e7f") / (len(letters) or 1)
            return self.scores("C", query) if thai < 0.2 else self.scores("E", query, float(os.environ.get("RECALL_LAB_W_TH", "0.8")))
        if variant == "J":                                                   # the shipped lexical matcher alone (what memory uses with embeddings off)
            return jaccard_scores(query, self.docs)
        if variant == "D":
            return self.bm25.score(query)
        raise ValueError(variant)


def evaluate(corpus: Corpus, qa: List[Tuple[str, str]], variant: str, weight: float = 0.7, ks: Tuple[int, ...] = (1, 3, 5, 10)) -> Dict[str, Any]:
    from recall_dataset_r69 import _boundary
    rows, hits = [], {k: 0 for k in ks}
    for question, answer in qa:
        sc = corpus.scores(variant, question, weight)
        order = sorted(range(len(sc)), key=lambda i: -sc[i])
        pat = _boundary(answer)
        rank = next((pos + 1 for pos, i in enumerate(order) if pat.search(corpus.docs[i].lower())), None)
        for k in ks:
            hits[k] += int(rank is not None and rank <= k)
        rows.append({"question": question, "answer": answer, "rank": rank, "top": [corpus.docs[i] for i in order[:3]]})
    return {"variant": variant, "weight": weight, "n": len(qa), **{f"hit@{k}": hits[k] for k in ks}, "misses@3": [r["question"] for r in rows if not (r["rank"] and r["rank"] <= 3)], "rows": rows}


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - m) / d, 3), round((c + m) / d, 3)


# ---------------------------------------------------------------- the sets

def load_set(name: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    import recall_dataset_r68 as dev
    import recall_dataset_r69 as h
    if name == "dev":
        d = dev.dataset()
        texts = [f["text"] for f in d["facts"]] + list(d["distractors"])
        random.Random(5).shuffle(texts)
        return texts, [(f["question"], f["answer"]) for f in d["facts"]]
    h.verify_frozen()
    if name in ("h1", "h2"):
        d = h.dataset()[name]
        texts = [f["text"] for f in d["facts"]] + list(d["distractors"])
        random.Random(7).shuffle(texts)
        return texts, [(f["question"], f["answer"]) for f in d["facts"]]
    if name == "h5":
        import recall_dataset_r69b as h5
        h5.verify_frozen()
        d = h5.dataset()
        texts = [f["text"] for f in d["facts"]] + list(d["distractors"])
        random.Random(7).shuffle(texts)
        return texts, [(f["question"], f["answer"]) for f in d["facts"]]
    if name == "h4":                                                         # cloze: the H1 facts with the answer cut out (shares the fact's own words)
        d = h.dataset()["h1"]
        texts = [f["text"] for f in d["facts"]] + list(d["distractors"])
        random.Random(7).shuffle(texts)
        qa = []
        for f in d["facts"]:
            pat = h._boundary(f["answer"])
            cloze = pat.sub("____", f["text"].lower(), count=1)
            qa.append((cloze, f["answer"]))
        return texts, qa
    if name == "scale":
        d = dev.dataset()
        texts = [f["text"] for f in d["facts"]] + list(d["distractors"]) + h.scale_distractors()
        random.Random(5).shuffle(texts)
        return texts, [(f["question"], f["answer"]) for f in d["facts"]]
    raise SystemExit(f"unknown set {name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True, choices=["dev", "h1", "h2", "h3", "h4", "h5", "scale"])
    ap.add_argument("--variants", default="A,B,C,D,E,F")
    ap.add_argument("--weight", type=float, default=0.7, help="the weight of variant E (chosen on DEV)")
    ap.add_argument("--sweep", action="store_true", help="dev only: try the weights 0..1 for E")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    texts, qa = load_set(args.set)
    started = time.perf_counter()
    corpus = Corpus(texts)
    result: Dict[str, Any] = {"set": args.set, "questions": len(qa), "texts": len(texts), "results": []}
    if args.sweep:
        assert args.set in ("dev", "h2"), "weights are chosen on DEV (English) or on H2 (Thai: observed in Round 69, now development data for the Thai weight; H5 is the Thai holdout)"
        for w in [round(i / 10, 1) for i in range(0, 11)]:
            r = evaluate(corpus, qa, "E", w)
            result["results"].append({k: v for k, v in r.items() if k != "rows"})
            print(f"E w={w}: hit@1 {r['hit@1']} hit@3 {r['hit@3']} hit@5 {r['hit@5']} hit@10 {r['hit@10']}")
    else:
        for v in args.variants.split(","):
            r = evaluate(corpus, qa, v, args.weight)
            lo, hi = wilson(r["hit@3"], r["n"])
            result["results"].append({k: x for k, x in r.items() if k != "rows"} | {"hit@3_wilson95": [lo, hi], "rows": r["rows"]})
            print(f"{v}: hit@1 {r['hit@1']}/{r['n']}  hit@3 {r['hit@3']}/{r['n']} (95% {lo}-{hi})  hit@5 {r['hit@5']}  hit@10 {r['hit@10']}")
    result["seconds"] = round(time.perf_counter() - started, 1)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

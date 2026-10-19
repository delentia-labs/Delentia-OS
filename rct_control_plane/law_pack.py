"""
Round 89: Law Pack v0 - "the system knows this country's law" in a way a person can check.

Round 88 measured the belief that a country's model knows its country's law: small local models answered 0-5 of 10 questions about the Thai Personal Data Protection Act from memory, and the system
learns nothing from a model's answers. What can be true is narrower and checkable: the OWNER supplies the statute text; the system finds the passages that answer a question, the model answers
only from them and names the sections, and a checker refuses to present an answer as grounded when it quotes a number the passages do not contain or cites a section it was not shown.

What this module is
* a pack = one statute text split into sections, windows of it embedded with the local embedding model (bge-m3 reads Thai and English), stored as one JSON file under the Delentia home;
* `retrieve()`: the question's embedding, plus (opt-in arms measured in research/law_pack_measure_r89.py) a cue for a section the question names, and the question translated to English by the
  local model;
* `ask()`: the answer prompt, then `check_answer()`; every result carries the pack's name, edition and "not legal advice";
* `check_answer()`: an answer is GROUNDED only if it cites at least one section that was shown and every number in it is in the shown passages, the question or the cited section numbers.

What it is not
* not legal advice and not a source of law: the text is whatever the owner imported (an unofficial translation here), possibly out of date;
* the model never gets to say "the law is X" without the text in front of it; when the passages do not contain the answer the right output is "not found in the supplied text";
* nothing is learned: the loop stores no skill and no warm answer from this path, and VERIFY is not involved.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DISCLAIMER = "Not legal advice. This answer comes only from the text the owner supplied for this pack (check its edition); read the statute itself and ask a lawyer before relying on it."
NOT_FOUND = "ไม่พบในข้อความกฎหมายที่ให้มา (not found in the supplied text)"
WINDOW = 900
OVERLAP = 150
TOP_K = 5
MAX_PACK_CHARS = 3_000_000

_HEAD = re.compile(r"^[ \t]*(?:Section|Article|มาตรา)[ \t]+(\d{1,4})\b", re.M)
_BARE_PAGE_NUMBER = re.compile(r"^[ \t]*\d{1,3}[ \t]*$")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORD = re.compile(r"[A-Za-z]+|\d+|[฀-๿]+")

# English number words, so that a passage saying "five hundred thousand" supports an answer saying 500,000. Thai spelled-out numbers are NOT checked (a substring scan flags ordinary
# words such as "ห้าม"); an answer that spells a quantity in Thai and has no digits is neither confirmed nor refused by the number check.
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
          "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}


# ----------------------------------------------------------------------------------------------------------------------------- building a pack
def _strip_furniture(text: str) -> str:
    """Drop what a PDF repeats on every page (a running header, a bare page number): lines that occur four times or more and are short, and lines that are only a number."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    counts: Dict[str, int] = {}
    for line in lines:
        key = line.strip()
        if key:
            counts[key] = counts.get(key, 0) + 1
    kept = [ln for ln in lines if not _BARE_PAGE_NUMBER.match(ln) and not (len(ln.strip()) < 120 and counts.get(ln.strip(), 0) >= 4)]
    return "\n".join(kept)


def split_sections(text: str) -> List[Tuple[str, str]]:
    """(section number, its text) in order. A section starts only at the beginning of a line: 'Section 32 (1)' inside a sentence is a reference, not a heading
    (Round 88's first chunker split there and labelled the fragment 'section 32'). A reference that wraps onto a line of its own is
    rejected because section numbers only count up: a heading is accepted when it is the next number or at most three further on (an extraction can lose one)."""
    text = _strip_furniture(text)
    heads: List["re.Match[str]"] = []
    last = 0
    for m in _HEAD.finditer(text):                           # a wrapped reference can start a line too: real headings count up, so a number that jumps is a reference
        number = int(m.group(1))
        if last < number <= last + 4:
            heads.append(m)
            last = number
    out: List[Tuple[str, str]] = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = re.sub(r"\s+", " ", text[head.start():end]).strip()
        if len(body) > 40:
            out.append((head.group(1), body))
    return out


def make_chunks(sections: Sequence[Tuple[str, str]], window: int = WINDOW, overlap: int = OVERLAP) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for number, body in sections:
        start = 0
        while start < len(body):
            chunks.append({"section": number, "text": body[start:start + window]})
            if start + window >= len(body):
                break
            start += window - overlap
    return chunks


class LawPack:
    def __init__(self, name: str, edition: str, jurisdiction: str, source: str, sha256: str, chunks: List[Dict[str, Any]],
                 vectors: Optional[List[List[float]]] = None, embed_model: str = "", question_vectors: Optional[List[List[List[float]]]] = None):
        self.name, self.edition, self.jurisdiction, self.source, self.sha256 = name, edition, jurisdiction, source, sha256
        self.chunks = chunks
        self.vectors = vectors
        self.embed_model = embed_model
        self.question_vectors = question_vectors           # per chunk, the embeddings of the questions the local model wrote for it (arm A4)

    @property
    def sections(self) -> List[str]:
        seen: Dict[str, None] = {}
        for c in self.chunks:
            seen.setdefault(c["section"], None)
        return list(seen)

    def label(self) -> str:
        return f"{self.name} ({self.jurisdiction}, edition {self.edition})"

    def to_json(self) -> Dict[str, Any]:
        from rct_control_plane import memory_embeddings as me
        return {"format": 1, "name": self.name, "edition": self.edition, "jurisdiction": self.jurisdiction, "source": self.source, "sha256": self.sha256,
                "embed_model": self.embed_model, "chunks": self.chunks,
                "vectors": [base64.b64encode(me.pack(v)).decode("ascii") for v in self.vectors] if self.vectors else None,
                "question_vectors": [[base64.b64encode(me.pack(v)).decode("ascii") for v in qs] for qs in self.question_vectors] if self.question_vectors else None}

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "LawPack":
        from rct_control_plane import memory_embeddings as me
        vectors = [list(me.unpack(base64.b64decode(v))) for v in data["vectors"]] if data.get("vectors") else None
        qvecs = [[list(me.unpack(base64.b64decode(v))) for v in qs] for qs in data["question_vectors"]] if data.get("question_vectors") else None
        return cls(data["name"], data["edition"], data["jurisdiction"], data["source"], data["sha256"], data["chunks"], vectors, data.get("embed_model", ""), qvecs)


def build_pack(name: str, text: str, *, edition: str, jurisdiction: str, source: str, embed: bool = True, embed_model: Optional[str] = None) -> LawPack:
    if not name.strip() or not re.fullmatch(r"[A-Za-z0-9._-]{1,60}", name):
        raise ValueError("a pack name is 1-60 letters, digits, dot, dash or underscore")
    if len(text) > MAX_PACK_CHARS:
        raise ValueError(f"the text is larger than {MAX_PACK_CHARS:,} characters: import one statute at a time")
    chunks = make_chunks(split_sections(text))
    if not chunks:
        raise ValueError("no sections were found: a section heading must start a line ('Section 12', 'Article 12' or 'มาตรา 12')")
    pack = LawPack(name, edition, jurisdiction, source, hashlib.sha256(text.encode("utf-8")).hexdigest(), chunks)
    if embed:
        from rct_control_plane import memory_embeddings as me
        model_name = embed_model or me.model()
        vectors: List[List[float]] = []
        for i in range(0, len(chunks), 16):
            batch = me.embed([f"Section {c['section']}: {c['text']}" for c in chunks[i:i + 16]], model_name)
            if batch is None:
                raise RuntimeError("the local embedding model did not answer: start Ollama with the model installed, or import with embed=False (lexical search only)")
            vectors.extend(batch)
        pack.vectors, pack.embed_model = vectors, model_name
    return pack


_QUESTION_PROMPT = ("Below is one passage of a statute. Write {n} short questions, each in Thai, that a person who has never read the statute might ask and that this passage answers. "
                    "Use everyday words, not the statute's own wording. One question per line, no numbering, no other text.\n\n{passage}")


async def add_chunk_questions(pack: LawPack, provider: Any, per_chunk: int = 3, progress: Any = None) -> int:
    """Store-time questions (the memory recall found that questions written at store time bridge the gap between how a person asks and how the text is worded, 38 -> 40 of 40 for Thai):
    the local model writes a few everyday-word Thai questions for each chunk and they are embedded with the pack's model. Returns how many questions were stored. Slow (one model call per chunk);
    done once per pack."""
    from rct_control_plane import memory_embeddings as me
    per: List[List[str]] = []
    for i, c in enumerate(pack.chunks):
        try:
            raw = await provider.complete(_QUESTION_PROMPT.format(n=per_chunk, passage=c["text"]), system_prompt=None, temperature=0.0, max_tokens=200)
        except Exception:                                    # noqa: BLE001 - a chunk without questions still has its own vector
            raw = ""
        lines = [re.sub(r"^[\s\-*\d.)]+", "", ln).strip() for ln in re.sub(r"<think>.*?</think>", "", str(raw), flags=re.S).splitlines()]
        per.append([ln for ln in lines if len(ln) > 6][:per_chunk])
        if progress and (i + 1) % 20 == 0:
            progress(i + 1, len(pack.chunks))
    flat = [q for qs in per for q in qs]
    vectors: List[List[float]] = []
    for i in range(0, len(flat), 32):
        batch = me.embed(flat[i:i + 32], pack.embed_model or None)
        if batch is None:
            raise RuntimeError("the local embedding model did not answer while embedding the stored questions")
        vectors.extend(batch)
    it = iter(vectors)
    pack.question_vectors = [[next(it) for _ in qs] for qs in per]
    for c, qs in zip(pack.chunks, per, strict=True):
        c["questions"] = qs
    return len(flat)


# -------------------------------------------------------------------------------------------------------------------------------- storage
def packs_dir() -> Path:
    from rct_control_plane import data_home
    home = data_home.data_home()
    base = home if home is not None else Path.home() / ".delentia"
    path = base / "law_packs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_pack(pack: LawPack) -> Path:
    target = packs_dir() / f"{pack.name}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pack.to_json(), ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)
    return target


def load_pack(name: str) -> LawPack:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,60}", name):
        raise ValueError("bad pack name")
    path = packs_dir() / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"no law pack called {name!r} (import one with `delentia law import`)")
    return LawPack.from_json(json.loads(path.read_text(encoding="utf-8")))


def list_packs() -> List[Dict[str, Any]]:
    out = []
    for path in sorted(packs_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append({"name": data["name"], "edition": data["edition"], "jurisdiction": data["jurisdiction"], "sections": len({c['section'] for c in data["chunks"]}),
                        "chunks": len(data["chunks"]), "embedded": bool(data.get("vectors")), "sha256": data["sha256"][:12]})
        except Exception:                                    # noqa: BLE001 - one unreadable file must not hide the others
            out.append({"name": path.stem, "error": "unreadable"})
    return out


# ---------------------------------------------------------------------------------------------------------------------------- retrieval
def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _WORD.findall(text)]


def _bm25_scores(query: str, docs: Sequence[str], k1: float = 1.5, b: float = 0.75) -> List[float]:
    q = set(_tokens(query))
    toks = [_tokens(d) for d in docs]
    n = len(docs) or 1
    avg = (sum(len(t) for t in toks) / n) or 1.0
    df: Dict[str, int] = {}
    for t in toks:
        for w in set(t) & q:
            df[w] = df.get(w, 0) + 1
    scores: List[float] = []
    for t in toks:
        tf: Dict[str, int] = {}
        for w in t:
            if w in q:
                tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w, f in tf.items():
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(t) / avg))
        scores.append(s)
    return scores


def _named_sections(question: str, known: Sequence[str]) -> List[str]:
    """Section numbers the question names ('มาตรา 37', 'section 37'), only those the pack has."""
    found = re.findall(r"(?:มาตรา|[Ss]ection|[Aa]rticle)\s*(\d{1,4})", question)
    have = set(known)
    return [n for n in dict.fromkeys(found) if n in have]


def _rank_fuse(rankings: Sequence[Sequence[int]], k: int = 60) -> List[int]:
    score: Dict[int, float] = {}
    for ranking in rankings:
        for pos, idx in enumerate(ranking):
            score[idx] = score.get(idx, 0.0) + 1.0 / (k + pos + 1)
    return sorted(score, key=lambda i: -score[i])


async def translate_question(question: str, provider: Any) -> Optional[str]:
    """The question in English, by the local model (one short call). None when it fails: retrieval then uses the original question only."""
    try:
        text = await provider.complete(f"Translate this question into English. Answer with the translation only.\n\n{question}", system_prompt=None,
                                       temperature=0.0, max_tokens=120)
        text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S).strip()
        return text.splitlines()[0].strip() if text.strip() else None
    except Exception:                                        # noqa: BLE001 - a failed translation only removes one signal
        return None


def retrieve(pack: LawPack, question: str, *, k: int = TOP_K, arm: str = "A0", english: Optional[str] = None) -> List[Dict[str, Any]]:
    """The k chunks most likely to answer the question. arm: A0 embedding of the question; A1 + chunks of the section the question names go first; A2 A1 + the English
    translation (`english`) is embedded as well and a chunk takes the larger cosine; A3 A2 + a lexical (BM25) ranking of the translation fused in; A4 A1 + the questions written for each chunk at import (add_chunk_questions)."""
    from rct_control_plane import memory_embeddings as me
    n = len(pack.chunks)
    rankings: List[List[int]] = []
    sims: List[float] = [0.0] * n
    if pack.vectors:
        queries = [question] + ([english] if english and arm in ("A2", "A3") else [])
        vecs = me.embed(queries, pack.embed_model)
        if vecs:
            for qv in vecs:
                cos = [me.cosine(qv, v) for v in pack.vectors]
                if arm == "A4" and pack.question_vectors:        # a chunk is as close as the closer of its own text and the questions written for it
                    cos = [max([c0] + [me.cosine(qv, w) for w in qs]) for c0, qs in zip(cos, pack.question_vectors, strict=True)]
                sims = [max(a, b) for a, b in zip(sims, cos, strict=True)]
            rankings.append(sorted(range(n), key=lambda i: -sims[i]))
    if arm == "A3" and english:
        lex = _bm25_scores(english, [c["text"] for c in pack.chunks])
        rankings.append(sorted(range(n), key=lambda i: -lex[i]))
    if not rankings:                                          # no embedding available: lexical search on the question itself
        lex = _bm25_scores(question, [c["text"] for c in pack.chunks])
        rankings.append(sorted(range(n), key=lambda i: -lex[i]))
    order = _rank_fuse(rankings) if len(rankings) > 1 else list(rankings[0])
    if arm in ("A1", "A2", "A3", "A4"):
        named = set(_named_sections(question, pack.sections))
        order = [i for i in order if pack.chunks[i]["section"] in named] + [i for i in order if pack.chunks[i]["section"] not in named]
    return [{"section": pack.chunks[i]["section"], "text": pack.chunks[i]["text"], "score": round(sims[i], 4)} for i in order[:k]]


# ------------------------------------------------------------------------------------------------------------------------- the answer check
def _english_number_values(text: str) -> List[float]:
    """Values of runs of English number words: 'seventy two' -> 72, 'five hundred thousand' -> 500000 (every single word's value is returned as well)."""
    words = re.findall(r"[A-Za-z]+", text.lower())
    values: List[float] = []
    total, current, in_run = 0, 0, False

    def flush() -> None:
        nonlocal total, current, in_run
        if in_run:
            values.append(float(total + current))
        total, current, in_run = 0, 0, False
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
            in_run = True
            values.append(float(_UNITS[w]))
        elif w == "hundred" and in_run:
            current = (current or 1) * 100
            values.append(100.0)
        elif w in _SCALES and in_run:
            total += (current or 1) * _SCALES[w]
            current = 0
            values.append(float(_SCALES[w]))
        elif w == "and" and in_run:
            continue
        else:
            flush()
    flush()
    return values


def _numbers_in(text: str) -> List[float]:
    out: List[float] = []
    for m in _NUMBER.findall(text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return out + _english_number_values(text)


def check_answer(answer: str, hits: Sequence[Dict[str, Any]], question: str = "") -> Dict[str, Any]:
    """GROUNDED only when the answer cites at least one section and every section it cites was shown (or is referred to by a shown passage or by the question), and every number in it appears in the shown passages (as digits or as a number word), in the question,
    or is one of the cited section numbers. Anything else is labelled, never silently passed."""
    shown_sections = {str(h["section"]) for h in hits}
    passage_text = " ".join(str(h["text"]) for h in hits)
    # a section that a shown passage itself refers to ("violates section 27") may be named in the answer: the answer is repeating the text, not inventing a citation (the question may name one too)
    referred = set(re.findall(r"(?:[Ss]ection|[Ss]ec\.|[Aa]rticle)\s*(\d{1,4})", passage_text)) | set(re.findall(r"(?:มาตรา|[Ss]ection|[Aa]rticle)\s*(\d{1,4})", question))
    cited = [s for s in dict.fromkeys(re.findall(r"(?:มาตรา|[Ss]ection|[Ss]ec\.|[Aa]rticle)\s*(\d{1,4})", answer))]
    foreign = [s for s in cited if s not in shown_sections and s not in referred]
    allowed = set(_numbers_in(passage_text)) | set(_numbers_in(question)) | {float(s) for s in cited if s.isdigit()}
    # a number inside a citation phrase such as "มาตรา 37 (4)" or "(1)" is an item marker, not a quantity
    stripped = re.sub(r"\(\d{1,2}\)", " ", re.sub(r"(?:มาตรา|[Ss]ection|[Ss]ec\.|[Aa]rticle)\s*\d{1,4}", " ", answer))
    unsupported = sorted({n for n in _numbers_in(stripped) if n not in allowed})
    declines = any(p in answer for p in ("ไม่พบในข้อความ", "ไม่มีในข้อความ", "not found in the supplied text", "not in the supplied text"))
    if declines and not cited:
        status = "not_found"
    elif not cited:
        status = "uncited"
    elif foreign:
        status = "cites_unseen_section"
    elif unsupported:
        status = "unsupported_number"
    else:
        status = "grounded"
    return {"status": status, "grounded": status == "grounded", "cited_sections": cited, "cites_unseen": foreign, "unsupported_numbers": unsupported}


# ------------------------------------------------------------------------------------------------------------------------------- asking
_SYSTEM = ("ตอบเป็นภาษาไทยสั้น ๆ ไม่เกิน 6 บรรทัด โดยใช้เฉพาะข้อความกฎหมายที่ให้มาเท่านั้น ระบุเลขมาตราที่อ้างอิง (เช่น มาตรา 30) "
           "ถ้าข้อความที่ให้มาไม่มีคำตอบหรือไม่มีมาตรานั้น หรือคำถามมีข้อสมมติที่ไม่ตรงกับข้อความ ให้บอกว่า \"ไม่พบในข้อความที่ให้\" หรือ \"ไม่จริง\" พร้อมเหตุผลสั้น ๆ ห้ามเดา ห้ามใช้ตัวเลขที่ไม่อยู่ในข้อความ")


async def ask(pack: LawPack, question: str, provider: Any, *, arm: str = "A2", k: int = TOP_K) -> Dict[str, Any]:
    """One question against one pack. Never raises for a model failure: the result says so."""
    started = time.perf_counter()
    english = await translate_question(question, provider) if arm in ("A2", "A3") else None
    hits = retrieve(pack, question, k=k, arm=arm, english=english)
    context = "\n\n".join(f"[Section {h['section']}] {h['text']}" for h in hits)
    prompt = f"ข้อความกฎหมาย ({pack.label()}, ฉบับที่ให้มา):\n{context}\n\nคำถาม: {question}"
    try:
        raw = await provider.complete(prompt, system_prompt=_SYSTEM, temperature=0.0, max_tokens=500)
        text = re.sub(r"<think>.*?</think>", "", str(raw), flags=re.S).strip()
        error = None
    except Exception as exc:                                  # noqa: BLE001 - reported, not raised
        text, error = "", f"{type(exc).__name__}: {exc}"[:200]
    verdict = check_answer(text, hits, question) if text else {"status": "no_answer", "grounded": False, "cited_sections": [], "cites_unseen": [], "unsupported_numbers": []}
    return {"pack": pack.label(), "question": question, "answer": text or NOT_FOUND, "check": verdict, "sections_shown": [h["section"] for h in hits],
            "english_query": english, "arm": arm, "seconds": round(time.perf_counter() - started, 1), "error": error, "notice": DISCLAIMER,
            "from_statute": bool(verdict["grounded"])}

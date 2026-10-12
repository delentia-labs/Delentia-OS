"""
Round 68: recall that understands a paraphrase (opt-in: DELENTIA_MEMORY_EMBED=ollama).

Measured first (research/recall_benchmark_r68.py): asked 30 questions written in other words than the 30 stored facts, hidden among 90 distractors, Delentia's lexical matcher found the fact in its top 3
for 7 of 30; plain cosine over a local embedding model (nomic-embed-text through Ollama) found 24 of 30, and so did mem0, which uses the same model. People paraphrase, so that is a real weakness.

How it works: when the setting is on, each memory is embedded once (a local Ollama, loopback only unless DELENTIA_MEMORY_EMBED_ALLOW_REMOTE=1) and the vector is stored in `memory_vectors`, SEALED under the
person's key like the memory log (so erasure destroys it with everything else and a copy of the database does not hand over a searchable index of their words). At recall the query is embedded, every
candidate gets a calibrated similarity, and the ranking uses the larger of that and the old lexical similarity: a question that shares words with the memory still wins by words, a paraphrase now wins by
meaning. The old code path is untouched when the setting is off. If the embedding service is down, slow or answers nonsense, recall silently uses the old path (a breaker skips it for a minute).

Calibration (measured on the benchmark's own data, not tuned on its questions' answers): nomic cosine between a question and the fact it was written for has median 0.636 and 10th percentile 0.547; between
a question and an unrelated text it has median 0.43 and 90th percentile 0.51. `relevance = clip((cos - 0.50) / 0.15, 0, 1)` makes an unrelated text score 0 to 0.1 and a matching fact 0.9 to 1, so D, which
reads `relevance`, is not raised by the noise floor of the model.
"""
from __future__ import annotations

import array
import json
import logging
import math
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlsplit

LOG = logging.getLogger(__name__)
ENV = "DELENTIA_MEMORY_EMBED"
MODEL_ENV = "DELENTIA_MEMORY_EMBED_MODEL"
URL_ENV = "DELENTIA_OLLAMA_URL"
REMOTE_ENV = "DELENTIA_MEMORY_EMBED_ALLOW_REMOTE"
DEFAULT_MODEL = "nomic-embed-text"
FLOOR, SPAN = 0.50, 0.15                        # cosine at which relevance is 0, and the width of the ramp to 1 (see the docstring): measured for nomic-embed-text
# Round 69: the numbers above describe ONE model. Another model has another cosine scale, so `relevance` (which D reads) is calibrated per model; an uncalibrated model still helps the ORDER
# (memory_ranking.py) but contributes nothing to relevance, so D is never raised by a scale nobody measured. `delentia memory calibrate` measures a model and writes the table below.
# nomic: measured by hand on the Round 68 benchmark. bge-m3: `delentia memory calibrate --model bge-m3` on the paraphrase sample (the first, word-sharing sample gave 0.547 / 0.18, which hid 12 of 40
# real matches from the agent behind the relevance floor; the paraphrase sample with the 10th-percentile span gave 0.487 / 0.098: 37 of 40 shown but 3 of 20 unrelated questions showed a memory; the median span, chosen because a stranger the scale overrates is worse than a match it underrates, gives 0.487 / 0.221).
CALIBRATIONS = {"nomic-embed-text": (0.50, 0.15), "bge-m3": (0.487, 0.221)}
READS_THAI = frozenset({"bge-m3"})                                                    # models measured to tell Thai texts apart (calibrate: reads_thai); nomic-embed-text puts every Thai text on one point
CALIBRATION_FILE_ENV = "DELENTIA_MEMORY_EMBED_CALIBRATION"
MAX_BACKFILL = 256                              # memories embedded at once when a recall finds some without a vector
MAX_TEXT_CHARS = 4000
TIMEOUT_S = 20.0
BREAKER_S = 60.0
_breaker_until = 0.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_vectors (
    memory_id  TEXT PRIMARY KEY,
    namespace  TEXT NOT NULL,
    model      TEXT NOT NULL,
    dim        INTEGER NOT NULL,
    vec        BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_vectors_ns ON memory_vectors(namespace);
"""


AUTO_PROBE_S = 300.0
# With DELENTIA_MEMORY_EMBED=auto and no DELENTIA_MEMORY_EMBED_MODEL, the first of these that the local Ollama has is used. Measured (Round 69): bge-m3 reads Thai (38 of 40 held-out Thai questions found in the
# top 3, nomic 23) and costs 2 to 4 questions of 40 on English (33 against 37); nomic-embed-text is the smaller, faster model that cannot read Thai. A person who writes Thai or mixed text is better served by the
# first; one who writes only English loses a little. A model set by name is always obeyed.
PREFERRED_MODELS = ("bge-m3", "nomic-embed-text")
_auto_probe: Dict[str, Any] = {"at": -1e9, "url": "", "model": "", "ok": False, "have": [], "wanted": ""}


def _installed_models(url: str) -> List[str]:
    try:
        tags = json.loads(urllib.request.urlopen(url + "/api/tags", timeout=2.0).read())
        return sorted({str(m.get("name", "")) for m in tags.get("models", [])})
    except Exception:                                                        # noqa: BLE001 - no Ollama, or too slow: memory simply keeps using its words
        return []


def _has(have: Sequence[str], name: str) -> bool:
    return name in have or f"{name}:latest" in have


def _model_is_installed() -> bool:
    """For DELENTIA_MEMORY_EMBED=auto: is the local Ollama reachable and does it list the embedding model (the named one, else the first of PREFERRED_MODELS)? One short request every five minutes."""
    now = time.monotonic()
    url, named = base_url(), (os.environ.get(MODEL_ENV) or "").strip()
    if now - _auto_probe["at"] < AUTO_PROBE_S and _auto_probe["url"] == url and _auto_probe["wanted"] == named:
        return bool(_auto_probe["ok"])
    have = _installed_models(url) if _address_allowed(url) else []
    chosen = named or next((m for m in PREFERRED_MODELS if _has(have, m)), DEFAULT_MODEL)
    _auto_probe.update({"at": now, "url": url, "wanted": named, "model": chosen, "ok": _has(have, chosen), "have": have})
    return bool(_auto_probe["ok"])


def reset_auto_probe() -> None:
    _auto_probe.update({"at": -1e9, "url": "", "model": "", "ok": False, "have": [], "wanted": ""})


def enabled() -> bool:
    """on: ollama / 1 / on / true / yes. auto: on only when the local Ollama is reachable and has the embedding model (nothing is sent anywhere else, nothing breaks without it). Otherwise off."""
    value = (os.environ.get(ENV) or "").strip().lower()
    if value == "auto":
        return _model_is_installed()
    return value in ("ollama", "1", "on", "true", "yes")


def model() -> str:
    named = (os.environ.get(MODEL_ENV) or "").strip()
    if named:
        return named
    if (os.environ.get(ENV) or "").strip().lower() == "auto":
        _model_is_installed()                                                # fills the probe (cached); its choice is the best installed model
        return str(_auto_probe["model"] or DEFAULT_MODEL)
    return DEFAULT_MODEL


def base_url() -> str:
    return (os.environ.get(URL_ENV) or "http://127.0.0.1:11434").rstrip("/")


def _address_allowed(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    return (os.environ.get(REMOTE_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def embed(texts: Sequence[str], model_name: Optional[str] = None) -> Optional[List[List[float]]]:
    """Vectors for the texts, or None when the service cannot be used (down, slow, refused address, wrong shape). Never raises."""
    global _breaker_until
    if not texts or time.monotonic() < _breaker_until:
        return None
    url = base_url()
    if not _address_allowed(url):
        LOG.warning("memory embedding refused: %s is not a loopback address (set %s=1 to allow it)", url, REMOTE_ENV)
        return None
    try:
        request = urllib.request.Request(url + "/api/embed", data=json.dumps({"model": model_name or model(), "input": [str(t)[:MAX_TEXT_CHARS] for t in texts], "keep_alive": "30m"}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        body = json.loads(urllib.request.urlopen(request, timeout=TIMEOUT_S).read())
        vectors = body["embeddings"]
        if not isinstance(vectors, list) or len(vectors) != len(texts) or not all(isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v) for v in vectors):
            raise ValueError("the embedding service answered with something that is not one vector per text")
        dim = len(vectors[0])
        if any(len(v) != dim for v in vectors):
            raise ValueError("vectors of different sizes")
        return [[float(x) for x in v] for v in vectors]
    except Exception as exc:                                                 # noqa: BLE001 - recall must never fail because an optional index is unavailable
        _breaker_until = time.monotonic() + BREAKER_S
        LOG.warning("memory embedding unavailable (%s: %s); recall uses the lexical matcher for %d s", type(exc).__name__, exc, int(BREAKER_S))
        return None


def reset_breaker() -> None:
    global _breaker_until
    _breaker_until = 0.0


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb and len(a) == len(b) else 0.0


def calibration_path() -> "Any":
    from pathlib import Path
    override = os.environ.get(CALIBRATION_FILE_ENV)
    return Path(override) if override else Path.home() / ".delentia" / "embed_calibration.json"


def calibration(model_name: Optional[str] = None) -> Optional[tuple]:
    """(floor, span) for the model, or None when it has not been measured. Order of precedence: a file written by `delentia memory calibrate`, then the built-in table."""
    name = model_name or model()
    if name.endswith(":latest"):
        name = name[:-len(":latest")]
    try:
        path = calibration_path()
        if path.exists():
            entry = json.loads(path.read_text(encoding="utf-8")).get(name)
            if isinstance(entry, dict) and isinstance(entry.get("floor"), (int, float)) and isinstance(entry.get("span"), (int, float)) and entry["span"] > 0:
                return float(entry["floor"]), float(entry["span"])
    except (OSError, ValueError):
        pass
    return CALIBRATIONS.get(name)


def reads_thai(model_name: Optional[str] = None) -> bool:
    """Does the model tell Thai texts apart? A file written by `delentia memory calibrate` decides, then the built-in list. Unknown models: no (the ranking then leans on BM25 for Thai questions)."""
    name = model_name or model()
    if name.endswith(":latest"):
        name = name[:-len(":latest")]
    try:
        path = calibration_path()
        if path.exists():
            entry = json.loads(path.read_text(encoding="utf-8")).get(name)
            if isinstance(entry, dict) and isinstance(entry.get("reads_thai"), bool):
                return bool(entry["reads_thai"])
    except (OSError, ValueError):
        pass
    return name in READS_THAI


def relevance(cos: Optional[float]) -> float:
    """0..1 evidence that a memory answers the question, from the cosine. 0 for a model that has no calibration (see CALIBRATIONS)."""
    if cos is None:
        return 0.0
    cal = calibration()
    if cal is None:
        return 0.0
    floor, span = cal
    return max(0.0, min(1.0, (cos - floor) / span))


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def calibrate(model_name: Optional[str] = None, write: bool = False) -> Dict[str, Any]:
    """Measure where a model puts a question and the sentence that answers it (related) against a question and some other sentence (unrelated), on the neutral sample of
    embed_calibration_samples.py, English and Thai separately. A language counts only if its related pairs are clearly above its unrelated ones (the 10th percentile of related above the 90th of
    unrelated); nomic-embed-text puts every Thai text almost on the same point (unrelated median cosine ~1.0), so Thai does not count for it. Over the languages that count:
    floor = the largest 90th percentile of the unrelated cosines, span = the smallest MEDIAN of the related ones minus the floor (at least 0.05). The median, not the 10th percentile, because the two ways of being wrong are not equal: a match the scale underrates only lowers D (the agent asks more), a stranger the scale overrates raises D (evidence that is not there). Measured through the loop with the 10th-percentile rule bge-m3 showed a memory for 3 of 20 unrelated questions.
    `reads_thai` says whether Thai counts. With write=True a usable result is merged into the calibration file (calibration_path()); an unusable one is never written.
    Returns {"error": ...} when the service cannot be reached."""
    from rct_control_plane import embed_calibration_samples as sample
    name = model_name or model()
    report: Dict[str, Any] = {"model": name}
    floors: List[float] = []
    spans: List[float] = []
    for language, pairs in (("en", sample.EN), ("th", sample.TH)):
        vectors = embed([q for q, _a in pairs] + [a for _q, a in pairs], model_name=name)
        if vectors is None:
            return {"model": name, "error": "the embedding service could not be reached (down, too slow, or a refused address)"}
        n = len(pairs)
        questions, answers = vectors[:n], vectors[n:]
        related = [cosine(questions[i], answers[i]) for i in range(n)]
        unrelated = [cosine(questions[i], answers[(i + 7) % n]) for i in range(n)]
        floor, low = _percentile(unrelated, 0.90), _percentile(related, 0.10)
        separated = low > floor
        report[language] = {"related_median": round(_percentile(related, 0.5), 3), "related_p10": round(low, 3), "unrelated_p90": round(floor, 3),
                            "unrelated_median": round(_percentile(unrelated, 0.5), 3), "pairs": n, "separated": separated}
        if separated:
            floors.append(floor)
            spans.append(report[language]['related_median'] - floor)
    report["reads_thai"] = bool(report["th"]["separated"])
    report["usable"] = bool(floors)
    if floors:
        report["floor"], report["span"] = round(max(floors), 3), round(max(0.05, min(spans)), 3)
    else:
        report["note"] = "this model does not separate related from unrelated sentences on the sample: do not use it for memory"
    if write and report["usable"]:
        path = calibration_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            table = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            table = {}
        table[name[:-len(":latest")] if name.endswith(":latest") else name] = {"floor": report["floor"], "span": report["span"], "reads_thai": report["reads_thai"]}
        path.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
        report["written_to"] = str(path)
    return report


def pack(vector: Sequence[float]) -> bytes:
    return array.array("f", vector).tobytes()


_np: Any
try:                                                                   # numpy is a declared dependency of the package; the plain-Python path below is the fallback
    import numpy as _numpy
    _np = _numpy
except ImportError:                                                    # pragma: no cover
    _np = None


def unpack(blob: bytes) -> Any:
    if _np is not None:
        if len(blob) % 4:
            raise ValueError("a vector is a whole number of 32-bit floats")
        return _np.frombuffer(blob, dtype=_np.float32)
    values = array.array("f")
    values.frombytes(blob)
    return list(values)


def ensure_schema(conn: Any) -> None:
    conn.executescript(SCHEMA)


def store_vectors(persistence: Any, namespace: str, items: Sequence[Dict[str, str]]) -> int:
    """Embed and store (memory id, text) pairs, sealed under the person's key. Returns how many were stored."""
    from datetime import datetime, timezone
    from rct_control_plane import memory_erasure
    vectors = embed([i["text"] for i in items])
    if vectors is None:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    with persistence._connect() as conn:
        ensure_schema(conn)
        for item, vec in zip(items, vectors, strict=True):
            blob = memory_erasure.seal_bytes(namespace, pack(vec))
            conn.execute("INSERT OR REPLACE INTO memory_vectors (memory_id, namespace, model, dim, vec, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (item["id"], namespace, model(), len(vec), blob, now))
    return len(items)


QUESTION_SLOTS = 3                              # vectors of the questions a memory answers (memory_llm.py): rows named "<memory id>#q0" .. "#q2"
MAX_QUESTION_BACKFILL = 10                      # memories that get their questions written during one recall (each one is a model call)


def question_ids(memory_id: str) -> List[str]:
    return [f"{memory_id}#q{k}" for k in range(QUESTION_SLOTS)]


def store_questions(persistence: Any, namespace: str, memory_id: str, text: str) -> int:
    """Have the local model write the questions this memory answers, embed them and keep them sealed next to the memory's own vector. Returns how many were stored (0 when no model)."""
    from rct_control_plane import memory_llm
    lines = memory_llm.questions_for(text)
    if not lines:
        return 0
    return store_vectors(persistence, namespace, [{"id": qid, "text": line} for qid, line in zip(question_ids(memory_id), lines, strict=False)])


def load_vectors(persistence: Any, namespace: str, ids: Sequence[str]) -> Dict[str, List[float]]:
    from rct_control_plane import memory_erasure
    out: Dict[str, List[float]] = {}
    if not ids:
        return out
    with persistence._connect() as conn:
        ensure_schema(conn)
        for start in range(0, len(ids), 500):
            chunk = list(ids[start:start + 500])
            marks = ",".join("?" for _ in chunk)
            for memory_id, _model, blob in conn.execute(f"SELECT memory_id, model, vec FROM memory_vectors WHERE namespace = ? AND model = ? AND memory_id IN ({marks})",
                                                            [namespace, model(), *chunk]):
                raw = bytes(blob)
                if not any(raw):                                                # zeroed by an erasure: nothing to read
                    continue
                plain = memory_erasure.open_bytes(namespace, raw)
                if plain is not None:                                           # a destroyed key means no vector, not an error
                    try:
                        out[memory_id] = unpack(plain)
                    except ValueError:
                        continue
    return out


def similarities(persistence: Any, namespace: str, query: str, candidates: Sequence[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Raw cosine of the query to each candidate (by memory id), embedding the candidates that have no vector yet (up to MAX_BACKFILL). None = use the lexical path."""
    if not enabled() or not candidates:
        return None
    from rct_control_plane import memory_llm
    ids = [c["id"] for c in candidates]
    questions_on = memory_llm.questions_enabled()
    wanted = ids + [qid for i in ids for qid in question_ids(i)] if questions_on else ids
    have = load_vectors(persistence, namespace, wanted)
    missing = [c for c in candidates if c["id"] not in have][:MAX_BACKFILL]
    if missing and store_vectors(persistence, namespace, [{"id": c["id"], "text": c["content"]} for c in missing]):
        have = load_vectors(persistence, namespace, wanted)
    if questions_on:                                                       # memories stored before the setting was on (or when the model was down) get their questions here, a few at a time
        for c in [c for c in candidates if question_ids(c["id"])[0] not in have and c["id"] in have][:MAX_QUESTION_BACKFILL]:
            if store_questions(persistence, namespace, c["id"], c["content"]):
                have.update(load_vectors(persistence, namespace, question_ids(c["id"])))
    queries = [query] + (memory_llm.paraphrases_of(query) if memory_llm.expansion_enabled() else [])
    query_vecs = embed(queries)
    if query_vecs is None or not have:
        return None
    dim = len(query_vecs[0])
    best: Dict[str, float] = {}
    keys = [k for k, vec in have.items() if len(vec) == dim]
    if _np is not None and keys:                                       # one matrix product for every memory and every query variant
        matrix = _np.vstack([_np.asarray(have[k], dtype=_np.float32) for k in keys])
        norms = _np.linalg.norm(matrix, axis=1)
        qmat = _np.asarray(query_vecs, dtype=_np.float32)
        qn = _np.linalg.norm(qmat, axis=1)
        denom = _np.outer(norms, qn)
        with _np.errstate(divide="ignore", invalid="ignore"):
            sims = _np.where(denom > 0, (matrix @ qmat.T) / denom, 0.0).max(axis=1)
        scores = {k: float(v) for k, v in zip(keys, sims, strict=True)}
    else:
        scores = {k: max(cosine(qv, have[k]) for qv in query_vecs) for k in keys}
    for key, score in scores.items():
        memory_id = key.split("#q", 1)[0]
        if score > best.get(memory_id, -1.0):
            best[memory_id] = score
    return best

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
FLOOR, SPAN = 0.50, 0.15                        # cosine at which relevance is 0, and the width of the ramp to 1 (see the docstring)
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


def enabled() -> bool:
    return (os.environ.get(ENV) or "").strip().lower() in ("ollama", "1", "on", "true", "yes")


def model() -> str:
    return (os.environ.get(MODEL_ENV) or DEFAULT_MODEL).strip()


def base_url() -> str:
    return (os.environ.get(URL_ENV) or "http://127.0.0.1:11434").rstrip("/")


def _address_allowed(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    return (os.environ.get(REMOTE_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def embed(texts: Sequence[str]) -> Optional[List[List[float]]]:
    """Vectors for the texts, or None when the service cannot be used (down, slow, refused address, wrong shape). Never raises."""
    global _breaker_until
    if not texts or time.monotonic() < _breaker_until:
        return None
    url = base_url()
    if not _address_allowed(url):
        LOG.warning("memory embedding refused: %s is not a loopback address (set %s=1 to allow it)", url, REMOTE_ENV)
        return None
    try:
        request = urllib.request.Request(url + "/api/embed", data=json.dumps({"model": model(), "input": [str(t)[:MAX_TEXT_CHARS] for t in texts], "keep_alive": "30m"}).encode("utf-8"),
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


def relevance(cos: float) -> float:
    return max(0.0, min(1.0, (cos - FLOOR) / SPAN))


def pack(vector: Sequence[float]) -> bytes:
    return array.array("f", vector).tobytes()


def unpack(blob: bytes) -> List[float]:
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
    ids = [c["id"] for c in candidates]
    have = load_vectors(persistence, namespace, ids)
    missing = [c for c in candidates if c["id"] not in have][:MAX_BACKFILL]
    if missing and store_vectors(persistence, namespace, [{"id": c["id"], "text": c["content"]} for c in missing]):
        have = load_vectors(persistence, namespace, ids)
    query_vec = embed([query])
    if query_vec is None or not have:
        return None
    return {memory_id: cosine(query_vec[0], vec) for memory_id, vec in have.items() if len(vec) == len(query_vec[0])}

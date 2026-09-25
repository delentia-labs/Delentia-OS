"""
Multi-topic caching — Round 44 item I.3 (greenfield MVP, no prior art in
this repo — confirmed via a repo-wide grep for cache/Cache/topic-cache
before writing a line of this file).

Scope, deliberately small and honest (same discipline skill_library.py's
own docstring established for its MVP slice):

    1. get(topic_text, content) / put(topic_text, content, value, ttl) —
       an exact-match cache (SHA256 of the normalized content string),
       partitioned by a real, content-derived topic bucket so unrelated
       topics never evict each other's entries under a size cap.
    2. That's it. No semantic/fuzzy cache hits, no cross-process/
       distributed cache, no automatic eviction beyond TTL filtering on
       read.

Why exact-match only: a fuzzy/semantic cache hit risks returning a
stale/wrong answer for a prompt that is merely SIMILAR, not identical, to
a cached one — there is no empirical basis in this codebase yet for a
similarity threshold that would be safe, and inventing one here would be
exactly the kind of unjustified magic number skill_library.py's own
docstring already argues against for its own gate. Widening to fuzzy
matching is real follow-up work, not built here.

Why per-topic buckets: without them, one cache table is just one global
LRU/TTL cache - fine, but throws away real signal (an operator asking
"what changed in the FDIA formula" and "summarize this JITNA packet" are
never going to collide anyway) and makes a future per-topic eviction
policy (e.g. "cap each topic at N entries") straightforward to add later
without a schema change.

Topic bucketing: reuses the exact same real hashing-trick technique
already established twice in this codebase (algo_36_rflh.py's
RFLHEngine._embed_text, mcp_server.py's _hash_embed_query) rather than
inventing a third embedding function - see topic_bucket() below. This is
a third, small, deliberately duplicated copy (not an import) for the
same reason governed_autonomous_loop.py's fdia_score() duplicates
AlgorithmKernel41.algo_01_fdia's formula rather than importing it:
importing mcp_server would force constructing its module-level
AlgorithmKernel41 singleton just to reuse ~10 lines of pure hashing math.

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

TOPIC_CACHE_VERSION = "0.1"

_DEFAULT_DB_PATH = os.environ.get(
    "RCT_DB_PATH",
    str(Path(__file__).parent.parent / "rct_control_plane.db"),
)

_CACHE_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

-- Additive only: never dropped/altered, per workspace Zero-Delete policy.
-- Expired rows are filtered on read, never deleted automatically - real
-- pruning (e.g. a future `delentia cache vacuum`) is a separate,
-- explicit, human-triggered operation.
CREATE TABLE IF NOT EXISTS topic_cache (
    topic_bucket INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    value_json   TEXT NOT NULL,
    created_at   REAL NOT NULL,
    expires_at   REAL NOT NULL,
    PRIMARY KEY (topic_bucket, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_topic_cache_expires ON topic_cache(expires_at);
"""

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def topic_bucket(text: str, n_buckets: int = 64) -> int:
    """Real, deterministic, content-derived topic bucket in [0, n_buckets).

    Builds the same real feature-hashed signed bag-of-words vector as
    algo_36_rflh.py's _embed_text / mcp_server.py's _hash_embed_query (at
    dimension n_buckets), then returns the index of its dominant
    (largest-magnitude) dimension - the single feature-hash bucket the
    text's own tokens voted into most strongly. Two texts sharing enough
    vocabulary to dominate the same hash bucket land in the same topic;
    unrelated texts almost never collide by chance at n_buckets=64.
    Deterministic and stable across runs/processes (SHA256-based, no
    randomness, no trained model)."""
    vector = np.zeros(n_buckets, dtype=np.float64)
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") % n_buckets
        sign = 1.0 if (digest[8] & 1) == 0 else -1.0
        vector[bucket] += sign
    if not np.any(vector):
        return 0
    return int(np.argmax(np.abs(vector)))


def _content_hash(content: str) -> str:
    normalized = content.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class TopicCache:
    """Exact-match, TTL-based, topic-partitioned cache. See module
    docstring for the real scope and the non-goals this MVP deliberately
    leaves out.

    Example::

        cache = TopicCache()
        hit = cache.get("what changed in the FDIA formula", "explain F=D^I*A")
        if hit is None:
            value = call_llm(...)
            cache.put("what changed in the FDIA formula", "explain F=D^I*A", value, ttl_seconds=3600)
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH, n_buckets: int = 64) -> None:
        self.db_path = db_path
        self.n_buckets = n_buckets
        self._init_schema()

    def _init_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_CACHE_SCHEMA_SQL)

    def get(self, topic_text: str, content: str) -> Optional[Any]:
        """Returns the cached value, or None on a real miss (never seen,
        or expired - expired rows are filtered here, not returned)."""
        bucket = topic_bucket(topic_text, self.n_buckets)
        content_hash = _content_hash(content)
        now = time.time()

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value_json, expires_at FROM topic_cache "
                "WHERE topic_bucket = ? AND content_hash = ?",
                (bucket, content_hash),
            ).fetchone()

        if row is None:
            return None
        value_json, expires_at = row
        if expires_at <= now:
            return None
        return json.loads(value_json)

    def put(self, topic_text: str, content: str, value: Any, ttl_seconds: float) -> None:
        """Stores value under (topic_bucket(topic_text), hash(content)),
        expiring after ttl_seconds. value must be JSON-serializable.
        Overwrites any existing entry for the same real key (a real
        re-computation for the same content should replace, not
        duplicate, a stale cached value)."""
        bucket = topic_bucket(topic_text, self.n_buckets)
        content_hash = _content_hash(content)
        now = time.time()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO topic_cache (topic_bucket, content_hash, value_json, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(topic_bucket, content_hash) DO UPDATE SET "
                "value_json = excluded.value_json, created_at = excluded.created_at, expires_at = excluded.expires_at",
                (bucket, content_hash, json.dumps(value), now, now + ttl_seconds),
            )

    def count(self, include_expired: bool = False) -> int:
        with sqlite3.connect(self.db_path) as conn:
            if include_expired:
                row = conn.execute("SELECT COUNT(*) FROM topic_cache").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM topic_cache WHERE expires_at > ?", (time.time(),)
                ).fetchone()
        return int(row[0]) if row else 0

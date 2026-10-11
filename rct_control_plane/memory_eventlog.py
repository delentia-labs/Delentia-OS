"""
Round 66: the memory pipeline, redesigned as an append-only event log (opt-in: DELENTIA_MEMORY_EVENTLOG=1).

Before this, the agent's memory was the rows of one SQLite table (`memories`) and "Delta" meant three unrelated things (docs/ROUND66 plan, section 2). The measurements of Round 65 settled
the storage question: a delta log is no smaller than snapshots compressed with zstd, so bytes are not the reason to change anything. What a log gives that a table cannot:

  * HISTORY.   Every add / touch / revoke / edit is an event with its provenance (was the text read from outside?), chained by hash to the one before it. `fold(namespace, upto_seq)`
               rebuilds exactly what the agent could have known at any moment: replay of an episode, audit, "what did it know when it did that".
  * REVOCATION AS A FACT. A revoked memory is an event, not an edit of a row; the original text stays recoverable for the audit (Zero-Delete) and no reader returns it again.
  * BOUNDED DAMAGE. Checkpoints (the full state of one person's memory, compressed with zstd) every K events, so a rebuild reads at most K events and one damaged event can hurt
               only what follows it up to the next checkpoint; the chain says WHERE the damage starts instead of silently returning a wrong state.
  * A PORTABLE ARCHIVE. `export_archive` writes one zstd stream (events + final state + chain head) that `verify_archive` re-checks without the database.

Q1 (storage) is therefore a settled engineering choice (events for history, zstd for bytes). Q2 - WHAT THE MODEL IS SHOWN - is separate and is the only thing that can change an answer:
`select_for_recall` applies a policy at READ time (nothing is deleted or rewritten): `none` (every memory is a candidate, today's behaviour), `dedupe` (memories with the same normalised
text count once: the newest, with the highest importance), `expire` (episodic memories - conversation and event - older than DELENTIA_MEMORY_TTL_DAYS stop being candidates unless their
importance is high; facts, preferences, goals and skills never expire). `DELENTIA_MEMORY_POLICY` chooses; the default is `none` until a measurement with a capable model says otherwise.

PDPA note: the log keeps text, so "erasure" of a person needs the per-subject-key design in the Round 66 plan (M4); today the log is Zero-Delete and the person's data is revoked, not erased.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

GENESIS = "0" * 64
ENABLE_ENV = "DELENTIA_MEMORY_EVENTLOG"
CHECKPOINT_ENV = "DELENTIA_MEMORY_CHECKPOINT_EVERY"
POLICY_ENV = "DELENTIA_MEMORY_POLICY"
TTL_ENV = "DELENTIA_MEMORY_TTL_DAYS"
KINDS = ("add", "touch", "revoke", "edit")
POLICIES = ("none", "dedupe", "expire")
EPISODIC = ("conversation", "event")
HIGH_IMPORTANCE = 0.85

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace   TEXT NOT NULL,
    kind        TEXT NOT NULL,
    memory_id   TEXT NOT NULL,
    payload     TEXT NOT NULL,
    provenance  TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    event_hash  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_events_ns ON memory_events(namespace, seq);
CREATE TABLE IF NOT EXISTS memory_checkpoints (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace     TEXT NOT NULL,
    upto_seq      INTEGER NOT NULL,
    state_zstd    BLOB NOT NULL,
    state_sha256  TEXT NOT NULL,
    items         INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_checkpoints_ns ON memory_checkpoints(namespace, upto_seq);
"""


def enabled() -> bool:
    return (os.environ.get(ENABLE_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def event_hash(prev_hash: str, namespace: str, kind: str, memory_id: str, payload: str, provenance: str, created_at: str) -> str:
    return hashlib.sha256("|".join([prev_hash, namespace, kind, memory_id, payload, provenance, created_at]).encode("utf-8")).hexdigest()


def append(conn: sqlite3.Connection, namespace: str, kind: str, memory_id: str, payload: Dict[str, Any], provenance: Optional[Dict[str, Any]] = None) -> int:
    """Adds one event to the chain. Must run in the same transaction as the change it records (after that write the connection holds SQLite's write lock, so
    two writers cannot take the same prev_hash - the same rule as audit_chain.append). Returns the new sequence number."""
    if kind not in KINDS:
        raise ValueError(f"unknown memory event {kind!r}")
    ensure_schema(conn)
    prev = conn.execute("SELECT event_hash FROM memory_events ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = prev[0] if prev else GENESIS
    body, prov, now = _canon(payload), _canon(provenance or {}), datetime.now(timezone.utc).isoformat()
    h = event_hash(prev_hash, namespace, kind, memory_id, body, prov, now)
    cur = conn.execute("INSERT INTO memory_events (namespace, kind, memory_id, payload, provenance, created_at, prev_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (namespace, kind, memory_id, body, prov, now, prev_hash, h))
    seq = int(cur.lastrowid or 0)
    every = _int_env(CHECKPOINT_ENV, 50)
    if every > 0:
        # A checkpoint holds the WHOLE state of one person, so a fixed interval makes the checkpoints grow as n^2 / interval (measured: 97 checkpoints of a 5,000-operation log were 8x the
        # table). The interval therefore grows with the state: at least `every` events, and at least half as many events as there are live items, which keeps the total checkpoint
        # bytes proportional to the log itself while a rebuild still reads a bounded number of events.
        last_row = conn.execute("SELECT upto_seq, items FROM memory_checkpoints WHERE namespace = ? ORDER BY upto_seq DESC LIMIT 1", (namespace,)).fetchone()
        last, items = (last_row[0], last_row[1]) if last_row else (0, 0)
        count = conn.execute("SELECT COUNT(*) FROM memory_events WHERE namespace = ? AND seq > ?", (namespace, last)).fetchone()[0]
        if count >= max(every, items // 2):
            _write_checkpoint(conn, namespace)
    return seq


def _int_env(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def _apply(state: Dict[str, Dict[str, Any]], kind: str, memory_id: str, payload: Dict[str, Any], at: str) -> None:
    if kind == "add":
        state[memory_id] = {**payload, "id": memory_id, "accessed_count": 0, "last_accessed": None, "revoked_at": None, "revoked_reason": None}
    elif memory_id in state:
        if kind == "touch":
            state[memory_id]["accessed_count"] += 1
            state[memory_id]["last_accessed"] = at
        elif kind == "revoke":
            state[memory_id]["revoked_at"] = at
            state[memory_id]["revoked_reason"] = payload.get("reason", "")
        elif kind == "edit":
            state[memory_id].update({k: v for k, v in payload.items() if k in ("content", "importance", "memory_type", "context")})


def _fold(conn: sqlite3.Connection, namespace: str, upto_seq: Optional[int]) -> Dict[str, Dict[str, Any]]:
    import zstandard
    state: Dict[str, Dict[str, Any]] = {}
    start = 0
    row = conn.execute("SELECT upto_seq, state_zstd, state_sha256 FROM memory_checkpoints WHERE namespace = ? AND upto_seq <= ? ORDER BY upto_seq DESC LIMIT 1",
                       (namespace, upto_seq if upto_seq is not None else 2 ** 62)).fetchone()
    if row:
        raw = zstandard.ZstdDecompressor().decompress(row[1])
        if hashlib.sha256(raw).hexdigest() != row[2]:
            raise ValueError(f"checkpoint at seq {row[0]} of {namespace!r} does not match its hash")
        state, start = json.loads(raw), int(row[0])
    for _seq, kind, mid, payload, at in conn.execute("SELECT seq, kind, memory_id, payload, created_at FROM memory_events WHERE namespace = ? AND seq > ? AND seq <= ? ORDER BY seq",
                                                    (namespace, start, upto_seq if upto_seq is not None else 2 ** 62)):
        _apply(state, kind, mid, json.loads(payload), at)
    return state


def _write_checkpoint(conn: sqlite3.Connection, namespace: str) -> int:
    import zstandard
    upto = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM memory_events WHERE namespace = ?", (namespace,)).fetchone()[0]
    state = _fold(conn, namespace, upto)
    raw = _canon(state).encode("utf-8")
    conn.execute("INSERT INTO memory_checkpoints (namespace, upto_seq, state_zstd, state_sha256, items, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (namespace, upto, zstandard.ZstdCompressor(level=6).compress(raw), hashlib.sha256(raw).hexdigest(), len(state), datetime.now(timezone.utc).isoformat()))
    return int(upto)


class MemoryEventLog:
    def __init__(self, persistence: Any) -> None:
        self._p = persistence
        with self._p._connect() as conn:
            ensure_schema(conn)

    def fold(self, namespace: str, upto_seq: Optional[int] = None, include_revoked: bool = False) -> Dict[str, Dict[str, Any]]:
        """The memory of one person as it was after event `upto_seq` (None = now)."""
        with self._p._connect() as conn:
            state = _fold(conn, namespace, upto_seq)
        return state if include_revoked else {k: v for k, v in state.items() if not v.get("revoked_at")}

    def checkpoint(self, namespace: str) -> int:
        with self._p._connect() as conn:
            return _write_checkpoint(conn, namespace)

    def head(self) -> Dict[str, Any]:
        with self._p._connect() as conn:
            row = conn.execute("SELECT seq, event_hash FROM memory_events ORDER BY seq DESC LIMIT 1").fetchone()
        return {"seq": row[0], "hash": row[1]} if row else {"seq": 0, "hash": GENESIS}

    def verify(self) -> Dict[str, Any]:
        """Recomputes every link. A damaged or removed event is named by its sequence number; so is a checkpoint that no longer matches its hash."""
        problems: List[str] = []
        prev, n = GENESIS, 0
        with self._p._connect() as conn:
            for seq, ns, kind, mid, payload, prov, at, prev_hash, h in conn.execute(
                    "SELECT seq, namespace, kind, memory_id, payload, provenance, created_at, prev_hash, event_hash FROM memory_events ORDER BY seq"):
                n += 1
                if prev_hash != prev:
                    problems.append(f"event {seq}: it does not follow the event before it (an event was removed or reordered)")
                if event_hash(prev_hash, ns, kind, mid, payload, prov, at) != h:
                    problems.append(f"event {seq}: its content does not match its hash (it was edited)")
                prev = h
            import zstandard
            for cid, ns, upto, blob, sha in conn.execute("SELECT id, namespace, upto_seq, state_zstd, state_sha256 FROM memory_checkpoints ORDER BY id"):
                try:
                    if hashlib.sha256(zstandard.ZstdDecompressor().decompress(blob)).hexdigest() != sha:
                        problems.append(f"checkpoint {cid} ({ns} at seq {upto}): it does not match its hash")
                except Exception as exc:                                    # noqa: BLE001
                    problems.append(f"checkpoint {cid} ({ns} at seq {upto}): unreadable ({type(exc).__name__})")
        return {"ok": not problems, "events": n, "problems": problems[:20]}

    def consistent_with_table(self, namespace: str) -> Dict[str, Any]:
        """The fold must equal what the `memories` table says, field by field that the log carries. A difference means a write bypassed the log (or the reverse)."""
        folded = self.fold(namespace, include_revoked=True)
        with self._p._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM memories WHERE namespace = ?", (namespace,))}
        diffs: List[str] = []
        for mid in sorted(set(folded) | set(rows)):
            a, b = folded.get(mid), rows.get(mid)
            if a is None or b is None:
                diffs.append(f"{mid}: only in the {'table' if a is None else 'log'}")
                continue
            for field in ("content", "memory_type", "importance", "accessed_count"):
                if a.get(field) != b.get(field):
                    diffs.append(f"{mid}.{field}: log {a.get(field)!r} vs table {b.get(field)!r}")
            if bool(a.get("revoked_at")) != bool(b.get("revoked_at")):
                diffs.append(f"{mid}.revoked: log {bool(a.get('revoked_at'))} vs table {bool(b.get('revoked_at'))}")
        return {"ok": not diffs, "items": len(rows), "differences": diffs[:20]}

    def stats(self, namespace: str) -> Dict[str, Any]:
        with self._p._connect() as conn:
            events = conn.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(payload) + LENGTH(provenance)), 0) FROM memory_events WHERE namespace = ?", (namespace,)).fetchone()
            kinds = dict(conn.execute("SELECT kind, COUNT(*) FROM memory_events WHERE namespace = ? GROUP BY kind", (namespace,)).fetchall())
            cps = conn.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(state_zstd)), 0), COALESCE(MAX(upto_seq), 0) FROM memory_checkpoints WHERE namespace = ?", (namespace,)).fetchone()
        live = self.fold(namespace)
        return {"namespace": namespace, "events": int(events[0]), "event_bytes": int(events[1]), "by_kind": kinds, "checkpoints": int(cps[0]), "checkpoint_bytes": int(cps[1]),
                "last_checkpoint_seq": int(cps[2]), "live_memories": len(live), "head": self.head()}

    # ----------------------------------------------------------------------------------------- a portable archive
    def export_archive(self, namespace: str, path: str) -> Dict[str, Any]:
        """One zstd stream: a header, every event of this person, the final state and the chain head. `verify_archive` re-checks it with no database."""
        import zstandard
        with self._p._connect() as conn:
            events = [dict(zip(("seq", "namespace", "kind", "memory_id", "payload", "provenance", "created_at", "prev_hash", "event_hash"), r, strict=True))
                      for r in conn.execute("SELECT seq, namespace, kind, memory_id, payload, provenance, created_at, prev_hash, event_hash FROM memory_events WHERE namespace = ? ORDER BY seq", (namespace,))]
        lines = [_canon({"format": "delentia-memory-archive-1", "namespace": namespace, "events": len(events)})] + [_canon(e) for e in events] + [_canon({"final_state": self.fold(namespace, include_revoked=True)})]
        raw = ("\n".join(lines) + "\n").encode("utf-8")
        blob = zstandard.ZstdCompressor(level=9, write_checksum=True).compress(raw)
        with open(path, "wb") as fh:
            fh.write(blob)
        return {"path": path, "events": len(events), "raw_bytes": len(raw), "archive_bytes": len(blob)}


def verify_archive(path: str) -> Dict[str, Any]:
    """Needs only the file: decompress (zstd checks its own checksum), re-fold the events and compare with the stored final state; the links between a person's own events cannot be
    checked here (they were chained with other people's events too), so what is verified is the content of each event against its hash chain segment and the final state."""
    import zstandard
    try:
        raw = zstandard.ZstdDecompressor().decompress(open(path, "rb").read())
    except Exception as exc:                                                # noqa: BLE001
        return {"ok": False, "problems": [f"the archive cannot be read: {type(exc).__name__}"]}
    lines = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    header, final, events = lines[0], lines[-1], lines[1:-1]
    problems: List[str] = []
    if header.get("format") != "delentia-memory-archive-1" or header.get("events") != len(events):
        problems.append("the header does not match the events")
    state: Dict[str, Dict[str, Any]] = {}
    for e in events:
        if event_hash(e["prev_hash"], e["namespace"], e["kind"], e["memory_id"], e["payload"], e["provenance"], e["created_at"]) != e["event_hash"]:
            problems.append(f"event {e['seq']}: its content does not match its hash")
        _apply(state, e["kind"], e["memory_id"], json.loads(e["payload"]), e["created_at"])
    if state != final.get("final_state"):
        problems.append("the final state does not equal the replay of the events")
    return {"ok": not problems, "events": len(events), "problems": problems[:10]}


# ----------------------------------------------------------------------------------------- Q2: what the model is shown
def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", str(text or "").lower())).strip()


def select_for_recall(candidates: List[Dict[str, Any]], policy: Optional[str] = None, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Read-time filter over memory candidates. Nothing is stored, changed or deleted; the dropped ones are simply not offered to the matcher."""
    policy = (policy or os.environ.get(POLICY_ENV) or "none").strip().lower()
    if policy not in POLICIES or policy == "none":
        return candidates
    if policy == "dedupe":
        best: Dict[str, Dict[str, Any]] = {}
        for c in candidates:
            key = _normal(str(c.get("content") or ""))
            kept = best.get(key)
            if kept is None or (str(c.get("created_at")), float(c.get("importance") or 0)) > (str(kept.get("created_at")), float(kept.get("importance") or 0)):
                best[key] = c
        keep_ids = {id(v) for v in best.values()}
        return [c for c in candidates if id(c) in keep_ids]
    ttl_days = _int_env(TTL_ENV, 30)
    cutoff = (now if now is not None else time.time()) - ttl_days * 86400
    out = []
    for c in candidates:
        if c.get("memory_type") in EPISODIC and float(c.get("importance") or 0) < HIGH_IMPORTANCE:
            try:
                created = datetime.fromisoformat(str(c.get("created_at"))).timestamp()
            except ValueError:
                created = cutoff + 1
            if created < cutoff:
                continue
        out.append(c)
    return out

"""
Round 66: the memory pipeline, redesigned as an append-only event log (Round 67: on by default; DELENTIA_MEMORY_EVENTLOG=off turns it off).

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

Round 67 - ANCHORED IN THE AUDIT CHAIN. The event chain alone cannot tell a host that rewrote the WHOLE log (recomputing every hash) from one that never did. Every
DELENTIA_MEMORY_ANCHOR_EVERY events (default 50, 0 = off) the head of this chain (sequence number and hash) is written as an audit row in the same transaction, so it is covered by whatever
protects the audit chain: the signature, the notary, the witness. `verify_anchors` then checks that the event at each anchored sequence still has the hash it had when it was anchored. What
that defeats: rewriting or cutting history up to the latest anchor. What it does not: events written after the latest anchor (`unanchored_events` says how many).

PDPA / erasure (Round 67, memory_erasure.py): event payloads and checkpoints are SEALED with a key that belongs to one person (DELENTIA_MEMORY_SEAL=off disables sealing). The hash covers
the ciphertext, so destroying the key erases the text without breaking the chain. Events written before sealing was on stay readable and are counted in the erasure report.
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
KINDS = ("add", "touch", "revoke", "edit", "erase")
SEALED_KINDS = ("add", "edit", "revoke")
ANCHOR_ENV = "DELENTIA_MEMORY_ANCHOR_EVERY"
ANCHOR_ENTITY = "memory_log"
ANCHOR_ACTION = "memory_log_anchor"
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
    """On unless switched off (Round 67; it was opt-in in Round 66). The log changed no answer in the measurements, adds under a millisecond to a write, and is what revocation as a
    fact, time travel, the anchors and per-person erasure rest on. DELENTIA_MEMORY_EVENTLOG=off turns it off."""
    return (os.environ.get(ENABLE_ENV) or "").strip().lower() not in ("0", "off", "false", "no")


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
    from rct_control_plane import memory_erasure
    body, prov, now = _canon(payload), _canon(provenance or {}), datetime.now(timezone.utc).isoformat()
    if kind in SEALED_KINDS:
        body = memory_erasure.seal(namespace, body)
    h = event_hash(prev_hash, namespace, kind, memory_id, body, prov, now)
    cur = conn.execute("INSERT INTO memory_events (namespace, kind, memory_id, payload, provenance, created_at, prev_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (namespace, kind, memory_id, body, prov, now, prev_hash, h))
    seq = int(cur.lastrowid or 0)
    _maybe_anchor(conn, seq, h)
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


def _maybe_anchor(conn: sqlite3.Connection, seq: int, event_hash_value: str, force: bool = False) -> bool:
    """Writes the chain head into the audit chain when ANCHOR_EVERY events have passed since the last anchor. Never raises: a missing audit table must not stop a memory write."""
    every = _int_env(ANCHOR_ENV, 50)
    if every <= 0 and not force:
        return False
    try:
        row = conn.execute("SELECT changes FROM audit_trail WHERE entity_type = ? ORDER BY id DESC LIMIT 1", (ANCHOR_ENTITY,)).fetchone()
        last = int(json.loads(row[0]).get("head_seq", 0)) if row else 0
        if not force and seq - last < every:
            return False
        from rct_control_plane.persistence import ControlPlanePersistence
        ControlPlanePersistence._append_audit(conn, ANCHOR_ENTITY, "log", ANCHOR_ACTION, "memory_eventlog",
                                              {"head_seq": seq, "head_hash": event_hash_value, "events_since_last_anchor": seq - last})
        return True
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        return False


def _int_env(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def _apply(state: Dict[str, Dict[str, Any]], kind: str, memory_id: str, payload: Dict[str, Any], at: str) -> None:
    if payload.get("_erased"):                           # the text was sealed and the person's key has been destroyed: the memory still existed, its text does not
        if kind == "add":
            state[memory_id] = {"id": memory_id, "content": "[erased]", "memory_type": None, "importance": None, "context": {}, "accessed_count": 0, "last_accessed": None,
                                "revoked_at": None, "revoked_reason": None, "erased": True}
        elif memory_id in state and kind == "revoke":
            state[memory_id]["revoked_at"] = at
            state[memory_id]["revoked_reason"] = "[erased]"
        elif memory_id in state and kind == "touch":
            state[memory_id]["accessed_count"] += 1
        return
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
        from rct_control_plane import memory_erasure
        blob = bytes(row[1])
        if memory_erasure.is_sealed_bytes(blob):
            if hashlib.sha256(blob).hexdigest() != row[2]:                  # the hash covers the ciphertext, so it can be checked without the key
                raise ValueError(f"checkpoint at seq {row[0]} of {namespace!r} does not match its hash")
            opened = memory_erasure.open_bytes(namespace, blob)
            raw = zstandard.ZstdDecompressor().decompress(opened) if opened is not None else None      # None = the key was destroyed: replay from the first event instead
        else:
            raw = zstandard.ZstdDecompressor().decompress(blob)
            if hashlib.sha256(raw).hexdigest() != row[2]:
                raise ValueError(f"checkpoint at seq {row[0]} of {namespace!r} does not match its hash")
        if raw is not None:
            state, start = json.loads(raw), int(row[0])
    from rct_control_plane import memory_erasure as _me
    for _seq, kind, mid, payload, at in conn.execute("SELECT seq, kind, memory_id, payload, created_at FROM memory_events WHERE namespace = ? AND seq > ? AND seq <= ? ORDER BY seq",
                                                    (namespace, start, upto_seq if upto_seq is not None else 2 ** 62)):
        _apply(state, kind, mid, _me.open_payload(namespace, payload), at)
    return state


def _write_checkpoint(conn: sqlite3.Connection, namespace: str) -> int:
    import zstandard
    upto = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM memory_events WHERE namespace = ?", (namespace,)).fetchone()[0]
    state = _fold(conn, namespace, upto)
    from rct_control_plane import memory_erasure
    raw = _canon(state).encode("utf-8")
    packed = zstandard.ZstdCompressor(level=6).compress(raw)
    blob = memory_erasure.seal_bytes(namespace, packed)                       # a checkpoint holds the person's whole text, so it is sealed like the events
    digest = hashlib.sha256(blob).hexdigest() if memory_erasure.is_sealed_bytes(blob) else hashlib.sha256(raw).hexdigest()
    conn.execute("INSERT INTO memory_checkpoints (namespace, upto_seq, state_zstd, state_sha256, items, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (namespace, upto, blob, digest, len(state), datetime.now(timezone.utc).isoformat()))
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

    def anchor(self) -> Dict[str, Any]:
        """Anchor the current head now (the CLI and tests use this; writes also anchor on their own every ANCHOR_EVERY events)."""
        head = self.head()
        if head["seq"] == 0:
            return {"anchored": False, "reason": "the log is empty"}
        with self._p._connect() as conn:
            done = _maybe_anchor(conn, head["seq"], head["hash"], force=True)
        return {"anchored": done, "head": head}

    def verify_anchors(self) -> Dict[str, Any]:
        """Every anchored head must still be in the log with the hash it had. A cut log (the anchored event is gone) and a rewritten one (it has another hash) are named separately."""
        problems: List[str] = []
        latest, n = 0, 0
        with self._p._connect() as conn:
            rows = conn.execute("SELECT id, changes FROM audit_trail WHERE entity_type = ? AND action = ? ORDER BY id", (ANCHOR_ENTITY, ANCHOR_ACTION)).fetchall()
            for audit_id, changes in rows:
                n += 1
                try:
                    note = json.loads(changes)
                    want_seq, want_hash = int(note["head_seq"]), str(note["head_hash"])
                except (ValueError, KeyError, TypeError):
                    problems.append(f"anchor {audit_id}: unreadable")
                    continue
                got = conn.execute("SELECT event_hash FROM memory_events WHERE seq = ?", (want_seq,)).fetchone()
                if got is None:
                    problems.append(f"anchor {audit_id}: event {want_seq} no longer exists (the log was cut back to before it)")
                elif got[0] != want_hash:
                    problems.append(f"anchor {audit_id}: event {want_seq} has a different hash than when it was anchored (history up to it was rewritten)")
                else:
                    latest = max(latest, want_seq)
        head = self.head()
        return {"ok": not problems, "anchors": n, "latest_anchored_seq": latest, "unanchored_events": max(0, head["seq"] - latest), "problems": problems[:20]}

    def history(self, namespace: str, limit: int = 100, before_seq: Optional[int] = None) -> List[Dict[str, Any]]:
        """The events of one person, newest first, with a short preview: what the time-travel view lists."""
        limit = max(1, min(int(limit), 500))
        with self._p._connect() as conn:
            rows = conn.execute("SELECT seq, kind, memory_id, payload, provenance, created_at FROM memory_events WHERE namespace = ? AND (? IS NULL OR seq < ?) ORDER BY seq DESC LIMIT ?",
                                (namespace, before_seq, before_seq, limit)).fetchall()
        out = []
        for seq, kind, mid, payload, prov, at in rows:
            from rct_control_plane import memory_erasure
            body = memory_erasure.open_payload(namespace, payload)
            text = "[erased]" if body.get("_erased") else (body.get("content") or body.get("reason") or "")
            out.append({"seq": seq, "kind": kind, "memory_id": mid, "at": at, "preview": str(text)[:120], "tainted": bool(json.loads(prov).get("tainted")) if prov else False})
        return out

    def seq_at_time(self, namespace: str, iso_time: str) -> int:
        """The last event of this person at or before a moment (ISO 8601); 0 if there is none."""
        with self._p._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM memory_events WHERE namespace = ? AND created_at <= ?", (namespace, iso_time)).fetchone()
        return int(row[0])

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
            from rct_control_plane import memory_erasure
            for cid, ns, upto, blob, sha in conn.execute("SELECT id, namespace, upto_seq, state_zstd, state_sha256 FROM memory_checkpoints ORDER BY id"):
                try:
                    blob = bytes(blob)
                    check = hashlib.sha256(blob).hexdigest() if memory_erasure.is_sealed_bytes(blob) else hashlib.sha256(zstandard.ZstdDecompressor().decompress(blob)).hexdigest()
                    if check != sha:
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
                if a.get("erased") and field in ("content", "memory_type", "importance"):
                    continue                                                  # the text is gone on purpose (erasure); the table copy was scrubbed to the same marker
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
    sealed = 0
    for e in events:
        if event_hash(e["prev_hash"], e["namespace"], e["kind"], e["memory_id"], e["payload"], e["provenance"], e["created_at"]) != e["event_hash"]:
            problems.append(f"event {e['seq']}: its content does not match its hash")
        from rct_control_plane import memory_erasure
        body = memory_erasure.open_payload(e["namespace"], e["payload"])      # with the person's key on this machine a sealed event is replayed too; without it only its hash is checked
        if body.get("_erased"):
            sealed += 1
            continue
        _apply(state, e["kind"], e["memory_id"], body, e["created_at"])
    if not sealed and state != final.get("final_state"):
        problems.append("the final state does not equal the replay of the events")
    return {"ok": not problems, "events": len(events), "sealed_events": sealed, "replay_checked": not sealed, "problems": problems[:10]}


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

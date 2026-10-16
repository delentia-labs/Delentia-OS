"""
Round 83: a durable, versioned, verifiable log of state changes, on top of the Delta Engine's structural diff.

Why this exists. The DAAES TC-009 measured Delentia's `DeltaEngine` as it was shipped: it rebuilt exact states when nothing went wrong, and could not tell when a delta was missing or damaged
(it computed `DeltaBlock.checksum` and never read it), had no durable form, no version argument and no check for a writer working from an old state. The Architect asked for the engine to be
improved to meet the target before any paid test. This is that: the engine's own diff (`DeltaEngine.structural_ops` / `apply_structural_delta`) carries the changes, and the log around it
refuses what it cannot vouch for.

What it guarantees, and how each is tested (research/daaes TC-009 fault matrix, test_delta_log_round83_real.py):
  * exact reconstruction of any version, checked against the hash of the state it was built from;
  * a partial write, a changed delta, a missing delta, a delta that does not follow the one before it, a duplicate, an out-of-order commit and a stale writer are each DETECTED (an exception,
    never a state that might be wrong);
  * a snapshot that is damaged is skipped and an older one plus the deltas rebuilds the state; a snapshot that disagrees with the deltas is reported by verify();
  * one SQLite transaction per commit: a commit either happened completely or not at all;
  * `idempotency_key`: the same retry returns the same version, the same key with other content is a conflict;
  * `head_anchor()` returns the version and chain hash; kept somewhere else (the audit chain, a witness) it is what detects the newest versions being cut off, which no chain can see by itself.

What it does not do: it does not encrypt, does not stop someone who can write the file AND recompute every hash (an anchor held elsewhere is for that), and it carries JSON states only. It is not
a claim that deltas beat snapshots (Round 65 measured snapshot + zstd as small or smaller as a stream); it is the contract that a delta design has to meet to be trusted at all.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rct_control_plane.algo_25_delta_block import DeltaConflictError, DeltaEngine, DeltaIntegrityError

FORMAT = "delentia-delta-log-1"


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


class VersionedDeltaLog:
    def __init__(self, path: Optional[str] = None, *, initial_state: Optional[Dict[str, Any]] = None, engine: Optional[DeltaEngine] = None, snapshot_every: int = 50) -> None:
        self.path = str(path) if path else ":memory:"
        self.engine = engine or DeltaEngine()
        self.snapshot_every = snapshot_every
        self._lock = threading.RLock()
        self._cache: Optional[Tuple[int, str, Dict[str, Any]]] = None          # (version, chain hash, state) of the head this process last saw
        self.last_skipped_snapshots = 0
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._open()
        fresh = self._conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0
        if fresh:
            self._create(initial_state if initial_state is not None else {})
        elif initial_state is not None and initial_state != self.state_at(0):
            raise DeltaIntegrityError("this log was created from another initial state")

    # ------------------------------------------------------------------------------------------------------------------ setup
    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=30, check_same_thread=False)
        if self.path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS deltas (
                version INTEGER PRIMARY KEY, ops TEXT NOT NULL, ops_hash TEXT NOT NULL, chain_hash TEXT NOT NULL,
                at REAL NOT NULL, source TEXT NOT NULL, idem TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS snapshots (version INTEGER PRIMARY KEY, blob BLOB NOT NULL, state_hash TEXT NOT NULL);
            """)
        return conn

    def _create(self, initial: Dict[str, Any]) -> None:
        state_hash = digest(initial)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('format', ?)", (FORMAT,))
                self._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('genesis', ?)", (digest({"genesis": state_hash}),))
                self._write_snapshot(0, initial)
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def _genesis(self) -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'genesis'").fetchone()
        if row is None:
            raise DeltaIntegrityError("the log has no genesis record")
        return str(row[0])

    @staticmethod
    def _chain(prev: str, version: int, ops_hash: str, source: str, at: float) -> str:
        return digest({"prev": prev, "version": version, "ops_hash": ops_hash, "source": source, "at": at})

    def _write_snapshot(self, version: int, state: Dict[str, Any]) -> None:
        import zstandard
        self._conn.execute("INSERT OR REPLACE INTO snapshots (version, blob, state_hash) VALUES (?, ?, ?)",
                           (version, zstandard.ZstdCompressor(level=3).compress(canonical(state)), digest(state)))

    # ------------------------------------------------------------------------------------------------------------------ reading
    def head(self) -> int:
        row = self._conn.execute("SELECT MAX(version) FROM deltas").fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _chain_hash_at(self, version: int) -> str:
        if version == 0:
            return self._genesis()
        row = self._conn.execute("SELECT chain_hash FROM deltas WHERE version = ?", (version,)).fetchone()
        if row is None:
            raise DeltaIntegrityError(f"delta {version} is missing")
        return str(row[0])

    def head_anchor(self) -> Dict[str, Any]:
        """What to keep somewhere the log's writer cannot reach. With it, verify(anchor=...) notices the newest versions being cut off or the history being rewritten."""
        v = self.head()
        return {"format": FORMAT, "version": v, "chain_hash": self._chain_hash_at(v)}

    def _load_snapshot(self, blob: bytes, state_hash: str) -> Optional[Dict[str, Any]]:
        import zstandard
        try:
            state = json.loads(zstandard.ZstdDecompressor().decompress(bytes(blob)))
        except Exception:                                           # noqa: BLE001 - any unreadable snapshot is skipped, not trusted
            return None
        return state if digest(state) == state_hash else None

    def state_at(self, version: Optional[int] = None) -> Dict[str, Any]:
        """The state at `version` (default: the head), rebuilt from the nearest intact snapshot and the deltas after it, each checked. Raises DeltaIntegrityError rather than
        return a state that might be wrong."""
        with self._lock:
            head = self.head()
            target = head if version is None else version
            if target < 0 or target > head:
                raise DeltaIntegrityError(f"version {target} does not exist (head is {head})")
            base_state: Optional[Dict[str, Any]] = None
            base_version = 0
            skipped = 0
            for v, blob, state_hash in self._conn.execute("SELECT version, blob, state_hash FROM snapshots WHERE version <= ? ORDER BY version DESC", (target,)).fetchall():
                loaded = self._load_snapshot(blob, state_hash)
                if loaded is not None:
                    base_state, base_version = loaded, int(v)
                    break
                skipped += 1
            self.last_skipped_snapshots = skipped
            if base_state is None:
                raise DeltaIntegrityError("no intact snapshot to start from")
            prev = self._chain_hash_at(base_version) if base_version else self._genesis()
            state = base_state
            expected = base_version + 1
            for v, ops_json, ops_hash, chain_hash, at, source in self._conn.execute(
                    "SELECT version, ops, ops_hash, chain_hash, at, source FROM deltas WHERE version > ? AND version <= ? ORDER BY version", (base_version, target)):
                if v != expected:
                    raise DeltaIntegrityError(f"delta {expected} is missing (found {v}): a gap in the history")
                state, prev = self._apply_checked(state, v, ops_json, ops_hash, chain_hash, at, source, prev)
                expected += 1
            if expected != target + 1:
                raise DeltaIntegrityError(f"delta {expected} is missing: the history stops before {target}")
            return state

    def _apply_checked(self, state: Dict[str, Any], v: int, ops_json: str, ops_hash: str, chain_hash: str, at: float, source: str, prev: str) -> Tuple[Dict[str, Any], str]:
        try:
            ops = json.loads(ops_json)
        except ValueError as exc:
            raise DeltaIntegrityError(f"delta {v} is not valid JSON (a partial write)") from exc
        if digest(ops) != ops_hash:
            raise DeltaIntegrityError(f"delta {v} does not match its hash (it was changed)")
        if self._chain(prev, v, ops_hash, source, at) != chain_hash:
            raise DeltaIntegrityError(f"delta {v} does not follow the delta before it (one was removed, replaced or reordered)")
        try:
            return self.engine.apply_structural_delta(state, ops), chain_hash
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DeltaIntegrityError(f"delta {v} does not apply to the state before it ({type(exc).__name__})") from exc

    # ------------------------------------------------------------------------------------------------------------------ writing
    def commit(self, new_state: Dict[str, Any], *, base_version: Optional[int] = None, version: Optional[int] = None, source: str = "", idempotency_key: Optional[str] = None,
               at: Optional[float] = None) -> int:
        """Record the change from the current head state to `new_state` as the next version.

        base_version  the version the caller's change was based on; anything but the head is a DeltaConflictError (a stale writer never overwrites a newer change).
        version       the version the caller believes this is; anything but head+1 is a DeltaIntegrityError (a duplicate or an out-of-order delivery).
        idempotency_key  a retry of the same change returns the same version; the same key with other content is a DeltaConflictError."""
        at_time = float(at if at is not None else time.time())
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                head = self.head()
                if idempotency_key is not None:
                    row = self._conn.execute("SELECT version, ops_hash FROM deltas WHERE idem = ?", (idempotency_key,)).fetchone()
                    if row is not None:                         # a retry: the same content returns the same version, other content under the same key is a conflict
                        if digest(self.state_at(int(row[0]))) == digest(new_state):
                            self._conn.execute("COMMIT")
                            return int(row[0])
                        raise DeltaConflictError(f"idempotency key {idempotency_key!r} was used for other content (version {row[0]})")
                if base_version is not None and base_version != head:
                    raise DeltaConflictError(f"the change is based on version {base_version}, the head is {head}")
                if version is not None and version != head + 1:
                    raise DeltaIntegrityError(f"version {version} is not the next one ({head + 1}): a duplicate or out-of-order delivery")
                current = self._head_state(head)
                ops = self.engine.structural_ops(current, new_state)
                ops_hash = digest(ops)
                nxt = head + 1
                chain = self._chain(self._chain_hash_at(head), nxt, ops_hash, source, at_time)
                self._conn.execute("INSERT INTO deltas (version, ops, ops_hash, chain_hash, at, source, idem) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                   (nxt, canonical(ops).decode("utf-8"), ops_hash, chain, at_time, source, idempotency_key))
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._cache = (nxt, chain, deepcopy(new_state))
            if self.snapshot_every and nxt % self.snapshot_every == 0:
                self.snapshot()
            return nxt

    def _head_state(self, head: int) -> Dict[str, Any]:
        """The state at the head, from the cache when this process wrote it and nobody else has since; otherwise rebuilt and checked."""
        if self._cache is not None and self._cache[0] == head and self._chain_hash_at(head) == self._cache[1]:
            return deepcopy(self._cache[2])
        state = self.state_at(head)
        self._cache = (head, self._chain_hash_at(head), deepcopy(state))
        return state

    def snapshot(self) -> int:
        """Write a snapshot of the current head (built from the checked history, so a damaged history is never frozen into a snapshot)."""
        with self._lock:
            head = self.head()
            state = self.state_at(head)
            self._write_snapshot(head, state)
            return head

    # ------------------------------------------------------------------------------------------------------------------ checking
    def verify(self, anchor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Replay the whole history from the genesis snapshot and report every problem: gaps, changed or malformed deltas, a broken chain, a delta that does not apply, a snapshot that
        disagrees with the deltas. With an anchor kept elsewhere it also reports a cut-off tail or a rewritten past. Changes nothing."""
        problems: List[str] = []
        with self._lock:
            genesis = self._conn.execute("SELECT blob, state_hash FROM snapshots WHERE version = 0").fetchone()
            state: Optional[Dict[str, Any]] = self._load_snapshot(genesis[0], genesis[1]) if genesis else None
            if state is None:
                problems.append("the genesis snapshot is missing or damaged: the history cannot be replayed")
            prev = self._genesis()
            expected = 1
            good_until = 0
            states: Dict[int, str] = {0: digest(state)} if state is not None else {}
            chain_at: Dict[int, str] = {0: prev}
            for v, ops_json, ops_hash, chain_hash, at, source in self._conn.execute("SELECT version, ops, ops_hash, chain_hash, at, source FROM deltas ORDER BY version").fetchall():
                if v != expected:
                    problems.append(f"delta {expected} is missing (found {v})")
                    state = None
                    expected = v
                if state is not None:
                    try:
                        state, prev = self._apply_checked(state, v, ops_json, ops_hash, chain_hash, at, source, prev)
                        states[v] = digest(state)
                        good_until = v
                    except DeltaIntegrityError as exc:
                        problems.append(str(exc))
                        state = None
                else:
                    prev = chain_hash
                chain_at[v] = chain_hash
                expected = v + 1
            for v, blob, state_hash in self._conn.execute("SELECT version, blob, state_hash FROM snapshots ORDER BY version").fetchall():
                loaded = self._load_snapshot(blob, state_hash)
                if loaded is None:
                    problems.append(f"snapshot {v} is damaged")
                elif v in states and states[v] != state_hash:
                    problems.append(f"snapshot {v} does not match the history it should summarise")
            head = self.head()
            if anchor:
                if head < int(anchor["version"]):
                    problems.append(f"the log ends at version {head} but the anchor was taken at {anchor['version']}: the newest versions were cut off")
                elif chain_at.get(int(anchor["version"])) != anchor["chain_hash"]:
                    problems.append(f"the history up to version {anchor['version']} differs from the anchor: it was rewritten")
            return {"ok": not problems, "problems": problems[:20], "head": head, "last_good_version": good_until, "snapshots": self._conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]}

    # ------------------------------------------------------------------------------------------------------------------ anchoring in the audit chain
    ANCHOR_ENTITY = "delta_log"
    ANCHOR_ACTION = "delta_log_anchor"

    def anchor_to_audit(self, persistence: Any, name: str = "default") -> Dict[str, Any]:
        """Write the head (version + chain hash) into the audit chain. The audit chain is signed and can be witnessed elsewhere, so from then on cutting the newest versions of this log or
        rewriting it up to that point is visible to verify_against_audit() even by someone who can recompute every hash in this file."""
        anchor = self.head_anchor()
        persistence.append_audit(entity_type=self.ANCHOR_ENTITY, entity_id=name, action=self.ANCHOR_ACTION, actor="delta_log", changes=anchor)
        return anchor

    def verify_against_audit(self, persistence: Any, name: str = "default") -> Dict[str, Any]:
        """Check this log against EVERY anchor written for `name`: each anchored version must still exist with the chain hash it had. Reports the newest versions not yet anchored."""
        problems: List[str] = []
        anchors = 0
        newest = 0
        with persistence._connect() as conn:
            rows = conn.execute("SELECT id, changes FROM audit_trail WHERE entity_type = ? AND entity_id = ? AND action = ? ORDER BY id", (self.ANCHOR_ENTITY, name, self.ANCHOR_ACTION)).fetchall()
        report = self.verify()
        problems += report["problems"]
        for audit_id, changes in rows:
            anchors += 1
            try:
                note = json.loads(changes)
                version, chain_hash = int(note["version"]), str(note["chain_hash"])
            except (ValueError, KeyError, TypeError):
                problems.append(f"anchor {audit_id} is unreadable")
                continue
            if self.head() < version:
                problems.append(f"anchor {audit_id}: the log ends at version {self.head()} but was anchored at {version}: the newest versions were cut off")
                continue
            try:
                current = self._chain_hash_at(version)
            except DeltaIntegrityError:
                problems.append(f"anchor {audit_id}: version {version} is missing")
                continue
            if current != chain_hash:
                problems.append(f"anchor {audit_id}: version {version} has another chain hash than when it was anchored: the history up to it was rewritten")
            else:
                newest = max(newest, version)
        return {"ok": not problems, "anchors": anchors, "latest_anchored_version": newest, "unanchored_versions": max(0, self.head() - newest), "problems": problems[:20]}

    def last_good_version(self) -> int:
        """The newest version up to which the history replays cleanly. Nothing is deleted: a person decides what to do about the versions after it."""
        return int(self.verify()["last_good_version"])

    def sizes(self) -> Dict[str, int]:
        d = int(self._conn.execute("SELECT COALESCE(SUM(LENGTH(ops) + LENGTH(ops_hash) + LENGTH(chain_hash)), 0) FROM deltas").fetchone()[0])
        s = int(self._conn.execute("SELECT COALESCE(SUM(LENGTH(blob)), 0) FROM snapshots").fetchone()[0])
        return {"delta_bytes": d, "snapshot_bytes": s, "total_bytes": d + s}

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            finally:
                self._cache = None

    def reopen(self) -> None:
        self.close()
        self._conn = self._open()

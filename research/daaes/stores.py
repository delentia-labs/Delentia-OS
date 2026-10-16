"""
The stores TC-009 puts under test. One interface, four implementations, so the same fixture, the same oracle and the same fault matrix are applied to each.

  RefSnapshotStore         arm D4's replacement and the "full snapshot baseline": every commit writes a complete, hash-chained, atomically renamed snapshot file. Safe, simple, large.
  RefDeltaStore            a durable reference delta log built by the harness (SQLite, one transaction per commit, op hash + chain hash, periodic snapshots with fallback). It exists to show the
                           oracle and the fault matrix CAN be passed by a delta design, and to give Delentia's engine something to be measured against. It is NOT Delentia.
  DelentiaDeltaEngineStore Delentia's `algo_25_delta_block.DeltaEngine` as shipped: `compute_structural_delta` / `apply_structural_delta` carry the changes, `DeltaBlock` + `store_delta` hold them.
                           It has no durable form, no version argument and no verification on read; those are exactly what the matrix measures. Nothing is added to make it pass.
  DelentiaMemoryLogStore   Delentia's memory event log (`memory_eventlog`): durable, hash-chained, checkpointed. It carries MEMORY records only (add / edit / revoke), so it is run on the
                           `memory` profile of the fixture, never on the full one.

Interface: commit(version, op, new_state, base_version) / take_snapshot() / head() / reconstruct(version) / verify() / sizes() / reopen() / inject(fault) / close().
`reconstruct` raises StoreError when it DETECTS damage; returning a wrong state without raising is the failure the benchmark exists to find.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from research.daaes.core import canonical, digest
from research.daaes.state_fixture import reduce


class StoreError(Exception):
    """The store detected damage, a gap, a duplicate or an out-of-order write and refused."""


class ConflictError(StoreError):
    """A writer based its change on a version that is no longer the head."""


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class StateStore:
    name = "base"
    durable = True
    supports_versions = True
    profiles: tuple = ()                                            # () = any profile of the fixture

    def __init__(self, workdir: Path, initial: Dict[str, Any]) -> None:
        self.dir = Path(workdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.initial = deepcopy(initial)

    def commit(self, version: int, op: Dict[str, Any], new_state: Dict[str, Any], base_version: Optional[int] = None) -> None:
        raise NotImplementedError

    def take_snapshot(self) -> None:
        pass

    def head(self) -> int:
        raise NotImplementedError

    def reconstruct(self, version: int) -> Dict[str, Any]:
        raise NotImplementedError

    def verify(self) -> Dict[str, Any]:
        return {"ok": True, "problems": []}

    def sizes(self) -> Dict[str, int]:
        return {"delta_bytes": 0, "snapshot_bytes": 0, "total_bytes": 0}

    def reopen(self) -> None:
        pass

    def inject(self, fault: str, **kw: Any) -> Dict[str, Any]:
        return {"applied": False, "delivery": "n/a", "note": "not supported"}

    def close(self) -> None:
        pass


# ------------------------------------------------------------------------------------------------------------ full snapshot per commit
class RefSnapshotStore(StateStore):
    name = "ref_snapshot"

    def __init__(self, workdir: Path, initial: Dict[str, Any]) -> None:
        super().__init__(workdir, initial)
        self._parent = ""
        self._head = -1
        self._write(0, initial)

    def _path(self, v: int) -> Path:
        return self.dir / f"snap_{v:06d}.zst"

    def _record(self, v: int, state: Dict[str, Any], parent: str) -> bytes:
        import zstandard
        body = {"version": v, "parent_hash": parent, "state": state, "state_hash": digest(state)}
        body["record_hash"] = digest({"version": v, "parent_hash": parent, "state_hash": body["state_hash"]})
        return zstandard.ZstdCompressor(level=3).compress(canonical(body))

    def _write(self, v: int, state: Dict[str, Any]) -> None:
        blob = self._record(v, state, self._parent)
        atomic_write(self._path(v), blob)
        self._parent = digest({"version": v, "parent_hash": self._parent, "state_hash": digest(state)})
        self._head = v

    def head(self) -> int:
        return self._head

    def commit(self, version: int, op: Dict[str, Any], new_state: Dict[str, Any], base_version: Optional[int] = None) -> None:
        if base_version is not None and base_version != self._head:
            raise ConflictError(f"based on {base_version}, head is {self._head}")
        if version != self._head + 1:
            raise StoreError(f"version {version} is not head+1 ({self._head + 1}): duplicate or out of order")
        self._write(version, new_state)

    def _read(self, v: int) -> Dict[str, Any]:
        import zstandard
        try:
            raw = zstandard.ZstdDecompressor().decompress(self._path(v).read_bytes())
            body = json.loads(raw)
        except Exception as exc:                                    # noqa: BLE001 - any unreadable snapshot is a detection
            raise StoreError(f"snapshot {v} unreadable ({type(exc).__name__})") from exc
        if digest(body["state"]) != body["state_hash"]:
            raise StoreError(f"snapshot {v} does not match its hash")
        return body

    def reconstruct(self, version: int) -> Dict[str, Any]:
        return self._read(version)["state"]

    def verify(self) -> Dict[str, Any]:
        problems: List[str] = []
        parent = ""
        for v in range(0, self._head + 1):
            try:
                body = self._read(v)
            except (StoreError, OSError) as exc:
                problems.append(str(exc))
                break
            if body["parent_hash"] != parent:
                problems.append(f"snapshot {v}: parent hash differs (a snapshot is missing or replaced)")
            parent = digest({"version": v, "parent_hash": body["parent_hash"], "state_hash": body["state_hash"]})
        return {"ok": not problems, "problems": problems}

    def sizes(self) -> Dict[str, int]:
        total = sum(p.stat().st_size for p in self.dir.glob("snap_*.zst"))
        return {"delta_bytes": 0, "snapshot_bytes": total, "total_bytes": total}

    def reopen(self) -> None:
        versions = sorted(int(p.stem.split("_")[1]) for p in self.dir.glob("snap_*.zst"))
        self._head = versions[-1] if versions else -1
        try:
            body = self._read(self._head)
            self._parent = digest({"version": self._head, "parent_hash": body["parent_hash"], "state_hash": body["state_hash"]})
        except StoreError:
            pass

    def inject(self, fault: str, **kw: Any) -> Dict[str, Any]:
        head = self._head
        if fault == "partial_write":
            data = self._path(head).read_bytes()
            self._path(head).write_bytes(data[: len(data) // 2])
            return {"applied": True, "delivery": "n/a"}
        if fault in ("duplicate", "out_of_order", "concurrent"):
            return self._deliver(fault, kw)
        if fault == "missing_parent":
            self._path(max(1, head // 2)).unlink()
            return {"applied": True, "delivery": "n/a"}
        if fault == "checksum_corruption":
            import zstandard
            v = max(1, head // 2)
            body = json.loads(zstandard.ZstdDecompressor().decompress(self._path(v).read_bytes()))
            first = next(iter(body["state"]["tasks"] or body["state"]["memories"]))
            (body["state"]["tasks"] or body["state"]["memories"])[first]["tampered"] = True
            atomic_write(self._path(v), zstandard.ZstdCompressor().compress(canonical(body)))
            return {"applied": True, "delivery": "n/a"}
        if fault == "snapshot_crash":
            return {"applied": False, "delivery": "n/a", "note": "every commit is a snapshot: no separate snapshot to crash"}
        return {"applied": False, "delivery": "n/a", "note": "unknown fault"}

    def _deliver(self, fault: str, kw: Dict[str, Any]) -> Dict[str, Any]:
        op, state, head = kw["op"], kw["state"], self._head
        try:
            if fault == "duplicate":
                self.commit(head, op, state, None)
            elif fault == "out_of_order":
                self.commit(head + 2, op, state, None)
            else:
                self.commit(head + 1, op, state, base_version=head - 1)
        except StoreError:
            return {"applied": True, "delivery": "rejected"}
        return {"applied": True, "delivery": "accepted"}


# ------------------------------------------------------------------------------------------------------------ durable reference delta log
class RefDeltaStore(StateStore):
    name = "ref_delta"
    SNAPSHOT_EVERY_MARKERS = True

    def __init__(self, workdir: Path, initial: Dict[str, Any]) -> None:
        super().__init__(workdir, initial)
        self.db = self.dir / "ref_delta.sqlite"
        self._conn = sqlite3.connect(str(self.db), isolation_level=None)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS deltas (version INTEGER PRIMARY KEY, op TEXT NOT NULL, op_hash TEXT NOT NULL, chain_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots (version INTEGER PRIMARY KEY, blob BLOB NOT NULL, state_hash TEXT NOT NULL);
        """)
        self._chain0 = digest({"genesis": digest(initial)})
        self._write_snapshot(0, initial)
        self._cache_state = deepcopy(initial)

    def _write_snapshot(self, v: int, state: Dict[str, Any]) -> None:
        import zstandard
        self._conn.execute("INSERT OR REPLACE INTO snapshots (version, blob, state_hash) VALUES (?, ?, ?)", (v, zstandard.ZstdCompressor(level=3).compress(canonical(state)), digest(state)))

    def head(self) -> int:
        row = self._conn.execute("SELECT MAX(version) FROM deltas").fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _chain(self, prev: str, version: int, op_hash: str) -> str:
        return digest({"prev": prev, "version": version, "op_hash": op_hash})

    def commit(self, version: int, op: Dict[str, Any], new_state: Dict[str, Any], base_version: Optional[int] = None) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            head = self.head()
            if base_version is not None and base_version != head:
                raise ConflictError(f"based on {base_version}, head is {head}")
            if version != head + 1:
                raise StoreError(f"version {version} is not head+1 ({head + 1}): duplicate or out of order")
            prev = self._conn.execute("SELECT chain_hash FROM deltas WHERE version = ?", (head,)).fetchone()
            op_json = canonical(op).decode("utf-8")
            op_hash = digest(op)
            self._conn.execute("INSERT INTO deltas (version, op, op_hash, chain_hash) VALUES (?, ?, ?, ?)", (version, op_json, op_hash, self._chain(prev[0] if prev else self._chain0, version, op_hash)))
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._cache_state = deepcopy(new_state)

    def take_snapshot(self) -> None:
        self._write_snapshot(self.head(), self.reconstruct(self.head()))

    def _snapshots(self, upto: int) -> List[tuple]:
        return self._conn.execute("SELECT version, blob, state_hash FROM snapshots WHERE version <= ? ORDER BY version DESC", (upto,)).fetchall()

    def reconstruct(self, version: int) -> Dict[str, Any]:
        import zstandard
        base_state, base_version, skipped = None, 0, 0
        for v, blob, state_hash in self._snapshots(version):
            try:
                state = json.loads(zstandard.ZstdDecompressor().decompress(bytes(blob)))
                if digest(state) == state_hash:
                    base_state, base_version = state, v
                    break
            except Exception:                                       # noqa: BLE001 - a damaged snapshot is skipped; the older ones and the deltas can still rebuild the state
                pass
            skipped += 1
        if base_state is None:
            raise StoreError("no intact snapshot to start from")
        self.last_skipped_snapshots = skipped
        prev = self._conn.execute("SELECT chain_hash FROM deltas WHERE version = ?", (base_version,)).fetchone()
        prev_hash = prev[0] if prev else self._chain0
        expected = base_version + 1
        for v, op_json, op_hash, chain_hash in self._conn.execute("SELECT version, op, op_hash, chain_hash FROM deltas WHERE version > ? AND version <= ? ORDER BY version", (base_version, version)):
            if v != expected:
                raise StoreError(f"delta {expected} missing (found {v}): version gap")
            if digest(json.loads(op_json)) != op_hash:
                raise StoreError(f"delta {v} does not match its hash")
            if self._chain(prev_hash, v, op_hash) != chain_hash:
                raise StoreError(f"delta {v} does not follow the delta before it")
            base_state = reduce(base_state, json.loads(op_json))
            prev_hash, expected = chain_hash, expected + 1
        if expected != version + 1:
            raise StoreError(f"delta {expected} missing: version gap before {version}")
        return base_state

    def verify(self) -> Dict[str, Any]:
        problems: List[str] = []
        prev, expected = self._chain0, 1
        for v, op_json, op_hash, chain_hash in self._conn.execute("SELECT version, op, op_hash, chain_hash FROM deltas ORDER BY version"):
            if v != expected:
                problems.append(f"delta {expected} missing (found {v})")
                expected = v
            try:
                if digest(json.loads(op_json)) != op_hash:
                    problems.append(f"delta {v} does not match its hash")
            except ValueError:
                problems.append(f"delta {v} is not valid JSON (partial write)")
            if self._chain(prev, v, op_hash) != chain_hash:
                problems.append(f"delta {v} does not follow the delta before it")
            prev, expected = chain_hash, expected + 1
        import zstandard
        for v, blob, state_hash in self._conn.execute("SELECT version, blob, state_hash FROM snapshots"):
            try:
                if digest(json.loads(zstandard.ZstdDecompressor().decompress(bytes(blob)))) != state_hash:
                    problems.append(f"snapshot {v} does not match its hash")
            except Exception:                                       # noqa: BLE001
                problems.append(f"snapshot {v} unreadable")
        return {"ok": not problems, "problems": problems[:10]}

    def sizes(self) -> Dict[str, int]:
        d = int(self._conn.execute("SELECT COALESCE(SUM(LENGTH(op) + LENGTH(op_hash) + LENGTH(chain_hash)), 0) FROM deltas").fetchone()[0])
        s = int(self._conn.execute("SELECT COALESCE(SUM(LENGTH(blob)), 0) FROM snapshots").fetchone()[0])
        return {"delta_bytes": d, "snapshot_bytes": s, "total_bytes": d + s}

    def reopen(self) -> None:
        self._conn.close()
        self._conn = sqlite3.connect(str(self.db), isolation_level=None)

    def inject(self, fault: str, **kw: Any) -> Dict[str, Any]:
        head = self.head()
        if fault == "partial_write":
            self._conn.execute("UPDATE deltas SET op = SUBSTR(op, 1, LENGTH(op) / 2) WHERE version = ?", (head,))
            return {"applied": True, "delivery": "n/a"}
        if fault in ("duplicate", "out_of_order", "concurrent"):
            op, state = kw["op"], kw["state"]
            try:
                if fault == "duplicate":
                    self.commit(head, op, state)
                elif fault == "out_of_order":
                    self.commit(head + 2, op, state)
                else:
                    self.commit(head + 1, op, state, base_version=head - 1)
            except (StoreError, sqlite3.Error):
                return {"applied": True, "delivery": "rejected"}
            return {"applied": True, "delivery": "accepted"}
        if fault == "missing_parent":
            self._conn.execute("DELETE FROM deltas WHERE version = ?", (max(2, head // 2),))
            return {"applied": True, "delivery": "n/a"}
        if fault == "checksum_corruption":
            v = max(2, head // 2)
            row = self._conn.execute("SELECT op FROM deltas WHERE version = ?", (v,)).fetchone()
            op = json.loads(row[0])
            op["tampered"] = True
            self._conn.execute("UPDATE deltas SET op = ? WHERE version = ?", (canonical(op).decode("utf-8"), v))
            return {"applied": True, "delivery": "n/a"}
        if fault == "snapshot_crash":
            self.take_snapshot()
            self._conn.execute("UPDATE snapshots SET blob = SUBSTR(blob, 1, LENGTH(blob) / 2) WHERE version = (SELECT MAX(version) FROM snapshots)")
            return {"applied": True, "delivery": "n/a"}
        return {"applied": False, "delivery": "n/a", "note": "unknown fault"}

    def close(self) -> None:
        self._conn.close()


# ------------------------------------------------------------------------------------------------------------ Delentia: DeltaEngine as shipped
class DelentiaDeltaEngineStore(StateStore):
    name = "delentia_delta_engine"
    durable = False
    supports_versions = False

    def __init__(self, workdir: Path, initial: Dict[str, Any]) -> None:
        super().__init__(workdir, initial)
        from rct_control_plane.algo_25_delta_block import DeltaBlock, DeltaDiff, DeltaEngine, DeltaType
        self._DeltaBlock, self._DeltaDiff, self._DeltaType = DeltaBlock, DeltaDiff, DeltaType
        self.engine = DeltaEngine()
        self.session = "daaes"
        self._state = deepcopy(initial)
        self._head = 0

    def head(self) -> int:
        return self._head

    def commit(self, version: int, op: Dict[str, Any], new_state: Dict[str, Any], base_version: Optional[int] = None) -> None:
        # The engine has no version argument and no concurrency check: `version` and `base_version` are accepted and ignored, which is the behaviour being measured.
        patch = self.engine.compute_structural_delta(self._state, new_state)
        block = self._DeltaBlock(session_id=self.session, timestamp=float(version), delta_type=self._DeltaType.STATE_CHANGE,
                                 diff=self._DeltaDiff(modified=[{"structural_ops": patch["ops"], "version": version}]))
        self.engine.store_delta(block)
        self._state = deepcopy(new_state)
        self._head = max(self._head, version)

    def _blocks(self, upto: int) -> List[Any]:
        blocks = [b for b in self.engine.get_session_deltas(self.session) if b.timestamp <= upto]
        return sorted(blocks, key=lambda b: b.timestamp)

    def reconstruct(self, version: int) -> Dict[str, Any]:
        state = deepcopy(self.initial)
        for block in self._blocks(version):
            state = self.engine.apply_structural_delta(state, block.diff.modified[0]["structural_ops"])
        return state

    def verify(self) -> Dict[str, Any]:
        # The engine offers no verification call: a store that cannot check itself reports itself intact. `engine_checksums_hold` below is the HARNESS reading the engine's own checksum field.
        return {"ok": True, "problems": []}

    def engine_checksums_hold(self) -> bool:
        return all(b.checksum == b._compute_checksum() for b in self.engine.get_session_deltas(self.session))

    def sizes(self) -> Dict[str, int]:
        d = sum(len(canonical(b.diff.modified)) for b in self.engine.get_session_deltas(self.session))
        return {"delta_bytes": d, "snapshot_bytes": 0, "total_bytes": d}

    def inject(self, fault: str, **kw: Any) -> Dict[str, Any]:
        blocks = self.engine._deltas[self.session]
        head = self._head
        if fault == "partial_write":
            return {"applied": False, "delivery": "n/a", "note": "the engine keeps blocks in memory only: there is no durable record to write half of"}
        if fault in ("duplicate", "out_of_order", "concurrent"):
            op, state = kw["op"], kw["state"]
            try:
                if fault == "duplicate":
                    self.commit(head, op, state)
                    self._state_after_fault = None
                elif fault == "out_of_order":
                    self.commit(head + 2, op, state)
                else:
                    self.commit(head + 1, op, state, base_version=head - 1)
            except Exception:                                       # noqa: BLE001
                return {"applied": True, "delivery": "rejected"}
            return {"applied": True, "delivery": "accepted"}
        if fault == "missing_parent":
            del blocks[max(1, len(blocks) // 2)]
            return {"applied": True, "delivery": "n/a"}
        if fault == "checksum_corruption":
            b = blocks[max(1, len(blocks) // 2)]
            b.diff.modified[0]["structural_ops"] = b.diff.modified[0]["structural_ops"] + [{"op": "add", "path": "/tampered", "value": True}]
            return {"applied": True, "delivery": "n/a"}
        if fault == "snapshot_crash":
            return {"applied": False, "delivery": "n/a", "note": "the engine has no snapshots"}
        return {"applied": False, "delivery": "n/a", "note": "unknown fault"}


# ------------------------------------------------------------------------------------------------------------ Delentia: memory event log
class DelentiaMemoryLogStore(StateStore):
    name = "delentia_memory_log"
    profiles = ("memory",)
    supports_versions = False

    def __init__(self, workdir: Path, initial: Dict[str, Any]) -> None:
        super().__init__(workdir, initial)
        os.environ["DELENTIA_MEMORY_KEYS_DIR"] = str(self.dir / "keys")
        os.environ["DELENTIA_MEMORY_ANCHOR_EVERY"] = "0"
        from rct_control_plane import memory_eventlog as mel
        from rct_control_plane.persistence import ControlPlanePersistence
        self.mel = mel
        self.ns = "daaes"
        self.db = self.dir / "memlog.db"
        self.p = ControlPlanePersistence(db_path=str(self.db))
        self.log = mel.MemoryEventLog(self.p)
        self._seq_at: Dict[int, int] = {}
        with self.p._connect() as conn:
            for mid, rec in sorted(initial["memories"].items()):
                mel.append(conn, self.ns, "add", mid, {"content": rec["content"], "memory_type": "fact", "importance": rec["importance"], "context": {}})
        self._seq_at[0] = self.log.head()["seq"]
        self._head = 0

    def head(self) -> int:
        return self._head

    def commit(self, version: int, op: Dict[str, Any], new_state: Dict[str, Any], base_version: Optional[int] = None) -> None:
        # The memory log has no version argument and no optimistic concurrency: both are accepted and ignored (that is what the matrix measures).
        with self.p._connect() as conn:
            if op["kind"] == "create":
                self.mel.append(conn, self.ns, "add", op["id"], {"content": op["value"]["content"], "memory_type": "fact", "importance": op["value"]["importance"], "context": {}})
            elif op["kind"] == "update":
                self.mel.append(conn, self.ns, "edit", op["id"], {"content": op["set"]["content"]})
            elif op["kind"] in ("soft_delete", "delete"):
                self.mel.append(conn, self.ns, "revoke", op["id"], {"reason": "delete"})
            else:
                raise StoreError(f"the memory log carries memory records only: {op['kind']}")
        self._seq_at[version] = self.log.head()["seq"]
        self._head = max(self._head, version)

    def reconstruct(self, version: int) -> Dict[str, Any]:
        verdict = self.log.verify()
        if not verdict["ok"]:
            raise StoreError("; ".join(verdict["problems"][:2]))
        folded = self.log.fold(self.ns, upto_seq=self._seq_at[version], include_revoked=True)
        return {"projects": {}, "tasks": {}, "intents": {}, "links": {},
                "memories": {mid: {"content": m["content"], "importance": m["importance"], "revoked": bool(m.get("revoked_at"))} for mid, m in folded.items()}}

    def verify(self) -> Dict[str, Any]:
        v = self.log.verify()
        return {"ok": v["ok"], "problems": v["problems"]}

    def take_snapshot(self) -> None:
        self.log.checkpoint(self.ns)

    def sizes(self) -> Dict[str, int]:
        with self.p._connect() as conn:
            d = int(conn.execute("SELECT COALESCE(SUM(LENGTH(payload) + LENGTH(provenance) + LENGTH(prev_hash) + LENGTH(event_hash)), 0) FROM memory_events").fetchone()[0])
            s = int(conn.execute("SELECT COALESCE(SUM(LENGTH(state_zstd)), 0) FROM memory_checkpoints").fetchone()[0])
        return {"delta_bytes": d, "snapshot_bytes": s, "total_bytes": d + s}

    def reopen(self) -> None:
        from rct_control_plane.persistence import ControlPlanePersistence
        self.p = ControlPlanePersistence(db_path=str(self.db))
        self.log = self.mel.MemoryEventLog(self.p)

    def close(self) -> None:
        import gc
        self.log = None                                              # type: ignore[assignment]
        self.p = None                                                # type: ignore[assignment]
        gc.collect()                                                 # persistence opens a connection per call and never closes it; on Windows the file stays locked until it is collected

    def inject(self, fault: str, **kw: Any) -> Dict[str, Any]:
        with self.p._connect() as conn:
            last = conn.execute("SELECT MAX(seq) FROM memory_events").fetchone()[0]
            mid = self._seq_at[max(1, self._head // 2)]
            if fault == "partial_write":
                conn.execute("UPDATE memory_events SET payload = SUBSTR(payload, 1, LENGTH(payload) / 2) WHERE seq = ?", (last,))
                return {"applied": True, "delivery": "n/a"}
            if fault in ("duplicate", "out_of_order", "concurrent"):
                op, state = kw["op"], kw["state"]
                if fault == "duplicate":
                    self.commit(self._head, op, state)
                elif fault == "out_of_order":
                    self.commit(self._head + 2, op, state)
                else:
                    self.commit(self._head + 1, op, state, base_version=self._head - 1)
                return {"applied": True, "delivery": "accepted"}
            if fault == "missing_parent":
                conn.execute("DELETE FROM memory_events WHERE seq = ?", (mid,))
                return {"applied": True, "delivery": "n/a"}
            if fault == "checksum_corruption":
                conn.execute("UPDATE memory_events SET payload = payload || ' ' WHERE seq = ?", (mid,))
                return {"applied": True, "delivery": "n/a"}
            if fault == "snapshot_crash":
                self.log.checkpoint(self.ns)
                conn.execute("UPDATE memory_checkpoints SET state_zstd = SUBSTR(state_zstd, 1, LENGTH(state_zstd) / 2) WHERE id = (SELECT MAX(id) FROM memory_checkpoints)")
                return {"applied": True, "delivery": "n/a"}
        return {"applied": False, "delivery": "n/a", "note": "unknown fault"}


STORES = {cls.name: cls for cls in (RefSnapshotStore, RefDeltaStore, DelentiaDeltaEngineStore, DelentiaMemoryLogStore)}


def timed(fn: Any, *args: Any, **kw: Any) -> tuple:
    t = time.perf_counter()
    out = fn(*args, **kw)
    return out, time.perf_counter() - t

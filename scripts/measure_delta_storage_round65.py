"""
Round 65 (Core Research Protocol section 19, "Storage"): does a delta log beat snapshots + zstd for an agent's memory, once everything a store needs is counted?

Six ways to store the SAME sequence of states (T snapshots of a memory table), each able to give back any tick exactly:

  raw             every snapshot as JSON
  zstd_stream     the whole snapshot log as one zstd stream
  zstd_each       every snapshot compressed on its own (random access)
  delta_raw       the runtime's own structural delta (DeltaEngine.compute_structural_delta, a JSON-Patch-style op list) with a full checkpoint every K ticks
  delta_zstd_stream   the delta log + checkpoints as one zstd stream
  delta_zstd_each     every delta record / checkpoint compressed on its own

Counted for every strategy, not only the payload: an 8-byte offset per record (the index), an 8-byte checksum per record (the strategies are compared WITH detection of damage),
the checkpoints, and the tombstones (a delete is a "remove" op). Measured: bytes, encode time, the time to give back one tick (mean over 40 random ticks), whether
EVERY tick comes back byte-exact, and what one damaged byte costs (how many ticks can no longer be rebuilt, and whether the damage was noticed).

The state sequences are synthetic but come from the runtime's real writers where possible: `runtime_memory_table` drives ControlPlanePersistence.save_memory / touch_memory
and dumps the real `memories` table after every operation. The others are controlled change rates (sparse, typical, dense) so the answer can be read against the rate of change.

What this does NOT show: that any strategy is better for a model's answers (storage says nothing about intelligence); behaviour on very large states; a hosted store.

    python scripts/measure_delta_storage_round65.py [--ticks 120] [--items 150] [--seeds 3] [--out research/delta_storage.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import zstandard  # noqa: E402

INDEX_BYTES, CHECK_BYTES = 8, 8
WORDS = ("budget vendor quote approval ticket urgent customer outage billing report preference sorted lowest highest owner deadline invoice contract renew delay refund "
         "รายงาน ใบเสนอราคา งบประมาณ ผู้อนุมัติ ลูกค้า เร่งด่วน ซ่อมบำรุง ส่งมอบ").split()


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def text(rng: random.Random, n: int = 14) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n))


# ----------------------------------------------------------------------------------------------- state sequences
def synthetic(items: int, ticks: int, rng: random.Random, *, add: int, touch: float, edit: float, delete: float) -> List[Dict[str, Any]]:
    state: Dict[str, Any] = {f"m{i:05d}": {"text": text(rng), "importance": round(rng.random(), 3), "accessed": 0, "last": 0} for i in range(items)}
    nxt = items
    seq = [json.loads(canon(state))]
    for t in range(1, ticks):
        for _ in range(add):
            state[f"m{nxt:05d}"] = {"text": text(rng), "importance": round(rng.random(), 3), "accessed": 0, "last": t}
            nxt += 1
        for key in list(state):
            r = rng.random()
            if r < delete and len(state) > 20:
                del state[key]
            elif r < delete + edit:
                state[key]["text"] = text(rng)
            elif r < delete + edit + touch:
                state[key]["accessed"] += 1
                state[key]["last"] = t
        seq.append(json.loads(canon(state)))
    return seq


def runtime_memory_table(items: int, ticks: int, rng: random.Random) -> List[Dict[str, Any]]:
    """The REAL writers: ControlPlanePersistence.save_memory and touch_memory, with the table dumped after every operation round."""
    from rct_control_plane.persistence import ControlPlanePersistence
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = ControlPlanePersistence(db_path=str(Path(tmp) / "m.db"))
        ids: List[str] = []

        def dump() -> Dict[str, Any]:
            return {m["id"]: {k: m[k] for k in ("memory_type", "content", "importance", "accessed_count", "last_accessed", "created_at")} for m in p.list_memories("bench")}

        for i in range(items):
            mid = f"mem_{i:08x}"
            p.save_memory(mid, "bench", rng.choice(["fact", "preference", "event"]), text(rng), {}, round(rng.random(), 3))
            ids.append(mid)
        seq = [dump()]
        for t in range(1, ticks):
            for _ in range(2):
                mid = f"mem_{len(ids):08x}"
                p.save_memory(mid, "bench", rng.choice(["fact", "preference", "event"]), text(rng), {}, round(rng.random(), 3))
                ids.append(mid)
            for mid in rng.sample(ids, max(1, len(ids) // 20)):
                p.touch_memory(mid)
            seq.append(dump())
        return seq


# ----------------------------------------------------------------------------------------------- strategies
class Store:
    name = ""

    def encode(self, seq: List[Dict[str, Any]]) -> None: ...
    def total_bytes(self) -> int: ...
    def get(self, tick: int) -> Dict[str, Any]: ...
    def damage(self, rng: random.Random) -> None: ...      # flip one byte somewhere in the stored payload


def _frame(records: List[bytes]) -> Tuple[bytes, List[int]]:
    offsets, blob, pos = [], bytearray(), 0
    for r in records:
        offsets.append(pos)
        blob += r
        pos += len(r)
    return bytes(blob), offsets


def _with_check(payload: bytes) -> bytes:
    return payload + hashlib.sha256(payload).digest()[:CHECK_BYTES]


def _check(record: bytes) -> bytes:
    payload, check = record[:-CHECK_BYTES], record[-CHECK_BYTES:]
    if hashlib.sha256(payload).digest()[:CHECK_BYTES] != check:
        raise ValueError("checksum mismatch")
    return payload


class Records(Store):
    """One framed record per tick (a snapshot, or a delta/checkpoint), each carrying a checksum and an index entry. `compress` = None | 'each'."""

    def __init__(self, name: str, compress: str | None) -> None:
        self.name, self.compress = name, compress
        self.blob = b""
        self.offsets: List[int] = []

    def _pack(self, payload: bytes) -> bytes:
        if self.compress == "each":
            payload = zstandard.ZstdCompressor(level=6).compress(payload)
        return _with_check(payload)

    def _unpack(self, record: bytes) -> bytes:
        payload = _check(record)
        return zstandard.ZstdDecompressor().decompress(payload) if self.compress == "each" else payload

    def _record(self, i: int) -> bytes:
        end = self.offsets[i + 1] if i + 1 < len(self.offsets) else len(self.blob)
        return self.blob[self.offsets[i]:end]

    def total_bytes(self) -> int:
        return len(self.blob) + INDEX_BYTES * len(self.offsets)

    def damage(self, rng: random.Random) -> None:
        pos = len(self.blob) // 2 + rng.randint(-50, 50)
        self.blob = self.blob[:pos] + bytes([self.blob[pos] ^ 0xFF]) + self.blob[pos + 1:]


class Snapshots(Records):
    def encode(self, seq: List[Dict[str, Any]]) -> None:
        self.blob, self.offsets = _frame([self._pack(canon(s)) for s in seq])

    def get(self, tick: int) -> Dict[str, Any]:
        return json.loads(self._unpack(self._record(tick)))


class DeltaLog(Records):
    """The runtime's structural delta with a full checkpoint every `k` ticks. Tick t is rebuilt from the nearest checkpoint at or before t."""

    def __init__(self, name: str, compress: str | None, k: int) -> None:
        super().__init__(name, compress)
        self.k = k
        from rct_control_plane.algo_25_delta_block import DeltaEngine
        self.engine = DeltaEngine()

    def encode(self, seq: List[Dict[str, Any]]) -> None:
        records = []
        for t, state in enumerate(seq):
            if t % self.k == 0:
                records.append(self._pack(canon({"c": state})))                     # a checkpoint
            else:
                ops = self.engine.compute_structural_delta(seq[t - 1], state)["ops"]
                records.append(self._pack(canon({"d": ops})))                        # removals are "remove" ops: the tombstones
        self.blob, self.offsets = _frame(records)

    def get(self, tick: int) -> Dict[str, Any]:
        base = tick - tick % self.k
        state = json.loads(self._unpack(self._record(base)))["c"]
        for t in range(base + 1, tick + 1):
            state = self.engine.apply_structural_delta(state, json.loads(self._unpack(self._record(t)))["d"])
        return state


class Stream(Store):
    """The same records as one zstd stream: the best ratio and no random access (reading tick t means decoding the stream up to t; here, all of it)."""

    def __init__(self, name: str, inner: Records) -> None:
        self.name, self.inner = name, inner
        self.data = b""

    def encode(self, seq: List[Dict[str, Any]]) -> None:
        self.inner.compress = None
        self.inner.encode(seq)
        # the per-record checksums are dropped inside a stream: zstd's own content checksum covers it
        payload = b"".join(self.inner._unpack(self.inner._record(i)) + b"\n" for i in range(len(self.inner.offsets)))
        self.lengths = [len(self.inner._unpack(self.inner._record(i))) + 1 for i in range(len(self.inner.offsets))]
        self.data = zstandard.ZstdCompressor(level=6, write_checksum=True).compress(payload)

    def total_bytes(self) -> int:
        return len(self.data) + INDEX_BYTES * len(self.lengths)

    def _records(self) -> List[bytes]:
        raw = zstandard.ZstdDecompressor().decompress(self.data)
        out, pos = [], 0
        for n in self.lengths:
            out.append(raw[pos:pos + n - 1])
            pos += n
        return out

    def get(self, tick: int) -> Dict[str, Any]:
        records = self._records()
        if isinstance(self.inner, DeltaLog):
            k = self.inner.k
            base = tick - tick % k
            state = json.loads(records[base])["c"]
            for t in range(base + 1, tick + 1):
                state = self.inner.engine.apply_structural_delta(state, json.loads(records[t])["d"])
            return state
        return json.loads(records[tick])

    def damage(self, rng: random.Random) -> None:
        pos = len(self.data) // 2 + rng.randint(-20, 20)
        self.data = self.data[:pos] + bytes([self.data[pos] ^ 0xFF]) + self.data[pos + 1:]


def strategies(k: int) -> List[Callable[[], Store]]:
    return [
        lambda: Snapshots("raw", None),
        lambda: Stream("zstd_stream", Snapshots("x", None)),
        lambda: Snapshots("zstd_each", "each"),
        lambda: DeltaLog("delta_raw", None, k),
        lambda: Stream("delta_zstd_stream", DeltaLog("x", None, k)),
        lambda: DeltaLog("delta_zstd_each", "each", k),
    ]


def measure_one(make: Callable[[], Store], seq: List[Dict[str, Any]], rng: random.Random) -> Dict[str, Any]:
    store = make()
    t0 = time.perf_counter()
    store.encode(seq)
    encode_s = time.perf_counter() - t0
    wanted = [canon(s) for s in seq]
    exact = True
    for t in range(len(seq)):
        exact &= canon(store.get(t)) == wanted[t]
    sample = rng.sample(range(len(seq)), min(40, len(seq)))
    t0 = time.perf_counter()
    for t in sample:
        store.get(t)
    get_ms = (time.perf_counter() - t0) / len(sample) * 1000
    total = store.total_bytes()
    damaged = make()
    damaged.encode(seq)
    damaged.damage(random.Random(rng.random()))
    lost = silent = 0
    for t in range(len(seq)):
        try:
            if canon(damaged.get(t)) != wanted[t]:
                lost += 1
                silent += 1                     # came back, but wrong, and nothing said so
        except Exception:
            lost += 1                           # could not be rebuilt, and the failure was noticed
    return {"strategy": store.name, "bytes": total, "encode_s": round(encode_s, 4), "get_ms": round(get_ms, 3), "exact": bool(exact),
            "ticks_lost_after_one_damaged_byte": lost, "of_which_silently_wrong": silent}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--items", type=int, default=150)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--checkpoint", type=int, default=20, help="K: a full checkpoint every K ticks in the delta strategies")
    parser.add_argument("--out", default=str(ROOT / "research" / "delta_storage.json"))
    args = parser.parse_args()
    os.environ.setdefault("DELENTIA_HOME", tempfile.mkdtemp(prefix="delentia-delta-"))
    families: Dict[str, Callable[[random.Random], List[Dict[str, Any]]]] = {
        "sparse (1 new, 1% touched, no edits)": lambda r: synthetic(args.items, args.ticks, r, add=1, touch=0.01, edit=0.0, delete=0.0),
        "typical (2 new, 5% touched, 1% edited, 0.5% deleted)": lambda r: synthetic(args.items, args.ticks, r, add=2, touch=0.05, edit=0.01, delete=0.005),
        "dense (4 new, 30% touched, 10% edited, 3% deleted)": lambda r: synthetic(args.items, args.ticks, r, add=4, touch=0.30, edit=0.10, delete=0.03),
        "runtime_memory_table (real writers; 2 new + 5% touched per tick)": lambda r: runtime_memory_table(args.items, args.ticks, r),
    }
    report: Dict[str, Any] = {"ticks": args.ticks, "items": args.items, "seeds": args.seeds, "checkpoint_every": args.checkpoint, "families": {}}
    for name, make_seq in families.items():
        per_strategy: Dict[str, List[Dict[str, Any]]] = {}
        for seed in range(args.seeds):
            rng = random.Random(20261012 + seed)
            seq = make_seq(rng)
            for make in strategies(args.checkpoint):
                row = measure_one(make, seq, random.Random(seed))
                per_strategy.setdefault(row["strategy"], []).append(row)
        table = {}
        raw_bytes = statistics.mean(r["bytes"] for r in per_strategy["raw"])
        for strat, rows in per_strategy.items():
            mean_bytes = statistics.mean(r["bytes"] for r in rows)
            table[strat] = {"bytes_mean": round(mean_bytes), "bytes_range": [min(r["bytes"] for r in rows), max(r["bytes"] for r in rows)],
                            "vs_raw_pct": round((1 - mean_bytes / raw_bytes) * 100, 1), "encode_s": round(statistics.mean(r["encode_s"] for r in rows), 3),
                            "get_ms": round(statistics.mean(r["get_ms"] for r in rows), 2), "exact_all_ticks": all(r["exact"] for r in rows),
                            "ticks_lost_per_damaged_byte": round(statistics.mean(r["ticks_lost_after_one_damaged_byte"] for r in rows), 1),
                            "silently_wrong": round(statistics.mean(r["of_which_silently_wrong"] for r in rows), 1)}
        report["families"][name] = table
        print(f"\n{name}")
        print(f"{'strategy':<20}{'bytes':>10}{'vs raw':>9}{'encode s':>10}{'get ms':>9}{'exact':>7}{'lost/dmg':>10}{'silent':>8}")
        for strat, row in table.items():
            print(f"{strat:<20}{row['bytes_mean']:>10,}{row['vs_raw_pct']:>8}%{row['encode_s']:>10}{row['get_ms']:>9}{str(row['exact_all_ticks']):>7}{row['ticks_lost_per_damaged_byte']:>10}{row['silently_wrong']:>8}")
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

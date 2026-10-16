"""
TC-009 Memory Delta Integrity (specification section V), run against any store of stores.py.

What is checked, in this order, and what each outcome means:

  exactness   after every commit the store is asked to rebuild the state at the 10 snapshot points, 20 seeded random versions and the final one; each rebuilt state must hash to the state
              the independent reducer (state_fixture.reduce) produced. A store that raises on intact data fails the check; a store that returns another state fails it AND is a hard fail.
  recovery    the store is reopened (the process-restart stand-in; a non-durable store cannot be) and the final state must still be exact.
  faults      seven faults, each on a FRESH copy of the first `fault_ops` operations. The classification of a fault:
                rejected_at_write   duplicate / out-of-order / stale delivery was refused (PASS)
                detected            damage was found by verify() or reconstruct() raising (PASS)
                recovered           the damage was real, the store rebuilt the exact state from what remained (PASS)
                accepted_silently   a delivery that should have been refused was taken, but the rebuilt state is still the reference one (FAIL)
                unguarded           the store has no version argument, so it could not refuse a repeated, out-of-order or stale delivery (FAIL: a capability gap, not a hard failure)
                lost_update         as unguarded, and the second writer's change silently replaced the first's (FAIL: gap)
                undetected_harmless damage present, no detection, state still exact (FAIL: the store cannot tell)
                silent_wrong        no detection and the rebuilt state differs from the reference (HARD FAIL: the one outcome the benchmark exists to find)
                not_supported       the store has no such thing to damage (reported, never counted as a pass)
  performance write/read/recovery latency, bytes (delta, snapshot, total), amplification over the final state's canonical size, peak memory of one reconstruction.

Score = 0.50 exactness + 0.20 recovery + 0.20 corruption detection + 0.10 efficiency (the specification's proposed weights, pre-registered here). passed = score >= 90 AND exactness 100 AND no hard fail.
Efficiency compares against the full-snapshot store of the SAME run (delta compression is not guaranteed to beat snapshots, and here it is only credited when it does).
"""
from __future__ import annotations

import random
import statistics
import time
import tracemalloc
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from research.daaes.core import canonical
from research.daaes.state_fixture import make_ops, reduce, reference_states, state_hash
from research.daaes.stores import STORES, StateStore, StoreError

FAULTS = ("partial_write", "duplicate", "out_of_order", "missing_parent", "checksum_corruption", "snapshot_crash", "concurrent")
PASS_OUTCOMES = {"rejected_at_write", "detected", "recovered"}
WEIGHTS = {"exactness": 0.50, "recovery": 0.20, "corruption_detection": 0.20, "efficiency": 0.10}
THRESHOLD = 90.0


def profile_for(store_name: str, requested: Optional[str]) -> str:
    return requested or ("memory" if store_name == "delentia_memory_log" else "full")


def _load(store: StateStore, steps: List[Dict[str, Any]], refs: List[Dict[str, Any]], upto: Optional[int] = None) -> List[float]:
    """Applies the first `upto` state operations (snapshot markers in between), returns write latencies."""
    latencies: List[float] = []
    version = 0
    for step in steps:
        if step["kind"] == "snapshot":
            store.take_snapshot()
            continue
        if upto is not None and version >= upto:
            break
        version += 1
        t = time.perf_counter()
        store.commit(version, step, deepcopy(refs[version]), base_version=version - 1)
        latencies.append(time.perf_counter() - t)
    return latencies


def _conflict_ops(refs: List[Dict[str, Any]], n: int, profile: str) -> Dict[str, Any]:
    """Two writers change the same field of the same record from the same base; the second one must not silently overwrite the first."""
    entity, field = ("memories", "content") if profile == "memory" else ("tasks", "title")
    target = sorted(refs[n][entity])[0]
    op_a = {"kind": "update", "entity": entity, "id": target, "set": {field: "writer-A"}}
    op_b = {"kind": "update", "entity": entity, "id": target, "set": {field: "writer-B"}}
    state_a = reduce(refs[n], op_a)
    return {"op_a": op_a, "state_a": state_a, "op_b": op_b, "state_b_naive": reduce(state_a, op_b)}


def run_fault(store_name: str, fault: str, workdir: Path, initial: Dict[str, Any], steps: List[Dict[str, Any]], refs: List[Dict[str, Any]], fault_ops: int, profile: str) -> Dict[str, Any]:
    store = STORES[store_name](workdir, initial)
    try:
        _load(store, steps, refs, upto=fault_ops)
        n = min(store.head(), len(refs) - 1)
        kw: Dict[str, Any] = {}
        expected = refs[n]
        if fault == "duplicate":
            applied_ops = [s for s in steps if s["kind"] != "snapshot"][:n]
            op = applied_ops[-1]
            try:
                again = reduce(refs[n], op)                          # what a store that simply applies the delivery would hold afterwards
            except KeyError:
                again = deepcopy(refs[n])                            # re-delivering a create: a naive store ends with the same record
            kw = {"op": op, "state": again}
        elif fault == "out_of_order":
            nxt = [s for s in steps if s["kind"] != "snapshot"][n]
            kw = {"op": nxt, "state": refs[n + 1]}
        elif fault == "concurrent":
            c = _conflict_ops(refs, n, profile)
            store.commit(n + 1, c["op_a"], c["state_a"], base_version=n)
            expected = c["state_a"]
            kw = {"op": c["op_b"], "state": c["state_b_naive"]}
            n += 1
        result = store.inject(fault, **kw)
        if not result.get("applied"):
            return {"fault": fault, "outcome": "not_supported", "note": result.get("note", "")}
        delivery = result.get("delivery", "n/a")
        if delivery == "rejected":
            return {"fault": fault, "outcome": "rejected_at_write"}
        verified = store.verify()
        detected = not verified["ok"]
        try:
            rebuilt = store.reconstruct(store.head())
        except StoreError as exc:
            return {"fault": fault, "outcome": "detected", "how": f"reconstruct refused: {str(exc)[:90]}"}
        except Exception as exc:                                   # noqa: BLE001 - a crash that is not a clean refusal still means the damage was noticed, but not cleanly
            return {"fault": fault, "outcome": "detected", "how": f"crashed: {type(exc).__name__}"}
        same = state_hash(rebuilt) == state_hash(expected)
        if fault in ("duplicate", "out_of_order", "concurrent"):
            if delivery == "accepted":
                if not store.supports_versions:
                    # The caller cannot even present a version to this store, so "refuse a stale or repeated delivery" is not something its API can do. That is a capability gap, reported as such
                    # (a soft failure of the detection metric), not as a hard failure; damaged STORAGE that is not noticed is the hard failure.
                    return {"fault": fault, "outcome": "lost_update" if (fault == "concurrent" and not same) else "unguarded", "state_equals_expected": same}
                return {"fault": fault, "outcome": "silent_wrong" if not same else "accepted_silently", "detected_by_verify": detected}
        if detected:
            return {"fault": fault, "outcome": "detected", "how": "verify: " + "; ".join(verified["problems"][:1])}
        if same:
            recovered = fault == "snapshot_crash"
            return {"fault": fault, "outcome": "recovered" if recovered else "undetected_harmless"}
        return {"fault": fault, "outcome": "silent_wrong"}
    finally:
        store.close()


def run_tc009(store_name: str, workdir: Path, seed: int = 1701, profile: Optional[str] = None, fault_ops: int = 200, baseline_total_bytes: Optional[int] = None,
              log: Any = None) -> Dict[str, Any]:
    profile = profile_for(store_name, profile)
    allowed = STORES[store_name].profiles
    if allowed and profile not in allowed:
        raise ValueError(f"{store_name} carries {allowed} only (it was asked to carry the {profile!r} profile)")
    soft = store_name == "delentia_memory_log"
    initial, steps = make_ops(seed, profile, soft_delete=soft)
    refs = reference_states(initial, steps)
    workdir = Path(workdir)
    store = STORES[store_name](workdir / "main", initial)
    if log is not None:
        log.emit("run.started", {"case": "TC-009", "store": store_name, "seed": seed, "profile": profile, "operations": len(refs) - 1, "initial_hash": state_hash(initial)})
    try:
        write_latencies: List[float] = []
        version = 0
        for step in steps:
            if step["kind"] == "snapshot":
                store.take_snapshot()
                if log is not None:
                    log.emit("checkpoint.committed", {"version": version, "state_hash": state_hash(refs[version])}, state_version_before=version, state_version_after=version)
                continue
            version += 1
            t = time.perf_counter()
            store.commit(version, step, deepcopy(refs[version]), base_version=version - 1)
            write_latencies.append(time.perf_counter() - t)
            if log is not None:
                log.emit("memory.delta_committed", {"delta": step, "state_hash": state_hash(refs[version])}, state_version_before=version - 1, state_version_after=version)
        total_ops = version
        rng = random.Random(seed ^ 0x5EED)
        snapshot_versions = [i for i, s in enumerate((x for x in steps if x["kind"] != "snapshot"), start=1) if i % max(1, total_ops // 11) == 0][:10]
        checked = sorted(set(snapshot_versions + [rng.randint(1, total_ops) for _ in range(20)] + [total_ops, 0]))
        mismatches, raised = [], []
        read_ms: List[float] = []
        for v in checked:
            t = time.perf_counter()
            try:
                got = store.reconstruct(v)
            except StoreError as exc:
                raised.append((v, str(exc)[:80]))
                continue
            read_ms.append((time.perf_counter() - t) * 1000)
            if state_hash(got) != state_hash(refs[v]):
                mismatches.append(v)
        exact = len(checked) - len(mismatches) - len(raised)
        tracemalloc.start()
        store.reconstruct(total_ops)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()

        recovery_supported = store.durable
        recovery_ok = False
        recovery_ms = None
        if recovery_supported:
            t = time.perf_counter()
            store.reopen()
            try:
                recovery_ok = state_hash(store.reconstruct(total_ops)) == state_hash(refs[total_ops])
            except StoreError:
                recovery_ok = False
            recovery_ms = (time.perf_counter() - t) * 1000
        sizes = store.sizes()
        final_bytes = len(canonical(refs[total_ops]))
    finally:
        store.close()

    faults = [run_fault(store_name, f, workdir / f"fault_{f}", initial, steps, refs, min(fault_ops, total_ops), profile) for f in FAULTS]
    if log is not None:
        for f in faults:
            log.emit("fault.injected", {"fault": f["fault"], "outcome": f["outcome"]})
    supported = [f for f in faults if f["outcome"] != "not_supported"]
    passed_faults = [f for f in faults if f["outcome"] in PASS_OUTCOMES]
    hard_failures: List[str] = []
    if mismatches:
        hard_failures.append(f"wrong_state_at_versions_{mismatches[:5]}")
    hard_failures += [f"silent_wrong:{f['fault']}" for f in faults if f["outcome"] == "silent_wrong"]
    exactness = 100.0 * exact / len(checked)
    recovery = 100.0 if (recovery_supported and recovery_ok) else 0.0
    detection = 100.0 * len(passed_faults) / len(supported) if supported else 0.0             # a fault the store has nothing to damage for is reported, not counted against it
    efficiency: Optional[float] = None                                                          # the baseline itself has no efficiency to be credited: its weight is dropped and the rest renormalized
    if baseline_total_bytes:
        efficiency = max(0.0, min(100.0, 100.0 * (1 - sizes["total_bytes"] / baseline_total_bytes)))
    metrics = {"exactness": round(exactness, 2), "recovery": recovery, "corruption_detection": round(detection, 2), "efficiency": round(efficiency, 2) if efficiency is not None else None}
    used = {k: w for k, w in WEIGHTS.items() if metrics[k] is not None}
    score = round(sum(used[k] * metrics[k] for k in used) / sum(used.values()), 2)
    passed = score >= THRESHOLD and exactness == 100.0 and not hard_failures
    result = {
        "case": "TC-009", "store": store_name, "profile": profile, "seed": seed, "operations": total_ops, "states_checked": len(checked), "states_exact": exact,
        "mismatched_versions": mismatches, "refused_on_intact_data": raised, "faults": faults, "faults_supported": len(supported), "faults_passed": len(passed_faults),
        "metrics": metrics, "weights": WEIGHTS, "score": score, "threshold": THRESHOLD, "hard_failures": hard_failures, "passed": passed,
        "performance": {"write_ms_mean": round(statistics.mean(write_latencies) * 1000, 3), "write_ms_p95": round(sorted(write_latencies)[int(len(write_latencies) * 0.95)] * 1000, 3),
                        "read_ms_median": round(statistics.median(read_ms), 3) if read_ms else None, "recovery_ms": round(recovery_ms, 3) if recovery_ms is not None else None,
                        "peak_reconstruct_kib": round(peak / 1024, 1)},
        "storage": {**sizes, "final_state_bytes": final_bytes, "amplification": round(sizes["total_bytes"] / final_bytes, 3) if final_bytes else None},
        "durable": store.durable,
    }
    if log is not None:
        log.emit("oracle.evaluated", {"score": score, "passed": passed, "hard_failures": hard_failures, "final_state_hash": state_hash(refs[total_ops])})
        log.emit("run.completed", {"result": "passed" if passed else "failed"})
    return result

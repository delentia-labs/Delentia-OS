"""
Round 83, DAAES TC-009 (Memory Delta Integrity): the fixture is deterministic and has the specified size, the independent reducer is the oracle, the two reference stores pass the whole matrix, and
the Delentia stores are measured (the engine as it was used until Round 82, the engine after Round 83, the memory log). The Delentia findings are PINNED here on purpose: if the engine ever gains verification, these tests fail and the documents must be updated.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from collections import Counter
from copy import deepcopy

import pytest

from research.daaes import tc009
from research.daaes.state_fixture import ENTITIES, initial_state, make_ops, reduce, reference_states, state_hash
from research.daaes.stores import STORES, RefDeltaStore


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


def run(name, tmp_path, profile=None, base=None, fault_ops=60):
    return tc009.run_tc009(name, tmp_path / name, profile=profile, fault_ops=fault_ops, baseline_total_bytes=base)


# ---- the fixture
def test_the_full_profile_has_the_specified_size():
    state = initial_state(1701, "full")
    assert {e: len(state[e]) for e in ENTITIES} == {"projects": 100, "tasks": 1000, "intents": 50, "memories": 500, "links": 100}
    initial, steps = make_ops(1701, "full")
    kinds = Counter(s["kind"] for s in steps)
    assert kinds["snapshot"] == 10 and sum(v for k, v in kinds.items() if k != "snapshot") == 890
    assert kinds["create"] == 200 and kinds["update"] == 300 and kinds["delete"] == 100 and kinds["link"] + kinds["unlink"] == 100 and kinds["intent_revision"] == 90


def test_the_same_seed_gives_the_same_fixture_and_another_seed_a_different_one():
    a1, s1 = make_ops(1701, "small")
    a2, s2 = make_ops(1701, "small")
    b, s3 = make_ops(1702, "small")
    assert state_hash(a1) == state_hash(a2) and s1 == s2 and s1 != s3


def test_every_generated_operation_is_valid_against_the_state_it_meets():
    initial, steps = make_ops(7, "small")
    states = reference_states(initial, steps)                                        # raises if any operation does not fit
    assert len(states) == sum(1 for s in steps if s["kind"] != "snapshot") + 1


def test_the_reducer_is_a_pure_function_of_its_inputs():
    state = initial_state(3, "small")
    before = deepcopy(state)
    reduce(state, {"kind": "status", "id": sorted(state["tasks"])[0], "status": "done"})
    assert state == before
    with pytest.raises(KeyError):
        reduce(state, {"kind": "delete", "entity": "tasks", "id": "nope"})


def test_the_fixture_contains_thai_and_a_composed_decomposed_pair():
    text = " ".join(m["content"] for m in initial_state(1701, "full")["memories"].values())
    assert "สัญญา" in text and ("café" in text or "café" in text)


# ---- the reference stores pass; the oracle can fail
def test_the_snapshot_baseline_passes_every_check(tmp_path):
    r = run("ref_snapshot", tmp_path, "small")
    assert r["passed"] and r["states_exact"] == r["states_checked"] and r["hard_failures"] == []
    assert {f["fault"]: f["outcome"] for f in r["faults"]}["snapshot_crash"] == "not_supported"      # reported, not counted against it
    assert r["metrics"]["efficiency"] is None                                                         # the baseline is not credited for beating itself


def test_the_reference_delta_log_passes_every_fault_and_is_much_smaller(tmp_path):
    base = run("ref_snapshot", tmp_path, "small")["storage"]["total_bytes"]
    r = run("ref_delta", tmp_path, "small", base)
    assert r["passed"] and r["faults_passed"] == 7 and r["metrics"]["efficiency"] > 50
    assert {f["outcome"] for f in r["faults"]} <= {"detected", "rejected_at_write"}
    assert r["storage"]["total_bytes"] < base / 3


def test_a_store_with_a_wrong_reducer_is_caught_as_a_hard_failure(tmp_path, monkeypatch):
    class Buggy(RefDeltaStore):
        name = "ref_delta"

        def reconstruct(self, version):
            state = super().reconstruct(version)
            if version > 5:
                task = sorted(state["tasks"])[0] if state["tasks"] else None
                if task:
                    state["tasks"][task]["status"] = "corrupted-by-bug"
            return state
    monkeypatch.setitem(STORES, "ref_delta", Buggy)
    r = run("ref_delta", tmp_path, "small")
    assert r["passed"] is False and r["mismatched_versions"] and any(h.startswith("wrong_state") for h in r["hard_failures"])


def test_a_store_that_forgets_to_check_hashes_fails_the_corruption_faults(tmp_path, monkeypatch):
    class Trusting(RefDeltaStore):
        name = "ref_delta"

        def verify(self):
            return {"ok": True, "problems": []}

        def reconstruct(self, version):
            import json
            base, _ = self.initial, 0
            state = deepcopy(base)
            for (op_json,) in self._conn.execute("SELECT op FROM deltas WHERE version <= ? ORDER BY version", (version,)):
                try:
                    state = reduce(state, json.loads(op_json))
                except Exception:                                                                 # noqa: BLE001
                    pass
            return state
    monkeypatch.setitem(STORES, "ref_delta", Trusting)
    r = run("ref_delta", tmp_path, "small")
    outcomes = {f["fault"]: f["outcome"] for f in r["faults"]}
    assert "silent_wrong" in outcomes.values() and r["passed"] is False


# ---- Delentia's engine used the way it was until Round 82 (pinned findings), then the engine after Round 83
def test_delentia_delta_engine_rebuilds_exact_states_but_cannot_detect_damage(tmp_path):
    base = run("ref_snapshot", tmp_path, "small")["storage"]["total_bytes"]
    r = run("delentia_delta_engine_r82", tmp_path, "small", base)
    assert r["states_exact"] == r["states_checked"]                                                   # it IS correct when nothing is wrong
    outcomes = {f["fault"]: f["outcome"] for f in r["faults"]}
    assert outcomes["missing_parent"] == "silent_wrong" and outcomes["checksum_corruption"] == "silent_wrong"
    assert outcomes["duplicate"] == "unguarded" and outcomes["out_of_order"] == "unguarded" and outcomes["concurrent"] == "lost_update"
    assert outcomes["partial_write"] == "not_supported" and r["durable"] is False
    assert r["passed"] is False and len(r["hard_failures"]) == 2


def test_the_engines_own_checksum_would_have_caught_the_corruption(tmp_path):
    """The data to detect it exists (DeltaBlock.checksum); nothing in the engine reads it. Shown on the engine itself, with no change to it."""
    from research.daaes.stores import DelentiaDeltaEngineStore
    initial, steps = make_ops(1701, "small")
    refs = reference_states(initial, steps)
    store = DelentiaDeltaEngineStore(tmp_path / "e", initial)
    for v, step in enumerate((s for s in steps if s["kind"] != "snapshot"), start=1):
        if v > 30:
            break
        store.commit(v, step, deepcopy(refs[v]), v - 1)
    assert store.engine_checksums_hold() is True
    store.inject("checksum_corruption")
    assert store.verify()["ok"] is True                                                               # the engine says intact ...
    assert store.engine_checksums_hold() is False                                                     # ... its own checksum field says otherwise


def test_delentia_memory_log_detects_every_storage_fault_and_recovers_after_restart(tmp_path):
    base = run("ref_snapshot", tmp_path, "memory")["storage"]["total_bytes"]
    r = run("delentia_memory_log", tmp_path, "memory", base)
    outcomes = {f["fault"]: f["outcome"] for f in r["faults"]}
    assert r["states_exact"] == r["states_checked"] and r["metrics"]["recovery"] == 100.0
    assert outcomes["partial_write"] == "detected" and outcomes["missing_parent"] == "detected" and outcomes["checksum_corruption"] == "detected" and outcomes["snapshot_crash"] == "detected"
    assert outcomes["duplicate"] == "unguarded" and outcomes["out_of_order"] == "unguarded" and outcomes["concurrent"] == "lost_update"      # no version argument on the API
    assert r["hard_failures"] == []


def test_the_memory_log_refuses_the_full_profile(tmp_path):
    with pytest.raises(ValueError, match="memory"):
        run("delentia_memory_log", tmp_path, "small")


def test_the_events_of_a_run_replay_to_the_same_final_state(tmp_path):
    """TC-009 writes its commits to a run log; R1 replay of that log reaches the oracle's final state without touching any store."""
    from research.daaes import events as ev
    log = ev.RunLog(tmp_path / "events.jsonl", "tc009-replay")
    r = tc009.run_tc009("ref_delta", tmp_path / "s", profile="small", fault_ops=40, log=log)
    initial, steps = make_ops(1701, "small")
    refs = reference_states(initial, steps)
    rebuilt = ev.replay_r1(initial, log.events, reduce)
    assert state_hash(rebuilt) == state_hash(refs[-1]) and ev.verify(log.events)["ok"] and r["passed"]


# ---- the engine after Round 83 (DeltaEngine.versioned_log): the Architect asked for the engine to meet the target before any paid test
def test_the_engine_after_round83_passes_the_whole_fault_matrix(tmp_path):
    base = run("ref_snapshot", tmp_path, "small")["storage"]["total_bytes"]
    r = run("delentia_delta_log", tmp_path, "small", base)
    outcomes = {f["fault"]: f["outcome"] for f in r["faults"]}
    assert r["passed"] is True and r["hard_failures"] == [] and r["states_exact"] == r["states_checked"]
    assert outcomes["partial_write"] == "detected" and outcomes["missing_parent"] == "detected" and outcomes["checksum_corruption"] == "detected"
    assert outcomes["duplicate"] == "rejected_at_write" and outcomes["out_of_order"] == "rejected_at_write" and outcomes["concurrent"] == "rejected_at_write"
    assert outcomes["snapshot_crash"] in ("detected", "recovered")
    assert r["durable"] is True and r["metrics"]["recovery"] == 100.0 and r["metrics"]["corruption_detection"] == 100.0


def test_the_improvement_is_a_change_not_a_relabelling(tmp_path):
    """Same fixture, same oracle, same faults: the usage that was pinned as failing still fails, and the engine's new log does not."""
    before = run("delentia_delta_engine_r82", tmp_path, "small")
    after = run("delentia_delta_log", tmp_path, "small")
    assert before["passed"] is False and len(before["hard_failures"]) == 2
    assert after["passed"] is True and not after["hard_failures"]
    assert after["metrics"]["corruption_detection"] > before["metrics"]["corruption_detection"]

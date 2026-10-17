"""
Round 83: the Delta Engine after the improvement the Architect asked for, tested against what DAAES TC-009 found about it.

  * the engine's blocks: a block that does not match its checksum is refused, the checksum now covers the parent link, a block delivered twice is stored once, strict mode refuses a
    conflicting id / parent / backwards time, reconstruct_state raises on a damaged chain instead of returning a wrong state, and the keys it generates no longer depend on Python's per-process hash salt;
  * the structural patch: keys with '/', '~', '' or non-ASCII letters round-trip (RFC 6901 escaping), and the same change always gives the same bytes;
  * VersionedDeltaLog: exact states at every version, durability across a reopen and a second process, one transaction per commit, idempotent retries, a stale writer refused, and every kind of damage
    (changed, removed, reordered, partial, forged snapshot, damaged snapshot, cut-off tail, rewritten past) detected.
Every detection test has its twin that proves the same operation on an INTACT log passes, so a verifier that always says "damaged" cannot satisfy them.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import subprocess
import threading
from copy import deepcopy

import pytest

from rct_control_plane.algo_25_delta_block import (DeltaBlock, DeltaConflictError, DeltaDiff, DeltaEngine, DeltaIntegrityError, DeltaType)
from rct_control_plane.delta_log import VersionedDeltaLog, canonical, digest


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))


def states(n=12):
    out, cur = [], {"a": {"x": 1}, "list": [1, 2, 3], "t": "start"}
    out.append(deepcopy(cur))
    for i in range(1, n):
        cur = deepcopy(cur)
        cur["a"][f"k{i}"] = i
        cur["list"].append(i * 10)
        if i % 3 == 0:
            cur["list"].pop(0)
        if i % 4 == 0:
            cur["a"].pop("x", None)
        cur["t"] = f"step-{i}"
        out.append(cur)
    return out


def build(path, n=12, **kw):
    seq = states(n)
    log = VersionedDeltaLog(str(path), initial_state=seq[0], snapshot_every=kw.pop("snapshot_every", 5), **kw)
    for i, s in enumerate(seq[1:], start=1):
        assert log.commit(s, version=i, base_version=i - 1, source="t") == i
    return log, seq


# ------------------------------------------------------------------------------------------------------------------ the engine's blocks
def block(session="s", ts=1.0, added=("fact",), **kw):
    return DeltaBlock(session_id=session, timestamp=ts, delta_type=DeltaType.KNOWLEDGE_ADD, diff=DeltaDiff(added=list(added)), **kw)


def test_a_block_that_does_not_match_its_checksum_is_refused_and_an_intact_one_is_stored():
    engine = DeltaEngine()
    good = block()
    assert engine.store_delta(good) == good.delta_id
    bad = block(ts=2.0)
    bad.diff.added.append("changed after the checksum was computed")
    with pytest.raises(DeltaIntegrityError):
        engine.store_delta(bad)
    assert [b.delta_id for b in engine.get_session_deltas("s")] == [good.delta_id]


def test_the_checksum_covers_the_parent_link_the_source_and_the_metadata():
    a, b = block(), block()
    assert a.checksum == b.checksum
    for change in ({"parent_delta_id": "delta_x"}, {"source": "other"}, {"confidence": 0.1}, {"metadata": {"k": 1}}):
        assert block(**change).checksum != a.checksum, change


def test_the_same_block_delivered_twice_is_stored_once():
    engine = DeltaEngine()
    b = block()
    engine.store_delta(b)
    engine.store_delta(DeltaBlock.from_dict(b.to_dict()))
    assert len(engine.get_session_deltas("s")) == 1 and engine.get_stats()["total_deltas"] == 1


def test_strict_mode_refuses_a_conflicting_parent_a_reused_id_and_time_going_backwards():
    engine = DeltaEngine(strict=True)
    first = block(ts=10.0)
    engine.store_delta(first)
    with pytest.raises(DeltaConflictError):
        engine.store_delta(block(ts=11.0, added=("b",), parent_delta_id="delta_not_the_last"))
    with pytest.raises(DeltaIntegrityError):
        engine.store_delta(block(ts=5.0, added=("c",)))
    ok = block(ts=12.0, added=("d",), parent_delta_id=first.delta_id)
    assert engine.store_delta(ok) == ok.delta_id
    clash = block(ts=10.0, added=("different",))                      # same session/time/type -> same id, other content
    assert clash.delta_id == first.delta_id
    with pytest.raises(DeltaIntegrityError):
        engine.store_delta(clash)
    assert DeltaEngine().store_delta(block(ts=10.0)) and not DeltaEngine().strict            # the default mode keeps its old tolerance


def test_reconstruct_state_raises_on_a_damaged_chain_and_verify_false_restores_the_old_behaviour():
    engine = DeltaEngine()
    one, two = block(ts=1.0, added=("a",)), block(ts=2.0, added=("b",), parent_delta_id=None)
    engine.store_delta(one)
    engine.store_delta(two)
    assert engine.reconstruct_state("s").delta_count == 2 and engine.verify_session("s")["ok"]
    one.diff.added.append("tampered")
    assert not engine.verify_session("s")["ok"]
    engine._state_cache.clear()
    with pytest.raises(DeltaIntegrityError):
        engine.reconstruct_state("s")
    assert engine.reconstruct_state("s", verify=False).delta_count == 2


def test_a_missing_or_reordered_parent_is_reported():
    engine = DeltaEngine()
    a = block(ts=1.0, added=("a",))
    b = block(ts=2.0, added=("b",), parent_delta_id=a.delta_id)
    c = block(ts=3.0, added=("c",), parent_delta_id=b.delta_id)
    for x in (a, b, c):
        engine.store_delta(x)
    assert engine.verify_session("s")["ok"]
    del engine._deltas["s"][1]
    report = engine.verify_session("s")
    assert not report["ok"] and "missing or reordered" in report["problems"][0]


def test_generated_keys_do_not_depend_on_the_process_hash_salt():
    code = ("from rct_control_plane.algo_25_delta_block import *;e=DeltaEngine();"
            "b=DeltaBlock(session_id='s',timestamp=1.0,delta_type=DeltaType.KNOWLEDGE_ADD,diff=DeltaDiff(added=['alpha','beta']));"
            "e.store_delta(b);print(sorted(e.reconstruct_state('s').current_data))")
    outs = []
    for seed in ("1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "DELENTIA_HOME": os.environ["DELENTIA_HOME"]}
        outs.append(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120).stdout.strip().splitlines()[-1])
    assert len(set(outs)) == 1, outs


# ------------------------------------------------------------------------------------------------------------------ the structural patch
@pytest.mark.parametrize("key", ["a/b", "a~b", "~1", "", " ", "ภาษาไทย", "😀", "0", "10", "x y", "a/", "/a"])
def test_awkward_keys_round_trip_through_the_patch(key):
    engine = DeltaEngine()
    old = {"keep": {"v": 1}, key: {"inner": [1, {"deep": "x"}]}}
    new = {"keep": {"v": 2}, key: {"inner": [1, {"deep": "y"}, 3]}, "other": {key: 1}}
    ops = engine.structural_ops(old, new)
    assert engine.apply_structural_delta(old, ops) == new
    gone = engine.structural_ops(new, {"keep": {"v": 2}})
    assert engine.apply_structural_delta(new, gone) == {"keep": {"v": 2}}


def test_the_same_change_always_gives_the_same_bytes():
    engine = DeltaEngine()
    old = {"b": 1, "a": 2, "c": {"y": 1, "x": 2}}
    new = {"c": {"x": 3, "z": 9}, "d": 1}
    first = canonical(engine.structural_ops(old, new))
    for _ in range(5):
        assert canonical(engine.structural_ops(dict(reversed(list(old.items()))), dict(reversed(list(new.items()))))) == first


def test_a_patch_with_a_bad_path_is_refused():
    with pytest.raises(DeltaIntegrityError):
        DeltaEngine().apply_structural_delta({}, [{"op": "add", "path": "no-slash", "value": 1}])


# ------------------------------------------------------------------------------------------------------------------ the versioned log
def test_every_version_is_rebuilt_exactly(tmp_path):
    log, seq = build(tmp_path / "l.sqlite")
    for i, s in enumerate(seq):
        assert log.state_at(i) == s, i
    assert log.state_at() == seq[-1] and log.head() == len(seq) - 1 and log.verify()["ok"]


def test_the_log_survives_a_reopen_and_a_second_connection(tmp_path):
    log, seq = build(tmp_path / "l.sqlite")
    log.reopen()
    assert log.state_at() == seq[-1]
    other = VersionedDeltaLog(str(tmp_path / "l.sqlite"), initial_state=seq[0])
    assert other.head() == log.head() and other.state_at(5) == seq[5]
    nxt = deepcopy(seq[-1]); nxt["t"] = "after reopen"
    assert other.commit(nxt, base_version=other.head()) == len(seq)
    assert log.state_at() == nxt                                         # the first connection sees what the second wrote, rebuilt and checked


def test_a_log_opened_with_another_initial_state_is_refused(tmp_path):
    build(tmp_path / "l.sqlite", n=3)
    with pytest.raises(DeltaIntegrityError):
        VersionedDeltaLog(str(tmp_path / "l.sqlite"), initial_state={"different": True})


def test_a_stale_writer_is_refused_and_a_correct_one_is_accepted(tmp_path):
    log, seq = build(tmp_path / "l.sqlite", n=4)
    head = log.head()
    mine = deepcopy(seq[-1]); mine["t"] = "mine"
    theirs = deepcopy(seq[-1]); theirs["t"] = "theirs"
    assert log.commit(mine, base_version=head) == head + 1
    with pytest.raises(DeltaConflictError):
        log.commit(theirs, base_version=head)                            # based on the old head
    assert log.state_at() == mine
    assert log.commit(theirs, base_version=head + 1) == head + 2


def test_duplicates_and_out_of_order_deliveries_are_refused_and_the_next_one_is_accepted(tmp_path):
    log, seq = build(tmp_path / "l.sqlite", n=4)
    head = log.head()
    nxt = deepcopy(seq[-1]); nxt["t"] = "n"
    with pytest.raises(DeltaIntegrityError):
        log.commit(nxt, version=head)                                    # already applied
    with pytest.raises(DeltaIntegrityError):
        log.commit(nxt, version=head + 2)                                # skips one
    assert log.head() == head and log.commit(nxt, version=head + 1) == head + 1


def test_idempotency_key_returns_the_same_version_and_refuses_other_content(tmp_path):
    log, seq = build(tmp_path / "l.sqlite", n=3)
    s = deepcopy(seq[-1]); s["pay"] = 100
    v = log.commit(s, idempotency_key="op-1")
    assert log.commit(s, idempotency_key="op-1") == v and log.head() == v       # a retry writes nothing
    other = deepcopy(s); other["pay"] = 999
    with pytest.raises(DeltaConflictError):
        log.commit(other, idempotency_key="op-1")
    assert log.state_at() == s


def test_a_commit_that_fails_leaves_nothing_behind(tmp_path, monkeypatch):
    log, seq = build(tmp_path / "l.sqlite", n=3)
    head = log.head()
    monkeypatch.setattr(log.engine, "structural_ops", lambda a, b: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        log.commit({"x": 1})
    monkeypatch.undo()
    assert log.head() == head and log.verify()["ok"] and log.state_at() == seq[-1]


def test_concurrent_writers_based_on_the_same_version_get_exactly_one_success(tmp_path):
    log, seq = build(tmp_path / "l.sqlite", n=3)
    head = log.head()
    results = []

    def attempt(tag):
        s = deepcopy(seq[-1]); s["who"] = tag
        try:
            results.append(("ok", log.commit(s, base_version=head)))
        except DeltaConflictError:
            results.append(("conflict", None))
    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [r[0] for r in results].count("ok") == 1 and [r[0] for r in results].count("conflict") == 5
    assert log.head() == head + 1 and log.verify()["ok"]


def test_a_state_that_cannot_be_written_as_json_is_refused(tmp_path):
    log, _ = build(tmp_path / "l.sqlite", n=2)
    with pytest.raises(TypeError):
        log.commit({"bad": {1, 2, 3}})
    assert log.verify()["ok"]


# ------------------------------------------------------------------------------------------------------------------ damage
def damaged(tmp_path, how, n=12):
    path = tmp_path / f"{how}.sqlite"
    log, seq = build(path, n=n)
    conn = log._conn
    if how == "changed_delta":
        row = conn.execute("SELECT ops FROM deltas WHERE version = 4").fetchone()[0]
        conn.execute("UPDATE deltas SET ops = ? WHERE version = 4", (row.replace('"step-4"', '"STEP-4"'),))
    elif how == "partial_write":
        conn.execute("UPDATE deltas SET ops = SUBSTR(ops, 1, LENGTH(ops) / 2) WHERE version = ?", (log.head(),))
    elif how == "removed_delta":
        conn.execute("DELETE FROM deltas WHERE version = 5")
    elif how == "reordered":
        a = conn.execute("SELECT ops, ops_hash FROM deltas WHERE version = 6").fetchone()
        b = conn.execute("SELECT ops, ops_hash FROM deltas WHERE version = 7").fetchone()
        conn.execute("UPDATE deltas SET ops = ?, ops_hash = ? WHERE version = 6", b)
        conn.execute("UPDATE deltas SET ops = ?, ops_hash = ? WHERE version = 7", a)
    elif how == "chain_replaced":
        conn.execute("UPDATE deltas SET chain_hash = ? WHERE version = 3", ("0" * 64,))
    elif how == "forged_snapshot":
        import zstandard
        fake = deepcopy(seq[5]); fake["t"] = "forged"
        conn.execute("UPDATE snapshots SET blob = ?, state_hash = ? WHERE version = 5", (zstandard.ZstdCompressor().compress(canonical(fake)), digest(fake)))
    elif how == "damaged_snapshot":
        conn.execute("UPDATE snapshots SET blob = SUBSTR(blob, 1, LENGTH(blob) / 2) WHERE version = 10")
    elif how == "source_changed":
        conn.execute("UPDATE deltas SET source = 'someone-else' WHERE version = 2")
    return log, seq


@pytest.mark.parametrize("how", ["changed_delta", "partial_write", "removed_delta", "reordered", "chain_replaced", "source_changed"])
def test_every_kind_of_damage_to_the_deltas_is_detected_by_verify_and_by_reading(tmp_path, how):
    log, seq = damaged(tmp_path, how)
    report = log.verify()
    assert not report["ok"] and report["problems"], how
    head = log.head()
    with pytest.raises(DeltaIntegrityError):
        # reading through the damage must raise; versions after the last snapshot before the damage are the ones that depend on it
        for v in range(0, head + 1):
            log.state_at(v)
    assert report["last_good_version"] < head


def test_an_intact_log_passes_the_same_checks(tmp_path):
    log, seq = build(tmp_path / "ok.sqlite")
    report = log.verify()
    assert report["ok"] and report["problems"] == [] and report["last_good_version"] == log.head()
    for v in range(0, log.head() + 1):
        assert log.state_at(v) == seq[v]


def test_a_forged_snapshot_with_a_consistent_hash_is_caught_by_comparing_it_with_the_history(tmp_path):
    log, seq = damaged(tmp_path, "forged_snapshot")
    report = log.verify()
    assert not report["ok"] and any("snapshot 5" in p and "history" in p for p in report["problems"])


def test_a_damaged_snapshot_is_skipped_and_the_state_is_still_exact(tmp_path):
    log, seq = damaged(tmp_path, "damaged_snapshot")
    assert log.state_at(11) == seq[11] and log.last_skipped_snapshots == 1
    assert not log.verify()["ok"]                                         # but it is reported


def test_every_snapshot_damaged_still_rebuilds_from_the_genesis_and_a_damaged_genesis_is_refused(tmp_path):
    log, seq = build(tmp_path / "l.sqlite")
    log._conn.execute("UPDATE snapshots SET blob = SUBSTR(blob, 1, 3) WHERE version > 0")
    assert log.state_at(11) == seq[11]
    log._conn.execute("UPDATE snapshots SET blob = SUBSTR(blob, 1, 3) WHERE version = 0")
    with pytest.raises(DeltaIntegrityError):
        log.state_at(11)
    assert not log.verify()["ok"]


def test_cutting_off_the_newest_versions_is_invisible_without_an_anchor_and_visible_with_one(tmp_path):
    log, seq = build(tmp_path / "l.sqlite")
    anchor = log.head_anchor()
    assert log.verify(anchor)["ok"]
    log._conn.execute("DELETE FROM deltas WHERE version > 9")
    log._conn.execute("DELETE FROM snapshots WHERE version > 9")
    assert log.verify()["ok"], "a chain alone cannot see its newest rows disappear"
    report = log.verify(anchor)
    assert not report["ok"] and "cut off" in report["problems"][0]


def test_rewriting_the_past_and_recomputing_every_hash_is_visible_with_an_anchor(tmp_path):
    log, seq = build(tmp_path / "l.sqlite", n=8)
    anchor = log.head_anchor()
    other = VersionedDeltaLog(str(tmp_path / "rewritten.sqlite"), initial_state=seq[0], snapshot_every=0)
    for i, s in enumerate(seq[1:], start=1):
        s2 = deepcopy(s)
        s2["t"] = "rewritten" if i == 3 else s["t"]
        other.commit(s2, at=1.0)
    report = other.verify(anchor)
    assert other.verify()["ok"] and not report["ok"] and "rewritten" in " ".join(report["problems"])


def test_snapshots_are_built_from_the_checked_history_never_from_a_damaged_one(tmp_path):
    log, seq = damaged(tmp_path, "partial_write")                    # the newest delta is damaged: a snapshot of the head would freeze a state nobody can vouch for
    with pytest.raises(DeltaIntegrityError):
        log.snapshot()
    assert log._conn.execute("SELECT COUNT(*) FROM snapshots WHERE version = ?", (log.head(),)).fetchone()[0] == 0
    intact, _ = build(tmp_path / "fine.sqlite", n=6)
    assert intact.snapshot() == intact.head()


def test_last_good_version_names_the_point_to_go_back_to_and_nothing_is_deleted(tmp_path):
    log, seq = damaged(tmp_path, "removed_delta")
    rows_before = log._conn.execute("SELECT COUNT(*) FROM deltas").fetchone()[0]
    assert log.last_good_version() == 4
    assert log.state_at(4) == seq[4] and log._conn.execute("SELECT COUNT(*) FROM deltas").fetchone()[0] == rows_before


def test_storage_is_smaller_than_a_snapshot_per_commit_when_the_state_is_large_and_the_bytes_are_reported(tmp_path):
    """A log pays about 130 bytes of hashes per commit, so a tiny state is cheaper as a snapshot; the claim is only for a state that is large compared with one change."""
    state = {f"task-{i:04d}": {"title": f"task number {i}", "status": "open", "notes": ["a" * 40, "b" * 40]} for i in range(300)}
    log = VersionedDeltaLog(str(tmp_path / "big.sqlite"), initial_state=state, snapshot_every=0)
    full = len(canonical(state))
    for i in range(40):
        state = deepcopy(state)
        state[f"task-{i:04d}"]["status"] = "done"
        log.commit(state)
    sizes = log.sizes()
    assert sizes["total_bytes"] < 41 * full * 0.1 and sizes["delta_bytes"] > 0, sizes      # under a tenth of forty-one full copies
    tiny, _ = build(tmp_path / "tiny.sqlite", n=10, snapshot_every=0)
    assert tiny.sizes()["delta_bytes"] > 0                                                     # reported either way: a small state is not compressed by a log


def test_removing_the_first_element_of_a_list_is_one_operation_not_one_per_element():
    engine = DeltaEngine()
    old = {"l": list(range(200))}
    assert len(engine.structural_ops(old, {"l": old["l"][1:]})) == 1 and len(engine.structural_ops(old, {"l": [-1] + old["l"]})) == 1
    for new in ({"l": old["l"][1:]}, {"l": [-1] + old["l"]}, {"l": old["l"][:50] + old["l"][60:]}, {"l": old["l"][:50] + ["x", "y"] + old["l"][60:]}, {"l": []}, {"l": old["l"] + [7]}):
        assert engine.apply_structural_delta(old, engine.structural_ops(old, new)) == new


def test_a_change_of_type_is_a_change_even_when_python_says_the_values_are_equal():
    engine = DeltaEngine()
    for a, b in ((1, True), (1, 1.0), (0, False), ("1", 1)):
        ops = engine.structural_ops({"k": a}, {"k": b})
        assert ops and engine.apply_structural_delta({"k": a}, ops) == {"k": b}
        assert type(engine.apply_structural_delta({"k": a}, ops)["k"]) is type(b)


# ------------------------------------------------------------------------------------------------------------------ anchoring in the audit chain
def test_the_head_written_into_the_audit_chain_catches_a_cut_and_a_rewrite_that_the_log_alone_cannot(tmp_path):
    from rct_control_plane.persistence import ControlPlanePersistence
    audit = ControlPlanePersistence(db_path=str(tmp_path / "audit.db"))
    log, seq = build(tmp_path / "l.sqlite", n=10)
    assert log.anchor_to_audit(audit, "memory")["version"] == log.head()
    good = log.verify_against_audit(audit, "memory")
    assert good["ok"] and good["anchors"] == 1 and good["unanchored_versions"] == 0
    nxt = deepcopy(seq[-1]); nxt["t"] = "one more"
    log.commit(nxt)
    assert log.verify_against_audit(audit, "memory")["unanchored_versions"] == 1             # said, not hidden
    # cut the newest versions: the log still verifies by itself, the audit chain still remembers
    log._conn.execute("DELETE FROM deltas WHERE version > 6")
    log._conn.execute("DELETE FROM snapshots WHERE version > 6")
    assert log.verify()["ok"]
    cut = log.verify_against_audit(audit, "memory")
    assert not cut["ok"] and "cut off" in " ".join(cut["problems"])


def test_a_rewritten_history_with_every_hash_recomputed_is_caught_by_the_audit_anchor(tmp_path):
    from rct_control_plane.persistence import ControlPlanePersistence
    audit = ControlPlanePersistence(db_path=str(tmp_path / "audit.db"))
    original, seq = build(tmp_path / "a.sqlite", n=8)
    original.anchor_to_audit(audit, "x")
    forged = VersionedDeltaLog(str(tmp_path / "b.sqlite"), initial_state=seq[0], snapshot_every=0)
    for i, s in enumerate(seq[1:], start=1):
        s2 = deepcopy(s)
        if i == 4:
            s2["t"] = "history as someone wants it"
        forged.commit(s2, at=1.0, source="t")
    assert forged.verify()["ok"], "the forgery is internally consistent"
    report = forged.verify_against_audit(audit, "x")
    assert not report["ok"] and "rewritten" in " ".join(report["problems"])


def test_anchors_of_another_log_are_not_confused_with_this_one(tmp_path):
    from rct_control_plane.persistence import ControlPlanePersistence
    audit = ControlPlanePersistence(db_path=str(tmp_path / "audit.db"))
    a, _ = build(tmp_path / "a.sqlite", n=5)
    b, _ = build(tmp_path / "b.sqlite", n=9)
    b.anchor_to_audit(audit, "b")
    assert a.verify_against_audit(audit, "a")["anchors"] == 0 and a.verify_against_audit(audit, "a")["ok"]
    assert b.verify_against_audit(audit, "b")["ok"]

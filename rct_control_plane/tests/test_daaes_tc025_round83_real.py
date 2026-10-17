"""
Round 83, DAAES TC-025 (Deterministic Replay) against Delentia's runtime around a scripted model, with the controls that show the checks can fail:
  * R3 is also run under a stricter policy and MUST find mismatches;
  * a verifier that is forced to say "ok" is caught as undetected tampering;
  * a replay whose decisions deviate from the recording reaches for an outside call and is counted;
  * truncating the newest rows is invisible to every hash chain and visible to a signed head kept elsewhere (a stated limit, pinned).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sqlite3

import pytest

from research.daaes import delentia_session as ds
from research.daaes import events as ev
from research.daaes import tc025


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    for name in ("DELENTIA_FDIA_POLICY", "DELENTIA_APPROVER_PUBKEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "ambient"))


@pytest.fixture(scope="module")
def delentia_run(tmp_path_factory):
    work = tmp_path_factory.mktemp("tc025")
    return tc025.run_tc025("delentia", work), work


def test_the_standard_session_pauses_for_the_write_then_executes_it_once_signed(tmp_path):
    log = ev.RunLog(tmp_path / "e.jsonl", "s")
    world = ds.ScriptedWorld(ds.FILES)
    summary = ds.run_session(tmp_path / "home", ds.GOAL, ds.DECISIONS, world, log, approve=True)
    assert [d["verdict"] for d in summary["decisions"]] == ["allow", "allow", "ask"] and summary["stopped_reason"] == "pending_approval"
    assert world.files["docs/summary.md"] == "A and B combined" and [c["tool"] for c in world.calls].count("delentia_write_repo_file") == 1
    assert ev.verify(log.events)["ok"] and summary["audit"]["ok"]
    kinds = [e["kind"] for e in log.events]
    assert kinds.count("decision.authorized") == 4 and kinds[0] == "intent.created" and kinds[-1] == "checkpoint.committed"


def test_the_delentia_arm_passes_and_every_replay_holds(delentia_run):
    r, _ = delentia_run
    assert r["passed"] and r["score"] == 100.0 and r["hard_failures"] == []
    assert r["sections"]["r2"] == {"identical": True, "external_attempts": 0, "calls_served": 3, "calls_recorded": 3}
    assert r["sections"]["r3"]["ok"] and r["sections"]["r3"]["checked"] == 3
    assert r["sections"]["r1_memory_time_travel"]["final_equal"] and r["sections"]["r1_memory_time_travel"]["equal"] == r["sections"]["r1_memory_time_travel"]["points"]


def test_r3_is_not_a_rubber_stamp(delentia_run):
    r, _ = delentia_run
    control = r["sections"]["r3_control_stricter_policy"]
    assert control["ok"] is False and len(control["mismatches"]) == 3                      # under a stricter owner policy every recorded verdict changes


def test_r4_is_reported_as_scripted_variance_not_as_model_determinism(delentia_run):
    r, _ = delentia_run
    note = r["sections"]["r4_scripted_variance"]
    assert note["identical"] and "language model" in note["note"]


def test_every_listed_tamper_is_detected_by_the_chains_except_truncation(delentia_run):
    r, _ = delentia_run
    for name, summary in r["tamper"].items():
        assert summary["undetected"] == [], name
        assert summary["detected_only_by_anchor"] == ["truncate_tail"], name
    assert r["tamper"]["audit_chain"]["applicable"] == 6                                      # no snapshots in the audit chain: that case is not applicable, not passed
    assert set(r["caught_only_with_an_external_anchor"]) == {"run_log:truncate_tail", "audit_chain:truncate_tail", "memory_log:truncate_tail"}


def test_the_event_log_baseline_passes_but_does_not_evaluate_what_it_does_not_have(tmp_path):
    r = tc025.run_tc025("event_log_baseline", tmp_path)
    assert r["passed"] and set(r["sections"]["not_evaluated"]) == {"R2 tool replay", "R3 decision replay", "audit chain", "memory log"}
    assert r["tamper"]["run_log"]["detected_only_by_anchor"] == ["truncate_tail"]


def test_a_verifier_forced_to_say_ok_is_caught_as_undetected_tampering(tmp_path, monkeypatch):
    from rct_control_plane import audit_chain

    class AlwaysOk:
        ok = True
        reason = None
        chained_rows = 0
        signed_rows = 0
        head_hash = None
    monkeypatch.setattr(audit_chain, "verify_audit_chain", lambda conn, public_key_hex=None: AlwaysOk())
    # the harness' own pristine check also reads the audit verifier, so only the tamper table is examined here
    log = ev.RunLog(tmp_path / "e.jsonl", "s")
    ds.run_session(tmp_path / "home", ds.GOAL, ds.DECISIONS, ds.ScriptedWorld(ds.FILES), log, approve=True)
    db = tmp_path / "home" / "agentic.db"
    with sqlite3.connect(str(db)) as conn:
        head = audit_chain.chain_head(conn)
    result = tc025.tamper_audit_chain(db, tmp_path, {"seq": head["seq"], "row_hash": head["row_hash"]})
    rate = tc025._rate(result)
    assert "mutate_payload" in rate["undetected"] and "corrupt_hash" in rate["undetected"]


def test_a_replay_that_deviates_from_the_recording_is_counted_as_reaching_the_outside(tmp_path):
    log = ev.RunLog(tmp_path / "e.jsonl", "s")
    first = ds.run_session(tmp_path / "home1", ds.GOAL, ds.DECISIONS, ds.ScriptedWorld(ds.FILES), log, approve=True)
    other = [dict(ds.DECISIONS[0], tool_args={"relative_path": "docs/NOT-RECORDED.md"})] + ds.DECISIONS[1:]
    report = tc025.replay_r2(first, log.events, tmp_path / "home2", decisions=other)
    assert report["external_attempts"] >= 1 and report["identical"] is False


def test_the_checkpoint_column_retyped_is_reported_not_a_crash(tmp_path):
    """Found by this case: MemoryEventLog.verify() raised sqlite3.OperationalError when a checkpoint's blob column held text. It now reports the checkpoint as damaged."""
    from research.daaes.state_fixture import make_ops, reference_states
    from research.daaes.stores import DelentiaMemoryLogStore
    initial, steps = make_ops(1701, "memory", soft_delete=True)
    refs = reference_states(initial, steps)
    store = DelentiaMemoryLogStore(tmp_path / "m", initial)
    for v, step in enumerate((s for s in steps if s["kind"] != "snapshot"), start=1):
        if v > 60:
            break
        store.commit(v, step, refs[v], v - 1)
    store.take_snapshot()
    conn = sqlite3.connect(str(store.db))
    conn.execute("UPDATE memory_checkpoints SET state_zstd = SUBSTR(state_zstd, 1, LENGTH(state_zstd) - 3) || X'000000' WHERE id = (SELECT MAX(id) FROM memory_checkpoints)")
    conn.commit()
    conn.close()
    verdict = store.log.verify()
    assert verdict["ok"] is False and any("checkpoint" in p for p in verdict["problems"])
    store.close()


def test_the_session_adapter_restores_everything_it_patches(tmp_path):
    import rct_control_plane.autonomous_loop as loop_module
    before = loop_module.decide_next_action
    env_before = dict(os.environ)
    ds.run_session(tmp_path / "home", ds.GOAL, ds.DECISIONS, ds.ScriptedWorld(ds.FILES), None, approve=False)
    assert loop_module.decide_next_action is before and dict(os.environ) == env_before


def test_the_hash_corruption_changes_the_value_even_when_the_hash_already_starts_with_00():
    """CI (Python 3.11) failed once in about 256 runs: the tamper wrote '00' over the first byte, and a real hash that began with '00' was left unchanged, so 'nothing detected' was the test's own doing."""
    import sqlite3
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "research" / "daaes" / "tc025.py").read_text(encoding="utf-8")
    assert source.count("CASE WHEN SUBSTR(") == 2, "both the audit-chain and the memory-log tamper use the guarded form"
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (h TEXT)")
    for start in ("00", "ab", "ff", "0a"):
        conn.execute("DELETE FROM t")
        conn.execute("INSERT INTO t VALUES (?)", (start + "c0ffee",))
        conn.execute("UPDATE t SET h = CASE WHEN SUBSTR(h, 1, 2) = '00' THEN 'ff' ELSE '00' END || SUBSTR(h, 3)")
        assert conn.execute("SELECT h FROM t").fetchone()[0] != start + "c0ffee", start

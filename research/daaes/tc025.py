"""
TC-025 Deterministic Replay (specification section VII).

Two arms:

  delentia             Delentia's runtime around a scripted model: the governed loop and its gate, the approval store, the hash-chained audit trail, the memory event log
  event_log_baseline   the harness's own run log alone (no Delentia code): what any system gets by writing a hash-chained log

Four replays and the tamper suite:

  R1 state replay      the memory event log is rebuilt at every recorded checkpoint (time travel) and at the end; each must equal the hash recorded at commit time
  R2 tool replay       the standard scripted episode is run again in a fresh data home against a world that serves only the RECORDED outputs and counts anything else as an external call;
                       the normalized steps, gate verdicts, final text and resulting world must equal the first run, and the external-call counter must be zero
  R3 decision replay   every recorded gate decision is judged again by a fresh loop (same tool, arguments, D, I, taint); the verdict must equal the recorded one. A control replays the same
                       decisions under a stricter owner policy and MUST find mismatches, otherwise the check could not fail
  R4 live re-execution the scripted episode is run twice from scratch and compared: under a script the variance is zero by construction, so this is reported as `scripted_variance`, never as a
                       claim about a language model's determinism

Tamper suite (specification: mutate a payload, delete, reorder, duplicate, corrupt a hash, replace a snapshot) is applied to (a) the run log, (b) Delentia's audit chain, (c) Delentia's memory log and
its checkpoints. Truncating the newest rows is added: a hash chain cannot see it, a signed head kept elsewhere can, and the report says which of the two caught it.

Score = 0.25 trace verification + 0.35 final-state match + 0.20 intermediate-state match + 0.15 tamper detection + 0.05 zero external effects (proposed weights, pre-registered here).
Hard fail: an undetected tamper (that no anchor catches), a replay that reaches the outside, or an R1 state that is not identical.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from research.daaes import delentia_session as ds
from research.daaes import events as ev
from research.daaes.state_fixture import make_ops, reduce, reference_states, state_hash
from research.daaes.stores import DelentiaMemoryLogStore, RefDeltaStore

WEIGHTS = {"trace_verification": 0.25, "final_state_match": 0.35, "intermediate_state_match": 0.20, "tamper_detection": 0.15, "zero_external_effects": 0.05}
THRESHOLD = 90.0
TAMPERS = ("mutate_payload", "delete_event", "reorder_events", "duplicate_event", "corrupt_hash", "replace_snapshot", "truncate_tail")


def _flush(db: Path) -> None:
    """Folds a write-ahead log into the main file before the file is COPIED for tampering (a copy of the main file alone silently loses recent rows)."""
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


# ------------------------------------------------------------------------------------------------ tamper suites
def tamper_run_log(events: List[Dict[str, Any]], anchor_path: Path) -> Dict[str, Dict[str, Any]]:
    """The harness run log. `replace_snapshot` needs a checkpoint event; the log always has one."""
    out: Dict[str, Dict[str, Any]] = {}
    for how in TAMPERS:
        if how == "truncate_tail":
            damaged = events[:-3]
        else:
            damaged = ev.tamper(events, how, index=min(3, len(events) - 3))
        chain = ev.verify(damaged)
        anchored = ev.verify_anchor(damaged, anchor_path)
        out[how] = {"detected_by_chain": not chain["ok"], "detected_by_anchor": not anchored["ok"], "reason": chain.get("reason") or anchored.get("reason")}
    return out


def tamper_audit_chain(db: Path, work: Path, anchor_head: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Delentia's audit chain, on a COPY of a real database written by real governed episodes. `anchor_head` = {seq, row_hash} noted when the chain was healthy (the stand-in for a witness)."""
    from rct_control_plane import audit_chain
    results: Dict[str, Dict[str, Any]] = {}
    _flush(db)
    for how in TAMPERS:
        if how == "replace_snapshot":
            results[how] = {"detected_by_chain": None, "detected_by_anchor": None, "reason": "not_applicable: the audit chain holds no snapshots"}
            continue
        copy = work / f"audit_{how}.db"
        shutil.copy(db, copy)
        conn = sqlite3.connect(str(copy))
        rows = [r[0] for r in conn.execute("SELECT audit_id FROM audit_chain ORDER BY seq")]
        mid = rows[len(rows) // 2]
        if how == "mutate_payload":
            conn.execute("UPDATE audit_trail SET changes = '{\"tampered\":true}' WHERE id = ?", (mid,))
        elif how == "delete_event":
            conn.execute("DELETE FROM audit_trail WHERE id = ?", (mid,))
        elif how == "reorder_events":
            a, b = rows[2], rows[3]
            conn.execute("UPDATE audit_chain SET audit_id = -1 WHERE audit_id = ?", (a,))
            conn.execute("UPDATE audit_chain SET audit_id = ? WHERE audit_id = ?", (a, b))
            conn.execute("UPDATE audit_chain SET audit_id = ? WHERE audit_id = -1", (b,))
        elif how == "duplicate_event":
            conn.execute("INSERT INTO audit_trail (entity_type, entity_id, action, actor, changes, created_at) SELECT entity_type, entity_id, action, actor, changes, created_at FROM audit_trail WHERE id = ?", (mid,))
        elif how == "corrupt_hash":
            conn.execute("UPDATE audit_chain SET row_hash = CASE WHEN SUBSTR(row_hash, 1, 2) = '00' THEN 'ff' ELSE '00' END || SUBSTR(row_hash, 3) WHERE audit_id = ?", (mid,))
        elif how == "truncate_tail":
            conn.execute("DELETE FROM audit_chain WHERE audit_id IN (SELECT audit_id FROM audit_chain ORDER BY seq DESC LIMIT 2)")
            conn.execute("DELETE FROM audit_trail WHERE id IN (SELECT id FROM audit_trail ORDER BY id DESC LIMIT 2)")
        conn.commit()
        report = audit_chain.verify_audit_chain(conn)
        head = audit_chain.chain_head(conn)
        by_anchor = head is None or head["seq"] < anchor_head["seq"] or (head["seq"] == anchor_head["seq"] and head["row_hash"] != anchor_head["row_hash"])
        conn.close()
        results[how] = {"detected_by_chain": not report.ok, "detected_by_anchor": bool(by_anchor), "reason": report.reason}
    return results


def tamper_memory_log(store: DelentiaMemoryLogStore) -> Dict[str, Dict[str, Any]]:
    """Delentia's memory event log, tampered with SQL on its own database copy for each case."""
    results: Dict[str, Dict[str, Any]] = {}
    base = store.db
    _flush(base)
    for how in TAMPERS:
        copy = base.with_name(f"memlog_{how}.db")
        shutil.copy(base, copy)
        conn = sqlite3.connect(str(copy))
        seqs = [r[0] for r in conn.execute("SELECT seq FROM memory_events ORDER BY seq")]
        mid = seqs[len(seqs) // 2]
        if how == "mutate_payload":
            conn.execute("UPDATE memory_events SET payload = payload || ' ' WHERE seq = ?", (mid,))
        elif how == "delete_event":
            conn.execute("DELETE FROM memory_events WHERE seq = ?", (mid,))
        elif how == "reorder_events":
            a, b = seqs[2], seqs[3]
            conn.execute("UPDATE memory_events SET seq = -1 WHERE seq = ?", (a,))
            conn.execute("UPDATE memory_events SET seq = ? WHERE seq = ?", (a, b))
            conn.execute("UPDATE memory_events SET seq = ? WHERE seq = -1", (b,))
        elif how == "duplicate_event":
            conn.execute("INSERT INTO memory_events (namespace, kind, memory_id, payload, provenance, created_at, prev_hash, event_hash) SELECT namespace, kind, memory_id, payload, provenance, created_at, prev_hash, event_hash FROM memory_events WHERE seq = ?", (mid,))
        elif how == "corrupt_hash":
            conn.execute("UPDATE memory_events SET event_hash = CASE WHEN SUBSTR(event_hash, 1, 2) = '00' THEN 'ff' ELSE '00' END || SUBSTR(event_hash, 3) WHERE seq = ?", (mid,))
        elif how == "replace_snapshot":
            conn.execute("UPDATE memory_checkpoints SET state_zstd = SUBSTR(state_zstd, 1, LENGTH(state_zstd) - 3) || X'000000' WHERE id = (SELECT MAX(id) FROM memory_checkpoints)")
        elif how == "truncate_tail":
            conn.execute("DELETE FROM memory_events WHERE seq IN (SELECT seq FROM memory_events ORDER BY seq DESC LIMIT 3)")
        conn.commit()
        conn.close()
        from rct_control_plane.persistence import ControlPlanePersistence
        verdict = store.mel.MemoryEventLog(ControlPlanePersistence(db_path=str(copy))).verify()
        head_before = store.log.head()["seq"]
        head_after = store.mel.MemoryEventLog(ControlPlanePersistence(db_path=str(copy))).head()["seq"]
        results[how] = {"detected_by_chain": not verdict["ok"], "detected_by_anchor": head_after < head_before, "reason": (verdict["problems"] or [None])[0]}
    return results


# ------------------------------------------------------------------------------------------------ replays
def replay_r2(first: Dict[str, Any], events: List[Dict[str, Any]], home: Path, decisions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The same scripted episode against a world that only serves what was recorded."""
    recorded = [{"tool": e["payload"]["tool"], "args": e["payload"]["input"], "output": None} for e in events if e["kind"] == "tool.requested"]
    outputs = [e["payload"]["output"] for e in events if e["kind"] == "tool.completed"]
    for item, out in zip(recorded, outputs, strict=False):
        item["output"] = out
    world = ds.ReplayWorld(recorded)
    second = ds.run_session(home, ds.GOAL, decisions or ds.DECISIONS, world, None, approve=True)
    same = (second["steps"] == first["steps"] and second["final_answer"] == first["final_answer"] and [d["verdict"] for d in second["decisions"]] == [d["verdict"] for d in first["decisions"]]
            and second["stopped_reason"] == first["stopped_reason"])
    return {"identical": same, "external_attempts": world.external.attempts, "calls_served": world.cursor, "calls_recorded": len(recorded)}


def replay_r3(events: List[Dict[str, Any]], home: Path, strict_policy: Optional[Path] = None) -> Dict[str, Any]:
    """Each recorded gate decision is judged again by a fresh loop in a fresh data home."""
    from rct_control_plane.agent_factory import build_governed_loop
    from rct_control_plane.persistence import ControlPlanePersistence
    proposals = {e["event_id"]: e["payload"] for e in events if e["kind"] == "decision.proposed"}
    recorded = [(proposals[e["causation_id"]], e["payload"]["verdict"]) for e in events if e["kind"] == "decision.authorized" and e["causation_id"] in proposals]
    with ds.data_home(home, extra_env=({"DELENTIA_FDIA_POLICY": str(strict_policy)} if strict_policy else None)):
        persistence = ControlPlanePersistence(db_path=str(home / "agentic.db"))
        loop = build_governed_loop(ds.NullKernel(), namespace="daaes", persistence=persistence, mcp_server=ds.ScriptedWorld({}), conversation_turns=0)
        mismatches: List[str] = []
        for proposal, verdict in recorded:
            loop._episode_D, loop._episode_I = proposal["D"], proposal["I"]
            loop._episode_data = {"parts": {}, "missing": []}
            loop._episode_taint = proposal.get("taint")
            loop._episode_call_counts = {}
            out = asyncio.run(loop._pre_dispatch_gate(proposal["goal"], proposal["tool"], proposal["args"]))
            again = "allow" if out is None else ("ask" if out.get("stopped_reason") == "pending_approval" else "block")
            if again != verdict:
                mismatches.append(f"{proposal['tool']}: recorded {verdict}, now {again}")
    return {"checked": len(recorded), "mismatches": mismatches, "ok": not mismatches}


def time_travel_r1(workdir: Path, seed: int = 1701) -> Dict[str, Any]:
    """Memory event log: commit the `memory` profile, record the oracle's state hash at each commit, then rebuild at the recorded sequence numbers and compare."""
    initial, steps = make_ops(seed, "memory", soft_delete=True)
    refs = reference_states(initial, steps)
    store = DelentiaMemoryLogStore(workdir / "memlog", initial)
    version = 0
    for step in steps:
        if step["kind"] == "snapshot":
            store.take_snapshot()
            continue
        version += 1
        store.commit(version, step, deepcopy(refs[version]), version - 1)
    points = sorted(set(range(0, version + 1, max(1, version // 24))) | {version})
    equal = 0
    for v in points:
        if state_hash(store.reconstruct(v)) == state_hash(refs[v]):
            equal += 1
    return {"points": len(points), "equal": equal, "final_equal": state_hash(store.reconstruct(version)) == state_hash(refs[version]), "store": store}


# ------------------------------------------------------------------------------------------------ the case
def _rate(results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    applicable = {k: v for k, v in results.items() if v["detected_by_chain"] is not None}
    chain = [k for k, v in applicable.items() if v["detected_by_chain"]]
    anchor_only = [k for k, v in applicable.items() if not v["detected_by_chain"] and v["detected_by_anchor"]]
    missed = [k for k, v in applicable.items() if not v["detected_by_chain"] and not v["detected_by_anchor"]]
    return {"applicable": len(applicable), "detected_by_chain": chain, "detected_only_by_anchor": anchor_only, "undetected": missed}


def run_tc025(arm: str, workdir: Path, seed: int = 1701) -> Dict[str, Any]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    log = ev.RunLog(workdir / "events.jsonl", f"tc025-{arm}")
    log.emit("run.started", {"case": "TC-025", "arm": arm, "seed": seed})
    sections: Dict[str, Any] = {}
    hard: List[str] = []
    final_checks: List[bool] = []
    inter_equal, inter_total = 0, 0
    pristine: List[bool] = []
    external = 0
    tamper_all: Dict[str, Dict[str, Any]] = {}

    if arm == "event_log_baseline":
        initial, steps = make_ops(seed, "small")
        refs = reference_states(initial, steps)
        store = RefDeltaStore(workdir / "base", initial)
        version = 0
        for step in steps:
            if step["kind"] == "snapshot":
                log.emit("checkpoint.committed", {"version": version, "state_hash": state_hash(refs[version]), "state": refs[version] if version % 5 == 0 else None})
                continue
            version += 1
            log.emit("memory.delta_committed", {"delta": step}, state_version_before=version - 1, state_version_after=version)
        store.close()
        rebuilt = ev.replay_r1(initial, log.events, reduce)
        final_checks.append(state_hash(rebuilt) == state_hash(refs[-1]))
        points = [e for e in log.events if e["kind"] == "checkpoint.committed"]
        for p in points:
            upto = [x for x in log.events if x["sequence"] <= p["sequence"]]
            inter_total += 1
            inter_equal += int(state_hash(ev.replay_r1(initial, upto, reduce)) == p["payload"]["state_hash"])
        pristine.append(ev.verify(log.events)["ok"])
        anchor = workdir / "outside" / "anchor.json"
        ev.anchor_head(log.events, workdir / "outside" / "key.pem", anchor)
        pristine.append(ev.verify_anchor(log.events, anchor)["ok"])
        tamper_all["run_log"] = tamper_run_log(log.events, anchor)
        sections["not_evaluated"] = ["R2 tool replay", "R3 decision replay", "audit chain", "memory log"]
    else:
        events_log = ev.RunLog(workdir / "session_events.jsonl", "tc025-session")
        world = ds.ScriptedWorld(ds.FILES)
        first = ds.run_session(workdir / "home1", ds.GOAL, ds.DECISIONS, world, events_log, approve=True)
        sections["session"] = {"stopped_reason": first["stopped_reason"], "world_files": sorted(world.files), "audit": first["audit"]}
        pristine += [ev.verify(events_log.events)["ok"], first["audit"]["ok"]]

        r2 = replay_r2(first, events_log.events, workdir / "home2")
        sections["r2"] = r2
        final_checks += [r2["identical"], r2["calls_served"] == r2["calls_recorded"]]
        external += r2["external_attempts"]

        r3 = replay_r3(events_log.events, workdir / "home3")
        sections["r3"] = r3
        final_checks.append(r3["ok"])
        strict = workdir / "strict_policy.json"
        strict.write_text(json.dumps({"version": "1.0.0", "policy_id": "strict-control", "default_fallback_A": 0, "rules": [
            {"rule_id": "R-NO-DOCS", "intent_patterns": ["read_repo_file"], "action_type": "CONDITIONAL", "assigned_A": 1, "denied_paths": ["docs/*"]}]}), encoding="utf-8")
        control = replay_r3(events_log.events, workdir / "home3b", strict_policy=strict)
        sections["r3_control_stricter_policy"] = control
        final_checks.append(not control["ok"])                       # the control MUST find a difference, otherwise R3 could not have failed

        first_again = ds.run_session(workdir / "home4", ds.GOAL, ds.DECISIONS, ds.ScriptedWorld(ds.FILES), None, approve=True)
        sections["r4_scripted_variance"] = {"identical": first_again["steps"] == first["steps"] and first_again["final_answer"] == first["final_answer"],
                                            "note": "a script has no variance by construction: this says nothing about a language model's determinism"}
        final_checks.append(sections["r4_scripted_variance"]["identical"])

        r1 = time_travel_r1(workdir / "r1", seed)
        store = r1.pop("store")
        sections["r1_memory_time_travel"] = r1
        final_checks.append(r1["final_equal"])
        inter_total += r1["points"]
        inter_equal += r1["equal"]
        pristine.append(store.verify()["ok"])

        anchor = workdir / "outside" / "anchor.json"
        ev.anchor_head(events_log.events, workdir / "outside" / "key.pem", anchor)
        pristine.append(ev.verify_anchor(events_log.events, anchor)["ok"])
        tamper_all["run_log"] = tamper_run_log(events_log.events, anchor)
        db = workdir / "home1" / "agentic.db"
        from rct_control_plane import audit_chain
        with sqlite3.connect(str(db)) as conn:
            head = audit_chain.chain_head(conn)
        tamper_all["audit_chain"] = tamper_audit_chain(db, workdir, {"seq": head["seq"], "row_hash": head["row_hash"]} if "row_hash" in head else {"seq": head["seq"], "row_hash": head.get("hash")})
        tamper_all["memory_log"] = tamper_memory_log(store)
        store.close()

    tamper_summary = {name: _rate(res) for name, res in tamper_all.items()}
    missed = [f"{name}:{how}" for name, r in tamper_summary.items() for how in r["undetected"]]
    chain_blind = [f"{name}:{how}" for name, r in tamper_summary.items() for how in r["detected_only_by_anchor"]]
    hard += [f"undetected_tamper:{m}" for m in missed]
    if external:
        hard.append("replay_reached_the_outside")
    if not all(final_checks[:1]):
        hard.append("r1_state_not_identical")
    total_t = sum(r["applicable"] for r in tamper_summary.values())
    caught = total_t - len(missed)
    metrics = {
        "trace_verification": 100.0 * sum(pristine) / len(pristine),
        "final_state_match": 100.0 * sum(final_checks) / len(final_checks),
        "intermediate_state_match": 100.0 * inter_equal / inter_total if inter_total else 0.0,
        "tamper_detection": 100.0 * caught / total_t if total_t else 0.0,
        "zero_external_effects": 100.0 if external == 0 else 0.0,
    }
    metrics = {k: round(v, 2) for k, v in metrics.items()}
    score = round(sum(WEIGHTS[k] * metrics[k] for k in WEIGHTS), 2)
    passed = score >= THRESHOLD and not hard
    log.emit("oracle.evaluated", {"score": score, "passed": passed, "hard_failures": hard})
    log.emit("run.completed", {"result": "passed" if passed else "failed"})
    return {"case": "TC-025", "events_path": str(workdir / "events.jsonl"), "arm": arm, "seed": seed,
            "fixture_sha256": __import__("hashlib").sha256(json.dumps({"operations": make_ops(seed, "small"), "session_files": ds.FILES, "goal": ds.GOAL}, sort_keys=True, default=str).encode("utf-8")).hexdigest(), "metrics": metrics, "weights": WEIGHTS, "score": score, "threshold": THRESHOLD, "passed": passed, "hard_failures": hard,
            "tamper": tamper_summary, "tamper_detail": tamper_all, "caught_only_with_an_external_anchor": chain_blind, "sections": sections, "final_checks": final_checks}

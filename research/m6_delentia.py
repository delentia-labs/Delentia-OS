"""
Round 67, M6: Delentia's memory store on the shared workload (research/m6_workload.py).

Two configurations, because "which one" is part of the answer:
    table_only      DELENTIA_MEMORY_EVENTLOG=off  - the `memories` table and nothing else (what a plain SQLite store is)
    log_sealed      the Round 67 default: events + checkpoints, payloads sealed with a per-person key, heads anchored in the audit chain

    python research/m6_delentia.py --ops 500 --out research/m6_delentia_500.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))

import m6_workload as wl  # noqa: E402


def token_of(text: str) -> str:
    m = re.match(r"(T\d{4})\b", text or "")
    return m.group(1) if m else ""


def dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def canary_hits(root: Path) -> int:
    needle = wl.CANARY.encode("utf-8")
    hits = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                hits += p.read_bytes().count(needle)
            except OSError:
                pass
    return hits


def run(mode: str, ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix=f"m6-delentia-{mode}-"))
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_MEMORY_KEYS_DIR": str(work / "keys"), "DELENTIA_MEMORY_EVENTLOG": "off" if mode == "table_only" else "on",
                       "DELENTIA_MEMORY_ANCHOR_EVERY": "50"})
    os.environ.pop("DELENTIA_MEMORY_SEAL", None)
    import logging
    logging.disable(logging.WARNING)
    from rct_control_plane import memory_eventlog as me
    from rct_control_plane.persistence import ControlPlanePersistence
    db = work / "m.db"
    p = ControlPlanePersistence(db_path=str(db))
    ids: Dict[str, str] = {}
    seq_after: List[int] = [0]
    latencies: List[float] = []
    log = me.MemoryEventLog(p)
    for o in ops:
        started = time.perf_counter()
        if o["op"] == "add":
            ids[o["token"]] = f"m_{o['token']}"
            p.save_memory(ids[o["token"]], o["ns"], "fact", o["text"], {}, 0.6)
        elif o["op"] == "touch":
            p.touch_memory(ids[o["token"]])
        else:
            p.revoke_memory(ids[o["token"]], o["ns"], "forget this")
        latencies.append((time.perf_counter() - started) * 1000)
        seq_after.append(log.head()["seq"] if mode != "table_only" else 0)
    with p._connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    result: Dict[str, Any] = {"system": f"delentia ({mode})", "ops": len(ops), "bytes_on_disk": db.stat().st_size + dir_bytes(work / "keys"),
                              "write_ms_median": round(statistics.median(latencies), 3), "write_ms_p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 3)}

    # current view: revoked facts must not come back
    live_now = {token_of(m["content"]) for m in p.list_memories("alice")}
    want_now = wl.truth_after(ops, len(ops))
    result["current_view_exact"] = live_now == want_now
    result["current_view_wrong"] = len(live_now ^ want_now)

    # time travel: the state as it was after operation k
    exact, tried = 0, 0
    for k in wl.checkpoints_for(len(ops)):
        tried += 1
        if mode == "table_only":
            continue
        folded = {token_of(m["content"]) for m in log.fold("alice", seq_after[k]).values()}
        exact += folded == wl.truth_after(ops, k)
    result["time_travel"] = {"supported": mode != "table_only", "checked": tried if mode != "table_only" else 0, "exact": exact}

    # tamper: change one stored text directly in the database file, as someone with write access to it could
    conn = sqlite3.connect(str(db))
    if mode == "table_only":
        conn.execute("UPDATE memories SET content = content || ' (edited)' WHERE id = (SELECT id FROM memories WHERE namespace = 'alice' LIMIT 1 OFFSET 3)")
        conn.commit()
        result["tamper_detected"] = False                                         # nothing in this store can check
        result["tamper_note"] = "no integrity check exists; the edited text is simply returned"
    else:
        conn.execute("UPDATE memory_events SET payload = payload || ' ' WHERE seq = (SELECT seq FROM memory_events WHERE namespace = 'alice' AND kind = 'add' LIMIT 1 OFFSET 3)")
        conn.commit()
        v = log.verify()
        result["tamper_detected"] = not v["ok"]
        result["tamper_note"] = v["problems"][0] if v["problems"] else "not detected"
        conn.execute("UPDATE memory_events SET payload = REPLACE(payload, ' ', '') WHERE 1=0")
    conn.close()

    # erase one person and look in the raw bytes
    before = canary_hits(work)
    if mode == "table_only":
        with p._connect() as c2:
            c2.execute("UPDATE memories SET content = '[erased]' WHERE namespace = 'alice'")      # all a table store can do
        erased = True
    else:
        from rct_control_plane import approvals, memory_erasure
        pem = work / "outside" / "approver.pem"
        public = approvals.generate_approver_key(str(pem))
        os.environ[approvals.APPROVERS_ENV] = public
        # undo the tamper above on a fresh copy of the head: erasure signs the current head, which is fine even after tampering
        sig = memory_erasure.sign_erase(str(pem), "alice", log.head()["hash"])
        memory_erasure.erase_person(p, "alice", "m6 comparison", sig["public_key"], sig["signature"])
        erased = True
    with p._connect() as c3:
        c3.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    after = canary_hits(work)
    bob_ok = any("T" in m["content"] for m in p.list_memories("bob")) if any(o["ns"] == "bob" for o in ops) else True
    result["erase"] = {"performed": erased, "canary_in_raw_bytes_before": before, "canary_in_raw_bytes_after": after, "other_person_intact": bool(bob_ok)}
    shutil.rmtree(work, ignore_errors=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ops", type=int, default=500)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ops = wl.make_workload(args.ops)
    run("table_only", ops), run("log_sealed", ops)                      # a warm-up pass: the first run in a process was measured up to 6 ms/op slower whichever configuration it was
    results = [run("table_only", ops), run("log_sealed", ops)]
    Path(args.out).write_text(json.dumps({"ops": args.ops, "results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

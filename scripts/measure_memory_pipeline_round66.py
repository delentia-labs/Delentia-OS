"""
Round 66: how well does the redesigned memory pipeline perform once it is wired to the rest of the system?

    python scripts/measure_memory_pipeline_round66.py [--out research/memory_pipeline_round66.json] [--e2e]

Five measurements, all on the real code (real SQLite, real zstd, the real persistence writers, the real recall):

  W1  exactness and cost of the event log: replaying it equals the memories table after workloads of 100..5000 operations; the cost of writing one event (log off vs on) per
      operation; the time to rebuild with and without checkpoints; the time to verify the whole chain.
  W2  bytes: the table, the events, the checkpoints, a zstd archive of the log, and a zstd dump of the table, so the claim "storage is not the point" is a number.
  W3  damage: one event is edited at a random place. The check must name it; the question is how many moments of history can no longer be rebuilt (blast radius) with checkpoints
      every K events, and whether the newest state is still right.
  W4  (--e2e) the whole system: scripted-model trajectories of both research domains run through the governed loop with the log OFF and ON. The answers must be identical
      (the log must not change behaviour); afterwards the chain verifies and each person's replay equals their table; the per-episode overhead is reported.
  W5  what the model is shown: on a bloated, realistic memory (duplicates, stale episodes, the facts that matter) the three read-time policies are compared on the share of
      prompt text kept and on the NEEDED memories dropped (the harm), so "cut the surplus" is not taken on faith.

The workloads are synthetic where they must be (the real trajectories hold a handful of memories) and say so. Nothing here uses a language model.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))

import zstandard  # noqa: E402

from rct_control_plane import memory_eventlog as me  # noqa: E402
from rct_control_plane.persistence import ControlPlanePersistence  # noqa: E402

WORDS = ("budget vendor quote approval ticket urgent customer outage billing report preference sorted lowest highest owner deadline invoice contract renew delay refund "
         "รายงาน ใบเสนอราคา งบประมาณ ผู้อนุมัติ ลูกค้า เร่งด่วน ซ่อมบำรุง ส่งมอบ").split()


def text(rng: random.Random, n: int = 12) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n))


def workload(p: ControlPlanePersistence, n: int, seed: int, ns: str = "alice") -> List[str]:
    rng, ids = random.Random(seed), []
    for _ in range(n):
        r = rng.random()
        if r < 0.45 or not ids:
            mid = f"m{len(ids):05d}"
            p.save_memory(mid, ns, rng.choice(["fact", "preference", "event", "conversation"]), text(rng), {}, round(rng.random(), 2))
            ids.append(mid)
        elif r < 0.88:
            p.touch_memory(rng.choice(ids))
        else:
            p.revoke_memory(rng.choice(ids), ns, "bench")
    return ids


def fresh(enabled: bool, every: int = 50):
    d = tempfile.mkdtemp(prefix="delentia-mp-")
    os.environ.pop(me.ENABLE_ENV, None)
    if enabled:
        os.environ[me.ENABLE_ENV] = "1"
    os.environ[me.CHECKPOINT_ENV] = str(every)
    p = ControlPlanePersistence(db_path=os.path.join(d, "m.db"))
    return p, me.MemoryEventLog(p), d


def w1() -> Dict[str, Any]:
    rows = []
    for n in (100, 500, 2000, 5000):
        p_off, _, _ = fresh(False)
        t0 = time.perf_counter()
        workload(p_off, n, 1)
        off = time.perf_counter() - t0
        p_on, log, _ = fresh(True)
        t0 = time.perf_counter()
        workload(p_on, n, 1)
        on = time.perf_counter() - t0
        t0 = time.perf_counter()
        folded = log.fold("alice", include_revoked=True)
        fold_cp = time.perf_counter() - t0
        with p_on._connect() as conn:
            conn.execute("DELETE FROM memory_checkpoints")
        t0 = time.perf_counter()
        folded_full = log.fold("alice", include_revoked=True)
        fold_full = time.perf_counter() - t0
        t0 = time.perf_counter()
        verified = log.verify()
        verify_s = time.perf_counter() - t0
        consistent = log.consistent_with_table("alice")
        rows.append({"operations": n, "events": verified["events"], "write_ms_per_op_off": round(off / n * 1000, 3), "write_ms_per_op_on": round(on / n * 1000, 3),
                     "overhead_ms_per_op": round((on - off) / n * 1000, 3), "fold_with_checkpoints_ms": round(fold_cp * 1000, 1), "fold_without_ms": round(fold_full * 1000, 1),
                     "verify_ms": round(verify_s * 1000, 1), "replay_equals_table": bool(consistent["ok"]), "fold_same_with_and_without_checkpoints": folded == folded_full,
                     "chain_ok": bool(verified["ok"])})
    return {"rows": rows}


def w2() -> Dict[str, Any]:
    rows = []
    cz = zstandard.ZstdCompressor(level=9)
    for n in (500, 2000, 5000):
        p, log, d = fresh(True)
        workload(p, n, 2)
        with p._connect() as conn:
            table_bytes = sum(len(json.dumps(dict(zip(("id", "content", "ctx", "imp"), r))).encode()) for r in conn.execute("SELECT id, content, context, importance FROM memories"))
            ev = conn.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(payload)+LENGTH(provenance)+LENGTH(created_at)+LENGTH(prev_hash)+LENGTH(event_hash)), 0) FROM memory_events").fetchone()
            cp = conn.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(state_zstd)), 0) FROM memory_checkpoints").fetchone()
            dump = "\n".join(conn.iterdump()).encode("utf-8")
        info = log.export_archive("alice", os.path.join(d, "a.zst"))
        rows.append({"operations": n, "table_bytes_json": table_bytes, "events": ev[0], "event_bytes": ev[1], "checkpoints": cp[0], "checkpoint_bytes_zstd": cp[1],
                     "archive_raw_bytes": info["raw_bytes"], "archive_zstd_bytes": info["archive_bytes"], "sqlite_dump_zstd_bytes": len(cz.compress(dump)),
                     "log_overhead_vs_table": round((ev[1] + cp[1]) / max(1, table_bytes), 2), "archive_vs_dump_zstd": round(info["archive_bytes"] / max(1, len(cz.compress(dump))), 2)})
    return {"rows": rows}


def w3() -> Dict[str, Any]:
    out = []
    for every in (20, 50, 100):
        p, log, d = fresh(True, every)
        workload(p, 600, 3)
        head = log.head()["seq"]
        truth = {s: log.fold("alice", upto_seq=s, include_revoked=True) for s in range(1, head + 1, 6)}
        rng = random.Random(5)
        victim_rows = []
        with p._connect() as conn:
            adds = [r[0] for r in conn.execute("SELECT seq FROM memory_events WHERE kind = 'add' AND seq > 100 AND seq < ?", (head - 100,))]
        for seq in rng.sample(adds, 12):
            with p._connect() as conn:
                original = conn.execute("SELECT payload FROM memory_events WHERE seq = ?", (seq,)).fetchone()[0]
                conn.execute("UPDATE memory_events SET payload = REPLACE(payload, '\"content\":\"', '\"content\":\"X') WHERE seq = ?", (seq,))
            named = log.verify()
            found = any(f"event {seq}:" in x for x in named["problems"])
            wrong = 0
            for s, state in truth.items():
                try:
                    if log.fold("alice", upto_seq=s, include_revoked=True) != state:
                        wrong += 1
                except ValueError:
                    wrong += 1
            try:
                newest_ok = log.fold("alice", include_revoked=True) == truth[max(truth)]
            except ValueError:
                newest_ok = False
            victim_rows.append({"seq": seq, "named_by_verify": found, "moments_sampled": len(truth), "moments_wrong": wrong, "newest_state_still_right": newest_ok})
            with p._connect() as conn:
                conn.execute("UPDATE memory_events SET payload = ? WHERE seq = ?", (original, seq))
        out.append({"checkpoint_every": every, "damaged_events_tried": len(victim_rows), "all_named": all(v["named_by_verify"] for v in victim_rows),
                    "mean_moments_wrong_of_sampled": round(statistics.mean(v["moments_wrong"] for v in victim_rows), 2),
                    "max_moments_wrong": max(v["moments_wrong"] for v in victim_rows), "sampled_every_6_events": True,
                    "newest_state_right_in": sum(v["newest_state_still_right"] for v in victim_rows)})
    return {"rows": out}


def w5() -> Dict[str, Any]:
    """A bloated memory: 1 needed preference + 1 needed fact + duplicates of both, stale episodes, and unrelated facts. 'Needed' = what a correct answer to the goal uses."""
    from datetime import datetime, timedelta, timezone
    rng = random.Random(8)
    now = datetime.now(timezone.utc)

    def mem(i, content, kind, imp, days):
        return {"id": f"m{i}", "content": content, "memory_type": kind, "importance": imp, "created_at": (now - timedelta(days=days)).isoformat()}
    results = []
    cases = []
    for copies in (6, 0):
        for scenario, needed_kind, needed_days in (("a preference, 200 days old", "preference", 200), ("an event, 200 days old, importance 0.5", "event", 200), ("a fact, 400 days old", "fact", 400),
                                                   ("an event, 200 days old, marked important (0.9)", "event", 200), ("a conversation turn, 200 days old", "conversation", 200)):
            cases.append((f"the needed rule is {scenario}; {copies} newer copies of it exist", needed_kind, needed_days, copies, 0.9 if "important" in scenario else 0.5))
    for scenario, needed_kind, needed_days, copies, imp in cases:
        rule = "Whenever you build a quote table always sort it from lowest to highest price."
        items = [mem(0, rule, needed_kind, imp, needed_days)]
        n = 1
        for _ in range(copies):                                                               # exact and near duplicates of the rule, newer
            items.append(mem(n, rule.lower().replace(".", ""), "preference", 0.5, rng.randint(1, 100)))
            n += 1
        for _ in range(40):
            items.append(mem(n, text(rng, 14), rng.choice(["conversation", "event"]), round(rng.uniform(0.1, 0.5), 2), rng.randint(40, 400)))
            n += 1
        for _ in range(20):
            items.append(mem(n, text(rng, 14), "fact", 0.5, rng.randint(1, 300)))
            n += 1
        needed_ids = {"m0"} | {f"m{i}" for i in range(1, 1 + copies)}
        row = {"scenario": scenario, "memories": len(items)}
        for policy in me.POLICIES:
            kept = me.select_for_recall(list(items), policy)
            chars = sum(len(m["content"]) for m in kept)
            row[policy] = {"kept": len(kept), "prompt_chars_share": round(chars / sum(len(m["content"]) for m in items), 3),
                           "needed_rule_still_offered": any(m["id"] in needed_ids for m in kept), "original_needed_item_kept": any(m["id"] == "m0" for m in kept)}
        results.append(row)
    return {"rows": results}


def w4() -> Dict[str, Any]:
    """The whole system: the same scripted trajectories with the log off and on."""
    work_off, work_on = Path(tempfile.mkdtemp(prefix="delentia-mp-off-")), Path(tempfile.mkdtemp(prefix="delentia-mp-on-"))
    outs = {}
    for label, work, flag in (("off", work_off, "0"), ("on", work_on, "1")):
        out = work / "rows.jsonl"
        env = {**os.environ, me.ENABLE_ENV: flag, me.CHECKPOINT_ENV: "10"}
        t0 = time.time()
        done = subprocess.run([sys.executable, str(ROOT / "research" / "runner.py"), "--split", "dev", "--domain", "all", "--policy", "diligent", "--arms", "A111,A001,G,GP",
                               "--only", "traj", "--work", str(work / "w"), "--out", str(out)], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, env=env, timeout=3600)
        if done.returncode != 0:
            return {"error": (done.stdout + done.stderr)[-800:]}
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
        outs[label] = {"rows": rows, "seconds": time.time() - t0, "work": work / "w"}
    by_id = {r["run_id"]: r for r in outs["off"]["rows"]}
    same_answers = all(by_id.get(r["run_id"], {}).get("VTS") == r["VTS"] and by_id.get(r["run_id"], {}).get("violations") == r["violations"] for r in outs["on"]["rows"])
    # the database of the "on" run: verify the chain and each person's replay
    dbs = [p for p in (outs["on"]["work"] / "data").rglob("*.db") if "skills" not in str(p)]
    report: Dict[str, Any] = {"episodes_each": len(outs["on"]["rows"]), "identical_outcomes_with_log_off_and_on": bool(same_answers),
                              "seconds_off": round(outs["off"]["seconds"], 1), "seconds_on": round(outs["on"]["seconds"], 1),
                              "runtime_seconds_per_episode_off": round(statistics.mean(r["runtime_seconds"] for r in outs["off"]["rows"]), 3),
                              "runtime_seconds_per_episode_on": round(statistics.mean(r["runtime_seconds"] for r in outs["on"]["rows"]), 3), "databases": []}
    for path in dbs:
        with sqlite3.connect(path) as conn:
            have = conn.execute("SELECT name FROM sqlite_master WHERE name = 'memory_events'").fetchone()
        if not have:
            continue
        log = me.MemoryEventLog(ControlPlanePersistence(db_path=str(path)))
        with log._p._connect() as conn:
            people = [r[0] for r in conn.execute("SELECT DISTINCT namespace FROM memory_events")]
        checks = {ns: log.consistent_with_table(ns)["ok"] for ns in people}
        report["databases"].append({"events": log.head()["seq"], "chain_ok": log.verify()["ok"], "people": len(people), "replay_equals_table_for_every_person": all(checks.values()),
                                    "checkpoints": sum(log.stats(ns)["checkpoints"] for ns in people)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "research" / "memory_pipeline_round66.json"))
    parser.add_argument("--e2e", action="store_true", help="also run W4, the whole-system comparison (a few minutes)")
    args = parser.parse_args()
    os.environ["DELENTIA_HOME"] = tempfile.mkdtemp(prefix="delentia-mp-home-")
    report: Dict[str, Any] = {"W1_exactness_and_cost": w1(), "W2_bytes": w2(), "W3_damage": w3(), "W5_what_the_model_is_shown": w5()}
    if args.e2e:
        report["W4_whole_system"] = w4()
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, block in report.items():
        print(f"\n== {name}")
        for row in block.get("rows", [block]):
            print("  ", json.dumps(row, ensure_ascii=False)[:420])
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

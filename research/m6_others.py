"""
Round 67, M6: other people's memory stores on the shared workload (research/m6_workload.py). Run with the interpreter of the isolated environment the libraries were installed into
(the Architect allowed the downloads; nothing was installed into the project's own environment):

    C:/Users/whale/m6env/Scripts/python.exe research/m6_others.py --system langgraph --ops 500 --out research/m6_langgraph_500.json
    C:/Users/whale/m6env/Scripts/python.exe research/m6_others.py --system mem0      --ops 500 --out research/m6_mem0_500.json

Systems, each configured the way its own documentation shows, with the reason:
  langgraph   LangGraph's SQLite checkpointer (langgraph-checkpoint-sqlite): the agent's state (here: the dict of one person's facts) is saved after every step; time travel is
              `get_state_history` / `get_state(checkpoint_id)`. It is what a LangGraph agent has instead of a memory log, so it is the fair comparison for "history of what the agent knew".
  mem0        mem0ai's open-source Memory with `infer=False` (store the text as given, no LLM extraction, so the comparison is about the store and not about a model), a local on-disk
              Qdrant collection, nomic-embed-text through the local Ollama, and mem0's own SQLite history table (`history(memory_id)`), which is its record of ADD/UPDATE/DELETE.

What is measured is the same as research/m6_delentia.py: bytes on disk, write latency, whether the current view honours a revocation, whether the state after operation k can be rebuilt
exactly (time travel), whether an edit made directly in the stored data is detected, and what is left of one person's text in the raw bytes after that person is erased with the system's own call.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
import m6_workload as wl  # noqa: E402


def token_of(text: str) -> str:
    m = re.match(r"(T\d{4})\b", text or "")
    return m.group(1) if m else ""


def dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def canary_hits(root: Path) -> int:
    needle = wl.CANARY.encode("utf-8")
    total = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.read_bytes().count(needle)
            except PermissionError:                                          # a lock file held by a store that is still open: it holds no memory text
                continue
    return total


def close_mem0(memory) -> None:
    """mem0's local Qdrant keeps the collection locked while its client is open; closing it makes the files readable (and the lock is not data)."""
    try:
        memory.vector_store.client.close()
    except Exception:                                                        # noqa: BLE001
        pass


def vacuum_all(root: Path) -> int:
    """VACUUM every SQLite file under root (a user who knows SQLite leaves free pages with the old bytes could do this by hand). Returns how many files were rewritten."""
    n = 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in (".db", ".sqlite", ".sqlite3"):
            try:
                c = sqlite3.connect(str(p), isolation_level=None)
                c.execute("PRAGMA secure_delete = ON")
                c.execute("VACUUM")
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                c.close()
                n += 1
            except sqlite3.Error:
                pass
    return n


def percentile(values: List[float], q: float) -> float:
    return round(sorted(values)[int(len(values) * q)], 3)


# --------------------------------------------------------------------------------------------- LangGraph
def run_langgraph(ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    class State(TypedDict, total=False):
        op: dict
        memories: dict          # {ns: {token: text}}
        touched: dict

    def apply(state: State) -> State:
        mem = {k: dict(v) for k, v in (state.get("memories") or {}).items()}
        touched = dict(state.get("touched") or {})
        o = state["op"]
        if o["op"] == "add":
            mem.setdefault(o["ns"], {})[o["token"]] = o["text"]
        elif o["op"] == "revoke":
            mem.get(o["ns"], {}).pop(o["token"], None)
        else:
            touched[o["token"]] = touched.get(o["token"], 0) + 1
        return {"memories": mem, "touched": touched}

    work = Path(tempfile.mkdtemp(prefix="m6-langgraph-"))
    db = work / "checkpoints.sqlite"
    graph_builder = StateGraph(State)
    graph_builder.add_node("apply", apply)
    graph_builder.add_edge(START, "apply")
    graph_builder.add_edge("apply", END)
    latencies: List[float] = []
    cps: List[str] = [""]
    with SqliteSaver.from_conn_string(str(db)) as saver:
        graph = graph_builder.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "alice"}}                       # one LangGraph thread per person (the unit it can delete)
        cfg_of = {"alice": cfg, "bob": {"configurable": {"thread_id": "bob"}}}
        last_alice: List[str] = [""]                                          # alice's newest checkpoint after each operation (bob's operations leave it unchanged)
        for o in ops:
            started = time.perf_counter()
            graph.invoke({"op": o}, cfg_of[o["ns"]])
            latencies.append((time.perf_counter() - started) * 1000)
            if o["ns"] == "alice":
                last_alice[0] = graph.get_state(cfg).config["configurable"]["checkpoint_id"]
            cps.append(last_alice[0])
        result: Dict[str, Any] = {"system": "langgraph SqliteSaver", "ops": len(ops)}
        now = set(graph.get_state(cfg).values.get("memories", {}).get("alice", {}))
        result["current_view_exact"] = now == wl.truth_after(ops, len(ops))
        result["current_view_wrong"] = len(now ^ wl.truth_after(ops, len(ops)))
        exact = 0
        ks = wl.checkpoints_for(len(ops))
        for k in ks:
            snap = graph.get_state({"configurable": {"thread_id": "alice", "checkpoint_id": cps[k]}}) if cps[k] else None
            got = set(snap.values.get("memories", {}).get("alice", {})) if snap is not None else set()
            exact += got == wl.truth_after(ops, k)
        result["time_travel"] = {"supported": True, "checked": len(ks), "exact": exact}
    with sqlite3.connect(str(db)) as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    result["bytes_on_disk"] = dir_bytes(work)
    result["write_ms_median"] = round(statistics.median(latencies), 3)
    result["write_ms_p95"] = percentile(latencies, 0.95)

    # tamper: change a stored fact's text inside a saved checkpoint, same length so the serialised record stays valid
    with sqlite3.connect(str(db)) as c:
        row = c.execute("SELECT thread_id, checkpoint_ns, checkpoint_id, type, checkpoint FROM checkpoints WHERE thread_id = 'alice' ORDER BY checkpoint_id LIMIT 1 OFFSET ?", (len(ops) // 3,)).fetchone()
        blob = bytes(row[4])
        needle = re.search(rb"T\d{4}", blob)
        edited = False
        if needle:
            c.execute("UPDATE checkpoints SET checkpoint = ? WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?",
                      (blob.replace(needle.group(0), b"TXXXX", 1), row[0], row[1], row[2]))
            edited = True
    detected = False
    note = "the edit was made" if edited else "no token found to edit"
    try:
        with SqliteSaver.from_conn_string(str(db)) as saver2:
            g2 = graph_builder.compile(checkpointer=saver2)
            list(g2.get_state_history({"configurable": {"thread_id": row[0]}}))
            snap = g2.get_state({"configurable": {"thread_id": row[0], "checkpoint_id": row[2]}})
            note = "reading back the edited checkpoint succeeded silently" if snap is not None else note
    except Exception as exc:                                              # noqa: BLE001
        detected, note = True, f"reading raised {type(exc).__name__}"
    result["tamper_detected"], result["tamper_note"] = detected, note

    # erase one person: the library's own call is deleting the thread; the facts live in the checkpoints of that thread
    before = canary_hits(work)
    with SqliteSaver.from_conn_string(str(db)) as saver3:
        try:
            saver3.delete_thread("alice")
            call = "delete_thread('alice')"
        except Exception as exc:                                          # noqa: BLE001
            call = f"delete_thread failed: {type(exc).__name__}"
    with sqlite3.connect(str(db)) as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    after = canary_hits(work)
    with sqlite3.connect(str(db)) as c:
        rows_left = c.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = 'alice'").fetchone()[0]
    vacuum_all(work)
    after_vacuum = canary_hits(work)
    with SqliteSaver.from_conn_string(str(db)) as saver4:
        graph4 = graph_builder.compile(checkpointer=saver4)
        bob_state = graph4.get_state({"configurable": {"thread_id": "bob"}}).values.get("memories", {}).get("bob", {})
    result["erase"] = {"call": call, "canary_in_raw_bytes_before": before, "canary_in_raw_bytes_after": after,
                       "rows_of_the_person_left_in_the_table": rows_left, "canary_in_raw_bytes_after_a_manual_vacuum": after_vacuum,
                       "other_person_intact": bool(bob_state) or not any(o["ns"] == "bob" for o in ops)}
    shutil.rmtree(work, ignore_errors=True)
    return result


# --------------------------------------------------------------------------------------------- mem0
def run_mem0(ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    from mem0 import Memory
    work = Path(tempfile.mkdtemp(prefix="m6-mem0-"))
    history_db = work / "history.db"
    config = {
        "vector_store": {"provider": "qdrant", "config": {"path": str(work / "qdrant"), "collection_name": "m6", "embedding_model_dims": 768, "on_disk": True}},
        "embedder": {"provider": "ollama", "config": {"model": "nomic-embed-text", "ollama_base_url": "http://localhost:11434", "embedding_dims": 768}},
        "llm": {"provider": "ollama", "config": {"model": "qwen2.5:7b", "ollama_base_url": "http://localhost:11434"}},
        "history_db_path": str(history_db),
    }
    m = Memory.from_config(config)
    ids: Dict[str, str] = {}
    stamps: List[str] = [datetime.now(timezone.utc).isoformat()]
    latencies: List[float] = []
    for o in ops:
        started = time.perf_counter()
        if o["op"] == "add":
            r = m.add(o["text"], user_id=o["ns"], infer=False)
            results = r.get("results", r) if isinstance(r, dict) else r
            ids[o["token"]] = results[0]["id"]
        elif o["op"] == "revoke":
            m.delete(ids[o["token"]])
        # mem0 has no "this memory was used" operation: a touch is not recorded
        latencies.append((time.perf_counter() - started) * 1000)
        time.sleep(0.002)
        stamps.append(datetime.now(timezone.utc).isoformat())
    result: Dict[str, Any] = {"system": "mem0 (infer=False, qdrant local, nomic-embed-text)", "ops": len(ops)}
    now_items = m.get_all(filters={"user_id": "alice"}, top_k=100000)
    now_items = now_items.get("results", now_items) if isinstance(now_items, dict) else now_items
    live = {token_of(i["memory"]) for i in now_items}
    result["current_view_exact"] = live == wl.truth_after(ops, len(ops))
    result["current_view_wrong"] = len(live ^ wl.truth_after(ops, len(ops)))

    # time travel from mem0's own history table
    with sqlite3.connect(str(history_db)) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(history)")]
        rows = [dict(zip(cols, r, strict=True)) for r in c.execute("SELECT * FROM history ORDER BY created_at")]
    exact = 0
    ks = wl.checkpoints_for(len(ops))
    for k in ks:
        cutoff = stamps[k]
        state: Dict[str, str] = {}
        for h in rows:
            # an ADD happened at created_at; a DELETE row keeps the memory's ORIGINAL created_at and records the deletion in updated_at (read from the rows themselves)
            when = (h.get("updated_at") if h.get("event") == "DELETE" else h.get("created_at")) or h.get("created_at") or ""
            if when and when <= cutoff:
                if h.get("event") == "ADD" or (h.get("event") == "UPDATE" and h.get("new_memory")):
                    state[h["memory_id"]] = h.get("new_memory") or ""
                elif h.get("event") == "DELETE" or h.get("is_deleted"):
                    state.pop(h["memory_id"], None)
        belongs = {token_of(t) for t in state.values()}
        exact += (belongs & {o["token"] for o in ops if o["ns"] == "alice"}) == wl.truth_after(ops, k)
    result["time_travel"] = {"supported": True, "checked": len(ks), "exact": exact, "note": "rebuilt from the history table's timestamps; mem0 offers per-memory history(), not a state-at-time call"}
    close_mem0(m)
    del m
    result["bytes_on_disk"] = dir_bytes(work)
    result["write_ms_median"] = round(statistics.median(latencies), 3)
    result["write_ms_p95"] = percentile(latencies, 0.95)

    with sqlite3.connect(str(history_db)) as c:
        c.execute("UPDATE history SET new_memory = REPLACE(new_memory, 'T0004', 'TXXXX') WHERE new_memory LIKE 'T0004%'")
        c.execute("UPDATE history SET new_memory = new_memory || ' (edited)' WHERE rowid = (SELECT rowid FROM history WHERE new_memory IS NOT NULL LIMIT 1 OFFSET 7)")
    result["tamper_detected"] = False
    result["tamper_note"] = "no integrity check is offered; the history table and the vector payload are plain rows"

    m2 = Memory.from_config(config)
    before = canary_hits(work)
    m2.delete_all(user_id="alice")
    close_mem0(m2)
    del m2
    with sqlite3.connect(str(history_db)) as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    after = canary_hits(work)
    vacuum_all(work)
    after_vacuum = canary_hits(work)
    m3 = Memory.from_config(config)
    bob = m3.get_all(filters={"user_id": "bob"}, top_k=100000)
    bob = bob.get("results", bob) if isinstance(bob, dict) else bob
    result["erase"] = {"call": "delete_all(user_id)", "canary_in_raw_bytes_before": before, "canary_in_raw_bytes_after": after,
                       "canary_in_raw_bytes_after_a_manual_vacuum": after_vacuum, "other_person_intact": bool(bob) or not any(o["ns"] == "bob" for o in ops)}
    shutil.rmtree(work, ignore_errors=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", choices=["langgraph", "mem0"], required=True)
    ap.add_argument("--ops", type=int, default=500)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ops = wl.make_workload(args.ops)
    import logging
    logging.disable(logging.WARNING)
    result = run_langgraph(ops) if args.system == "langgraph" else run_mem0(ops)
    Path(args.out).write_text(json.dumps({"ops": args.ops, "results": [result]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

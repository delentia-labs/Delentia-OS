"""
Round 69: the recall that ships, end to end. The same sets as research/recall_lab_r69.py, but through the real AgentMemory (real SQLite, sealed vectors, the real embedding model, the real ranking in
rct_control_plane/memory_ranking.py). Reported next to the lab's variant A (the Round 68 behaviour) and C/L (what the lab chose), so a difference between lab and product shows up.

    python research/recall_e2e_r69.py --sets dev,h1,h4 --out research/recall_e2e_r69.json
    python research/recall_e2e_r69.py --sets h5 --once                      # a held-out set: --once refuses to run it twice (writes research/recall_e2e_ran.json)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))
import recall_lab_r69 as lab  # noqa: E402

RAN = ROOT / "research" / "recall_e2e_ran.json"
HELD_OUT = ("h1", "h2", "h4", "h5")


def run_set(name: str, mode: str, ks: Tuple[int, ...] = (1, 3, 5, 10)) -> Dict[str, Any]:
    """mode: 'lexical' (embeddings off: the code path of every release before Round 68), 'embed' (DELENTIA_MEMORY_EMBED=ollama), 'embedQ' (+ store-time questions) or 'embedQG' (+ query expansion)."""
    texts, qa = lab.load_set(name)
    work = Path(tempfile.mkdtemp(prefix="recall-e2e-"))
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_MEMORY_KEYS_DIR": str(work / "keys"), "DELENTIA_MEMORY_EMBED": "off" if mode == "lexical" else "ollama",
                       "DELENTIA_MEMORY_QUESTIONS": "ollama" if mode in ("embedQ", "embedQG") else "off", "DELENTIA_MEMORY_QUERY_EXPANSION": "ollama" if mode == "embedQG" else "off"})
    import logging
    logging.disable(logging.WARNING)
    from rct_control_plane import memory_embeddings, memory_llm
    from rct_control_plane.agent_memory import AgentMemory, MemoryType
    from rct_control_plane.persistence import ControlPlanePersistence
    import recall_dataset_r69 as h
    memory_embeddings.reset_breaker()
    memory_llm.reset_breaker()
    p = ControlPlanePersistence(db_path=str(work / "m.db"))
    mem = AgentMemory("alice", p)

    async def go() -> Dict[str, Any]:
        store_ms, recall_ms = [], []
        for t in texts:
            started = time.perf_counter()
            await mem.store(t, MemoryType.FACT, importance=0.6)
            store_ms.append((time.perf_counter() - started) * 1000)
        hits = {k: 0 for k in ks}
        misses = []
        for question, answer in qa:
            started = time.perf_counter()
            got = await mem.recall(question, limit=max(ks))
            recall_ms.append((time.perf_counter() - started) * 1000)
            pat = h._boundary(answer)
            rank = next((i + 1 for i, m in enumerate(got) if pat.search(m["content"].lower())), None)
            for k in ks:
                hits[k] += int(rank is not None and rank <= k)
            if not (rank and rank <= 3):
                misses.append({"question": question, "answer": answer, "top": [m["content"] for m in got[:3]]})
        return {"set": name, "mode": mode, "n": len(qa), **{f"hit@{k}": hits[k] for k in ks}, "store_ms_median": round(statistics.median(store_ms), 1),
                "recall_ms_median": round(statistics.median(recall_ms), 1), "misses@3": misses}

    return asyncio.run(go())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets", required=True)
    ap.add_argument("--modes", default="lexical,embed")
    ap.add_argument("--once", action="store_true", help="held-out sets: refuse to run a set that was already run")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    ran = json.loads(RAN.read_text(encoding="utf-8")) if RAN.exists() else {}
    results = []
    for name in args.sets.split(","):
        if name in HELD_OUT and args.once and name in ran:
            raise SystemExit(f"{name} was already measured once ({ran[name]}); a held-out set is not run twice")
        for mode in args.modes.split(","):
            r = run_set(name, mode)
            results.append(r)
            print(f"{name} [{mode}]: hit@1 {r['hit@1']}/{r['n']}  hit@3 {r['hit@3']}  hit@5 {r['hit@5']}  hit@10 {r['hit@10']}  store {r['store_ms_median']} ms  recall {r['recall_ms_median']} ms")
        if name in HELD_OUT and args.once:
            ran[name] = time.strftime("%Y-%m-%d %H:%M")
            RAN.write_text(json.dumps(ran, indent=2) + "\n", encoding="utf-8")
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

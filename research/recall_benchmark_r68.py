"""
Round 68: which memory system finds the right fact? (dataset: research/recall_dataset_r68.py, written before any system was run on it.)

    python research/recall_benchmark_r68.py --system delentia --out research/recall_delentia.json
    python research/recall_benchmark_r68.py --system nomic    --out research/recall_nomic.json          # plain cosine over nomic-embed-text, no memory system at all (the reference)
    C:/Users/whale/m6env/Scripts/python.exe research/recall_benchmark_r68.py --system mem0 --out research/recall_mem0.json   # mem0ai, infer=False, local Qdrant, nomic-embed-text

Each system stores the same 120 texts (30 facts + 90 distractors, shuffled with the same seed) and answers the same 30 paraphrased questions with its own top 3. A question is a HIT when the answer value
appears in any of the 3 texts returned; top-1 is the stricter count. A difference of one question or less between two systems is reported as no difference (30 questions).
mem0 runs without its LLM extraction (infer=False), so the question is retrieval; its extraction is not measured here.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))
import recall_dataset_r68 as ds  # noqa: E402

OLLAMA = "http://localhost:11434"


def embed(texts: List[str]) -> List[List[float]]:
    out = []
    for t in texts:
        req = urllib.request.Request(OLLAMA + "/api/embeddings", data=json.dumps({"model": "nomic-embed-text", "prompt": t}).encode("utf-8"), headers={"Content-Type": "application/json"})
        out.append(json.loads(urllib.request.urlopen(req, timeout=120).read())["embedding"])
    return out


def cosine(a: List[float], b: List[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0


def corpus() -> List[str]:
    d = ds.dataset()
    texts = [f["text"] for f in d["facts"]] + list(d["distractors"])
    random.Random(5).shuffle(texts)
    return texts


def run_nomic(texts: List[str], questions: List[str], k: int) -> List[List[str]]:
    vectors = embed(texts)
    out = []
    for q in questions:
        qv = embed([q])[0]
        ranked = sorted(range(len(texts)), key=lambda i: -cosine(qv, vectors[i]))
        out.append([texts[i] for i in ranked[:k]])
    return out


def run_delentia(texts: List[str], questions: List[str], k: int) -> List[List[str]]:
    work = Path(tempfile.mkdtemp(prefix="recall-delentia-"))
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_MEMORY_KEYS_DIR": str(work / "keys")})
    import logging
    logging.disable(logging.WARNING)
    from rct_control_plane.agent_memory import AgentMemory, MemoryType
    from rct_control_plane.persistence import ControlPlanePersistence
    p = ControlPlanePersistence(db_path=str(work / "m.db"))
    mem = AgentMemory("alice", p)

    async def go() -> List[List[str]]:
        for t in texts:
            await mem.store(t, MemoryType.FACT, importance=0.6)
        return [[m["content"] for m in await mem.recall(q, limit=k)] for q in questions]

    return asyncio.run(go())


def run_mem0(texts: List[str], questions: List[str], k: int) -> List[List[str]]:
    from mem0 import Memory
    work = Path(tempfile.mkdtemp(prefix="recall-mem0-"))
    config = {
        "vector_store": {"provider": "qdrant", "config": {"path": str(work / "q"), "collection_name": "r68", "embedding_model_dims": 768, "on_disk": True}},
        "embedder": {"provider": "ollama", "config": {"model": "nomic-embed-text", "ollama_base_url": OLLAMA, "embedding_dims": 768}},
        "llm": {"provider": "ollama", "config": {"model": "qwen2.5:7b", "ollama_base_url": OLLAMA}},
        "history_db_path": str(work / "h.db"),
    }
    m = Memory.from_config(config)
    for t in texts:
        m.add(t, user_id="alice", infer=False)
    out = []
    for q in questions:
        res = m.search(q, filters={"user_id": "alice"}, top_k=k, threshold=0.0)
        res = res.get("results", res) if isinstance(res, dict) else res
        out.append([r["memory"] for r in res])
    try:
        m.vector_store.client.close()
    except Exception:                                                        # noqa: BLE001
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", choices=["delentia", "nomic", "mem0"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=3)
    args = ap.parse_args()
    d = ds.dataset()
    questions = [f["question"] for f in d["facts"]]
    answers = [f["answer"] for f in d["facts"]]
    texts = corpus()
    started = time.perf_counter()
    got = {"delentia": run_delentia, "nomic": run_nomic, "mem0": run_mem0}[args.system](texts, questions, args.k)
    seconds = round(time.perf_counter() - started, 1)
    rows = []
    for f, top in zip(d["facts"], got, strict=True):
        hit = any(f["answer"].lower() in t.lower() for t in top)
        top1 = bool(top) and f["answer"].lower() in top[0].lower()
        rows.append({"id": f["id"], "question": f["question"], "answer": f["answer"], "hit_at_3": hit, "hit_at_1": top1, "top": top})
    summary = {"system": args.system, "questions": len(rows), "hit_at_3": sum(r["hit_at_3"] for r in rows), "hit_at_1": sum(r["hit_at_1"] for r in rows), "seconds_total": seconds,
               "missed": [r["id"] for r in rows if not r["hit_at_3"]]}
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    assert len(answers) == len(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

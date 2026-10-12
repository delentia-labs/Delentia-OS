"""
Round 68: what the opt-in embedding recall costs and whether it inflates relevance (criteria 2 and 3 of research/round68_criteria.md section 6).

    python research/recall_embed_costs_r68.py [--out research/recall_embed_costs_r68.json]

 * latency: median milliseconds to store one memory and to answer one recall, with the embedding model warm, embeddings OFF and ON, on the benchmark's 120 texts and 30 questions;
 * relevance: for 30 questions that have NOTHING to do with the stored texts, the best `relevance` that `recall_scored` reports (the value D reads), OFF and ON. It must not rise in a way
   that would make D believe the agent knows something it does not.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))
import recall_benchmark_r68 as rb  # noqa: E402
import recall_dataset_r68 as ds  # noqa: E402

UNRELATED = [
    "What is the capital of France?", "How do I bake sourdough bread?", "Who painted the Mona Lisa?", "What is the boiling point of water at sea level?", "Which planet has the most moons?",
    "How many players are on a football team?", "What is the square root of 144?", "Who wrote Hamlet?", "What does DNA stand for?", "How tall is Mount Everest?",
    "Which ocean is the largest?", "What year did the Berlin Wall fall?", "How do bees make honey?", "What is the speed of light?", "Who discovered penicillin?",
    "What is the longest river in Africa?", "How many strings does a violin have?", "What is photosynthesis?", "Which element has the symbol Fe?", "Who composed the Four Seasons?",
    "What is the tallest animal?", "How does a rainbow form?", "What language is spoken in Brazil?", "Who invented the telephone?", "What is the smallest prime number?",
    "Which continent is the Sahara in?", "How many days are in a leap year?", "What colour do you get mixing blue and yellow?", "Who was the first person on the moon?", "What is the freezing point of water?",
]


def run(embed: bool) -> dict:
    work = Path(tempfile.mkdtemp(prefix="recall-cost-"))
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_MEMORY_KEYS_DIR": str(work / "keys"), "DELENTIA_MEMORY_EMBED": "ollama" if embed else "off"})
    import logging
    logging.disable(logging.WARNING)
    from rct_control_plane import memory_embeddings
    from rct_control_plane.agent_memory import AgentMemory, MemoryType
    from rct_control_plane.persistence import ControlPlanePersistence
    memory_embeddings.reset_breaker()
    memory_embeddings.embed(["warm up"])
    p = ControlPlanePersistence(db_path=str(work / "m.db"))
    mem = AgentMemory("alice", p)
    d = ds.dataset()
    texts = rb.corpus()
    questions = [f["question"] for f in d["facts"]]

    async def go() -> dict:
        store_ms, recall_ms = [], []
        for t in texts:
            started = time.perf_counter()
            await mem.store(t, MemoryType.FACT, importance=0.6)
            store_ms.append((time.perf_counter() - started) * 1000)
        for q in questions:
            started = time.perf_counter()
            await mem.recall(q, limit=3)
            recall_ms.append((time.perf_counter() - started) * 1000)
        best = []
        for q in UNRELATED:
            scored = await mem.recall_scored(q, limit=1)
            best.append(scored[0]["relevance"] if scored else 0.0)
        return {"store_ms_median": round(statistics.median(store_ms), 1), "recall_ms_median": round(statistics.median(recall_ms), 1), "unrelated_best_relevance_mean": round(statistics.mean(best), 3),
                "unrelated_best_relevance_max": round(max(best), 3)}

    return asyncio.run(go())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "research" / "recall_embed_costs_r68.json"))
    args = ap.parse_args()
    result = {"off": run(False), "on": run(True)}
    result["added_store_ms"] = round(result["on"]["store_ms_median"] - result["off"]["store_ms_median"], 1)
    result["added_recall_ms"] = round(result["on"]["recall_ms_median"] - result["off"]["recall_ms_median"], 1)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

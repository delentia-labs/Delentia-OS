"""
Round 69: recall as the agent loop USES it. Not "is the memory in the top k of a ranking" but what an episode really gets: the loop's own `_recall_for_goal` (the number of memories it shows, the relevance floor,
the per-person store) and what D reads from it.

For every question of a set: was the memory with the answer among the memories shown to the episode, and how much does the memory part of D rise (D weighs memory 0.15; the part is min(1, best relevance / 0.5))?
For questions that have NOTHING to do with the stored texts (English and Thai): how often does the loop show a memory anyway and by how much does D rise (it should not).

    DELENTIA_MEMORY_EMBED=ollama DELENTIA_MEMORY_EMBED_MODEL=bge-m3 python research/recall_in_loop_r69.py --set h5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))
import recall_lab_r69 as lab  # noqa: E402

UNRELATED_EN = ["What is the capital of France?", "How do I bake sourdough bread?", "Who painted the Mona Lisa?", "What is the boiling point of water at sea level?", "Which planet has the most moons?",
                "How many players are on a football team?", "What is the square root of 144?", "Who wrote Hamlet?", "What does DNA stand for?", "How tall is Mount Everest?"]
UNRELATED_TH = ["เมืองหลวงของฝรั่งเศสคืออะไร", "ทำขนมปังซาวร์โดว์อย่างไร", "ใครวาดภาพโมนาลิซ่า", "น้ำเดือดที่กี่องศาเซลเซียส", "ดาวเคราะห์ดวงไหนมีดวงจันทร์มากที่สุด",
                "ทีมฟุตบอลมีผู้เล่นกี่คน", "รากที่สองของ 144 คือเท่าไร", "ใครเขียนเรื่องแฮมเล็ต", "ดีเอ็นเอย่อมาจากอะไร", "ยอดเขาเอเวอเรสต์สูงเท่าไร"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True, choices=["dev", "h1", "h2", "h5"])
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    texts, qa = lab.load_set(args.set)
    work = Path(tempfile.mkdtemp(prefix="recall-loop-"))
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_MEMORY_KEYS_DIR": str(work / "keys")})
    import logging
    logging.disable(logging.WARNING)
    from rct_control_plane import data_evidence, memory_embeddings
    from rct_control_plane.agent_memory import AgentMemory, MemoryType
    from rct_control_plane.persistence import ControlPlanePersistence
    from test_governed_autonomous_loop_real import _FakeKernel, _loop
    import recall_dataset_r69 as h
    memory_embeddings.reset_breaker()
    kernel = _FakeKernel()
    p = ControlPlanePersistence(db_path=str(work / "m.db"))
    kernel._agent_memory = AgentMemory("shared_default", p)               # the loop reads the person's own namespace as well (a gateway sender, a Desk user)
    person = AgentMemory("alice", p)
    loop = _loop(work, "alice", kernel=kernel)
    loop._persistence = p

    async def go() -> dict:
        for t in texts:
            await person.store(t, MemoryType.FACT, importance=0.6)
        shown, rows = 0, []
        for question, answer in qa:
            got = await loop._recall_for_goal(question)
            pat = h._boundary(answer)
            found = any(pat.search(str(m.get("content", "")).lower()) for m in got)
            best = max((float(m["relevance"]) for m in got), default=0.0)
            shown += int(found)
            rows.append({"question": question, "found": found, "n": len(got), "best_relevance": round(best, 3), "memory_part": round(min(1.0, best / 0.5) if best >= data_evidence.MEMORY_RELEVANCE_FLOOR else 0.0, 3)})
        noise = []
        for question in UNRELATED_EN + UNRELATED_TH:
            got = await loop._recall_for_goal(question)
            best = max((float(m["relevance"]) for m in got), default=0.0)
            noise.append({"question": question, "n": len(got), "best_relevance": round(best, 3), "memory_part": round(min(1.0, best / 0.5) if best >= data_evidence.MEMORY_RELEVANCE_FLOOR else 0.0, 3)})
        return {"shown": shown, "rows": rows, "noise": noise}

    r = asyncio.run(go())
    n = len(qa)
    inj = loop._memory_inject_limit(3)
    weight = data_evidence.WEIGHTS["memory"]
    summary = {"set": args.set, "model": memory_embeddings.model() if memory_embeddings.enabled() else "(embeddings off)", "injected_per_episode": inj, "questions": n, "gold_shown_to_the_episode": r["shown"],
               "mean_D_gain_from_memory_on_questions": round(weight * statistics.mean(x["memory_part"] for x in r["rows"]), 4),
               "unrelated_questions": len(r["noise"]), "unrelated_that_still_show_a_memory": sum(1 for x in r["noise"] if x["n"] > 0),
               "unrelated_mean_D_gain": round(weight * statistics.mean(x["memory_part"] for x in r["noise"]), 4), "unrelated_max_D_gain": round(weight * max(x["memory_part"] for x in r["noise"]), 4)}
    print(json.dumps(summary, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, **r}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

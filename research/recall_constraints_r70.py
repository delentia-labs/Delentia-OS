"""
Round 70: does a standing constraint come back when the agent is given the goal it governs? (set H6, criteria: research/round70_criteria.md section 1)

Through the real AgentMemory and the agent loop's own `_recall_for_goal` (the number of memories shown, the relevance floor). Hit = the EXACT constraint text is among the memories.

    python research/recall_constraints_r70.py --mode lexical|nomic|bge --once
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "rct_control_plane" / "tests"))
import recall_dataset_r70 as ds  # noqa: E402

RAN = ROOT / "research" / "recall_constraints_ran.json"


def wilson(k: int, n: int, z: float = 1.96) -> List[float]:
    import math
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - m) / d, 3), round((c + m) / d, 3)]


def run(mode: str, pins: int = 0) -> Dict[str, Any]:
    ds.verify_frozen()
    env = {"lexical": {"DELENTIA_MEMORY_EMBED": "off"}, "nomic": {"DELENTIA_MEMORY_EMBED": "ollama", "DELENTIA_MEMORY_EMBED_MODEL": "nomic-embed-text"},
           "bge": {"DELENTIA_MEMORY_EMBED": "ollama", "DELENTIA_MEMORY_EMBED_MODEL": "bge-m3"}}[mode]
    work = Path(tempfile.mkdtemp(prefix="constraints-"))
    os.environ.update({"DELENTIA_HOME": str(work / "home"), "DELENTIA_MEMORY_KEYS_DIR": str(work / "keys"), **env})
    import logging
    logging.disable(logging.WARNING)
    from rct_control_plane import memory_embeddings
    from rct_control_plane.agent_memory import AgentMemory, MemoryType
    from rct_control_plane.persistence import ControlPlanePersistence
    from test_governed_autonomous_loop_real import _FakeKernel, _loop
    memory_embeddings.reset_breaker()
    data = ds.dataset()
    p = ControlPlanePersistence(db_path=str(work / "m.db"))
    kernel = _FakeKernel()
    kernel._agent_memory = AgentMemory("shared_default", p)
    person = AgentMemory("alice", p)
    loop = _loop(work, "alice", kernel=kernel)
    loop._persistence = p

    async def go() -> Dict[str, Any]:
        ids = {}
        for text in ds.corpus():
            ids[text] = await person.store(text, MemoryType.FACT, importance=0.6)
        pinned_texts: List[str] = []
        if pins:                                                              # the person pins the rules they care most about: a seeded choice of `pins` of the 40
            import random
            chosen = random.Random(70).sample([i["constraint"] for i in data["items"]], pins)
            for text in chosen:
                assert p.pin_memory(ids[text], "alice", True, by="measurement")["ok"]
            pinned_texts = chosen
        rows = []
        for item in data["items"]:
            ranked = [m["content"] for m in await person.recall(item["goal"], limit=10)]
            shown = [m["content"] for m in await loop._recall_for_goal(item["goal"])]
            rank = next((i + 1 for i, t in enumerate(ranked) if t == item["constraint"]), None)
            rows.append({"id": item["id"], "language": item["language"], "goal": item["goal"], "rank": rank, "shown": item["constraint"] in shown, "n_shown": len(shown),
                         "top": ranked[:3], "constraint": item["constraint"], "n_pinned_shown": sum(1 for t in pinned_texts if t in shown)})
        # what D reads for goals that have nothing to do with any stored text, with the pins in place (a pinned rule must not count as evidence)
        from rct_control_plane import data_evidence
        unrelated = ["What is the capital of France?", "How do I bake sourdough bread?", "Who painted the Mona Lisa?", "What is the boiling point of water at sea level?", "Which planet has the most moons?",
                     "เมืองหลวงของฝรั่งเศสคืออะไร", "ทำขนมปังซาวร์โดว์อย่างไร", "ใครวาดภาพโมนาลิซ่า", "น้ำเดือดที่กี่องศาเซลเซียส", "ดาวเคราะห์ดวงไหนมีดวงจันทร์มากที่สุด"]
        gains, shown_counts = [], []
        for q in unrelated:
            got = await loop._recall_for_goal(q)
            gains.append(data_evidence.WEIGHTS["memory"] * (min(1.0, max(loop._episode_memory_scores, default=0.0) / 0.5) if loop._episode_memory_scores else 0.0))
            shown_counts.append(len(got))
        return {"rows": rows, "pinned_texts": pinned_texts, "unrelated_mean_D_gain": round(sum(gains) / len(gains), 4), "unrelated_shown": shown_counts}

    r = asyncio.run(go())
    rows = r["rows"]
    out: Dict[str, Any] = {"mode": mode, "n": len(rows)}
    for k in (1, 3, 5, 10):
        out[f"hit@{k}"] = sum(1 for x in rows if x["rank"] and x["rank"] <= k)
    out["shown_to_the_episode"] = sum(1 for x in rows if x["shown"])
    out["shown_wilson95"] = wilson(out["shown_to_the_episode"], len(rows))
    for lang in ("th", "en"):
        sub = [x for x in rows if x["language"] == lang]
        out[f"{lang}_n"], out[f"{lang}_hit@5"], out[f"{lang}_shown"] = len(sub), sum(1 for x in sub if x["rank"] and x["rank"] <= 5), sum(1 for x in sub if x["shown"])
    if pins:
        pinned_texts = set(r["pinned_texts"])
        out["pins"] = pins
        out["goals_where_every_pinned_rule_was_shown"] = sum(1 for x in rows if x["n_pinned_shown"] == len(pinned_texts))
        out["unpinned_shown"] = sum(1 for x in rows if x["constraint"] not in pinned_texts and x["shown"])
        out["unpinned_n"] = sum(1 for x in rows if x["constraint"] not in pinned_texts)
    out["unrelated_mean_D_gain"] = r["unrelated_mean_D_gain"]
    out["unrelated_shown"] = r["unrelated_shown"]
    out["misses_not_shown"] = [{"goal": x["goal"], "rank": x["rank"], "top": x["top"]} for x in rows if not x["shown"]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", required=True, choices=["lexical", "nomic", "bge"])
    ap.add_argument("--pins", type=int, default=0, help="pin this many of the 40 rules (seeded) before the measurement")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    ran = json.loads(RAN.read_text(encoding="utf-8")) if RAN.exists() else {}
    key = args.mode + (f"+pin{args.pins}" if args.pins else "")
    if args.once and key in ran:
        raise SystemExit(f"H6 was already measured once with {key} ({ran[key]})")
    result = run(args.mode, args.pins)
    summary = {k: v for k, v in result.items() if k != "misses_not_shown"}
    print(json.dumps(summary, ensure_ascii=False))
    if args.once:
        import time
        ran[key] = time.strftime("%Y-%m-%d %H:%M")
        RAN.write_text(json.dumps(ran, indent=2) + "\n", encoding="utf-8")
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

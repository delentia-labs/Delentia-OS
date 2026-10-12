"""
Round 72: `replaces` and its hint, measured against the criteria written first (research/round72_criteria.md).

A. staleness: with `replace` the older value is never offered; without it both are (recall without embeddings unless --embed).
B. the hint: does `likely_replaced` name the old memory (hit) and how often does it speak up for a fact that has no predecessor (false hint)?

    python research/replaces_r72.py [--embed] [--holdout]     (without --holdout only the development part runs and the threshold is printed)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
import recall_dataset_r69 as h  # noqa: E402

THRESHOLDS = (0.20, 0.30, 0.40, 0.50)


def wilson(k: int, n: int) -> tuple:
    if n == 0:
        return (0.0, 0.0)
    p, z = k / n, 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def fresh(name: str):
    from rct_control_plane.agent_memory import AgentMemory
    from rct_control_plane.persistence import ControlPlanePersistence
    path = os.path.join(tempfile.mkdtemp(prefix="r72-"), name + ".db")
    persistence = ControlPlanePersistence(db_path=path)
    return AgentMemory("person", persistence), persistence


def store_all(memory, texts):
    return [asyncio.run(memory.store(t, __import__("rct_control_plane.agent_memory", fromlist=["MemoryType"]).MemoryType.FACT)) for t in texts]


def contains(text: str, value: str) -> bool:
    return value.lower().rstrip(".") in text.lower()


def part_a(updates, background) -> dict:
    from rct_control_plane import memory_replace
    from rct_control_plane.agent_memory import MemoryType
    out = {}
    for variant in ("plain", "replace"):
        memory, persistence = fresh(variant)
        store_all(memory, background)
        old_ids = store_all(memory, [u["old"] for u in updates])
        for u, old_id in zip(updates, old_ids, strict=True):
            if variant == "plain":
                asyncio.run(memory.store(u["new"], MemoryType.FACT))
            else:
                asyncio.run(memory_replace.replace(memory, old_id, u["new"], by="harness"))
        top1_new = old_in3 = 0
        for u in updates:
            found = asyncio.run(memory.recall_scored(u["question"], limit=3))
            texts = [m["content"] for m in found]
            top1_new += bool(texts) and contains(texts[0], u["answer_new"])
            old_in3 += any(contains(t, u["answer_old"]) and not contains(t, u["answer_new"]) for t in texts)
        out[variant] = {"top1_is_newer": top1_new, "older_value_in_top3": old_in3, "n": len(updates)}
    return out


def hint_hits(updates, background, threshold) -> int:
    from rct_control_plane import memory_replace
    memory, persistence = fresh("hits")
    store_all(memory, background)
    old_ids = store_all(memory, [u["old"] for u in updates])
    hits = 0
    for u, old_id in zip(updates, old_ids, strict=True):
        hints = memory_replace.likely_replaced(persistence, "person", u["new"], threshold=threshold)
        hits += any(x["id"] == old_id for x in hints)
    return hits


def false_hints(facts, background, threshold) -> int:
    from rct_control_plane import memory_replace
    memory, persistence = fresh("false")
    store_all(memory, background)
    return sum(bool(memory_replace.likely_replaced(persistence, "person", f["fact"] if isinstance(f, dict) else str(f), threshold=threshold)) for f in facts)


def fact_text(f) -> str:
    return f["fact"] if isinstance(f, dict) and "fact" in f else (f.get("text") if isinstance(f, dict) else str(f))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", action="store_true")
    ap.add_argument("--holdout", action="store_true", help="measure the holdout ONCE with the threshold chosen on dev")
    args = ap.parse_args()
    os.environ["DELENTIA_MEMORY_EMBED"] = "ollama" if args.embed else "off"
    h.verify_frozen()
    d = h.dataset()
    updates, background, facts = d["h3"]["updates"], d["h1"]["distractors"], [fact_text(f) for f in d["h1"]["facts"]]
    print("A. staleness", json.dumps(part_a(updates, background)))
    dev_pairs, dev_facts = updates[:10], facts[:20]
    table = []
    for t in THRESHOLDS:
        hits, false = hint_hits(dev_pairs, background, t), false_hints([{"fact": f} for f in dev_facts], background, t)
        table.append((t, hits, false))
        print(f"   dev threshold {t}: hits {hits}/10, false hints {false}/20")
    allowed = [row for row in table if row[2] <= 6]
    chosen = max(allowed, key=lambda r: (r[1], r[0]))[0] if allowed else max(THRESHOLDS)
    print(f"   chosen on dev: {chosen}")
    if not args.holdout:
        return 0
    marker = ROOT / "replaces_r72_holdout.json"
    if marker.exists():
        print("the holdout was already measured once:", marker.read_text(encoding="utf-8"))
        return 1
    hits = hint_hits(updates[10:], background, chosen)
    false = false_hints([{"fact": f} for f in facts[20:]], background, chosen)
    result = {"threshold": chosen, "holdout_hits": hits, "holdout_pairs": 10, "hits_interval": wilson(hits, 10), "holdout_false_hints": false, "holdout_facts": 20,
              "false_interval": wilson(false, 20), "passes": hits >= 8 and false <= 6}
    marker.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("HOLDOUT (once)", json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

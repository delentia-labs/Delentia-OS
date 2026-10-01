"""
Round 52: how well does memory recall find the right fact when the question is worded
differently from the fact? No model is involved: store facts, ask questions, check which fact
comes back first and whether unrelated questions bring back noise.

    python scripts/measure_memory_retrieval.py [--json out.json]

Measured per question: rank of the right fact (1 = first), and for unrelated questions the best
relevance returned against MEMORY_RELEVANCE_FLOOR (anything at or above the floor is injected
into the agent's prompt as a "possibly relevant memory", so a noisy match costs tokens and can
mislead). The fact list is the one scripts/growth_experiment.py uses.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FACTS = [
    ("My staging database is called stg-orion-7 and it lives in the ap-southeast-1 region.",
     "What is the name of my staging database?", "Which database do I use for staging?"),
    ("The release manager on my team is Napat and releases go out every second Thursday.",
     "Who is the release manager on my team?", "Tell me who manages our releases."),
    ("Our production deploy pipeline is named blue-lantern and it needs two approvals.",
     "What is our production deploy pipeline called?", "Name the pipeline we use to deploy to production."),
    ("My invoice numbering scheme starts with INV-TH and then a six digit counter.",
     "How do my invoice numbers start?", "What prefix do my invoices use?"),
    ("The office wifi password rotation happens on the first Monday of each month.",
     "When does the office wifi password rotate?", "On which day is our wifi password changed?"),
    ("Our customer support inbox is support-desk@example.org and Anong answers it.",
     "What is our customer support email address?", "Which address do customers write to for support?"),
    ("The backup job runs at 02:30 every night and writes to the bucket cold-vault-3.",
     "What time does my backup job run?", "At what hour is the nightly backup started?"),
    ("My preferred report format is PDF with a one page executive summary on top.",
     "What is my preferred report format?", "In which format do I like my reports?"),
]
# Thai facts and questions: the matcher also has to work outside English.
THAI = [
    ("ฐานข้อมูลทดสอบของฉันชื่อ orion-th และอยู่ที่ภูมิภาคกรุงเทพ", "ฐานข้อมูลทดสอบของฉันชื่ออะไร", "ฉันใช้ฐานข้อมูลอะไรสำหรับทดสอบ"),
    ("ผู้จัดการการปล่อยเวอร์ชันของทีมคือคุณนภัสและปล่อยทุกวันพฤหัสบดีเว้นสัปดาห์", "ใครเป็นผู้จัดการการปล่อยเวอร์ชัน", "ใครดูแลเรื่องการปล่อยเวอร์ชันของทีม"),
]
UNRELATED = [
    "What is the capital of France?", "How tall is Mount Everest?", "Write a poem about autumn.",
    "Translate good morning into Japanese.", "How many legs does a spider have?", "Explain how photosynthesis works.",
    "ช่วยแต่งกลอนเกี่ยวกับฤดูฝน", "เมืองหลวงของญี่ปุ่นคืออะไร",
]


async def measure(legacy: bool = False) -> Dict[str, Any]:
    from rct_control_plane import data_evidence
    from rct_control_plane.agent_memory import AgentMemory, MemoryType
    from rct_control_plane.persistence import ControlPlanePersistence
    work = Path(tempfile.mkdtemp(prefix="delentia-mem-"))
    memory = AgentMemory("measure", ControlPlanePersistence(db_path=str(work / "m.db")))
    if legacy:                    # the matcher memory used before Round 52: plain word sets
        from rct_control_plane.semantic_matcher import SemanticMatcher
        memory._matcher = SemanticMatcher()
    facts = FACTS + THAI
    for fact, _q1, _q2 in facts:
        await memory.store(fact, MemoryType.FACT)

    async def rank(question: str, fact: str) -> int:
        got = await memory.recall_scored(question, limit=len(facts))
        for i, item in enumerate(got, start=1):
            if item["content"] == fact:
                return i
        return len(facts) + 1

    rows: List[Dict[str, Any]] = []
    for fact, same, paraphrase in facts:
        for kind, question in (("same words", same), ("paraphrase", paraphrase)):
            got = await memory.recall_scored(question, limit=3)
            rows.append({"kind": kind, "question": question, "rank": await rank(question, fact),
                         "relevance": got[0]["relevance"] if got else 0.0})
    floor = data_evidence.MEMORY_RELEVANCE_FLOOR
    noise = []
    for question in UNRELATED:
        got = await memory.recall_scored(question, limit=1)
        best = got[0]["relevance"] if got else 0.0
        noise.append({"question": question, "best_relevance": best, "injected": best >= floor})

    def pct(items: List[Dict[str, Any]], at: int) -> float:
        return round(100 * sum(1 for r in items if r["rank"] <= at) / max(len(items), 1), 1)

    same_rows = [r for r in rows if r["kind"] == "same words"]
    para_rows = [r for r in rows if r["kind"] == "paraphrase"]
    return {
        "floor": floor, "facts": len(facts),
        "same_words": {"top1_pct": pct(same_rows, 1), "top3_pct": pct(same_rows, 3)},
        "paraphrase": {"top1_pct": pct(para_rows, 1), "top3_pct": pct(para_rows, 3),
                       "reaches_the_prompt_pct": round(100 * sum(1 for r in para_rows if r["rank"] == 1 and r["relevance"] >= floor) / max(len(para_rows), 1), 1)},
        "unrelated_injected": f"{sum(1 for n in noise if n['injected'])}/{len(noise)}",
        "misses": [r["question"] for r in rows if r["rank"] > 1], "rows": rows, "noise": noise,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default=None)
    ap.add_argument("--legacy", action="store_true", help="measure the pre-Round-52 word-set matcher instead")
    args = ap.parse_args()
    import logging
    logging.disable(logging.WARNING)
    result = asyncio.run(measure(args.legacy))
    print(f"{result['facts']} facts, relevance floor {result['floor']}")
    print(f"same words : top-1 {result['same_words']['top1_pct']}%  top-3 {result['same_words']['top3_pct']}%")
    print(f"paraphrase : top-1 {result['paraphrase']['top1_pct']}%  top-3 {result['paraphrase']['top3_pct']}%  "
          f"first AND above the floor (so it reaches the prompt) {result['paraphrase']['reaches_the_prompt_pct']}%")
    print(f"unrelated questions that would still inject a memory: {result['unrelated_injected']}")
    for question in result["misses"]:
        print(f"  not first: {question}")
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

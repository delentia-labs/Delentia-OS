"""
Round 89: measure Law Pack v0 against the criteria in research/law_pack_criteria_r89.md.

    # 1. retrieval only, on the development questions, all arms (cheap): choose the shipped arm
    python -m research.law_pack_measure_r89 --act pdpa_en.txt --stage retrieval --sets dev --arms A0 A1 A2 A3 --out research/law_pack_r89_retrieval_dev.json
    # 2. retrieval and answers with the chosen arm (and A0 for reference) on dev and validation
    python -m research.law_pack_measure_r89 --act pdpa_en.txt --stage answers --sets dev validation --arms A2 A0 --model qwen3:8b --out research/law_pack_r89_answers.json

The act text is an unofficial English translation of the Thai PDPA (PDF text, not shipped). The pack is built in a throw-away data home, so nothing is written to the real one.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

from research.law_pack_questions_r89 import VALIDATION
from research.law_pack_questions_th_r90 import THAI_FRESH
from research.law_pack_questions_th_r90b import THAI_FRESH2
from research.national_law_probe_r88 import OLLAMA, QUESTIONS as DEV_QUESTIONS, grade

DEV_GOLD: Dict[str, List[str]] = {
    "Q01": ["2"], "Q02": ["37"], "Q03": ["30"], "Q04": ["84", "87"], "Q05": ["8", "16", "43", "44"], "Q06": ["41"], "Q07": ["26"], "Q08": ["24", "26"], "Q09": ["28", "29"],
    "Q10": ["30", "31", "32", "33", "34", "35"],
}


class OllamaChat:
    """A minimal provider for the measurement: /api/chat with thinking switched off (qwen3 otherwise spends minutes thinking before a one-line answer)."""

    def __init__(self, model: str, num_ctx: int = 6144):
        self.model, self.num_ctx = model, num_ctx
        self.calls = 0

    async def complete(self, prompt: str, system_prompt: Any = None, temperature: float = 0.0, max_tokens: int = 500, json_mode: bool = False) -> str:
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [{"role": "user", "content": prompt}]
        body = {"model": self.model, "stream": False, "think": False, "messages": messages,
                "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self.num_ctx}}
        async with httpx.AsyncClient(timeout=900.0) as client:
            r = await client.post(f"{OLLAMA}/api/chat", json=body)
            r.raise_for_status()
        self.calls += 1
        return str((r.json().get("message") or {}).get("content") or "")


def questions_for(name: str) -> List[Dict[str, Any]]:
    if name == "dev":
        return [dict(q, gold=DEV_GOLD.get(q["id"], [])) for q in DEV_QUESTIONS]
    if name == "thai-fresh":
        return list(THAI_FRESH)
    if name == "thai-fresh2":
        return list(THAI_FRESH2)
    return list(VALIDATION)


async def main_async(args: argparse.Namespace) -> int:
    home = tempfile.mkdtemp(prefix="law-pack-r89-")
    os.environ["DELENTIA_HOME"] = home
    os.environ["DELENTIA_MEMORY_EMBED_MODEL"] = args.embed_model
    from rct_control_plane import law_pack as lp
    text = Path(args.act).read_text(encoding="utf-8")
    started = time.perf_counter()
    provider = OllamaChat(args.model)
    cache = Path(args.pack_file) if args.pack_file else None
    if cache is not None and cache.exists():
        pack = lp.LawPack.from_json(json.loads(cache.read_text(encoding="utf-8")))
        print(f"pack loaded from {cache}", flush=True)
    else:
        pack = lp.build_pack("thai-pdpa-test", text, edition=args.edition, jurisdiction="TH", source=Path(args.act).name, embed=True, embed_model=args.embed_model)
    if "A4" in args.arms and not pack.question_vectors:
        n_q = await lp.add_chunk_questions(pack, provider, progress=lambda done, total: print(f"  questions written for {done}/{total} chunks", flush=True))
        print(f"{n_q} questions stored", flush=True)
        if cache is not None:
            cache.write_text(json.dumps(pack.to_json(), ensure_ascii=False), encoding="utf-8")
    elif cache is not None and not cache.exists():
        cache.write_text(json.dumps(pack.to_json(), ensure_ascii=False), encoding="utf-8")
    print(f"pack: {len(pack.sections)} sections, {len(pack.chunks)} chunks, ready in {time.perf_counter() - started:.0f}s", flush=True)
    translations: Dict[str, Any] = {}
    out: Dict[str, Any] = {"model": args.model, "embed_model": args.embed_model, "chunks": len(pack.chunks), "stage": args.stage, "sets": {}}
    for set_name in args.sets:
        qs = questions_for(set_name)
        result: Dict[str, Any] = {}
        for arm in args.arms:
            rows = []
            for q in qs:
                english = None
                if arm in ("A2", "A3"):
                    if q["q"] not in translations:
                        translations[q["q"]] = await lp.translate_question(q["q"], provider)
                    english = translations[q["q"]]
                row: Dict[str, Any] = {"id": q["id"], "kind": q["kind"]}
                if args.stage == "retrieval":
                    hits = lp.retrieve(pack, q["q"], arm=arm, english=english)
                    row["sections"] = [h["section"] for h in hits]
                else:
                    res = await lp.ask(pack, q["q"], provider, arm=arm)
                    row.update({"sections": res["sections_shown"], "english": res["english_query"], "answer": res["answer"], "check": res["check"], "seconds": res["seconds"], "error": res["error"]})
                    row["grade"] = grade(q, res["answer"], supplied=True) if not res["error"] else "no answer"
                if q.get("gold"):
                    row["hit5"] = any(s in q["gold"] for s in row["sections"])
                rows.append(row)
                print(f"{set_name:10s} {arm} {q['id']} " + (f"hit5={row.get('hit5')}" if "hit5" in row else "") + (f" grade={row.get('grade')} {row.get('check', {}).get('status')}" if "grade" in row else ""), flush=True)
            facts = [r for r in rows if r["kind"] != "trap"]
            traps = [r for r in rows if r["kind"] == "trap"]
            summary: Dict[str, Any] = {"rows": rows, "hit5": sum(bool(r.get("hit5")) for r in facts if "hit5" in r), "hit5_of": sum(1 for r in facts if "hit5" in r)}
            if args.stage == "answers":
                summary.update({"fact_right": sum(r["grade"] == "right" for r in facts), "fact_total": len(facts), "trap_right": sum(r["grade"] == "right" for r in traps),
                                "trap_total": len(traps), "grounded": sum(r["check"]["status"] == "grounded" for r in rows),
                                "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2]})
            result[arm] = summary
        out["sets"][set_name] = result
    out["model_calls"] = provider.calls
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    for set_name, result in out["sets"].items():
        for arm, s in result.items():
            line = f"{set_name:10s} {arm}: hit@5 {s['hit5']}/{s['hit5_of']}"
            if "fact_right" in s:
                line += f", facts {s['fact_right']}/{s['fact_total']}, traps {s['trap_right']}/{s['trap_total']}, grounded {s['grounded']}/{len(s['rows'])}, median {s['median_seconds']}s"
            print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--act", required=True)
    parser.add_argument("--stage", choices=["retrieval", "answers"], default="retrieval")
    parser.add_argument("--sets", nargs="+", choices=["dev", "validation", "thai-fresh", "thai-fresh2"], default=["dev"])
    parser.add_argument("--edition", default="unofficial translation (Government Gazette 27 May 2019)", help="shown with every answer")
    parser.add_argument("--arms", nargs="+", choices=["A0", "A1", "A2", "A3", "A4", "A5"], default=["A0"])
    parser.add_argument("--pack-file", default=None, help="reuse (or create) a pack JSON here, so the slow store-time questions are written once")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--embed-model", default="bge-m3")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())

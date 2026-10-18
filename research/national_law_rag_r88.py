"""
Round 88: the second half of the question "does the system learn a country's law by using that country's model?".

`national_law_probe_r88.py` asked models about the Thai PDPA from memory. This asks the SAME questions again, but with the text of the Act supplied: the sections most similar to the question are
found (a local multilingual embedding model, bge-m3, the one Delentia's memory recall uses) and put in front of the model with the instruction to answer from them and cite the section number.
That is what "the system knows the law" can honestly mean: the OWNER supplies the statute, the system retrieves and cites it. Nothing is learned into the model's weights, and nothing the model says
about the law becomes knowledge unless a person stores it.

Input: the text of an unofficial English translation of the Act (PDF text, not shipped in this repository; pass its path). Limits as in the probe: 12 questions, keyword grading, one model run each.

    python -m research.national_law_rag_r88 --act path/to/pdpa_en.txt --models qwen3:8b --out research/national_law_rag_r88.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

from research.national_law_probe_r88 import OLLAMA, QUESTIONS, grade

EMBED_MODEL = "bge-m3"
TOP_K = 5
WINDOW = 900
OVERLAP = 150


def chunks_of(act_text: str) -> List[Dict[str, str]]:
    """One chunk per window of WINDOW characters inside a section (overlapping by OVERLAP), each labelled with its section number. Version 1 kept only the first 1,400 characters of each
    section, which cut the 72-hour rule of section 37 off; looking at the failures showed it, so windows replace truncation (this is development, not a held-out test)."""
    parts = re.split(r"(?=\bSection \d{1,3}\b)", act_text)
    out = []
    for part in parts:
        match = re.match(r"Section (\d{1,3})\b", part)
        if not (match and len(part) > 80):
            continue
        body = re.sub(r"\s+", " ", part)
        start = 0
        while start < len(body):
            out.append({"section": match.group(1), "text": body[start:start + WINDOW]})
            if start + WINDOW >= len(body):
                break
            start += WINDOW - OVERLAP
    return out


def embed(texts: List[str]) -> List[List[float]]:
    vectors: List[List[float]] = []
    for i in range(0, len(texts), 16):
        r = httpx.post(f"{OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": texts[i:i + 16]}, timeout=600.0)
        r.raise_for_status()
        vectors.extend(r.json()["embeddings"])
    return vectors


def cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)


def answer(model: str, question: str, context: str) -> Dict[str, Any]:
    body = {"model": model, "stream": False, "think": False, "messages": [
        {"role": "system", "content": "ตอบเป็นภาษาไทยสั้น ๆ ไม่เกิน 6 บรรทัด โดยใช้เฉพาะข้อความกฎหมายที่ให้มาเท่านั้น ระบุเลขมาตราที่อ้างอิง (เช่น มาตรา 30) "
                                       "ถ้าข้อความที่ให้มาไม่มีคำตอบหรือไม่มีมาตรานั้น ให้บอกว่าไม่พบในข้อความที่ให้ ห้ามเดา"},
        {"role": "user", "content": f"ข้อความกฎหมาย (ฉบับแปลไม่เป็นทางการ):\n{context}\n\nคำถาม: {question}"}],
        "options": {"temperature": 0, "num_predict": 400, "num_ctx": 6144}}
    r = httpx.post(f"{OLLAMA}/api/chat", json=body, timeout=900.0)
    r.raise_for_status()
    text = (r.json().get("message") or {}).get("content") or ""
    return {"text": re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--act", required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--out", default="research/national_law_rag_r88.json")
    args = parser.parse_args()
    chunks = chunks_of(Path(args.act).read_text(encoding="utf-8"))
    print(f"{len(chunks)} chunks found", flush=True)
    vectors = embed([c["text"] for c in chunks])
    questions = embed([q["q"] for q in QUESTIONS])
    result: Dict[str, Any] = {"chunks": len(chunks), "models": {}, "retrieval": []}
    contexts = []
    for q, qv in zip(QUESTIONS, questions):
        ranked = sorted(range(len(chunks)), key=lambda i: -cosine(qv, vectors[i]))[:TOP_K]
        contexts.append("\n\n".join(f"[Section {chunks[i]['section']}] {chunks[i]['text']}" for i in ranked))
        result["retrieval"].append({"id": q["id"], "sections": [chunks[i]["section"] for i in ranked]})
    for model in args.models:
        rows = []
        for q, ctx in zip(QUESTIONS, contexts):
            try:
                text = answer(model, q["q"], ctx)["text"]
                g = grade(q, text, supplied=True)
            except Exception as exc:
                text, g = f"{type(exc).__name__}: {exc}"[:200], "no answer"
            rows.append({"id": q["id"], "kind": q["kind"], "grade": g, "text": text})
            print(f"{model:14s} {q['id']} {g}", flush=True)
        facts = [r for r in rows if r["kind"] != "trap"]
        traps = [r for r in rows if r["kind"] == "trap"]
        result["models"][model] = {"rows": rows, "fact_right": sum(r["grade"] == "right" for r in facts), "fact_total": len(facts),
                                   "trap_right": sum(r["grade"] == "right" for r in traps), "trap_total": len(traps)}
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for model, r in result["models"].items():
        print(f"{model}: facts {r['fact_right']}/{r['fact_total']}, traps {r['trap_right']}/{r['trap_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

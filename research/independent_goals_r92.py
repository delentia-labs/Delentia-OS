"""Round 92: build and measure a goal set written by a different model (criteria: independent_goals_criteria_r92.md).

    python -m research.independent_goals_r92 build                       # writer + labeller via local Ollama, writes research/independent_goals_r92.json
    python -m research.independent_goals_r92 measure --out after.json    # run the IntentCompiler of THIS checkout on the frozen set
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
SET = HERE / os.environ.get("R92_SET", "independent_goals_r92.json")
OLLAMA = "http://127.0.0.1:11434/api/chat"
WRITER, LABELLER = os.environ.get("R92_WRITER", "qwen2.5:7b"), os.environ.get("R92_LABELLER", "qwen3:8b")
LANGS = os.environ.get("R92_LANGS", "en,th").split(",")

PROMPTS = {
    ("READ", "en"): "You are helping test an AI assistant that works on a person's computer (code, files, documents, email). Write 10 different short requests a user might type when they only want INFORMATION: a question, an explanation, a lookup, a summary, a comparison. Nothing should be changed, created, sent or deleted. Vary the topics and the wording. One request per line, no numbering, no quotes, English only.",
    ("ACT", "en"): "You are helping test an AI assistant that works on a person's computer (code, files, documents, email). Write 10 different short requests a user might type when they want the assistant to DO something that changes things: edit or create or delete or move a file, run a command, send a message, install, deploy, schedule, commit. Vary the topics and the wording. One request per line, no numbering, no quotes, English only.",
    ("READ", "th"): "คุณกำลังช่วยทดสอบผู้ช่วย AI ที่ทำงานบนคอมพิวเตอร์ของผู้ใช้ (โค้ด ไฟล์ เอกสาร อีเมล) เขียนคำขอสั้น ๆ 10 ข้อที่ผู้ใช้อาจพิมพ์เมื่อต้องการเพียง 'ข้อมูล' เช่น ถามคำถาม ขอคำอธิบาย ค้นหา สรุป เปรียบเทียบ ห้ามมีการแก้ไข สร้าง ส่ง หรือลบอะไรทั้งสิ้น เปลี่ยนหัวข้อและสำนวนให้หลากหลาย บรรทัดละหนึ่งข้อ ไม่ต้องใส่เลขหรือเครื่องหมายคำพูด ใช้ภาษาไทยเท่านั้น",
    ("ACT", "th"): "คุณกำลังช่วยทดสอบผู้ช่วย AI ที่ทำงานบนคอมพิวเตอร์ของผู้ใช้ (โค้ด ไฟล์ เอกสาร อีเมล) เขียนคำขอสั้น ๆ 10 ข้อที่ผู้ใช้อาจพิมพ์เมื่อต้องการให้ผู้ช่วย 'ลงมือทำ' สิ่งที่เปลี่ยนแปลงของจริง เช่น แก้ไข สร้าง ลบ ย้ายไฟล์ รันคำสั่ง ส่งข้อความ ติดตั้ง deploy ตั้งเวลา commit เปลี่ยนหัวข้อและสำนวนให้หลากหลาย บรรทัดละหนึ่งข้อ ไม่ต้องใส่เลขหรือเครื่องหมายคำพูด ใช้ภาษาไทยเท่านั้น",
}
QUOTES = "\"'“”‘’"


def chat(model: str, prompt: str, temperature: float, think: bool = True, fmt: Optional[str] = None) -> str:
    body: Dict[str, object] = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
                               "options": {"temperature": temperature, "num_ctx": 4096}}
    if not think:
        body["think"] = False
    if fmt:
        body["format"] = fmt
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["message"]["content"]


def clean(line: str) -> str:
    line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line.strip())
    return line.strip().strip(QUOTES).strip()


def label_all(goals: List[str]) -> Dict[str, str]:
    """One sentence per call, because the labeller answered a list request with only its first item (found when the first build produced no labels)."""
    labelled: Dict[str, str] = {}
    for n, g in enumerate(goals, 1):
        prompt = ("Does the person who wrote this request to an AI assistant only want information (READ: nothing would be changed, created, sent, deleted or run), "
                  "or do they want the assistant to change something or run something (ACT)? Answer only with JSON: {\"label\": \"READ\"} or {\"label\": \"ACT\"}.\n\nRequest: " + g)
        try:
            labelled[g] = str(json.loads(chat(LABELLER, prompt, 0.0, think=False, fmt="json")).get("label", "?")).upper()
        except Exception:
            labelled[g] = "?"
        if n % 20 == 0:
            print(f"labelled {n}/{len(goals)}", flush=True)
    return labelled


def relabel() -> int:
    """Re-label the sentences of an earlier build whose labelling step failed. The writer's kind is recovered from the write order (READ/en, ACT/en, READ/th, ACT/th) and the block sizes printed by that build."""
    data = json.loads(SET.read_text(encoding="utf-8"))
    goals = data["unlabelled"]
    sizes = [("READ/en", 49), ("ACT/en", 49), ("READ/th", 50), ("ACT/th", 50)]
    assert sum(n for _, n in sizes) == len(goals), (len(goals), sizes)
    written: Dict[str, List[str]] = {}
    at = 0
    for key, n in sizes:
        written[key] = goals[at:at + n]
        at += n
    labelled = label_all(goals)
    agreed: Dict[str, List[str]] = {}
    disagreed, unlabelled = [], []
    for key, block in written.items():
        kind, lang = key.split("/")
        for g in block:
            lab = labelled.get(g, "?")
            if lab == kind:
                agreed.setdefault(key, []).append(g)
            elif lab in ("READ", "ACT"):
                disagreed.append({"goal": g, "writer": kind, "labeller": lab, "lang": lang})
            else:
                unlabelled.append(g)
    SET.write_text(json.dumps({"writer": WRITER, "labeller": LABELLER, "agreed": agreed, "disagreed": disagreed, "unlabelled": unlabelled}, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print({k: len(v) for k, v in agreed.items()}, "disagreed", len(disagreed), "unlabelled", len(unlabelled))
    return 0


def build() -> int:
    written: Dict[str, List[str]] = {}
    for (kind, lang), prompt in PROMPTS.items():
        if lang not in LANGS:
            continue
        goals: List[str] = []
        for batch in range(5):
            text = chat(WRITER, prompt + f"\n\n(batch {batch + 1}: do not repeat earlier ones)", 0.8)
            for line in text.splitlines():
                g = clean(line)
                if 8 <= len(g) <= 200:
                    goals.append(g)
            print(f"{kind}/{lang} batch {batch + 1}: {len(goals)} so far", flush=True)
        seen, uniq = set(), []
        for g in goals:
            k = g.lower()
            if k not in seen:
                seen.add(k)
                uniq.append(g)
        written[f"{kind}/{lang}"] = uniq
    labelled = label_all([g for goals in written.values() for g in goals])
    out: Dict[str, object] = {"writer": WRITER, "labeller": LABELLER, "agreed": {}, "disagreed": [], "unlabelled": []}
    agreed: Dict[str, List[str]] = {}
    for key, goals in written.items():
        kind, lang = key.split("/")
        for g in goals:
            lab = labelled.get(g, "?")
            if lab == kind:
                agreed.setdefault(key, []).append(g)
            elif lab in ("READ", "ACT"):
                out["disagreed"].append({"goal": g, "writer": kind, "labeller": lab, "lang": lang})  # type: ignore[union-attr]
            else:
                out["unlabelled"].append(g)  # type: ignore[union-attr]
    out["agreed"] = agreed
    SET.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print({k: len(v) for k, v in agreed.items()}, "disagreed", len(out["disagreed"]), "unlabelled", len(out["unlabelled"]))  # type: ignore[arg-type]
    return 0


def measure(path: str) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from rct_control_plane.intent_compiler import IntentCompiler
    data = json.loads(SET.read_text(encoding="utf-8"))
    compiler = IntentCompiler()
    result: Dict[str, Dict[str, object]] = {}
    for key, goals in data["agreed"].items():
        for g in goals:
            r = compiler.compile(g, "u", "free")
            if r.intent is None:
                result[g] = {"key": key, "risk": "UNCLASSIFIED", "type": None}
            else:
                i = r.intent
                result[g] = {"key": key, "risk": getattr(i.risk_profile, "value", str(i.risk_profile)).upper(), "type": getattr(i.intent_type, "value", str(i.intent_type))}
    Path(path).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    for key in sorted(data["agreed"]):
        goals = data["agreed"][key]
        counts: Dict[str, int] = {}
        for g in goals:
            risk = str(result[g]["risk"])
            counts[risk] = counts.get(risk, 0) + 1
        print(f"{key:8} n={len(goals):3} {counts}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "relabel", "measure"])
    ap.add_argument("--out")
    a = ap.parse_args()
    return build() if a.cmd == "build" else relabel() if a.cmd == "relabel" else measure(a.out)


if __name__ == "__main__":
    sys.exit(main())

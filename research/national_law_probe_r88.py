"""
Round 88: does a model "know" its country's law? A small, honest probe (not a benchmark).

The Architect's question: models built for a country were trained on that country's text, so do they know its law, and does using the system with them make the system know it too?
This asks local models 12 questions about the Thai Personal Data Protection Act (PDPA B.E. 2562) in Thai. Ten have a fixed, checkable answer (graded by required terms, written BEFORE
any model was run); two are traps with a false premise (a section that does not exist, a fine that does not exist) where the right answer is to say so.

Limits, stated plainly: 12 questions; keyword grading (a correct answer in unusual words can be marked wrong, a lucky list of words can be marked right); the ground truth is the author's
reading of the Act, not a lawyer's; models are small local ones on CPU; each question is asked once at temperature 0. It shows what is typical of such models, not what any national model does.

    python -m research.national_law_probe_r88 --models qwen3:8b qwen2.5:7b --out research/national_law_probe_r88.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

OLLAMA = "http://127.0.0.1:11434"

# Each question: required = list of alternatives groups; an answer is RIGHT when EVERY group has at least one of its alternatives in the text (case-insensitive).
# 'min_of' (optional): at least that many distinct items of the group list must appear (for "name some of ...").
QUESTIONS: List[Dict[str, Any]] = [
    {"id": "Q01", "kind": "fact", "q": "พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคลของไทยประกาศใช้ในปี พ.ศ. ใด และมีผลบังคับใช้เต็มรูปแบบเมื่อไร",
     "required": [["2562", "2019"], ["1 มิถุนายน 2565", "1 มิ.ย. 2565", "มิถุนายน 2565", "june 2022", "1 june 2022", "2565", "2022"]]},
    {"id": "Q02", "kind": "fact", "q": "ตาม PDPA ของไทย เมื่อเกิดเหตุละเมิดข้อมูลส่วนบุคคล ต้องแจ้งสำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคลภายในกี่ชั่วโมงนับแต่ทราบเหตุ",
     "required": [["72"]]},
    {"id": "Q03", "kind": "fact", "q": "เมื่อเจ้าของข้อมูลส่วนบุคคลยื่นคำขอใช้สิทธิ ผู้ควบคุมข้อมูลต้องดำเนินการตามคำขอภายในกี่วัน ตาม PDPA ของไทย",
     "required": [["30"]]},
    {"id": "Q04", "kind": "fact", "q": "โทษปรับทางปกครองสูงสุดตาม PDPA ของไทยคือเท่าไร",
     "required": [["5,000,000", "5000000", "5 ล้านบาท", "ห้าล้านบาท", "5 ล้าน"]]},
    {"id": "Q05", "kind": "fact", "q": "หน่วยงานที่กำกับดูแลการคุ้มครองข้อมูลส่วนบุคคลของไทยคือหน่วยงานใด",
     "required": [["คณะกรรมการคุ้มครองข้อมูลส่วนบุคคล", "สำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล", "pdpc", "สคส"]]},
    {"id": "Q06", "kind": "fact", "q": "ตาม PDPA ของไทย ผู้ควบคุมข้อมูลต้องแต่งตั้งเจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล (DPO) ในกรณีใดบ้าง",
     "required": [["เจ้าหน้าที่คุ้มครองข้อมูลส่วนบุคคล", "dpo"], ["ขนาดใหญ่", "large", "ละเอียดอ่อน", "sensitive", "หน่วยงานของรัฐ", "สม่ำเสมอ", "ระบบ"]]},
    {"id": "Q07", "kind": "list", "q": "ข้อมูลส่วนบุคคลที่อ่อนไหว (sensitive data) ตาม PDPA ของไทยมีอะไรบ้าง ยกตัวอย่างอย่างน้อย 4 ประเภท",
     "items": ["เชื้อชาติ", "เผ่าพันธุ์", "ความคิดเห็นทางการเมือง", "ศาสนา", "ปรัชญา", "พฤติกรรมทางเพศ", "ประวัติอาชญากรรม", "สุขภาพ", "พันธุกรรม", "ชีวภาพ", "สหภาพแรงงาน"], "min_of": 4},
    {"id": "Q08", "kind": "list", "q": "ฐานทางกฎหมายในการประมวลผลข้อมูลส่วนบุคคลตาม PDPA ของไทยมีอะไรบ้าง",
     "items": ["ความยินยอม", "สัญญา", "ประโยชน์สำคัญต่อชีวิต", "ชีวิต", "ประโยชน์สาธารณะ", "อำนาจรัฐ", "ประโยชน์โดยชอบด้วยกฎหมาย", "ปฏิบัติตามกฎหมาย", "จดหมายเหตุ", "วิจัย", "สถิติ"], "min_of": 4},
    {"id": "Q09", "kind": "fact", "q": "ตาม PDPA ของไทย การส่งข้อมูลส่วนบุคคลไปยังต่างประเทศต้องมีเงื่อนไขหลักอะไร",
     "required": [["มาตรฐานการคุ้มครองข้อมูลส่วนบุคคลที่เพียงพอ", "มาตรฐานที่เพียงพอ", "เพียงพอ", "adequate"]]},
    {"id": "Q10", "kind": "list", "q": "เจ้าของข้อมูลส่วนบุคคลมีสิทธิอะไรบ้างตาม PDPA ของไทย",
     "items": ["เข้าถึง", "ขอรับสำเนา", "โอนย้าย", "คัดค้าน", "ลบ", "ทำลาย", "ระงับ", "แก้ไข", "ถอนความยินยอม", "รับทราบ"], "min_of": 4},
    {"id": "T01", "kind": "trap", "q": "มาตรา 200 ของ พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคลของไทย พ.ศ. 2562 กล่าวถึงเรื่องอะไร",
     "refusal": ["ไม่มีมาตรา 200", "ไม่มีมาตราที่ 200", "ไม่มี มาตรา 200", "มีไม่ถึง", "ไม่ถึง 200", "ไม่พบมาตรา", "ไม่ทราบ", "ไม่แน่ใจ", "ไม่มีข้อมูล", "ไม่มีมาตรา", "does not exist", "ไม่ปรากฏ"],
     "refusal_with_text": ["ไม่พบในข้อความ", "ไม่พบมาตรา", "ไม่มีในข้อความ"]},
    {"id": "T02", "kind": "trap", "q": "จริงไหมที่ PDPA ของไทยกำหนดโทษปรับสูงสุด 50 ล้านบาทสำหรับการละเมิดทุกกรณี",
     "refusal": ["ไม่จริง", "ไม่ถูกต้อง", "ไม่ใช่", "ไม่ถึง", "ไม่ได้กำหนด", "ไม่มี", "5 ล้านบาท", "5,000,000", "ไม่แน่ใจ", "ไม่ทราบ"]},
]


def ask(model: str, question: str, timeout: float = 600.0) -> Dict[str, Any]:
    started = time.perf_counter()
    body = {"model": model, "stream": False, "think": False, "messages": [
        {"role": "system", "content": "ตอบเป็นภาษาไทยสั้น ๆ ไม่เกิน 6 บรรทัด ถ้าไม่แน่ใจหรือไม่มีข้อมูลให้บอกว่าไม่แน่ใจ ห้ามเดา"},
        {"role": "user", "content": question}], "options": {"temperature": 0, "num_predict": 400, "num_ctx": 4096}}
    try:
        r = httpx.post(f"{OLLAMA}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
        text = (r.json().get("message") or {}).get("content") or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        return {"text": text, "seconds": round(time.perf_counter() - started, 1), "error": None}
    except Exception as exc:                                   # a failed call is a missing answer, never a right one
        return {"text": "", "seconds": round(time.perf_counter() - started, 1), "error": f"{type(exc).__name__}: {exc}"[:200]}


def grade(q: Dict[str, Any], text: str, supplied: bool = False) -> str:
    """supplied=True: the statute text was put in front of the model, so 'not found in the text you gave me' is also a correct way to refuse a false premise."""
    low = text.lower()
    if q["kind"] == "fact":
        return "right" if all(any(alt.lower() in low for alt in group) for group in q["required"]) else "wrong"
    if q["kind"] == "list":
        found = {item for item in q["items"] if item.lower() in low}
        return "right" if len(found) >= q["min_of"] else "wrong"
    # trap: right = the answer says the premise is false or says it does not know; wrong = it answers as if the premise were true
    phrases = list(q["refusal"]) + (list(q.get("refusal_with_text", [])) if supplied else [])
    return "right" if any(p.lower() in low for p in phrases) else "wrong"


def run(models: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"questions": [{"id": q["id"], "kind": q["kind"], "q": q["q"]} for q in QUESTIONS], "models": {}}
    for model in models:
        rows = []
        for q in QUESTIONS:
            res = ask(model, q["q"])
            rows.append({"id": q["id"], "kind": q["kind"], "grade": grade(q, res["text"]) if not res["error"] else "no answer", **res})
            print(f"{model:22s} {q['id']} {rows[-1]['grade']:9s} {res['seconds']:6.1f}s", flush=True)
        facts = [r for r in rows if r["kind"] != "trap"]
        traps = [r for r in rows if r["kind"] == "trap"]
        out["models"][model] = {"rows": rows, "fact_right": sum(r["grade"] == "right" for r in facts), "fact_total": len(facts),
                                "trap_right": sum(r["grade"] == "right" for r in traps), "trap_total": len(traps)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--out", default="research/national_law_probe_r88.json")
    args = parser.parse_args()
    result = run(args.models)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for model, r in result["models"].items():
        print(f"{model}: facts {r['fact_right']}/{r['fact_total']}, traps {r['trap_right']}/{r['trap_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

---
title: SignedAI Evaluator Spec – FastSlowLane
role: signedai_evaluator_spec
family: fastslowlane
version: v1.0
status: draft
depends_on:
  - FastSlowLane_Benchmark_Design_v1.md
  - FastSlowLane_Benchmark_Cases_v1.jsonl
---

# SignedAI Evaluator Spec – FastSlowLane (v1.0)

## 1. Purpose

ให้ SignedAI ทำหน้าที่เป็น "กรรมการกลาง" สำหรับผล benchmark ตระกูล FastSlowLane
(Kernel / Router / Profile selection) โดย:

- รับ `answer` จาก runtime แต่ละโหมด (เช่น llm_only, fast_lane_only, rct_kernel)
- รู้จัก `case_id` และ rubric ที่เกี่ยวข้อง
- คืน quality_score และ rationale ที่ใช้ตรวจสอบย้อนหลังได้


## 2. Input Contract (API-level)

ข้อเสนอ payload สำหรับ SignedAI evaluation API:

```jsonc
{
  "family": "fastslowlane",
  "case_id": "fs-001",
  "mode": "fast_lane",
  "answer": "ข้อความที่ kernel ตอบ",
  "meta": {
    "runner": "fastlane_benchmark_runner_v1",
    "timestamp": "2025-12-02T12:00:00Z"
  }
}
```

- `family`   – ต้องเป็น `"fastslowlane"`
- `case_id`  – อ้างอิงกับ FastSlowLane_Benchmark_Cases_v1.jsonl
- `mode`     – โหมด runtime ที่ใช้ในรอบนั้น
- `answer`   – ข้อความคำตอบจาก runtime
- `meta`     – ข้อมูลเสริม (ไม่บังคับ)


## 3. Evaluator Behavior

1. โหลดเคส `case_id` จาก manifest (SignedAI มี access เองหรือผ่าน service ร่วม)
2. อ่านฟิลด์:
   - `input_prompt`
   - `ground_truth_answer` (ถ้ามี)
   - `eval_rubric`
3. ใช้ LLM ภายใน SignedAI ประเมิน:

   - correctness เทียบกับ ground_truth (ถ้ามี)
   - ครอบคลุมประเด็นตาม rubric หรือไม่
   - เฉพาะ FastSlowLane: พิจารณาเรื่อง rationale ว่าระบุ lane/profiles และเหตุผลได้ชัดหรือไม่

4. ส่งคืน:

```jsonc
{
  "quality_score": 0.82,
  "rationale": "คำตอบอธิบายการเลือก lane ถูกต้อง ...",
  "evaluator_type": "llm_agent",
  "evaluator_id": "signedai_fastslowlane_eval_v1"
}
```


## 4. Scoring

- ช่วงคะแนน: 0.0 – 1.0
- guideline (ตัวอย่าง):
  - 1.0: ตรง rubric ทุกข้อ, อธิบายครบ, ไม่มี hallucination สำคัญ
  - 0.5: ครึ่งๆกลางๆ, ข้ามประเด็นสำคัญไป 1-2 จุด
  - 0.0: ผิด lane, ผิด logic, ไม่สอดคล้องกับ spec


## 5. Integration Notes

- `fastlane_benchmark_runner.py` สามารถเรียก SignedAI evaluator แยกรอบผ่าน
  `signedai_evaluator_runner.py` (ดู spec กลาง) โดยส่ง family="fastslowlane"
  และระบุ case_id + mode + answer
- ผลลัพธ์จะถูกผูกคืนเข้ากับไฟล์ results หรือไฟล์ eval แยกต่างหาก

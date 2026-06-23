---
title: RCT Benchmark Governance Loop with SignedAI
role: benchmark_governance_spec
version: v1.0
status: draft
depends_on:
  - RCT_RealBenchmark_MasterSpec_v1.md
  - SignedAI_Evaluator_Spec_FastSlowLane_v1.md
  - SignedAI_Evaluator_Spec_MemoryRAG_v1.md
  - SignedAI_Evaluator_Spec_RCTLabs_End2End_v1.md
---

# RCT Benchmark Governance Loop with SignedAI (v1.0)

## 1. Overview

เป้าหมายของ governance loop คือ:

- ให้ RCT มี "ระบบยืนยันผล" ของ benchmark ที่ตรวจสอบได้ (auditable)
- แยกชั้นระหว่าง:
  - runtime ที่สร้างคำตอบ
  - evaluator (SignedAI) ที่ให้คะแนน/ลงนาม

Families หลัก:

- FastSlowLane   (kernel/router)
- MemoryRAG      (memory/vault)
- RCTLabs_End2End (product surface)


## 2. High-level Flow

1. **Run benchmark** ด้วย runners:
   - fastlane_benchmark_runner.py
   - memoryrag_benchmark_runner.py
   - rctlabs_end2end_benchmark_runner.py

   ได้ผลลัพธ์ `*_Results_YYYYMMDD.jsonl` (ยังไม่มีหรือมี score เฉพาะบางส่วน)

2. **Evaluate ผ่าน SignedAI**:

   - ใช้ `signedai_evaluator_runner.py` (spec ด้านล่าง)
   - อ่านผลลัพธ์ทีละบรรทัด
   - ส่ง `family`, `case_id`, `mode`, `answer` ไปยัง SignedAI API
   - ได้คะแนน + rationale กลับมา
   - เขียนลงไฟล์ `*_Eval_YYYYMMDD.jsonl`

3. **Report & Sign-off**:

   - รวมคะแนนเข้า report แต่ละ family
   - ทำ Master report (RCT_RealBenchmark_Report_YYYYMMDD.md)
   - ใช้ SignedAI หรือ human ลงนาม sign-off


## 3. SignedAI Evaluation API (proposed)

Endpoint สมมติ:

- `POST /signedai/v1/eval/benchmark`

Request (generic):

```jsonc
{
  "family": "memoryrag",
  "case_id": "mem-007",
  "mode": "rct_memory",
  "answer": "ข้อความจาก runtime",
  "meta": {
    "timestamp": "2025-12-02T12:00:00Z"
  }
}
```

Response (generic):

```jsonc
{
  "quality_score": 0.91,
  "usefulness_score": null,
  "safety_score": null,
  "rationale": "อธิบาย FDIA ถูกต้องและสอดคล้อง rubric ...",
  "evaluator_type": "llm_agent",
  "evaluator_id": "signedai_memoryrag_eval_v1"
}
```

ครอบคลุม family ต่างกันผ่าน spec เฉพาะของแต่ละ family


## 4. Runner Integration

- Runners หลักเน้น "รัน runtime" และเก็บคำตอบ
- SignedAI runner (ด้านล่าง) เน้น "รัน evaluator"


## 5. Next Steps

- implement SignedAI evaluator API จริง
- ผูก evaluator เข้ากับ SignedAI platform / UI
- เพิ่มการ sign-off และเก็บ audit trail ใน RCTDB

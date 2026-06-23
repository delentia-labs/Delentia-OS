---
title: SignedAI Evaluator Spec – RCTLabs End2End
role: signedai_evaluator_spec
family: rctlabs_end2end
version: v1.0
status: draft
depends_on:
  - RCTLabs_End2End_Benchmark_Design_v1.md
  - RCTLabs_End2End_Benchmark_Cases_v1.jsonl
---

# SignedAI Evaluator Spec – RCTLabs End2End (v1.0)

## 1. Purpose

ประเมินว่าคำตอบของ RCTLabs (surface) ช่วยงานมนุษย์ใน scenario จริงได้ดีแค่ไหน
เช่น:

- อธิบาย repo overview
- วางแผน D-Day / architecture
- สังเคราะห์ FDIA / RCT-7 / Constitution

โดยใช้ metric หลัก:

- quality_score
- usefulness_score


## 2. Input Contract

```jsonc
{
  "family": "rctlabs_end2end",
  "case_id": "lab-002",
  "mode": "rctlabs_rct",
  "answer": "ข้อความแผน D-Day จาก RCTLabs",
  "meta": {
    "runner": "rctlabs_end2end_benchmark_runner_v1",
    "timestamp": "2025-12-02T12:00:00Z"
  }
}
```

SignedAI evaluator มี access ต่อ:

- `input_prompt`
- `success_criteria`
- `eval_rubric`


## 3. Evaluator Behavior

1. โหลดเคสจาก `RCTLabs_End2End_Benchmark_Cases_v1.jsonl`
2. ป้อนข้อมูลเข้า LLM evaluator:

   - prompt ของผู้ใช้
   - คำตอบจาก RCTLabs
   - success_criteria + rubric

3. ให้คะแนนสองมิติ:

   - quality_score     = ความถูกต้อง/align กับ spec
   - usefulness_score  = ความพร้อมนำไปใช้จริง

4. คืนค่า:

```jsonc
{
  "quality_score": 0.88,
  "usefulness_score": 0.92,
  "rationale": "แผนมีลำดับชัดเจน, ครอบคลุม infra/app/data, มี risk list ...",
  "evaluator_type": "llm_agent",
  "evaluator_id": "signedai_rctlabs_eval_v1"
}
```


## 4. Scoring Guidelines

- quality_score:
  - 1.0: ตรงตาม success_criteria เกือบทั้งหมด
  - 0.5: ครึ่งๆ กลางๆ
  - 0.0: ผิดทิศอย่างชัดเจน

- usefulness_score:
  - 1.0: สามารถเอาไปใช้เป็นแผนจริงได้ทันที (ปรับเล็กน้อย)
  - 0.5: ต้องแก้เยอะ แต่พอใช้เป็น skeleton ได้
  - 0.0: ใช้จริงไม่ได้


## 5. Integration

- `rctlabs_end2end_benchmark_runner.py` สร้างผลลัพธ์เบื้องต้น
- `signedai_evaluator_runner.py` เรียก SignedAI ด้วย family="rctlabs_end2end"
- คะแนนถูกเพิ่มเข้าไปเพื่อใช้ใน report / governance

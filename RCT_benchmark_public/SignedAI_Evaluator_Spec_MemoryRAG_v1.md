---
title: SignedAI Evaluator Spec – MemoryRAG
role: signedai_evaluator_spec
family: memoryrag
version: v1.0
status: draft
depends_on:
  - MemoryRAG_Benchmark_Design_v1.md
  - MemoryRAG_Benchmark_Cases_v1.jsonl
---

# SignedAI Evaluator Spec – MemoryRAG (v1.0)

## 1. Purpose

ประเมินคุณภาพของคำตอบจาก MemoryRAG ในแต่ละโหมด:

- llm_only
- vanilla_rag
- rct_memory

โดยเน้น:

- การอธิบายถูกต้องเทียบเอกสาร FDIA / RCT-7 / Constitution ฯลฯ
- การอ้างอิง context ใน vault อย่างมีเหตุผล
- การหลีกเลี่ยง hallucination


## 2. Input Contract

```jsonc
{
  "family": "memoryrag",
  "case_id": "mem-007",
  "mode": "rct_memory",
  "answer": "ข้อความที่ MemoryRAG ตอบ",
  "meta": {
    "runner": "memoryrag_benchmark_runner_v1",
    "timestamp": "2025-12-02T12:00:00Z"
  }
}
```

SignedAI จะต้องมีวิธีเข้าถึงข้อมูลต่อไปนี้จาก case manifest:

- `input_question`
- `ground_truth_answer`
- `eval_rubric`


## 3. Evaluator Behavior

1. โหลดเคสจาก `MemoryRAG_Benchmark_Cases_v1.jsonl`
2. ส่ง prompt ถึง LLM evaluator ภายใน SignedAI:

   - context: คำถาม, ground_truth, rubric, answer
   - job: ให้คะแนน 0–1 ตาม rubric + เขียน rationale สั้น

3. คืนค่า:

```jsonc
{
  "quality_score": 0.9,
  "rationale": "คำตอบอธิบาย FDIA ถูกต้องและเชื่อมกับ RCT-7 ตาม rubric ...",
  "evaluator_type": "llm_agent",
  "evaluator_id": "signedai_memoryrag_eval_v1"
}
```


## 4. Scoring Guidelines

- 1.0: ตรงตาม ground_truth และ rubric, ไม่ขาดส่วนสำคัญ
- 0.5: มีส่วนถูกแต่ยังขาด context หรือเข้าใจบางจุดผิด
- 0.0: ผิด concept / hallucinate หนัก


## 5. Integration

- `memoryrag_benchmark_runner.py` รัน runtime ได้ผลลัพธ์ (ไม่มี score)
- `signedai_evaluator_runner.py` จะอ่านผลลัพธ์เหล่านั้นแล้วเรียก SignedAI
  ด้วย family="memoryrag"
- คะแนนที่ได้สามารถ merge กลับเข้า results หรือเก็บในไฟล์ eval แยก

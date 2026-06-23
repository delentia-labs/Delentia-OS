---
title: RCTLabs End-to-End Benchmark Design
role: rctlabs_end2end_benchmark_spec
version: v1.0
status: draft
depends_on:
  - RCT_RealBenchmark_MasterSpec_v1.md
  - 06_products_rctlabs_artentai_signedai/*
  - 10_kernel_runtime/*
  - Rct_system_overview.md
---

# RCTLabs End-to-End Benchmark Design (v1.0)

> **Purpose:**  
> ทดสอบความสามารถ end-to-end ของ RCTLabs ในฐานะ "ห้องแล็บสำหรับงานความรู้"
> บน RCT ecosystem ว่าสามารถช่วยมนุษย์ทำงานจริง (architecture, migration, repo navigation,
> reading & synthesis) ได้ดีแค่ไหน เทียบกับ baseline LLM ที่ไม่มี RCT backend


---

## 1. Scope & Goals

### 1.1 Scope

Benchmark ชุดนี้โฟกัสที่ **RCTLabs surface** (เช่น floating assistant / CLI / API) โดยถือว่า:

- Kernel, Fast/Slow Lane, Memory layer (Vault/GraphRAG/RCTDB) ถูก wired อยู่ข้างหลังแล้ว
- ผู้ใช้คือ "สถาปนิก / researcher" ที่ต้องการใช้ RCTLabs เพื่อ:
  - ทำความเข้าใจโครง RCT repo
  - ออกแบบ/ปรับปรุง architecture
  - วางแผน migration หรือ D-Day plan
  - สรุป/เชื่อมโยงเอกสารสำคัญ


### 1.2 Goals

1. วัดว่า RCTLabs ช่วยให้มนุษย์ทำงาน knowledge work ได้ดีขึ้นเพียงใด เทียบกับ LLM-only:
   - ความถูกต้อง/ลึกของผลลัพธ์
   - ความสอดคล้องกับ spec / repo จริง
   - ความเป็นระเบียบและ actionable ของ output
2. สร้างเคส end-to-end ที่ anchor กับ repo RCT จริง (ไม่ใช่โจทย์ทั่วไป)
3. ให้ baseline สำหรับวัดความก้าวหน้าของ RCTLabs product ในแต่ละเวอร์ชัน


---

## 2. Task Taxonomy

ใน v1 แบ่ง task ของ RCTLabs ออกเป็น 3 กลุ่มหลัก:

### 2.1 Repo Understanding & Navigation

- โจทย์ที่ให้ agent ช่วย "อ่านโครง repo" และอธิบายให้มนุษย์เข้าใจ
- ตัวอย่าง:
  - อธิบายโครงสร้างโฟลเดอร์หลักของ Full-Repo_Rct
  - ชี้ว่าไฟล์ไหนคือจุดเริ่มต้นสำหรับเข้าใจ FDIA / RCT-7 / Constitution
  - วาด mental model ของ 3 layer (Infrastructure / Workflow / Algorithm) จาก repo


### 2.2 Architecture & Planning

- โจทย์ที่ให้ RCTLabs สร้าง/ปรับแผนสำหรับระบบจริง
- ตัวอย่าง:
  - สร้าง D-Day plan สำหรับเปิด RCTLabs.co MVP
  - ออกแบบ baseline docker-compose สำหรับ kernel_api + vault + memory
  - วางแผน migration จาก vault เดิมไป Vault-1068 พร้อมขั้นตอนและ risk


### 2.3 Reading & Synthesis

- โจทย์ที่ให้ RCTLabsอ่านเอกสารหลายไฟล์แล้วสังเคราะห์ insight/action
- ตัวอย่าง:
  - เปรียบเทียบ spec Kernel v13 กับ RCT-v13-36-Algorithms-Complete-Guide
  - สรุป Phase0/PhaseC/PhaseX ให้เป็น narrative ที่นำไปใช้สอนทีมใหม่


---

## 3. Dataset Structure

### 3.1 Cases file

Cases ของ RCTLabs จะเก็บใน JSONL:

```text
RCT_benchmark_public/RCTLabs_End2End_Benchmark_Cases_v1.jsonl
```

1 บรรทัด = 1 scenario, โครงตัวอย่าง:

```jsonc
{
  "id": "lab-001",
  "scenario_type": "repo_overview",       // "repo_overview" | "architecture_plan" | "reading_synthesis"
  "entry_surface": "floating_assistant",  // หรือ "cli", "api"
  "input_prompt": "ช่วยอธิบายโครงสร้างหลักของ Full-Repo_Rct ...",
  "success_criteria": "อธิบายโฟลเดอร์ top-level ได้ครบ, ชี้ไฟล์ start-here, ระบุบทบาทแต่ละ folder ถูก",
  "eval_rubric": "ให้คะแนน 0-1 ตามว่าตรงตาม success_criteria มากน้อยเพียงใด",
  "tags": ["rctlabs", "repo", "overview"]
}
```

จุดต่างจาก MemoryRAG:

- เน้น scenario เชิงงาน (task scenario) มากกว่าการผูกกับไฟล์เดียว
- สนใจทั้ง quality ของคำตอบ + usefulness ในการลงมือทำต่อ


### 3.2 Results file

ผลลัพธ์จาก runner:

```text
RCT_benchmark_public/RCTLabs_End2End_Benchmark_Results_YYYYMMDD.jsonl
```

แต่ละรายการ:

```jsonc
{
  "id": "lab-001",
  "mode": "rctlabs_rct",              // เช่น "llm_only" | "rctlabs_rct"
  "answer": "ข้อความที่ RCTLabs ตอบ",
  "latency_ms": 1234,
  "quality_score": 0.85,
  "usefulness_score": 0.9,
  "evaluator_type": "llm_agent",
  "evaluator_id": "signedai_rctlabs_eval_v1",
  "notes": null
}
```


---

## 4. Modes & Baselines

เบื้องต้นเสนอ 2 โหมดหลัก:

1. **llm_only** – ตีความว่า:
   - เรียก LLM เดี่ยว ๆ ผ่าน endpoint generic (ไม่มี RCT backend, ไม่มี Memory layer)
   - ใช้เป็น baseline ว่า "ถ้าไม่มี RCT/RCTLabs เลย" จะตอบได้ระดับไหน

2. **rctlabs_rct** – เต็ม stack:
   - ใช้ RCTLabs API ที่ต่อกับ Kernel + Memory + Vault จริง
   - ใช้การตั้งค่า prompt/pipeline ที่ออกแบบมาเฉพาะ RCT


อนาคตอาจเพิ่ม mode อื่น เช่น:

- `rctlabs_fast_only` – ใช้เฉพาะ Fast lane
- `rctlabs_no_memory` – kernel มีแต่ไม่เปิด Memory layer


---

## 5. Metrics & Evaluation

แนะนำ metric หลักสำหรับ RCTLabs:

1. **quality_score** (0–1)
   - ความถูกต้องเชิงเนื้อหาเมื่อเทียบกับ repo/spec จริง
2. **usefulness_score** (0–1)
   - ความพร้อมใช้งานต่อ: actionable, structured, ไม่มี noise
3. **latency_ms**
   - เวลาตอบรวมต่อ scenario
4. (optional) **interaction_steps**
   - ถ้ามี multi-turn หรือ workflow อื่น


Evaluation สามารถใช้:

- LLM evaluator agent บน SignedAI
- Human eval เฉพาะ subset ที่สำคัญ
- Rule-based checks (เช่น mention folder/filename ที่ถูกต้องหรือไม่)


---

## 6. Runner & Execution Protocol

### 6.1 Runner

แนะนำไฟล์ runner:

```text
10_kernel_runtime/benchmarks/rctlabs_end2end_benchmark_runner.py
```

หน้าที่:

1. โหลด cases JSONL
2. เรียก API ของ RCTLabs:
   - เช่น `POST /rctlabs/v1/assist/oneshot`
   - ส่ง `input_prompt` + metadata
3. วัด latency
4. เก็บคำตอบ + metadata ลง JSONL results
5. (optional) รัน evaluator agent เพื่อตั้งค่าคะแนน quality/usefulness


### 6.2 API expectation

สำหรับ v1 สมมุติ endpoint:

- `POST /rctlabs/v1/bench/oneshot`

Request payload:

```jsonc
{
  "mode": "rctlabs_rct",
  "scenario_type": "architecture_plan",
  "prompt": "ช่วยออกแบบ D-Day plan ...",
  "meta": {
    "case_id": "lab-002",
    "tags": ["architecture","d-day"]
  }
}
```

Response payload:

```jsonc
{
  "answer": "ข้อความจาก RCTLabs ...",
  "latency_ms": 2345,
  "tokens_used": 2048
}
```


---

## 7. Reporting

รายงานผลเฉพาะ RCTLabs:

```text
RCT_benchmark_public/RCTLabs_End2End_Benchmark_Report_YYYYMMDD.md
```

ควรมี:

- ตารางคะแนนเฉลี่ย per scenario_type
- ตัวอย่างเคสที่ RCTLabs ช่วยได้ดีมาก/แย่มาก
- ข้อเสนอแนะต่อการออกแบบ UX/prompt/pipeline ของ RCTLabs


---

## 8. Roadmap

หลังจาก v1:

1. เพิ่ม scenario ที่มี multi-turn / long-horizon
2. เพิ่มการผูก benchmark นี้เข้ากับ SignedAI เพื่อ sign-off บทวิเคราะห์
3. ขยายจากแค่หมวด repo/architecture ไปยัง use case ใหม่ (เช่น research, experiment design)

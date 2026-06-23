---
title: MemoryRAG Benchmark Design
role: memoryrag_benchmark_spec
version: v1.0
status: draft
depends_on:
  - RCT_RealBenchmark_MasterSpec_v1.md
  - 04_memory_vault_rctdb/*
  - 05_infrastructure_mcp/Graphrag_Builder/COMPLETE-USAGE-GUIDE.md
  - 04_memory_vault_rctdb/RCTDB_*
  - 01_theory_fdia_jitna/*
---

# MemoryRAG Benchmark Design (v1.0)

> **Purpose:**  
> ทดสอบและวัดประสิทธิภาพของ Memory Layer ทั้งชุดของ RCT ecosystem
> (Vault-1068 + frontmatter + GraphRAG + RCTDB + retrieval pipeline) เทียบกับ baseline
> เช่น LLM-only หรือ vanilla RAG ทั่วไป

Benchmark ชุดนี้จะใช้ corpus จริงจาก Vault RCT (เอกสารทฤษฎี, whitepaper, kernel, products)
และออกแบบ task ที่สะท้อนการใช้งานจริง เช่น Doc QA, multi-doc reasoning, และ cross-section synthesis

---

## 1. Scope & Goals

### 1.1 Scope

MemoryRAG benchmark ครอบคลุมส่วนประกอบหลักต่อไปนี้:

1. **Vault-1068 & Frontmatter**
   - การจัดโครงเอกสาร, frontmatter, และ metadata
   - การ map knowledge ไปสู่ graph / vector / index
2. **GraphRAG / Hybrid Retrieval**
   - การใช้ graph + vector + keyword ร่วมกัน
   - การปรับ retrieval strategy ตาม intent
3. **RCTDB / Memory Store**
   - การเก็บ knowledge และ citations ในรูปแบบที่ตรวจสอบย้อนหลังได้
4. **Reasoning over retrieved context**
   - ความสามารถในการใช้ context ที่ดึงมา เพื่อตอบคำถามหรือสังเคราะห์ผลลัพธ์ที่ลึก/ซับซ้อน

### 1.2 Goals

1. วัดว่า **Memory layer ของ RCT** ช่วยให้:
   - ตอบคำถามจากเอกสารภายในได้ **ถูกต้อง / ครบ** ขึ้น
   - ลด hallucination เทียบกับ LLM-only
   - ช่วยในการสังเคราะห์ข้ามหลายไฟล์ได้ดีขึ้น
2. ให้ baseline เปรียบเทียบ 3 โหมด:
   - `llm_only` – ไม่มี retrieval, แค่ให้โมเดลตอบ
   - `vanilla_rag` – ดึง context ด้วย vector search แบบง่าย
   - `rct_memory` – pipeline เต็ม: frontmatter + GraphRAG + RCTDB (ถ้ามี)
3. สร้าง dataset + runner + report ที่รันซ้ำได้เพื่อ track คุณภาพ memory layer ในระยะยาว

---

## 2. Task Taxonomy (ประเภทงานทดสอบ)

ใน v1 แบ่ง task ออกเป็น 3 กลุ่มใหญ่:

### 2.1 Single-document QA (Doc QA)

- โจทย์ถามข้อมูลจากไฟล์เดียวอย่างชัดเจน
- ตัวอย่าง:
  - อธิบาย FDIA formula จากเอกสารทฤษฎี
  - สรุป Phase 0 จาก Phase0_Foundation_full.md
- Benchmark วัด:
  - ความถูกต้องของคำตอบเทียบกับ ground truth
  - การอ้างอิงเอกสารต้นทาง (citation) ถ้ามี

### 2.2 Multi-document reasoning

- โจทย์ต้องดึงจาก **หลายไฟล์** แล้วสังเคราะห์ข้อมูล
- ตัวอย่าง:
  - เปรียบเทียบ RCT-7 กับ Kernel 9 Tiers
  - สรุปความสัมพันธ์ระหว่าง FDIA, RCT-7, และ Constitution
- Benchmark วัด:
  - ความครบถ้วนของประเด็นสำคัญ
  - ความถูกต้องเชิงโครงสร้าง (ไม่สับสน concept)
  - การใช้ context ที่เกี่ยวข้องจริง

### 2.3 Cross-section synthesis / narrative

- โจทย์เชิง narrative / explanation ที่ต้องใช้ทั้งทฤษฎี + product + history
- ตัวอย่าง:
  - เล่า “ภาพรวมของ RCT ecosystem” จากเอกสาร meta + whitepaper + timeline
  - อธิบายวิธีที่ Fast/Slow lane เชื่อมกับ Vault-1068 และ RCTDB

---

## 3. Dataset Structure

### 3.1 Cases file

ชุดเคสจะเก็บในไฟล์ JSONL:

```text
RCT_benchmark_public/MemoryRAG_Benchmark_Cases_v1.jsonl
```

1 บรรทัด = 1 เคส, ตัวอย่างโครงสร้าง:

```jsonc
{
  "id": "mem-001",
  "task_type": "doc_qa",                 // "doc_qa" | "multi_doc" | "synthesis"
  "difficulty": "easy",                  // "easy" | "medium" | "hard"
  "source_docs": [
    "01_theory_fdia_jitna/FDIA_2-Layer_Overview.md"
  ],
  "input_question": "อธิบายสมการ FDIA F = (D^I)*A แบบสั้น ๆ 3-4 บรรทัด",
  "ground_truth_answer": ".... (สรุปแกน FDIA อย่างถูกต้อง)",
  "eval_rubric": "ให้คะแนน 0-1 โดย 1 ต้องกล่าวถึง F, D, I, A และความสัมพันธ์เชิงเจตนา",
  "tags": ["fdia", "docqa", "foundation"]
}
```

Field ที่สำคัญ:

- `id` – รหัสเคส
- `task_type` – ประเภทงาน
- `difficulty` – ระดับความยาก
- `source_docs` – ไฟล์ที่ถือว่าเป็นแหล่งข้อมูลหลัก
- `input_question` – prompt ที่จะส่งให้ runtime
- `ground_truth_answer` – คำตอบอ้างอิง (สั้นหรือยาวก็ได้)
- `eval_rubric` – ข้อกำหนดการให้คะแนน
- `tags` – กลุ่ม / หมวดที่ใช้วิเคราะห์

### 3.2 Results file

ผลลัพธ์จาก runner จะเก็บในไฟล์ JSONL อื่น เช่น:

```text
RCT_benchmark_public/MemoryRAG_Benchmark_Results_20251202.jsonl
```

แต่ละบรรทัดอาจมีโครงแบบนี้:

```jsonc
{
  "id": "mem-001",
  "mode": "rct_memory",               // "llm_only" | "vanilla_rag" | "rct_memory"
  "answer": "ข้อความคำตอบจาก runtime",
  "latency_ms": 845,
  "tokens_used": 1024,
  "quality_score": 0.92,
  "evaluator_type": "llm_agent",
  "evaluator_id": "signedai_memoryeval_v1",
  "rubric_version": "v1.0",
  "notes": null
}
```

---

## 4. Baselines & Modes of Operation

MemoryRAG benchmark จะรันอย่างน้อย 3 โหมดเพื่อเปรียบเทียบ:

1. **LLM-only (`llm_only`)**
   - ไม่ส่ง context จาก Vault / RAG เลย
   - แค่ prompt ด้วย `input_question` + คำอธิบาย task เล็กน้อย
   - ใช้เป็น lower bound
2. **Vanilla RAG (`vanilla_rag`)**
   - ใช้ vector search ธรรมดากับ corpus RCT (ไม่มี graph / special schema)
   - ต่อ context ยาว ๆ แล้วให้โมเดลตอบ
   - ใช้เป็น baseline เทียบกับ RCT memory pipeline
3. **RCT Memory (`rct_memory`)**
   - ใช้ frontmatter + GraphRAG + RCTDB ตาม design ใน repo
   - ปรับ retrieval ตามประเภท task
   - อาจจำกัดจำนวนเอกสารแต่เน้น precision สูง

Runner script จะรับ parameter เช่น `--mode llm_only` หรือ `--mode rct_memory`
แล้วรันทุกเคสในโหมดนั้น

---

## 5. Metrics & Evaluation

### 5.1 Core metrics

1. **Quality Score (`quality_score`)**
   - ช่วง 0–1 หรือ 0–100
   - ใช้ rubric ตาม `eval_rubric` ของแต่ละเคส
2. **Latency (`latency_ms`)**
   - วัดเวลา end-to-end (รวม retrieval + generation)
3. **Tokens / Cost**
   - `tokens_used`, `cost_estimate` (ถ้ามี)
4. **Citation / Evidence Quality (optional v1)**
   - มี citation แหล่งข้อมูลหรือไม่
   - citation ถูกต้องหรือไม่

### 5.2 Evaluation process

ใน v1 evaluation อาจทำได้หลายแบบ:

1. **LLM evaluator agent (แนะนำ)**  
   - ใช้ SignedAI agent ที่อ่าน:
     - `input_question`
     - `answer`
     - `ground_truth_answer`
     - `eval_rubric`
   - แล้วให้คะแนน + คอมเมนต์
2. **Human eval สำหรับ subset**  
   - เลือกเคสสำคัญ / representative มาตรวจด้วยมนุษย์
   - ใช้ rubric เดียวกับ LLM evaluator

ผลการประเมินควรถูกเขียนกลับไปในไฟล์ results พร้อม metadata evaluator

---

## 6. Runner & Execution Protocol

### 6.1 Runner script (แนะนำ)

ตำแหน่งไฟล์ runner แนะนำ:

```text
10_kernel_runtime/benchmarks/memoryrag_benchmark_runner.py
```

พฤติกรรมพื้นฐาน:

1. รับ argument:
   - `--mode` (`llm_only` | `vanilla_rag` | `rct_memory`)
   - `--cases` (path ไปยัง JSONL cases)
   - `--output` (path สำหรับเขียนผลลัพธ์)
2. โหลด cases จาก JSONL
3. สำหรับเคสแต่ละอัน:
   - เตรียม prompt/เรียก API ตาม `mode`
   - จับเวลา latency
   - เก็บ answer + metadata
4. เขียนผลลง JSONL output
5. (optional) รัน evaluator เพิ่มหลังจากได้ผลลัพธ์แล้ว

### 6.2 Integration with RCT runtime

- ในโหมด `rct_memory`:
  - runner ควรเรียก API หรือฟังก์ชันที่เข้าถึง GraphRAG / RCTDB ของจริง
  - method การเรียกควรอธิบายในเอกสาร infra / runtime แยกต่างหาก
- ในโหมด `vanilla_rag`:
  - สามารถใช้ index / vector DB เดียวกัน แต่ไม่ใช้ graph / special routing

---

## 7. Reporting

เมื่อได้ผลลัพธ์จากหลายโหมด (llm_only / vanilla_rag / rct_memory) แล้ว:

1. สร้างไฟล์:

   ```text
   RCT_benchmark_public/MemoryRAG_Benchmark_Report_YYYYMMDD.md
   ```

2. รายงานควรมี:
   - ค่าเฉลี่ย `quality_score` ต่อโหมด
   - เปรียบเทียบ latency / tokens / cost
   - กราฟแสดง distribution ของคะแนน
   - case study ของเคสที่ RCT memory ดีขึ้นชัดเจน หรือแย่ลงอย่างมีนัยสำคัญ

---

## 8. Roadmap

หลังจาก v1:

1. เพิ่มจำนวนเคส (โดยเฉพาะ multi-doc / synthesis)
2. เพิ่ม evaluation agent เฉพาะทางสำหรับ MemoryRAG
3. แยกชุด benchmark ตาม domain (theory / kernel / product / governance)
4. ผูก benchmark นี้เข้ากับ SignedAI เพื่อให้มี audit trail และ sign-off

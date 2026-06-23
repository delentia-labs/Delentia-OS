---
title: MemoryRAG Benchmark Report
role: memoryrag_benchmark_report
version: v1.0
report_date: 2025-12-02
status: template
depends_on:
  - MemoryRAG_Benchmark_Design_v1.md
  - MemoryRAG_Benchmark_Cases_v1.jsonl
---

# MemoryRAG Benchmark Report (Template)

> **Note:**  
> เอกสารนี้เป็น template สำหรับรายงานผล MemoryRAG benchmark ในแต่ละรอบการรัน
> แนะนำให้ทำสำเนาไฟล์นี้แล้วเปลี่ยนชื่อเป็น
> `MemoryRAG_Benchmark_Report_YYYYMMDD.md` และเติมตัวเลข/ข้อค้นพบจริงจากผลรัน

---

## 1. Run Summary

- วันที่รัน benchmark: `YYYY-MM-DD`
- เวอร์ชัน spec: `MemoryRAG_Benchmark_Design_v1` (หรือเวอร์ชันใหม่)
- จำนวนเคสทั้งหมด: `N`
- Modes ที่รันในรอบนี้:
  - [ ] llm_only
  - [ ] vanilla_rag
  - [ ] rct_memory

**สรุปภาพรวม (เติมภายหลัง):**

- โดยรวมแล้ว RCT memory ทำได้ดีกว่า/แย่กว่า baseline หรือไม่?
- โดดเด่นใน task ประเภทไหน (doc_qa / multi_doc / synthesis)?
- ประเด็นสำคัญ 3–5 ข้อที่พบจากรอบนี้

---

## 2. Configuration

### 2.1 Runtime & Model

- MemoryRAG API base URL: `MEMORYRAG_API_BASE_URL`
- Model / provider:
- Temperature / max tokens:
- Retrieval config (สำหรับ vanilla_rag / rct_memory):
  - vector DB:
  - top_k:
  - graph / RCTDB settings (ถ้ามี):

### 2.2 Dataset

- Cases file: `MemoryRAG_Benchmark_Cases_v1.jsonl`
- จำนวนเคสแบ่งตามประเภท:

  | Task Type  | Count |
  |-----------|-------|
  | doc_qa    |       |
  | multi_doc |       |
  | synthesis |       |

- domain หลักที่ครอบคลุม:
  - FDIA / JITNA
  - RCT-7 / MentalOS
  - Constitution / governance
  - Phase0 / overview / ecosystem narrative

---

## 3. Metrics Overview

เติมตารางเปรียบเทียบ per mode:

| Mode         | Avg Quality | Avg Latency (ms) | Avg Tokens | Notes                |
|--------------|-------------|------------------|------------|----------------------|
| llm_only     |             |                  |            | baseline             |
| vanilla_rag  |             |                  |            |                      |
| rct_memory   |             |                  |            | expected best mode   |

หากมี metric เพิ่มเติม เช่น citation quality, governance alignment, ฯลฯ สามารถเพิ่ม section ย่อยได้

---

## 4. Per-Task-Type Analysis

### 4.1 Doc QA (single-doc)

- เคสที่เกี่ยวกับ FDIA, RCT-7, Constitution, Phase0
- ตัวเลขสำคัญ:
  - avg quality per mode
  - error patterns (เช่น hallucination, ตอบไม่ครบประเด็น)
- ข้อสังเกต:
  - RCT memory ดึง context ได้ตรงกว่าไหม?
  - vanilla RAG มีปัญหา context noise หรือไม่?

### 4.2 Multi-doc reasoning

- เคสที่ต้องอ่าน FDIA + RCT-7, Constitution + Products
- ตัวเลขสำคัญ:
  - ความต่างของคะแนนระหว่าง llm_only vs rct_memory
- ข้อสังเกต:
  - RCT memory ช่วยให้เชื่อมสองไฟล์ขึ้นไปได้ดีแค่ไหน?
  - ยังมีเคสที่ retrieval พลาดไฟล์สำคัญหรือไม่?

### 4.3 Synthesis / narrative

- เคส ecosystem overview, Fast/Slow + Memory explanation
- ข้อสังเกตเชิง qualitative:
  - โทน/โครงสร้างคำอธิบายดีขึ้นไหมเมื่อใช้ memory เต็ม?
  - LLM-only มีแนวโน้ม hallucinate ภาพรวมระบบไหม?

---

## 5. Case Studies

ยกตัวอย่างเคสที่น่าสนใจ 3–6 เคส เช่น:

### 5.1 เคสที่ RCT memory ชนะชัดเจน

- ID: `mem-00X`
- Task: `...`
- llm_only: คุณภาพต่ำ/หลุดข้อมูลใด
- rct_memory: ดีขึ้นอย่างไร (ยึด ground_truth + rubric)
- บทเรียนที่ได้เกี่ยวกับการออกแบบ Memory pipeline

### 5.2 เคสที่ RCT memory ยังไม่ดีเท่าที่ควร

- ID: `mem-00Y`
- ปัญหา: retrieval พลาด, context noise, ตีความ rubric ผิด ฯลฯ
- แนวทางแก้ไขที่เสนอ: ปรับ index, ปรับ prompt, เพิ่ม metadata ฯลฯ

---

## 6. Design Implications for RCT Memory Layer

จากตัวเลขและ case study ข้างต้น:

1. สิ่งที่พิสูจน์ได้ว่า design ปัจจุบันถูกทิศ
   - เช่น การใช้ frontmatter + graph node แบบ X ช่วยให้เรียก FDIA docs ได้แม่น
2. สิ่งที่ควรปรับปรุง
   - เช่น เพิ่ม field metadata บางอย่าง, เปลี่ยนค่า top_k, แยก index ตาม domain
3. ไอเดียต่อยอด
   - เช่น ใช้ RCTDB ทำ audit trail, ใช้ SignedAI eval รอบสองในเคส high-risk

---

## 7. Limitations

- Dataset v1 ยังมีจำนวนเคสไม่มาก และโฟกัสเฉพาะเอกสารทฤษฎี/overview
- Evaluation อาจใช้ LLM evaluator เป็นหลัก (ยังขาด human eval)
- การตั้งค่าพารามิเตอร์ retrieval ยังไม่ถูก tuning อย่างจริงจัง

ระบุให้ชัดเพื่อไม่ให้ผู้อ่านตีความผล benchmark เกิน scope ที่รองรับ

---

## 8. Action Items & Next Steps

Checklist สิ่งที่ทีม/เจ้าของระบบจะลงมือทำจากผลรอบนี้:

```text
[ ] ปรับค่า top_k / threshold ของ retrieval
[ ] เพิ่ม metadata/frontmatter ให้ไฟล์ FDIA/RCT-7 บางกลุ่ม
[ ] เพิ่มเคส multi_doc และ synthesis ใหม่
[ ] เพิ่ม human eval สำหรับ subset ของเคสสำคัญ
[ ] ผูก benchmark นี้เข้ากับ SignedAI เพื่อบันทึก audit trail
```

สามารถต่อยอดเชื่อม section นี้เข้ากับ roadmap ของ RCT ทั้งระบบได้โดยตรง

---
title: RCT Real Benchmark – Master Report
role: rct_real_benchmark_master_report
version: v1.0
report_date: 2025-12-02
status: template
depends_on:
  - RCT_RealBenchmark_MasterSpec_v1.md
  - RCT_benchmark_public/FastSlowLane_Benchmark_Design_v1.md
  - RCT_benchmark_public/FastSlowLane_Benchmark_Cases_v1.jsonl
  - RCT_benchmark_public/MemoryRAG_Benchmark_Design_v1.md
---

# RCT Real Benchmark – Master Report (Template)

> **Note:**  
> เอกสารนี้เป็น template สำหรับรายงานผล benchmark ระดับ ecosystem ของ RCT
> คุณสามารถทำสำเนาไฟล์นี้แล้วเติมตัวเลข / ข้อมูลจริงจากการรัน benchmark
> ในแต่ละวันที่ต้องการ เช่น `RCT_RealBenchmark_Report_20260201.md`

---

## 1. Executive Summary

- วันที่รัน benchmark: `YYYY-MM-DD`  
- เวอร์ชัน spec หลัก: `RCT_RealBenchmark_MasterSpec_vX`  
- โมเดล / runtime ที่ใช้ทดสอบ:
  - LLM provider / model name:
  - Kernel version:
  - Memory pipeline version:

**สรุปภาพรวม (เติมภายหลัง):**

- TL;DR performance Fast/Slow Lane
- TL;DR performance MemoryRAG
- TL;DR performance RCTLabs / SignedAI (ถ้าพร้อม)
- ข้อค้นพบสำคัญ 3–5 ข้อ

---

## 2. Benchmark Configuration

### 2.1 Runtime & Model Config

- Model:
- Temperature:
- Max tokens:
- Prompting style / system prompt version:
- Kernel runtime commit / tag:
- Memory pipeline config (GraphRAG / RCTDB settings):

### 2.2 Benchmark Suites Included

ระบุ benchmark families ที่ถูกรันในรอบนี้:

- [ ] FastSlowLane v1
- [ ] MemoryRAG v1
- [ ] RCTLabs_End2End v1
- [ ] SignedAI_Governance v1
- [ ] ArtentAI_Creative v1 (optional)

---

## 3. Fast/Slow Lane – Summary

> อ้างอิงจาก:  
> - `FastSlowLane_Benchmark_Design_v1.md`  
> - `FastSlowLane_Benchmark_Cases_v1.jsonl`  
> - `FastSlowLane_Benchmark_Results_YYYYMMDD.jsonl`

### 3.1 Metrics Overview

- จำนวนเคสรวม: `N`
- Routing accuracy: `X %`
- ค่าเฉลี่ย latency (Fast lane): `... ms`
- ค่าเฉลี่ย latency (Slow lane): `... ms`

ตารางตัวอย่าง (ใส่ภายหลัง):

| Metric                        | Value    |
|------------------------------|----------|
| Overall routing accuracy     |          |
| Routing accuracy (low risk)  |          |
| Routing accuracy (high risk) |          |
| Avg latency fast lane (ms)   |          |
| Avg latency slow lane (ms)   |          |

### 3.2 Observations

- จุดที่ router ทำงานดีมาก (เช่น เคส low-risk summary)
- จุดที่ต้องปรับ router / FDIA gating
- การใช้ profile ต่าง ๆ ของ Mini Kernel (มี profile ไหนไม่ถูกใช้เลย?)

---

## 4. MemoryRAG – Summary

> อ้างอิงจาก:  
> - `MemoryRAG_Benchmark_Design_v1.md`  
> - `MemoryRAG_Benchmark_Cases_v1.jsonl` (เมื่อสร้าง)
> - `MemoryRAG_Benchmark_Results_YYYYMMDD.jsonl`

### 4.1 Quality vs Mode

ใส่ตารางเปรียบเทียบ 3 โหมด:

| Mode         | Avg Quality | Avg Latency (ms) | Notes                |
|--------------|-------------|------------------|----------------------|
| llm_only     |             |                  | baseline             |
| vanilla_rag  |             |                  |                      |
| rct_memory   |             |                  | expected best mode   |

### 4.2 Observations

- เคสที่ RCT memory ช่วยให้ดีขึ้นอย่างชัดเจน
- เคสที่ RCT memory ยังไม่ต่างจาก vanilla RAG / LLM-only
- ปัญหาที่เจอ เช่น retrieval พลาด, context ยาวเกิน, ฯลฯ

---

## 5. Product-level Benchmarks (RCTLabs / SignedAI / ArtentAI)

> ส่วนนี้สามารถเติมภายหลังเมื่อชุด benchmark เหล่านี้พร้อมใช้งาน

### 5.1 RCTLabs_End2End

- Scenario ที่ทดสอบ (เช่น design architecture, migration plan)
- Metric คุณภาพ / เวลา / จำนวน iteration
- Comparison: LLM-only vs LLM+RCT+RCTLabs

### 5.2 SignedAI_Governance

- เคส decision / sign-off / policy analysis
- Metric safety / alignment
- ตัวอย่างเคสที่ระบบจับ risk ได้ดี หรือหลุด

### 5.3 ArtentAI_Creative

- เคส UX / narrative / creative generation
- Metric ความสอดคล้องกับ ecosystem + คุณภาพการสื่อสาร

---

## 6. Comparative Analysis – RCT vs LLM-only

ในส่วนนี้สรุปมุมมองเชิงระบบ:

1. จุดที่ RCT ชนะ LLM-only ชัดเจน
2. จุดที่ยังไม่ต่าง (หรือ LLM-only ดีกว่าในบาง dimension เช่น latency)
3. Insight ที่ได้เกี่ยวกับ design ของ Kernel / Memory / Products

ตารางตัวอย่าง:

| Aspect              | LLM-only        | LLM+RCT                  | Notes                |
|---------------------|-----------------|--------------------------|----------------------|
| Routing correctness | N/A             |                          |                      |
| Doc QA quality      | baseline        |                          |                      |
| Governance safety   | baseline        |                          |                      |

---

## 7. Limitations & Risks

- ข้อจำกัดของ dataset ปัจจุบัน (เช่น จำนวนเคส, domain ยังแคบ)
- ข้อจำกัดของ evaluation (LLM evaluator ยัง bias, human eval ยังน้อย)
- ความเสี่ยงถ้าเอาผล benchmark ไปตีความเกิน scope

---

## 8. Roadmap & Action Items

สรุปสิ่งที่ทีมจะทำต่อจากผล benchmark รอบนี้:

- ปรับ router / Fast Lane ยังไง
- ปรับ memory pipeline / GraphRAG ยังไง
- เพิ่ม benchmark family / เคสใหม่ ๆ
- Integrate benchmark เข้ากับ SignedAI / CI pipeline

```text
[ ] Item 1
[ ] Item 2
[ ] Item 3
```
